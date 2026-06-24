"""VigilAI POC — 單一 FastAPI 服務。

對外 port 4014（容器內 8000）。同時負責：
  - serve 前端單頁
  - /api/analyze：影像 → VLM → 解析 → 觸發判斷 → Telegram 通知
  - rules（prompt）持久化 CRUD
  - Telegram chat_id probe
"""
from __future__ import annotations

import base64
import binascii
import hmac
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import detect, store, telegram, vlm

# 不設預設值：未提供時所有受保護端點 fail closed（見 require_auth）
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "")
STATIC_DIR = Path(__file__).parent / "static"

# rule_id -> 冷卻到期的 monotonic 時間
_cooldowns: dict[str, float] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient()
    yield
    await app.state.client.aclose()


app = FastAPI(title="VigilAI POC", lifespan=lifespan)


# ---- Auth -----------------------------------------------------------------

def require_auth(x_access_password: str = Header(default="")) -> None:
    # Fail closed：未設定密碼時一律拒絕，不開後門
    if not ACCESS_PASSWORD:
        raise HTTPException(status_code=503, detail="伺服器未設定 ACCESS_PASSWORD")
    if not hmac.compare_digest(x_access_password, ACCESS_PASSWORD):
        raise HTTPException(status_code=401, detail="存取密碼錯誤")


# ---- Schemas --------------------------------------------------------------

class Condition(BaseModel):
    type: Literal["boolean", "numeric"] = "boolean"
    operator: Literal[">=", "<=", ">", "<", "=="] = ">="
    value: float | None = None


class Rule(BaseModel):
    id: str = Field(default_factory=lambda: f"rule_{uuid.uuid4().hex[:8]}")
    name: str = "未命名規則"
    enabled: bool = True
    prompt: str
    condition: Condition = Field(default_factory=Condition)
    confidence_threshold: int = 60
    cooldown_sec: int = 60
    notify_text: str = ""


class AnalyzeRequest(BaseModel):
    image: str  # data:image/jpeg;base64,...


# ---- Helpers --------------------------------------------------------------

def _decode_image(data_url: str) -> bytes:
    raw = data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url
    try:
        return base64.b64decode(raw)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"影像解碼失敗: {e}")


def _is_cooling(rule_id: str) -> bool:
    exp = _cooldowns.get(rule_id)
    return exp is not None and time.monotonic() < exp


def _set_cooldown(rule_id: str, seconds: int) -> None:
    _cooldowns[rule_id] = time.monotonic() + max(0, seconds)


def _caption(rule: dict, ev: dict) -> str:
    prefix = rule.get("notify_text") or rule.get("name") or "VigilAI 偵測"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"{prefix}（規則：{rule.get('name')}）", f"時間：{now}"]
    if ev.get("value") is not None:
        lines.append(f"讀值：{ev['value']}")
    if ev.get("confidence") is not None:
        lines.append(f"信心：{ev['confidence']}")
    if ev.get("reason"):
        lines.append(f"VLM：{ev['reason']}")
    return "\n".join(lines)


# ---- Routes: 靜態頁 --------------------------------------------------------

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# ---- Routes: health（不需密碼）-------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    out: dict[str, Any] = {"status": "ok"}
    try:
        await vlm.list_models(app.state.client)
        out["ollama"] = "ok"
    except Exception as e:  # noqa: BLE001
        out["ollama"] = f"error: {e}"
        out["status"] = "degraded"
    out["telegram_configured"] = telegram.configured()
    out["model"] = vlm.OLLAMA_MODEL
    return out


# ---- Routes: login --------------------------------------------------------

class LoginRequest(BaseModel):
    password: str


@app.post("/api/login")
async def login(req: LoginRequest) -> dict:
    if not ACCESS_PASSWORD:
        raise HTTPException(status_code=503, detail="伺服器未設定 ACCESS_PASSWORD")
    if not hmac.compare_digest(req.password, ACCESS_PASSWORD):
        raise HTTPException(status_code=401, detail="存取密碼錯誤")
    return {"ok": True, "model": vlm.OLLAMA_MODEL, "telegram_configured": telegram.configured()}


# ---- Routes: rules CRUD ---------------------------------------------------

@app.get("/api/rules", dependencies=[Depends(require_auth)])
async def get_rules() -> list[dict]:
    return store.list_rules()


@app.post("/api/rules", dependencies=[Depends(require_auth)])
async def post_rule(rule: Rule) -> dict:
    return store.upsert_rule(rule.model_dump())


@app.delete("/api/rules/{rule_id}", dependencies=[Depends(require_auth)])
async def remove_rule(rule_id: str) -> dict:
    ok = store.delete_rule(rule_id)
    _cooldowns.pop(rule_id, None)
    return {"ok": ok}


# ---- Routes: telegram -----------------------------------------------------

@app.get("/api/telegram/probe", dependencies=[Depends(require_auth)])
async def telegram_probe() -> dict:
    return await telegram.probe_chat_id(app.state.client)


@app.post("/api/telegram/test", dependencies=[Depends(require_auth)])
async def telegram_test() -> dict:
    px = base64.b64decode(
        b"/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAP//////////////////////////////"
        b"////////////////////////////////////////////////////2wBDAf//////"
        b"////////////////////////////////////////////////////////////////"
        b"//////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFAABAAAAAAAAAAAAAAAA"
        b"AAAACP/EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8"
        b"QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8AvwA//9k="
    )
    return await telegram.send_photo(app.state.client, px, "✅ VigilAI 測試通知")


# ---- Routes: analyze ------------------------------------------------------

@app.post("/api/analyze", dependencies=[Depends(require_auth)])
async def analyze(req: AnalyzeRequest) -> dict:
    image_bytes = _decode_image(req.image)
    rules = store.enabled_rules()
    results = []

    for rule in rules:
        rid = rule["id"]
        if _is_cooling(rid):
            results.append({
                "rule_id": rid, "name": rule.get("name"),
                "triggered": False, "cooled_down": True, "notified": False,
                "reason": "冷卻中", "raw": "", "confidence": None, "value": None,
                "detected": None, "condition_type": rule.get("condition", {}).get("type"),
            })
            continue

        vlm_res = await vlm.infer(app.state.client, req.image, rule)
        parsed = detect.parse_vlm_json(vlm_res["raw"])
        ev = detect.evaluate(rule, parsed)

        notified = False
        notify_error = None
        if ev["triggered"]:
            tg = await telegram.send_photo(app.state.client, image_bytes, _caption(rule, ev))
            notified = tg.get("ok", False)
            if not notified:
                notify_error = tg.get("error") or tg.get("body")
            _set_cooldown(rid, int(rule.get("cooldown_sec", 60)))

        results.append({
            "rule_id": rid,
            "name": rule.get("name"),
            "condition_type": rule.get("condition", {}).get("type"),
            "triggered": ev["triggered"],
            "cooled_down": False,
            "confidence": ev["confidence"],
            "value": ev["value"],
            "detected": ev["detected"],
            "reason": ev["reason"],
            "raw": vlm_res["raw"],
            "inference_ms": vlm_res["inference_ms"],
            "vlm_error": vlm_res["error"],
            "notified": notified,
            "notify_error": notify_error,
        })

    return {"ts": datetime.now().isoformat(timespec="seconds"), "results": results}


# 靜態資源（CSS/JS）掛最後，避免蓋掉 /api 路由
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

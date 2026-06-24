"""Ollama VLM client（OpenAI 相容 /v1/chat/completions）。"""
from __future__ import annotations

import os
import time

import httpx

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.transferhelper.com/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")  # 由 .env / 環境提供，不寫死
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b")

SYSTEM_PROMPT = "你是影像偵測助手。只輸出 JSON，不要多餘文字。"


def _build_user_text(rule: dict) -> str:
    cond = rule.get("condition", {}) or {}
    prompt = rule.get("prompt", "").strip()
    if cond.get("type") == "numeric":
        return (
            f"{prompt}\n"
            '只輸出以下 JSON（value 為純數字，讀不到填 null）：'
            '{"value": <number|null>, "confidence": 0-100, "reason": "簡短說明"}'
        )
    return (
        f"{prompt}\n"
        '請依畫面回答，只輸出以下 JSON：'
        '{"detected": true|false, "confidence": 0-100, "reason": "簡短說明"}'
    )


async def infer(client: httpx.AsyncClient, image_data_url: str, rule: dict) -> dict:
    """呼叫 VLM，回傳 {raw, inference_ms, error}。"""
    payload = {
        "model": OLLAMA_MODEL,
        "temperature": 0,
        # 讓 Ollama 把模型多留在 VRAM 一段時間，減少閒置卸載造成的冷啟動
        # （若端點 proxy 不支援此欄位會被忽略，無害）
        "keep_alive": "30m",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_user_text(rule)},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {OLLAMA_API_KEY}",
        "Content-Type": "application/json",
    }
    t0 = time.monotonic()
    last_err = None
    for attempt in range(2):  # 最多 retry 1 次
        try:
            r = await client.post(
                f"{OLLAMA_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
                timeout=60,
            )
            r.raise_for_status()
            data = r.json()
            raw = data["choices"][0]["message"]["content"]
            return {
                "raw": raw,
                "inference_ms": int((time.monotonic() - t0) * 1000),
                "error": None,
            }
        except Exception as e:  # noqa: BLE001 - POC 容錯
            last_err = str(e)
    return {
        "raw": "",
        "inference_ms": int((time.monotonic() - t0) * 1000),
        "error": last_err,
    }


async def list_models(client: httpx.AsyncClient) -> dict:
    headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}"}
    r = await client.get(f"{OLLAMA_BASE_URL}/models", headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()

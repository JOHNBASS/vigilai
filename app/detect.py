"""偵測結果解析與觸發判斷。

把「感知」與「決策」分開：VLM 只負責讀畫面回 JSON，是否觸發由這裡用程式判斷。
數值比較（溫度 >= 38）尤其要靠程式，VLM 對大小邏輯不穩定。
"""
from __future__ import annotations

import json
import re
from typing import Any

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_vlm_json(text: str) -> dict | None:
    """VLM 可能在 JSON 前後夾雜文字，抓第一個 {...} 區塊再 parse。"""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _to_number(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        if m:
            return float(m.group(0))
    return None


def _compare(value: float, operator: str, target: float) -> bool:
    return {
        ">=": value >= target,
        "<=": value <= target,
        ">": value > target,
        "<": value < target,
        "==": value == target,
    }.get(operator, False)


def evaluate(rule: dict, parsed: dict | None) -> dict:
    """回傳判斷結果 dict：triggered / confidence / value|detected / reason。"""
    cond = rule.get("condition", {}) or {}
    ctype = cond.get("type", "boolean")
    out: dict[str, Any] = {
        "triggered": False,
        "confidence": None,
        "reason": "",
        "detected": None,
        "value": None,
    }
    if parsed is None:
        out["reason"] = "VLM 回傳無法解析為 JSON"
        return out

    out["confidence"] = _to_number(parsed.get("confidence"))
    out["reason"] = str(parsed.get("reason", ""))

    if ctype == "numeric":
        value = _to_number(parsed.get("value"))
        out["value"] = value
        if value is None:
            out["reason"] = out["reason"] or "畫面中讀不到數值"
            return out
        operator = cond.get("operator", ">=")
        target = _to_number(cond.get("value"))
        if target is None:
            return out
        out["triggered"] = _compare(value, operator, target)
    else:  # boolean
        detected = parsed.get("detected")
        out["detected"] = bool(detected) if detected is not None else None
        threshold = _to_number(rule.get("confidence_threshold")) or 0
        conf = out["confidence"] if out["confidence"] is not None else 100
        out["triggered"] = bool(detected) and conf >= threshold

    return out

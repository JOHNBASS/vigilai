"""極簡 JSON 檔持久化：rules.json + settings.json。

POC 不引入資料庫，rule（含使用者寫的 prompt）與少量設定（如 Telegram chat_id）
存成 JSON 檔，掛 Docker volume 後容器重啟 / 換瀏覽器都還在。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
RULES_FILE = DATA_DIR / "rules.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

_lock = threading.Lock()


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _write(path: Path, data: Any) -> None:
    _ensure_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic-ish rename


# ---- Rules ----------------------------------------------------------------

def list_rules() -> list[dict]:
    with _lock:
        return _read(RULES_FILE, [])


def enabled_rules() -> list[dict]:
    return [r for r in list_rules() if r.get("enabled", True)]


def upsert_rule(rule: dict) -> dict:
    with _lock:
        rules = _read(RULES_FILE, [])
        idx = next((i for i, r in enumerate(rules) if r["id"] == rule["id"]), None)
        if idx is None:
            rules.append(rule)
        else:
            rules[idx] = rule
        _write(RULES_FILE, rules)
        return rule


def delete_rule(rule_id: str) -> bool:
    with _lock:
        rules = _read(RULES_FILE, [])
        new = [r for r in rules if r["id"] != rule_id]
        _write(RULES_FILE, new)
        return len(new) != len(rules)


# ---- Settings -------------------------------------------------------------

def get_settings() -> dict:
    with _lock:
        return _read(SETTINGS_FILE, {})


def update_settings(patch: dict) -> dict:
    with _lock:
        s = _read(SETTINGS_FILE, {})
        s.update(patch)
        _write(SETTINGS_FILE, s)
        return s

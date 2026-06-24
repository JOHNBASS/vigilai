"""Telegram Bot client：sendPhoto 通知 + getUpdates 撈 chat_id。

chat_id 來源優先序：環境變數 TELEGRAM_CHAT_ID > settings.json（probe 撈到後寫入）。
"""
from __future__ import annotations

import os

import httpx

from . import store

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_ENV_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"


def get_chat_id() -> str | None:
    if _ENV_CHAT_ID:
        return _ENV_CHAT_ID
    cid = store.get_settings().get("telegram_chat_id")
    return str(cid) if cid else None


def configured() -> bool:
    return bool(BOT_TOKEN) and bool(get_chat_id())


async def probe_chat_id(client: httpx.AsyncClient) -> dict:
    """呼叫 getUpdates，從最近訊息撈出 chat_id 並寫入 settings.json。"""
    if not BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN 未設定"}
    r = await client.get(_api("getUpdates"), timeout=20)
    r.raise_for_status()
    data = r.json()
    results = data.get("result", [])
    if not results:
        return {
            "ok": False,
            "error": "找不到任何訊息。請先用手機對 @VigilAi_beta_bot 傳一則訊息（例如 /start）再試。",
        }
    # 取最後一則訊息的 chat
    for upd in reversed(results):
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat")
        if chat and chat.get("id") is not None:
            chat_id = str(chat["id"])
            store.update_settings({"telegram_chat_id": chat_id})
            return {
                "ok": True,
                "chat_id": chat_id,
                "chat_name": chat.get("title") or chat.get("username") or chat.get("first_name"),
            }
    return {"ok": False, "error": "訊息中找不到 chat id"}


async def send_photo(client: httpx.AsyncClient, image_bytes: bytes, caption: str) -> dict:
    chat_id = get_chat_id()
    if not BOT_TOKEN or not chat_id:
        return {"ok": False, "error": "Telegram 未設定（缺 token 或 chat_id）"}
    files = {"photo": ("frame.jpg", image_bytes, "image/jpeg")}
    form = {"chat_id": chat_id, "caption": caption[:1024]}
    r = await client.post(_api("sendPhoto"), data=form, files=files, timeout=30)
    ok = r.status_code == 200 and r.json().get("ok", False)
    return {"ok": ok, "status": r.status_code, "body": r.text[:300]}

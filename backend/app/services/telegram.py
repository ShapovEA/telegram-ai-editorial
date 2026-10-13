import json
import logging
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096


class TelegramError(Exception):
    def __init__(self, message: str, *, retry_after: int | None = None, permanent: bool = False):
        super().__init__(message)
        self.retry_after = retry_after
        self.permanent = permanent


async def call(method: str, payload: dict[str, Any] | None = None, *, files: dict[str, tuple[str, bytes, str]] | None = None) -> Any:
    token = get_settings().telegram_bot_token
    if not token:
        raise TelegramError("Не задан TELEGRAM_BOT_TOKEN", permanent=True)
    url = f"https://api.telegram.org/bot{token}/{method}"
    async with httpx.AsyncClient(timeout=60) as client:
        if files:
            data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, dict | list) else str(v)) for k, v in (payload or {}).items() if v is not None}
            resp = await client.post(url, data=data, files=files)
        else:
            resp = await client.post(url, json={k: v for k, v in (payload or {}).items() if v is not None})
    try:
        body = resp.json()
    except ValueError as exc:
        raise TelegramError(f"Telegram вернул не JSON: HTTP {resp.status_code}") from exc
    if not body.get("ok"):
        params = body.get("parameters") or {}
        code = body.get("error_code")
        raise TelegramError(
            f"Telegram {method}: {body.get('description')}",
            retry_after=params.get("retry_after"),
            permanent=code in (400, 403),
        )
    return body["result"]


async def get_chat(chat: str | int) -> dict[str, Any]:
    return await call("getChat", {"chat_id": chat})


async def get_admins(chat: str | int) -> list[dict[str, Any]]:
    return await call("getChatAdministrators", {"chat_id": chat})


async def get_me() -> dict[str, Any]:
    return await call("getMe")


_bot_username: str | None = None


async def bot_username() -> str:
    global _bot_username
    if _bot_username is None:
        _bot_username = (await get_me()).get("username") or ""
    return _bot_username


async def send_message(chat: str | int, html: str, *, buttons: list[list[dict[str, str]]] | None = None, preview: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat,
        "text": html[:MESSAGE_LIMIT],
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": not preview},
    }
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    return await call("sendMessage", payload)


async def send_photo(chat: str | int, *, url: str | None = None, data: bytes | None = None, caption: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"chat_id": chat, "caption": caption, "parse_mode": "HTML" if caption else None}
    if url:
        payload["photo"] = url
        return await call("sendPhoto", payload)
    return await call("sendPhoto", payload, files={"photo": ("image.png", data or b"", "image/png")})


async def send_poll(chat: str | int, question: str, options: list[str], *, multiple: bool = False) -> dict[str, Any]:
    return await call(
        "sendPoll",
        {
            "chat_id": chat,
            "question": question[:300],
            "options": [{"text": o[:100]} for o in options[:10]],
            "is_anonymous": True,
            "allows_multiple_answers": multiple,
        },
    )

import html
import logging

from app.config import get_settings
from app.db.models import Channel, User
from app.db.session import session_scope
from app.services import telegram

log = logging.getLogger(__name__)


def cabinet_url(path: str) -> str:
    return get_settings().frontend_url.rstrip("/") + path


async def notify_owner(channel_id: int, text: str, *, buttons: list[list[dict[str, str]]] | None = None) -> bool:
    async with session_scope() as s:
        ch = await s.get(Channel, channel_id)
        if ch is None:
            return False
        user = await s.get(User, ch.owner_id)
        chat = user.telegram_user_id if user else None
        title = ch.title
    if not chat:
        return False
    try:
        await telegram.send_message(chat, f"<b>{html.escape(title)}</b>\n{text}", buttons=buttons)
        return True
    except telegram.TelegramError as exc:
        log.warning("notify failed: %s", exc)
        return False


def link_buttons(path: str, label: str = "Открыть в кабинете") -> list[list[dict[str, str]]]:
    url = cabinet_url(path)
    if "localhost" in url or "127.0.0.1" in url:
        return []
    return [[{"text": label, "url": url}]]


def approval_buttons(post_id: int) -> list[list[dict[str, str]]]:
    return [
        [{"text": "Одобрить", "callback_data": f"approve:{post_id}"}, {"text": "Отклонить", "callback_data": f"reject:{post_id}"}],
        *link_buttons(f"/posts/{post_id}"),
    ]

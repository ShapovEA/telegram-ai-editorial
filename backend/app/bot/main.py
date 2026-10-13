import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message, MessageReactionCountUpdated, Poll
from sqlalchemy import select, update

from app.config import get_settings
from app.db.models import Channel, Post, User
from app.db.session import session_scope

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")
router = Router()


@router.message(CommandStart(deep_link=True))
async def start_link(message: Message, command: CommandObject) -> None:
    code = (command.args or "").strip()
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.telegram_link_code == code))).scalar_one_or_none()
        if user is None:
            await message.answer("Код не найден или устарел. Получите новый код в кабинете.")
            return
        other = (await s.execute(select(User).where(User.telegram_user_id == message.from_user.id, User.id != user.id))).scalar_one_or_none()
        if other:
            other.telegram_user_id = None
        user.telegram_user_id = message.from_user.id
        user.telegram_username = message.from_user.username
        user.telegram_link_code = None
    await message.answer("Готово: аккаунт привязан. Вернитесь в кабинет и подключите канал.")


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer("Это бот AI-отдела для ведения Telegram-каналов. Привяжите аккаунт по ссылке из кабинета.")


@router.channel_post(F.new_chat_title)
async def on_title(message: Message) -> None:
    async with session_scope() as s:
        await s.execute(update(Channel).where(Channel.telegram_chat_id == message.chat.id).values(title=message.new_chat_title))


@router.message_reaction_count()
async def on_reactions(update: MessageReactionCountUpdated) -> None:
    counts: dict[str, int] = {}
    for r in update.reactions:
        key = getattr(r.type, "emoji", None) or getattr(r.type, "custom_emoji_id", None) or r.type.type
        counts[key] = r.total_count
    async with session_scope() as s:
        channel = (await s.execute(select(Channel).where(Channel.telegram_chat_id == update.chat.id))).scalar_one_or_none()
        if channel is None:
            return
        post = (
            await s.execute(select(Post).where(Post.channel_id == channel.id, Post.telegram_message_ids.contains([update.message_id])))
        ).scalar_one_or_none()
        if post is None:
            return
        post.reactions = counts
        post.reactions_total = sum(counts.values())


@router.poll()
async def on_poll(poll: Poll) -> None:
    async with session_scope() as s:
        post = (await s.execute(select(Post).where(Post.telegram_poll_id == poll.id))).scalar_one_or_none()
        if post is None:
            return
        post.poll_results = {"counts": {o.text: o.voter_count for o in poll.options}, "total": poll.total_voter_count, "closed": poll.is_closed}


async def main() -> None:
    token = get_settings().telegram_bot_token
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN не задан — бот не запущен")
        while True:
            await asyncio.sleep(3600)
    bot = Bot(token)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot, allowed_updates=["message", "channel_post", "message_reaction_count", "poll", "my_chat_member"])


if __name__ == "__main__":
    asyncio.run(main())

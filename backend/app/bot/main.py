import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message, MessageReactionCountUpdated, Poll
from sqlalchemy import select

from app.config import get_settings
from app.db.models import Channel, Post, Run, User
from app.db.session import session_scope
from app.domain.enums import AWAITING_DECISION, RunStatus

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
    await message.answer("Готово: аккаунт привязан. Сюда будут приходить посты на одобрение и уведомления.")


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer("Это бот AI-отдела для ведения Telegram-каналов. Привяжите аккаунт по ссылке из кабинета.")


async def _resume(post_id: int, user_tg: int, action: str) -> str:
    async with session_scope() as s:
        post = await s.get(Post, post_id)
        if post is None:
            return "Пост не найден"
        channel = await s.get(Channel, post.channel_id)
        owner = await s.get(User, channel.owner_id)
        if owner.telegram_user_id != user_tg:
            return "Это не ваш канал"
        if post.status not in AWAITING_DECISION or not post.run_id:
            return "Пост уже обработан"
        run = await s.get(Run, post.run_id)
        if run is None or run.status != RunStatus.waiting:
            return "Пост уже обработан"
        run_id = post.run_id
    from app.worker.tasks import run_graph

    await run_graph.kiq(run_id, {"action": action, "source": "telegram"})
    return "Одобрено, пост поставлен в расписание" if action == "approve" else "Пост отклонён"


@router.callback_query(F.data.regexp(r"^(approve|reject):\d+$"))
async def on_decision(callback: CallbackQuery) -> None:
    action, post_id = callback.data.split(":")
    text = await _resume(int(post_id), callback.from_user.id, action)
    await callback.answer(text, show_alert=False)
    if callback.message:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.reply(text)
        except Exception:
            pass


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
    from app.worker import tasks
    from app.worker.broker import broker

    await broker.startup()
    log.info("broker ready, task %s registered", tasks.run_graph.task_name)
    bot = Bot(token)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "message_reaction_count", "poll", "my_chat_member"])


if __name__ == "__main__":
    asyncio.run(main())

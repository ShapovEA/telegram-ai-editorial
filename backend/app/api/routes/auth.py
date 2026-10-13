import secrets

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, make_token, password_hash
from app.api.serializers import user_out
from app.db.models import User
from app.db.session import get_session
from app.services import telegram

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/register")
async def register(body: RegisterIn, session: AsyncSession = Depends(get_session)) -> dict:
    exists = (await session.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "Пользователь с таким email уже есть")
    user = User(email=body.email.lower(), password_hash=password_hash.hash(body.password), name=body.name)
    session.add(user)
    await session.commit()
    return {"token": make_token(user.id), "user": user_out(user)}


@router.post("/login")
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)) -> dict:
    user = (await session.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if user is None or not password_hash.verify(body.password, user.password_hash):
        raise HTTPException(401, "Неверный email или пароль")
    return {"token": make_token(user.id), "user": user_out(user)}


@router.get("/me")
async def me(user: User = Depends(current_user)) -> dict:
    return user_out(user)


@router.post("/telegram-link")
async def telegram_link(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict:
    try:
        bot = await telegram.bot_username()
    except (telegram.TelegramError, httpx.HTTPError) as exc:
        raise HTTPException(400, f"Бот сервиса недоступен: {exc}") from exc
    db_user = await session.get(User, user.id)
    db_user.telegram_link_code = secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:16]
    await session.commit()
    return {"url": f"https://t.me/{bot}?start={db_user.telegram_link_code}", "code": db_user.telegram_link_code}

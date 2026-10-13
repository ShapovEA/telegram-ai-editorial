from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Channel, User
from app.db.session import get_session

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
ALGORITHM = "HS256"


def make_token(user_id: int) -> str:
    s = get_settings()
    payload = {"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(minutes=s.access_token_ttl_minutes)}
    return jwt.encode(payload, s.app_secret, algorithm=ALGORITHM)


def _decode(token: str) -> int:
    try:
        payload = jwt.decode(token, get_settings().app_secret, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сессия истекла, войдите снова") from exc


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    token: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    raw = creds.credentials if creds else token
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужно войти")
    user = await session.get(User, _decode(raw))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден")
    return user


async def owned_channel(channel_id: int, user: User, session: AsyncSession) -> Channel:
    ch = await session.get(Channel, channel_id)
    if ch is None or ch.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Канал не найден")
    return ch

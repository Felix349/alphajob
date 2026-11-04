"""路由共用的依赖：当前登录用户。"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import decode_access_token
from app.models import User
from app.repositories import users as users_repo


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期"
    )
    token = request.cookies.get(get_settings().cookie_name)
    if not token:
        raise unauthorized
    user_id = decode_access_token(token)
    if user_id is None:
        raise unauthorized
    user = await users_repo.get_by_id(db, user_id)
    if user is None:  # token 有效但用户已被删除
        raise unauthorized
    return user

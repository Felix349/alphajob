"""用户表的数据访问。只负责读写数据库，不包含业务规则。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession, *, email: str, password_hash: str, display_name: str | None
) -> User:
    user = User(email=email, password_hash=password_hash, display_name=display_name)
    db.add(user)
    await db.flush()  # 拿到数据库生成的默认值，提交由调用方（service）决定
    await db.refresh(user)
    return user

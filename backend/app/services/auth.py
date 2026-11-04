"""认证相关的业务逻辑。路由层只调用这里，不直接碰数据库。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories import users as users_repo
from app.schemas.auth import LoginRequest, RegisterRequest


class EmailAlreadyRegistered(Exception):
    pass


class InvalidCredentials(Exception):
    pass


# 用户不存在时也做一次哈希校验，让“账号不存在”和“密码错误”耗时接近，防止通过响应时间探测已注册邮箱
_DUMMY_HASH = hash_password("dummy-password-for-timing")


async def register(db: AsyncSession, data: RegisterRequest) -> User:
    if await users_repo.get_by_email(db, data.email):
        raise EmailAlreadyRegistered
    try:
        user = await users_repo.create(
            db,
            email=data.email,
            password_hash=hash_password(data.password),
            display_name=data.display_name,
        )
        await db.commit()
    except IntegrityError as exc:  # 并发注册同一邮箱时，由数据库唯一约束兜底
        await db.rollback()
        raise EmailAlreadyRegistered from exc
    return user


async def authenticate(db: AsyncSession, data: LoginRequest) -> User:
    user = await users_repo.get_by_email(db, data.email)
    if user is None:
        verify_password(data.password, _DUMMY_HASH)
        raise InvalidCredentials
    if not verify_password(data.password, user.password_hash):
        raise InvalidCredentials
    return user

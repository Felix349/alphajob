"""数据库引擎与会话管理。

每个请求通过依赖注入拿到一个独立的 AsyncSession，请求结束自动关闭。
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """流式接口用：响应要持续几十秒，期间在生成器内部自己开、关会话，
    不依赖请求级的 get_db（它的生命周期和流式响应不一致）。测试中会被替换成测试库。"""
    return SessionLocal

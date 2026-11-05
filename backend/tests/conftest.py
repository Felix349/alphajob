"""测试夹具：使用独立的测试数据库 alphajob_test，每个测试前清空数据。"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.db import get_db, get_session_factory
from app.main import app
from app.models import Base

# NullPool：每次用完就关闭连接，避免连接在不同事件循环之间复用导致的报错
test_engine = create_async_engine(get_settings().test_database_url, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
async def _create_schema() -> AsyncIterator[None]:
    # 测试库直接按模型建表（开发库才走 Alembic 迁移）
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await test_engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


async def _override_get_db() -> AsyncIterator[AsyncSession]:
    async with TestSessionLocal() as session:
        yield session


def _use_test_db() -> None:
    app.dependency_overrides[get_db] = _override_get_db
    # 流式接口在生成器里自己开会话，也要指向测试库
    app.dependency_overrides[get_session_factory] = lambda: TestSessionLocal


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    _use_test_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def user_client(make_client):
    """已注册并登录的客户端。用法：client = await user_client("a@example.com")"""

    async def _login(email: str = "user0@example.com") -> AsyncClient:
        c = await make_client()
        resp = await c.post(
            "/api/auth/register", json={"email": email, "password": "correct-horse-battery"}
        )
        assert resp.status_code == 201, resp.text
        return c

    return _login


@pytest.fixture
async def make_client():
    """需要多个互相独立的登录会话时使用（例如测试用户 A 不能访问用户 B 的数据）。"""
    clients: list[AsyncClient] = []

    async def _make() -> AsyncClient:
        _use_test_db()
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(c)
        return c

    yield _make
    for c in clients:
        await c.aclose()
    app.dependency_overrides.clear()

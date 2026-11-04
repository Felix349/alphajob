"""投递记录与日程的数据访问。

数据隔离的硬性规则：这里每个查询都必须带上 user_id 条件。
拿不到（不存在或不属于当前用户）统一返回 None，由上层转成 404，不区分两者，避免泄露数据是否存在。
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Application, Event, Stage

# ---------- 投递记录 ----------


async def list_for_user(
    db: AsyncSession, user_id: uuid.UUID, *, stage: Stage | None = None, q: str | None = None
) -> list[Application]:
    stmt = select(Application).where(Application.user_id == user_id)
    if stage is not None:
        stmt = stmt.where(Application.stage == stage)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(Application.company.ilike(pattern) | Application.role.ilike(pattern))
    stmt = stmt.order_by(Application.stage, Application.position, Application.created_at)
    return list((await db.execute(stmt)).scalars())


async def get_for_user(
    db: AsyncSession, user_id: uuid.UUID, app_id: uuid.UUID, *, with_events: bool = False
) -> Application | None:
    stmt = select(Application).where(Application.id == app_id, Application.user_id == user_id)
    if with_events:
        stmt = stmt.options(selectinload(Application.events))
    return (await db.execute(stmt)).scalar_one_or_none()


async def min_position(db: AsyncSession, user_id: uuid.UUID, stage: Stage) -> float | None:
    stmt = select(func.min(Application.position)).where(
        Application.user_id == user_id, Application.stage == stage
    )
    return (await db.execute(stmt)).scalar_one()


async def next_events(
    db: AsyncSession, user_id: uuid.UUID, app_ids: list[uuid.UUID], now: datetime
) -> dict[uuid.UUID, Event]:
    """每个投递最近一个尚未开始的日程。用 PostgreSQL 的 DISTINCT ON 一次查完，避免 N+1 查询。"""
    if not app_ids:
        return {}
    stmt = (
        select(Event)
        .where(Event.user_id == user_id, Event.application_id.in_(app_ids), Event.start_at >= now)
        .order_by(Event.application_id, Event.start_at)
        .ext(distinct_on(Event.application_id))
    )
    return {e.application_id: e for e in (await db.execute(stmt)).scalars()}


# ---------- 日程事件 ----------


async def get_event_for_user(
    db: AsyncSession, user_id: uuid.UUID, event_id: uuid.UUID
) -> Event | None:
    stmt = select(Event).where(Event.id == event_id, Event.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_events_in_range(
    db: AsyncSession, user_id: uuid.UUID, start: datetime, end: datetime
) -> list[tuple[Event, Application]]:
    stmt = (
        select(Event, Application)
        .join(Application, Event.application_id == Application.id)
        .where(Event.user_id == user_id, Event.start_at >= start, Event.start_at < end)
        .order_by(Event.start_at)
    )
    return [(e, a) for e, a in (await db.execute(stmt)).all()]

"""投递记录与日程的业务逻辑。"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, Event, Stage, User
from app.repositories import applications as repo
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationOut,
    ApplicationUpdate,
    CalendarEventOut,
    EventCreate,
    EventOut,
    EventUpdate,
)

# 新卡片放在列的最上方：比当前最小的 position 再小一个间隔。
# 间隔足够大，拖拽时取两张卡片的中间值，可以连续插入很多次而不需要重排。
POSITION_GAP = 1024.0
MAX_CALENDAR_RANGE = timedelta(days=400)


class NotFound(Exception):
    pass


class InvalidRange(Exception):
    pass


async def _top_position(db: AsyncSession, user_id: uuid.UUID, stage: Stage) -> float:
    current = await repo.min_position(db, user_id, stage)
    return (current if current is not None else POSITION_GAP) - POSITION_GAP


async def _require_app(
    db: AsyncSession, user: User, app_id: uuid.UUID, *, with_events: bool = False
) -> Application:
    app = await repo.get_for_user(db, user.id, app_id, with_events=with_events)
    if app is None:
        raise NotFound
    return app


def _to_detail(app: Application, next_event: Event | None) -> ApplicationDetail:
    return ApplicationDetail.model_validate(
        {
            **ApplicationOut.model_validate(app).model_dump(exclude={"next_event"}),
            "next_event": EventOut.model_validate(next_event) if next_event else None,
            "jd_text": app.jd_text,
            "jd_parsed": app.jd_parsed,
            "notes": app.notes,
            "events": [EventOut.model_validate(e) for e in app.events],
        }
    )


# ---------- 投递记录 ----------


async def list_applications(
    db: AsyncSession, user: User, *, stage: Stage | None = None, q: str | None = None
) -> list[ApplicationOut]:
    apps = await repo.list_for_user(db, user.id, stage=stage, q=q)
    upcoming = await repo.next_events(db, user.id, [a.id for a in apps], datetime.now(UTC))
    result = []
    for a in apps:
        out = ApplicationOut.model_validate(a)
        if (e := upcoming.get(a.id)) is not None:
            out.next_event = EventOut.model_validate(e)
        result.append(out)
    return result


async def create_application(
    db: AsyncSession, user: User, data: ApplicationCreate
) -> ApplicationDetail:
    values = data.model_dump(exclude={"jd_parsed"})
    if data.stage != Stage.WISHLIST and data.applied_at is None:
        values["applied_at"] = date.today()
    app = Application(
        user_id=user.id,
        jd_parsed=data.jd_parsed.model_dump(mode="json") if data.jd_parsed else None,
        position=await _top_position(db, user.id, data.stage),
        **values,
    )
    db.add(app)
    await db.commit()
    return await get_application(db, user, app.id)


async def get_application(db: AsyncSession, user: User, app_id: uuid.UUID) -> ApplicationDetail:
    app = await _require_app(db, user, app_id, with_events=True)
    upcoming = await repo.next_events(db, user.id, [app.id], datetime.now(UTC))
    return _to_detail(app, upcoming.get(app.id))


async def update_application(
    db: AsyncSession, user: User, app_id: uuid.UUID, data: ApplicationUpdate
) -> ApplicationDetail:
    app = await _require_app(db, user, app_id)
    changes = data.model_dump(exclude_unset=True)

    if "jd_parsed" in changes:
        changes["jd_parsed"] = data.jd_parsed.model_dump(mode="json") if data.jd_parsed else None

    new_stage = changes.get("stage")
    if new_stage is not None and new_stage != app.stage:
        # 换列但没有指定位置：放到目标列最上方
        if "position" not in changes:
            changes["position"] = await _top_position(db, user.id, new_stage)
        # 从“待投递”拖出去，视为已经投递：自动记录投递日期
        if app.applied_at is None and new_stage != Stage.WISHLIST and "applied_at" not in changes:
            changes["applied_at"] = date.today()

    for key, value in changes.items():
        setattr(app, key, value)
    await db.commit()
    return await get_application(db, user, app.id)


async def delete_application(db: AsyncSession, user: User, app_id: uuid.UUID) -> None:
    app = await _require_app(db, user, app_id)
    await db.delete(app)  # 日程通过外键 ON DELETE CASCADE 一起删除
    await db.commit()


# ---------- 日程事件 ----------


async def create_event(
    db: AsyncSession, user: User, app_id: uuid.UUID, data: EventCreate
) -> EventOut:
    await _require_app(db, user, app_id)  # 只能给自己的投递加日程
    event = Event(application_id=app_id, user_id=user.id, **data.model_dump())
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return EventOut.model_validate(event)


async def update_event(
    db: AsyncSession, user: User, event_id: uuid.UUID, data: EventUpdate
) -> EventOut:
    event = await repo.get_event_for_user(db, user.id, event_id)
    if event is None:
        raise NotFound
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(event, key, value)
    if event.end_at is not None and event.end_at < event.start_at:
        raise InvalidRange("结束时间不能早于开始时间")
    await db.commit()
    await db.refresh(event)
    return EventOut.model_validate(event)


async def delete_event(db: AsyncSession, user: User, event_id: uuid.UUID) -> None:
    event = await repo.get_event_for_user(db, user.id, event_id)
    if event is None:
        raise NotFound
    await db.delete(event)
    await db.commit()


async def list_calendar(
    db: AsyncSession, user: User, start: datetime, end: datetime
) -> list[CalendarEventOut]:
    if end <= start:
        raise InvalidRange("结束时间必须晚于开始时间")
    if end - start > MAX_CALENDAR_RANGE:
        raise InvalidRange("一次最多查询 400 天")
    rows = await repo.list_events_in_range(db, user.id, start, end)
    return [
        CalendarEventOut(
            **EventOut.model_validate(e).model_dump(),
            company=a.company,
            role=a.role,
            stage=a.stage,
        )
        for e, a in rows
    ]

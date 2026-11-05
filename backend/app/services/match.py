"""岗位匹配分析（流式）与备考清单。"""

import json
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm import LLMClient, LLMError, StreamDone, StreamReset, TextDelta
from app.llm.logging import logged_stream_structured
from app.models import Application, MatchReport, PrepItem, Resume, User
from app.prompts import match as match_prompt
from app.repositories import applications as app_repo
from app.schemas.match import (
    MatchAnalysis,
    MatchReportOut,
    PrepItemCreate,
    PrepItemOut,
    PrepItemUpdate,
)


class NotFound(Exception):
    pass


class MatchPrecondition(Exception):
    """开始分析前的检查没通过（没有简历、没有 JD）。message 可以直接展示给用户。"""


# ---------- 匹配分析 ----------


async def _resume_of(db: AsyncSession, user: User) -> Resume | None:
    return (await db.execute(select(Resume).where(Resume.user_id == user.id))).scalar_one_or_none()


async def check_ready(db: AsyncSession, user: User, app_id: uuid.UUID) -> None:
    """在开始流式响应之前检查条件，这样不满足时可以返回普通的 400，而不是开了流再报错。"""
    app = await app_repo.get_for_user(db, user.id, app_id)
    if app is None:
        raise NotFound
    if not (app.jd_text or app.jd_parsed):
        raise MatchPrecondition("这条投递还没有岗位描述（JD），请先在详情页补充")
    if await _resume_of(db, user) is None:
        raise MatchPrecondition("还没有上传简历，请先到“我的简历”页面上传")


def _to_out(report: MatchReport, resume: Resume | None) -> MatchReportOut:
    return MatchReportOut(
        id=report.id,
        application_id=report.application_id,
        report=MatchAnalysis.model_validate(report.report),
        model=report.model,
        created_at=report.created_at,
        resume_updated_at=report.resume_updated_at,
        stale=resume is not None and resume.updated_at > report.resume_updated_at,
    )


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}


async def stream_match(
    session_factory: async_sessionmaker[AsyncSession],
    llm: LLMClient,
    user: User,
    app_id: uuid.UUID,
    notes: str | None,
) -> AsyncIterator[dict]:
    """生成 SSE 事件：delta（JSON 片段）、reset（结果作废、重新生成）、done（最终结果）、error。"""
    async with session_factory() as db:
        app = await app_repo.get_for_user(db, user.id, app_id)
        resume = await _resume_of(db, user)
        if app is None or resume is None:  # 理论上 check_ready 已经挡住了，这里防并发删除
            yield _sse("error", {"detail": "投递或简历已不存在"})
            return

        try:
            async for event in logged_stream_structured(
                db,
                llm,
                user=user,
                feature="match_report",
                system=match_prompt.SYSTEM,
                prompt=match_prompt.build_prompt(app, resume.content_md, notes),
                schema=MatchAnalysis,
                effort="medium",
            ):
                if isinstance(event, TextDelta):
                    yield _sse("delta", {"text": event.text})
                elif isinstance(event, StreamReset):
                    yield _sse("reset", {"reason": event.reason})
                elif isinstance(event, StreamDone):
                    report = await _save_report(db, user, app, resume, event.result)
                    yield _sse("done", _to_out(report, resume).model_dump(mode="json"))
        except LLMError as exc:
            yield _sse("error", {"detail": f"分析失败：{exc}"})


async def _save_report(db: AsyncSession, user: User, app: Application, resume: Resume, result):
    analysis: MatchAnalysis = result.data
    report = MatchReport(
        application_id=app.id,
        user_id=user.id,
        report=analysis.model_dump(mode="json"),
        model=result.model,
        resume_updated_at=resume.updated_at,
    )
    db.add(report)

    # 重新生成时：删掉“AI 生成且还没完成”的旧条目；用户手动加的、已经勾选完成的都保留
    await db.execute(
        delete(PrepItem).where(
            PrepItem.application_id == app.id, PrepItem.source == "ai", PrepItem.done.is_(False)
        )
    )
    base = await _max_position(db, app.id)
    for i, item in enumerate(sorted(analysis.prep_items, key=lambda p: p.priority)):
        db.add(
            PrepItem(
                application_id=app.id,
                user_id=user.id,
                content=item.content[:500],
                category=item.category,
                priority=item.priority,
                source="ai",
                position=base + (i + 1) * 1024,
            )
        )
    await db.commit()
    await db.refresh(report)
    return report


async def latest_report(db: AsyncSession, user: User, app_id: uuid.UUID) -> MatchReportOut | None:
    if await app_repo.get_for_user(db, user.id, app_id) is None:
        raise NotFound
    report = (
        await db.execute(
            select(MatchReport)
            .where(MatchReport.application_id == app_id, MatchReport.user_id == user.id)
            .order_by(MatchReport.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if report is None:
        return None
    return _to_out(report, await _resume_of(db, user))


# ---------- 备考清单 ----------


async def _max_position(db: AsyncSession, app_id: uuid.UUID) -> float:
    stmt = select(func.max(PrepItem.position)).where(PrepItem.application_id == app_id)
    return (await db.execute(stmt)).scalar_one() or 0.0


async def list_prep_items(db: AsyncSession, user: User, app_id: uuid.UUID) -> list[PrepItemOut]:
    if await app_repo.get_for_user(db, user.id, app_id) is None:
        raise NotFound
    rows = await db.execute(
        select(PrepItem)
        .where(PrepItem.application_id == app_id, PrepItem.user_id == user.id)
        .order_by(PrepItem.done, PrepItem.priority, PrepItem.position)
    )
    return [PrepItemOut.model_validate(p) for p in rows.scalars()]


async def create_prep_item(
    db: AsyncSession, user: User, app_id: uuid.UUID, data: PrepItemCreate
) -> PrepItemOut:
    if await app_repo.get_for_user(db, user.id, app_id) is None:
        raise NotFound
    item = PrepItem(
        application_id=app_id,
        user_id=user.id,
        source="manual",
        position=await _max_position(db, app_id) + 1024,
        **data.model_dump(),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return PrepItemOut.model_validate(item)


async def _require_item(db: AsyncSession, user: User, item_id: uuid.UUID) -> PrepItem:
    item = (
        await db.execute(
            select(PrepItem).where(PrepItem.id == item_id, PrepItem.user_id == user.id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise NotFound
    return item


async def update_prep_item(
    db: AsyncSession, user: User, item_id: uuid.UUID, data: PrepItemUpdate
) -> PrepItemOut:
    item = await _require_item(db, user, item_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return PrepItemOut.model_validate(item)


async def delete_prep_item(db: AsyncSession, user: User, item_id: uuid.UUID) -> None:
    item = await _require_item(db, user, item_id)
    await db.delete(item)
    await db.commit()

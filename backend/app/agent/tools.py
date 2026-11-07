"""Agent 可以使用的工具。

两类工具：
- 读工具：查询投递、日程、备考项、薄弱点、题库。立即执行，结果返回给模型。
- 写工具：修改阶段、添加日程、添加 / 勾选备考项、标记薄弱点已解决。
  不会立即执行，只生成一条“待确认的操作”，用户在界面上点确认后才真正修改数据。

每个工具由三部分组成：参数模型（Pydantic，自动生成给模型看的 JSON Schema）、
用途说明（模型靠它决定什么时候调用、怎么调用）、执行函数。
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.agent.context import AgentContext
from app.llm import ToolSpec
from app.models import (
    Application,
    EventType,
    Interview,
    MatchReport,
    PrepItem,
    Stage,
    WeakPoint,
)
from app.repositories import applications as app_repo
from app.schemas.application import ApplicationUpdate, EventCreate
from app.schemas.match import MatchAnalysis, PrepItemCreate, PrepItemUpdate
from app.services import applications as app_service
from app.services import interview as interview_service
from app.services import match as match_service

STAGE_LABEL = {
    Stage.WISHLIST: "待投递", Stage.APPLIED: "已投递", Stage.WRITTEN_TEST: "笔试",
    Stage.INTERVIEWING: "面试中", Stage.HR: "HR 面", Stage.OFFER: "Offer", Stage.ENDED: "已结束",
}  # fmt: skip
EVENT_LABEL = {
    EventType.WRITTEN_TEST: "笔试", EventType.INTERVIEW: "面试",
    EventType.DEADLINE: "截止", EventType.OTHER: "其他",
}  # fmt: skip


class ToolError(Exception):
    """工具执行失败（参数指向的数据不存在等）。message 会作为错误结果返回给模型，让它自己调整。"""


@dataclass
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    run: Callable[[AgentContext, Any], Awaitable[Any]]
    # 写工具：describe 生成给用户看的确认文案，同时校验参数指向的数据确实属于当前用户
    write: bool = False
    describe: Callable[[AgentContext, Any], Awaitable[str]] | None = None

    def spec(self) -> ToolSpec:
        schema = self.args.model_json_schema()
        schema.pop("title", None)
        return ToolSpec(self.name, self.description, schema)


async def _app(ctx: AgentContext, app_id: uuid.UUID) -> Application:
    app = await app_repo.get_for_user(ctx.db, ctx.user.id, app_id)
    if app is None:
        raise ToolError(f"找不到 id 为 {app_id} 的投递，请先用 list_applications 查询正确的 id")
    return app


def _name(app: Application) -> str:
    return f"{app.company} · {app.role}"


# ====================== 读工具 ======================


class ListApplicationsArgs(BaseModel):
    stage: Stage | None = Field(default=None, description="只看某个阶段；不填则返回全部")
    keyword: str | None = Field(default=None, description="按公司或岗位名模糊搜索，例如“字节”")


async def list_applications(ctx: AgentContext, a: ListApplicationsArgs):
    apps = await app_repo.list_for_user(ctx.db, ctx.user.id, stage=a.stage, q=a.keyword)
    upcoming = await app_repo.next_events(ctx.db, ctx.user.id, [x.id for x in apps], ctx.now())
    return [
        {
            "id": str(x.id),
            "company": x.company,
            "role": x.role,
            "stage": STAGE_LABEL[x.stage],
            "applied_at": x.applied_at.isoformat() if x.applied_at else None,
            "next_event": (
                f"{EVENT_LABEL[e.type]}「{e.title}」{ctx.fmt(e.start_at)}"
                if (e := upcoming.get(x.id))
                else None
            ),
        }
        for x in apps[:50]
    ]


class GetApplicationArgs(BaseModel):
    application_id: uuid.UUID = Field(description="投递的 id（来自 list_applications）")


async def get_application(ctx: AgentContext, a: GetApplicationArgs):
    app = await app_repo.get_for_user(ctx.db, ctx.user.id, a.application_id, with_events=True)
    if app is None:
        raise ToolError("找不到这条投递")
    prep = (
        await ctx.db.execute(
            select(func.count(), func.count().filter(PrepItem.done)).where(
                PrepItem.application_id == app.id
            )
        )
    ).one()
    report = (
        await ctx.db.execute(
            select(MatchReport)
            .where(MatchReport.application_id == app.id)
            .order_by(MatchReport.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    interviews = (
        await ctx.db.execute(
            select(Interview.round, Interview.status).where(Interview.application_id == app.id)
        )
    ).all()
    return {
        "id": str(app.id),
        "company": app.company,
        "role": app.role,
        "stage": STAGE_LABEL[app.stage],
        "jd_summary": (app.jd_parsed or {}).get("summary"),
        "notes": app.notes,
        "events": [
            {"type": EVENT_LABEL[e.type], "title": e.title, "time": ctx.fmt(e.start_at)}
            for e in app.events
        ],
        "prep_items": {"total": prep[0], "done": prep[1]},
        # 统一按现在的规则计算（旧数据里存的可能是模型给的分数）
        "match_score": MatchAnalysis.from_stored(report.report).score if report else None,
        "interview_reviews": [{"round": r, "status": s} for r, s in interviews],
    }


class ListEventsArgs(BaseModel):
    days_ahead: int = Field(default=7, ge=0, le=60, description="查询未来多少天，默认 7 天")
    days_back: int = Field(default=0, ge=0, le=30, description="同时包含过去多少天，默认 0")


async def list_events(ctx: AgentContext, a: ListEventsArgs):
    now = ctx.now()
    rows = await app_repo.list_events_in_range(
        ctx.db, ctx.user.id, now - timedelta(days=a.days_back), now + timedelta(days=a.days_ahead)
    )
    return [
        {
            "application_id": str(app.id),
            "company": app.company,
            "role": app.role,
            "type": EVENT_LABEL[e.type],
            "title": e.title,
            "time": ctx.fmt(e.start_at),
            "is_past": e.start_at < now,
        }
        for e, app in rows
    ]


class ListPrepItemsArgs(BaseModel):
    application_id: uuid.UUID | None = Field(
        default=None, description="只看某条投递；不填则返回全部"
    )
    include_done: bool = Field(default=False, description="是否包含已完成的项")


async def list_prep_items(ctx: AgentContext, a: ListPrepItemsArgs):
    stmt = (
        select(PrepItem, Application)
        .join(Application, PrepItem.application_id == Application.id)
        .where(PrepItem.user_id == ctx.user.id)
        .order_by(PrepItem.done, PrepItem.priority, PrepItem.position)
        .limit(40)
    )
    if a.application_id:
        stmt = stmt.where(PrepItem.application_id == a.application_id)
    if not a.include_done:
        stmt = stmt.where(PrepItem.done.is_(False))
    return [
        {
            "id": str(p.id),
            "application": _name(app),
            "application_id": str(app.id),
            "content": p.content,
            "priority": p.priority,
            "done": p.done,
        }
        for p, app in (await ctx.db.execute(stmt)).all()
    ]


class ListWeakPointsArgs(BaseModel):
    include_resolved: bool = Field(default=False, description="是否包含已经解决的薄弱点")


async def list_weak_points(ctx: AgentContext, a: ListWeakPointsArgs):
    stmt = (
        select(WeakPoint, Application)
        .join(Application, WeakPoint.application_id == Application.id)
        .where(WeakPoint.user_id == ctx.user.id)
        .order_by(WeakPoint.created_at.desc())
        .limit(30)
    )
    if not a.include_resolved:
        stmt = stmt.where(WeakPoint.status == "open")
    return [
        {
            "id": str(w.id),
            "topic": w.topic,
            "detail": w.detail,
            "from": _name(app),
            "status": w.status,
        }
        for w, app in (await ctx.db.execute(stmt)).all()
    ]


class SearchQuestionsArgs(BaseModel):
    keyword: str | None = Field(default=None, description="在题目和参考回答中搜索的关键词")
    only_unmastered: bool = Field(default=True, description="只看还没掌握的题")


async def search_questions(ctx: AgentContext, a: SearchQuestionsArgs):
    items = await interview_service.list_questions(ctx.db, ctx.user, q=a.keyword)
    if a.only_unmastered:
        items = [q for q in items if q.mastery != "mastered"]
    return [
        {"question": q.question, "score": q.score, "tags": q.tags, "from": f"{q.company} {q.round}"}
        for q in items[:15]
    ]


# ====================== 写工具（需要用户确认）======================


class UpdateStageArgs(BaseModel):
    application_id: uuid.UUID = Field(description="投递的 id")
    stage: Stage = Field(description="新的阶段")


async def describe_update_stage(ctx: AgentContext, a: UpdateStageArgs) -> str:
    app = await _app(ctx, a.application_id)
    return f"把「{_name(app)}」的阶段从“{STAGE_LABEL[app.stage]}”改为“{STAGE_LABEL[a.stage]}”"


async def run_update_stage(ctx: AgentContext, a: UpdateStageArgs):
    await app_service.update_application(
        ctx.db, ctx.user, a.application_id, ApplicationUpdate(stage=a.stage)
    )
    return "阶段已更新"


class CreateEventArgs(BaseModel):
    application_id: uuid.UUID = Field(description="投递的 id")
    type: EventType = Field(description="日程类型")
    title: str = Field(min_length=1, max_length=128, description="标题，例如“二面”“在线笔试”")
    start_at: datetime = Field(
        description="开始时间，ISO 8601 格式，例如 2026-11-07T14:00。不带时区时按用户本地时间理解"
    )


def _local(ctx: AgentContext, dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=ctx.tz)


async def describe_create_event(ctx: AgentContext, a: CreateEventArgs) -> str:
    app = await _app(ctx, a.application_id)
    when = ctx.fmt(_local(ctx, a.start_at))
    return f"给「{_name(app)}」添加日程：{EVENT_LABEL[a.type]}「{a.title}」，{when}"


async def run_create_event(ctx: AgentContext, a: CreateEventArgs):
    await app_service.create_event(
        ctx.db,
        ctx.user,
        a.application_id,
        EventCreate(type=a.type, title=a.title, start_at=_local(ctx, a.start_at)),
    )
    return "日程已添加"


class AddPrepItemArgs(BaseModel):
    application_id: uuid.UUID = Field(description="投递的 id")
    content: str = Field(min_length=1, max_length=500, description="一条具体的备考任务，以动词开头")
    priority: int = Field(default=2, ge=1, le=3, description="1 最优先，3 最次要")


async def describe_add_prep(ctx: AgentContext, a: AddPrepItemArgs) -> str:
    app = await _app(ctx, a.application_id)
    return f"给「{_name(app)}」添加备考任务：{a.content}"


async def run_add_prep(ctx: AgentContext, a: AddPrepItemArgs):
    await match_service.create_prep_item(
        ctx.db,
        ctx.user,
        a.application_id,
        PrepItemCreate(content=a.content, priority=a.priority),  # type: ignore[arg-type]
    )
    return "备考任务已添加"


class SetPrepDoneArgs(BaseModel):
    item_id: uuid.UUID = Field(description="备考项的 id（来自 list_prep_items）")
    done: bool = Field(default=True, description="true 表示标记为完成")


async def _prep(ctx: AgentContext, item_id: uuid.UUID) -> PrepItem:
    stmt = select(PrepItem).where(PrepItem.id == item_id, PrepItem.user_id == ctx.user.id)
    item = (await ctx.db.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise ToolError("找不到这条备考项，请先用 list_prep_items 查询正确的 id")
    return item


async def describe_set_prep(ctx: AgentContext, a: SetPrepDoneArgs) -> str:
    item = await _prep(ctx, a.item_id)
    return f"把备考任务「{item.content}」标记为{'已完成' if a.done else '未完成'}"


async def run_set_prep(ctx: AgentContext, a: SetPrepDoneArgs):
    await match_service.update_prep_item(ctx.db, ctx.user, a.item_id, PrepItemUpdate(done=a.done))
    return "备考任务已更新"


class ResolveWeakPointArgs(BaseModel):
    weak_point_id: uuid.UUID = Field(description="薄弱点的 id（来自 list_weak_points）")


async def _weak(ctx: AgentContext, wid: uuid.UUID) -> WeakPoint:
    stmt = select(WeakPoint).where(WeakPoint.id == wid, WeakPoint.user_id == ctx.user.id)
    w = (await ctx.db.execute(stmt)).scalar_one_or_none()
    if w is None:
        raise ToolError("找不到这条薄弱点，请先用 list_weak_points 查询正确的 id")
    return w


async def describe_resolve(ctx: AgentContext, a: ResolveWeakPointArgs) -> str:
    return f"把薄弱点「{(await _weak(ctx, a.weak_point_id)).topic}」标记为已解决"


async def run_resolve(ctx: AgentContext, a: ResolveWeakPointArgs):
    w = await _weak(ctx, a.weak_point_id)
    w.status = "resolved"
    await ctx.db.commit()
    return "薄弱点已标记为解决"


# ====================== 注册表 ======================

TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool("list_applications", "列出用户的投递记录（公司、岗位、阶段、下一场日程）。回答任何关于投递的问题前，先用它拿到投递的 id。", ListApplicationsArgs, list_applications),
        Tool("get_application", "查看一条投递的详情：JD 要点、全部日程、备考进度、匹配度、复盘情况。", GetApplicationArgs, get_application),
        Tool("list_events", "按时间范围查询用户的笔试、面试、截止日期等日程。", ListEventsArgs, list_events),
        Tool("list_prep_items", "查询备考清单（默认只返回未完成的项）。", ListPrepItemsArgs, list_prep_items),
        Tool("list_weak_points", "查询从面试复盘中发现的薄弱点（默认只返回未解决的）。", ListWeakPointsArgs, list_weak_points),
        Tool("search_questions", "搜索用户在真实面试中被问过的题目（个人题库）。", SearchQuestionsArgs, search_questions),
        Tool("update_application_stage", "修改一条投递的阶段。需要用户确认后才会执行。", UpdateStageArgs, run_update_stage, True, describe_update_stage),
        Tool("create_event", "给一条投递添加笔试、面试或截止日期等日程。需要用户确认后才会执行。", CreateEventArgs, run_create_event, True, describe_create_event),
        Tool("add_prep_item", "给一条投递添加备考任务。需要用户确认后才会执行。", AddPrepItemArgs, run_add_prep, True, describe_add_prep),
        Tool("set_prep_item_done", "把一条备考任务标记为完成或未完成。需要用户确认后才会执行。", SetPrepDoneArgs, run_set_prep, True, describe_set_prep),
        Tool("resolve_weak_point", "把一条薄弱点标记为已解决。需要用户确认后才会执行。", ResolveWeakPointArgs, run_resolve, True, describe_resolve),
    ]
}  # fmt: skip

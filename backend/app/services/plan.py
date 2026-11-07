"""今日计划 / 本周计划。

做法：先由代码“确定性地”收集上下文，再交给模型排序、写理由。
不让模型自己调工具去探索：上下文是固定的几类数据，一次性给齐更稳定、更便宜，也更容易测试。
（对话模式才让模型自由调用工具，见 app/agent/loop.py。）
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import WEEKDAYS, AgentContext
from app.agent.tools import EVENT_LABEL, STAGE_LABEL
from app.llm import LLMClient
from app.llm.logging import logged_structured
from app.models import (
    AgentPlan,
    Application,
    EventType,
    Interview,
    Mastery,
    PrepItem,
    Question,
    Stage,
    WeakPoint,
)
from app.prompts import plan as plan_prompt
from app.repositories import applications as app_repo
from app.schemas.agent import TodayPlan, WeekPlan


class NotFound(Exception):
    pass


def plan_date_for(kind: str, ctx: AgentContext) -> date:
    today = ctx.now().date()
    return today if kind == "today" else today - timedelta(days=today.weekday())  # 本周一


async def gather_context(ctx: AgentContext, kind: str) -> dict:
    db, uid, now = ctx.db, ctx.user.id, ctx.now()
    if kind == "today":
        start, end = now - timedelta(days=3), now + timedelta(days=7)
    else:
        monday = datetime.combine(plan_date_for("week", ctx), datetime.min.time(), ctx.tz)
        start, end = monday - timedelta(days=3), monday + timedelta(days=10)

    events = await app_repo.list_events_in_range(db, uid, start, end)
    apps = [a for a in await app_repo.list_for_user(db, uid) if a.stage != Stage.ENDED]

    prep_rows = (
        await db.execute(
            select(PrepItem, Application.company)
            .join(Application, PrepItem.application_id == Application.id)
            .where(PrepItem.user_id == uid, PrepItem.done.is_(False))
            .order_by(PrepItem.priority, PrepItem.position)
            .limit(30)
        )
    ).all()
    weak_rows = (
        await db.execute(
            select(WeakPoint, Application.company)
            .join(Application, WeakPoint.application_id == Application.id)
            .where(WeakPoint.user_id == uid, WeakPoint.status == "open")
            .order_by(WeakPoint.created_at.desc())
            .limit(15)
        )
    ).all()
    questions = (
        await db.execute(
            select(Question.question, Question.score)
            .where(Question.user_id == uid, Question.mastery != Mastery.MASTERED)
            .order_by(Question.score)
            .limit(8)
        )
    ).all()

    return {
        "now": f"{now:%Y-%m-%d %H:%M} 星期{WEEKDAYS[now.weekday()]}",
        "events": [
            {
                "time": ctx.fmt(e.start_at),
                "is_past": e.start_at < now,
                "type": EVENT_LABEL[e.type],
                "title": e.title,
                "company": a.company,
                "application_id": str(a.id),
            }
            for e, a in events
        ],
        "active_applications": [
            {"id": str(a.id), "company": a.company, "role": a.role, "stage": STAGE_LABEL[a.stage]}
            for a in apps[:30]
        ],
        "open_prep_items": [
            {
                "content": p.content,
                "priority": p.priority,
                "company": c,
                "application_id": str(p.application_id),
            }
            for p, c in prep_rows
        ],  # fmt: skip
        "open_weak_points": [
            {"topic": w.topic, "detail": w.detail, "from": c} for w, c in weak_rows
        ],
        "interviews_to_review": await _unreviewed(db, uid, events, now),
        "questions_to_review": [{"question": q, "score": s} for q, s in questions],
    }


async def _unreviewed(db: AsyncSession, uid: uuid.UUID, events, now: datetime) -> list[dict]:
    """面完了、但还没有复盘记录的场次：过去 3 天内的面试日程，且之后没有新建复盘。"""
    past = [(e, a) for e, a in events if e.type == EventType.INTERVIEW and e.start_at < now]
    if not past:
        return []
    reviewed = (
        await db.execute(
            select(Interview.application_id, Interview.created_at).where(Interview.user_id == uid)
        )
    ).all()
    result = []
    for e, a in past:
        if not any(app_id == a.id and created >= e.start_at for app_id, created in reviewed):
            result.append({"company": a.company, "title": e.title, "application_id": str(a.id)})
    return result


async def generate(ctx: AgentContext, llm: LLMClient, kind: str) -> AgentPlan:
    context = await gather_context(ctx, kind)
    schema = TodayPlan if kind == "today" else WeekPlan
    result = await logged_structured(
        ctx.db,
        llm,
        user=ctx.user,
        feature=f"plan_{kind}",
        system=plan_prompt.TODAY_SYSTEM if kind == "today" else plan_prompt.WEEK_SYSTEM,
        prompt=plan_prompt.build_prompt(context),
        schema=schema,
        effort="medium",
    )
    data = result.data.model_dump(mode="json")
    if kind == "today":
        # 模型给的 application_id 不可信：只保留真的属于当前用户的，其他置空（前端据此生成跳转链接）
        valid = {a["id"] for a in context["active_applications"]}
        for item in data["items"]:
            if item["application_id"] not in valid:
                item["application_id"] = None
    plan = AgentPlan(
        user_id=ctx.user.id,
        kind=kind,
        plan_date=plan_date_for(kind, ctx),
        plan=data,
        done_items=[],
        model=result.model,
    )
    ctx.db.add(plan)
    await ctx.db.commit()
    await ctx.db.refresh(plan)
    return plan


async def latest(ctx: AgentContext, kind: str) -> AgentPlan | None:
    """今天（或本周）最新生成的一份计划；过了这一天（这一周）就返回 None，提示用户重新生成。"""
    stmt = (
        select(AgentPlan)
        .where(
            AgentPlan.user_id == ctx.user.id,
            AgentPlan.kind == kind,
            AgentPlan.plan_date == plan_date_for(kind, ctx),
        )
        .order_by(AgentPlan.created_at.desc())
        .limit(1)
    )
    return (await ctx.db.execute(stmt)).scalar_one_or_none()


async def toggle_item(ctx: AgentContext, plan_id: uuid.UUID, index: int, done: bool) -> AgentPlan:
    stmt = select(AgentPlan).where(AgentPlan.id == plan_id, AgentPlan.user_id == ctx.user.id)
    plan = (await ctx.db.execute(stmt)).scalar_one_or_none()
    if plan is None or plan.kind != "today" or index >= len(plan.plan.get("items", [])):
        raise NotFound
    items = set(plan.done_items)
    items.add(index) if done else items.discard(index)
    plan.done_items = sorted(items)  # 重新赋值：JSONB 列原地修改不会被 SQLAlchemy 检测到
    await ctx.db.commit()
    await ctx.db.refresh(plan)
    return plan

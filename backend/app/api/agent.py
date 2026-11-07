import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import EventSourceResponse

from app.agent import actions
from app.agent.context import AgentContext, resolve_tz
from app.agent.loop import run_agent
from app.api.deps import SSE_HEADERS, get_current_user, require_llm
from app.core.db import get_db, get_session_factory
from app.llm import ChatMessage, LLMClient, LLMError
from app.models import User
from app.schemas.agent import AgentActionOut, ChatRequest, PlanItemToggle, PlanOut, PlanRequest
from app.services import plan as plan_service

router = APIRouter(prefix="/agent", tags=["agent"])


# ---------- 对话 ----------


@router.post(
    "/chat",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE 事件流"}},
)
async def chat(
    data: ChatRequest,
    user: User = Depends(get_current_user),
    llm: LLMClient = Depends(require_llm),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
):
    """和求职 Agent 对话，以 SSE 推送每一步：thinking（模型的过渡语）、tool_call、tool_result、
    proposal（待确认的写操作）、message（最终回答）、error。"""
    history = [ChatMessage(m.role, m.content) for m in data.messages]
    tz = resolve_tz(data.timezone)

    async def events():
        # 响应要持续十几秒，在生成器内部自己管理数据库会话（原因见 core/db.py）
        async with session_factory() as db:
            me = await db.get(User, user.id)
            async for event in run_agent(AgentContext(db, me, tz), llm, history):
                yield {"event": event["event"], "data": _dumps(event["data"])}

    return EventSourceResponse(events(), ping=15, headers=SSE_HEADERS)


def _dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


# ---------- 待确认的操作 ----------


def _ctx(db: AsyncSession, user: User, timezone: str | None = None) -> AgentContext:
    return AgentContext(db, user, resolve_tz(timezone))


@router.post("/actions/{action_id}/confirm", response_model=AgentActionOut)
async def confirm_action(
    action_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        return await actions.confirm(_ctx(db, user), action_id)
    except actions.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="操作不存在") from None
    except actions.AlreadyHandled:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="这个操作已经处理过了") from None


@router.post("/actions/{action_id}/cancel", response_model=AgentActionOut)
async def cancel_action(
    action_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        return await actions.cancel(_ctx(db, user), action_id)
    except actions.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="操作不存在") from None
    except actions.AlreadyHandled:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="这个操作已经处理过了") from None


# ---------- 计划 ----------


@router.get("/plan", response_model=PlanOut | None)
async def get_plan(
    kind: Literal["today", "week"],
    timezone: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当天（本周）最新的一份计划；还没生成或已经过期时返回 null。"""
    return await plan_service.latest(_ctx(db, user, timezone), kind)


@router.post("/plan", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan(
    data: PlanRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(require_llm),
):
    try:
        return await plan_service.generate(_ctx(db, user, data.timezone), llm, data.kind)
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"生成计划失败：{exc}") from None


@router.patch("/plan/{plan_id}", response_model=PlanOut)
async def toggle_plan_item(
    plan_id: uuid.UUID,
    data: PlanItemToggle,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await plan_service.toggle_item(_ctx(db, user), plan_id, data.index, data.done)
    except plan_service.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="计划或计划项不存在") from None

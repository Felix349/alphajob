import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import EventSourceResponse

from app.api.deps import get_current_user, require_llm
from app.core.db import get_db, get_session_factory
from app.llm import LLMClient
from app.models import User
from app.schemas.match import (
    MatchReportOut,
    MatchRequest,
    PrepItemCreate,
    PrepItemOut,
    PrepItemUpdate,
)
from app.services import match as service

router = APIRouter(tags=["match"])

APP_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="投递记录不存在")
ITEM_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="备考项不存在")


@router.get("/applications/{app_id}/match-report", response_model=MatchReportOut | None)
async def get_match_report(
    app_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        return await service.latest_report(db, user, app_id)
    except service.NotFound:
        raise APP_NOT_FOUND from None


@router.post(
    "/applications/{app_id}/match-report",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE 事件流"}},
)
async def create_match_report(
    app_id: uuid.UUID,
    data: MatchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(require_llm),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
):
    """生成匹配分析，以 SSE 流式返回。

    事件：delta（模型输出的 JSON 片段，前端边收边渲染）、reset（结果作废、正在修正）、
    done（保存好的最终结果）、error（失败原因）。
    """
    try:
        await service.check_ready(db, user, app_id, data.resume_language)
    except service.NotFound:
        raise APP_NOT_FOUND from None
    except service.MatchPrecondition as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None

    return EventSourceResponse(
        service.stream_match(session_factory, llm, user, app_id, data.notes, data.resume_language),
        ping=15,  # 每 15 秒发一次心跳，防止代理认为连接空闲而断开
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},  # 禁止代理缓冲
    )


@router.get("/applications/{app_id}/prep-items", response_model=list[PrepItemOut])
async def list_prep_items(
    app_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        return await service.list_prep_items(db, user, app_id)
    except service.NotFound:
        raise APP_NOT_FOUND from None


@router.post(
    "/applications/{app_id}/prep-items",
    response_model=PrepItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_prep_item(
    app_id: uuid.UUID,
    data: PrepItemCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.create_prep_item(db, user, app_id, data)
    except service.NotFound:
        raise APP_NOT_FOUND from None


@router.patch("/prep-items/{item_id}", response_model=PrepItemOut)
async def update_prep_item(
    item_id: uuid.UUID,
    data: PrepItemUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.update_prep_item(db, user, item_id, data)
    except service.NotFound:
        raise ITEM_NOT_FOUND from None


@router.delete("/prep-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prep_item(
    item_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        await service.delete_prep_item(db, user, item_id)
    except service.NotFound:
        raise ITEM_NOT_FOUND from None

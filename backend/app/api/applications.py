import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.llm import LLMClient, LLMError, LLMNotConfigured
from app.llm.factory import get_llm_client
from app.models import Stage, User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationOut,
    ApplicationUpdate,
    EventCreate,
    EventOut,
)
from app.schemas.jd import ParsedJD, ParseJDRequest
from app.services import applications as service
from app.services import jd as jd_service

router = APIRouter(prefix="/applications", tags=["applications"])

NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="投递记录不存在")


def require_llm() -> LLMClient:
    """依赖：拿到配置好的大模型客户端；没配 API Key 时返回 503，前端可以提示用户手动填写。
    测试中通过 app.dependency_overrides[require_llm] 替换成假的实现。"""
    try:
        return get_llm_client()
    except LLMNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"智能解析暂不可用：{exc}"
        ) from None


@router.get("", response_model=list[ApplicationOut])
async def list_applications(
    stage: Stage | None = None,
    q: str | None = Query(default=None, max_length=100, description="按公司或岗位模糊搜索"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_applications(db, user, stage=stage, q=q)


@router.post("", response_model=ApplicationDetail, status_code=status.HTTP_201_CREATED)
async def create_application(
    data: ApplicationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_application(db, user, data)


# 注意：这个路由必须写在 /{app_id} 之前，否则 "parse-jd" 会被当成 app_id 去匹配
@router.post("/parse-jd", response_model=ParsedJD)
async def parse_jd(
    data: ParseJDRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(require_llm),
):
    try:
        return await jd_service.parse_jd(db, llm, user, data.jd_text)
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"解析失败：{exc}") from None


@router.get("/{app_id}", response_model=ApplicationDetail)
async def get_application(
    app_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        return await service.get_application(db, user, app_id)
    except service.NotFound:
        raise NOT_FOUND from None


@router.patch("/{app_id}", response_model=ApplicationDetail)
async def update_application(
    app_id: uuid.UUID,
    data: ApplicationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.update_application(db, user, app_id, data)
    except service.NotFound:
        raise NOT_FOUND from None


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    app_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        await service.delete_application(db, user, app_id)
    except service.NotFound:
        raise NOT_FOUND from None


@router.post("/{app_id}/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    app_id: uuid.UUID,
    data: EventCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.create_event(db, user, app_id, data)
    except service.NotFound:
        raise NOT_FOUND from None

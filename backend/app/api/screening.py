"""岗位快速筛选的接口。

典型顺序：建批次 → 读取岗位（插件提交 / 粘贴文本）→ 粗筛 → 补充 JD → 精排（SSE）→ 加入投递记录。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import EventSourceResponse

from app.api.deps import SSE_HEADERS, get_current_user, optional_llm, require_llm
from app.core.db import get_db, get_session_factory
from app.llm import LLMClient, LLMError
from app.models import User
from app.schemas.screening import (
    AddJobsResult,
    BatchCreate,
    BatchDetail,
    BatchOut,
    ExtractRequest,
    JdIn,
    JobOut,
    JobsIn,
    ScreenResult,
)
from app.services import screening as service

router = APIRouter(prefix="/screening", tags=["screening"])

BATCH_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="筛选批次不存在")
JOB_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="岗位不存在")


def _precondition(exc: service.Precondition) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _llm_failed(exc: LLMError) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"AI 调用失败：{exc}")


# ---------- 批次 ----------


@router.post("/batches", response_model=BatchDetail, status_code=status.HTTP_201_CREATED)
async def create_batch(
    data: BatchCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.create_batch(db, user, data)


@router.get("/batches", response_model=list[BatchOut])
async def list_batches(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await service.list_batches(db, user)


@router.get("/batches/{batch_id}", response_model=BatchDetail)
async def get_batch(
    batch_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        return await service.get_batch(db, user, batch_id)
    except service.NotFound:
        raise BATCH_NOT_FOUND from None


@router.delete("/batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_batch(
    batch_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        await service.delete_batch(db, user, batch_id)
    except service.NotFound:
        raise BATCH_NOT_FOUND from None


# ---------- 读取岗位 ----------


@router.post("/batches/{batch_id}/jobs", response_model=AddJobsResult)
async def add_jobs(
    batch_id: uuid.UUID,
    data: JobsIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交结构化的岗位列表（浏览器插件用）。翻页后重复提交会自动去重。"""
    try:
        return await service.add_jobs(db, user, batch_id, data.jobs)
    except service.NotFound:
        raise BATCH_NOT_FOUND from None
    except service.Precondition as exc:
        raise _precondition(exc) from None


@router.post("/batches/{batch_id}/extract", response_model=AddJobsResult)
async def extract_jobs(
    batch_id: uuid.UUID,
    data: ExtractRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(require_llm),
):
    """从粘贴的招聘列表页文本里抽取岗位。"""
    try:
        return await service.extract_jobs(db, llm, user, batch_id, data.text)
    except service.NotFound:
        raise BATCH_NOT_FOUND from None
    except service.Precondition as exc:
        raise _precondition(exc) from None
    except LLMError as exc:
        raise _llm_failed(exc) from None


# ---------- 粗筛 ----------


@router.post("/batches/{batch_id}/screen", response_model=ScreenResult)
async def screen(
    batch_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(require_llm),
):
    """硬条件过滤 + 粗筛，返回进入精排、但还缺 JD 的岗位。"""
    try:
        return await service.screen(db, llm, user, batch_id)
    except service.NotFound:
        raise BATCH_NOT_FOUND from None
    except service.Precondition as exc:
        raise _precondition(exc) from None
    except LLMError as exc:
        raise _llm_failed(exc) from None


# ---------- 补充 JD ----------


@router.put("/jobs/{job_id}/jd", response_model=JobOut)
async def set_jd(
    job_id: uuid.UUID,
    data: JdIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.set_jd(db, user, job_id, data.jd_text)
    except service.NotFound:
        raise JOB_NOT_FOUND from None


# ---------- 精排 ----------


@router.post(
    "/batches/{batch_id}/rank",
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE 事件流"}},
)
async def rank(
    batch_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(require_llm),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
):
    """精排进入名单且有 JD 的岗位。事件：start（总数）、job（每完成一个）、done（最终排序）。"""
    try:
        await service.check_rank_ready(db, user, batch_id)
    except service.NotFound:
        raise BATCH_NOT_FOUND from None
    except service.Precondition as exc:
        raise _precondition(exc) from None
    return EventSourceResponse(
        service.rank_batch(session_factory, llm, user, batch_id), ping=15, headers=SSE_HEADERS
    )


# ---------- 加入投递记录 ----------


@router.post("/jobs/{job_id}/import", status_code=status.HTTP_201_CREATED)
async def import_job(
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: LLMClient | None = Depends(optional_llm),
) -> dict[str, uuid.UUID]:
    """加入投递记录（“想投”阶段）。返回投递记录的 id；重复调用返回同一条。"""
    try:
        return {"application_id": await service.import_job(db, llm, user, job_id)}
    except service.NotFound:
        raise JOB_NOT_FOUND from None

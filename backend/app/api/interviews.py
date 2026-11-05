import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import Mastery, User
from app.schemas.interview import (
    InterviewDetail,
    InterviewOut,
    QuestionBankItem,
    QuestionOut,
    QuestionUpdate,
)
from app.services import interview as service
from app.storage import LocalStorage, get_storage
from app.tasks import TaskQueue, get_task_queue

router = APIRouter(tags=["interviews"])

APP_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="投递记录不存在")
NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="复盘记录不存在")


@router.post(
    "/applications/{app_id}/interviews",
    response_model=InterviewOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_interview(
    app_id: uuid.UUID,
    # 默认空字符串：FastAPI 会把空的表单字段当成“缺失”并返回英文报错，这里交给业务层给出中文提示
    round: str = Form(default="", description="面试轮次，例如“一面”"),
    held_on: date | None = Form(default=None),
    text: str | None = Form(default=None, description="文字回忆（和 audio 二选一）"),
    audio: UploadFile | None = File(default=None, description="口述回忆的录音（和 text 二选一）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
    queue: TaskQueue = Depends(get_task_queue),
):
    """新建一次复盘。立即返回（状态为 pending），后台 Worker 处理完成后状态变为 done。
    文件上传要用 multipart/form-data，所以这里用表单字段而不是 JSON。"""
    upload = None
    if audio is not None and audio.filename:
        data = await audio.read(service.MAX_AUDIO_BYTES + 1)
        upload = service.AudioUpload(filename=audio.filename, data=data)
    try:
        interview = await service.create_interview(
            db, storage, queue, user, app_id, round=round, held_on=held_on, text=text, audio=upload
        )
    except service.NotFound:
        raise APP_NOT_FOUND from None
    except service.InvalidInput as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from None
    return InterviewOut.model_validate(interview)


@router.get("/applications/{app_id}/interviews", response_model=list[InterviewOut])
async def list_application_interviews(
    app_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    try:
        return await service.list_interviews(db, user, app_id)
    except service.NotFound:
        raise APP_NOT_FOUND from None


@router.get("/interviews", response_model=list[InterviewOut])
async def list_all_interviews(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await service.list_interviews(db, user)


@router.get("/interviews/{interview_id}", response_model=InterviewDetail)
async def get_interview(
    interview_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.get_interview(db, user, interview_id)
    except service.NotFound:
        raise NOT_FOUND from None


@router.post("/interviews/{interview_id}/retry", response_model=InterviewOut)
async def retry_interview(
    interview_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    queue: TaskQueue = Depends(get_task_queue),
):
    try:
        interview = await service.retry_interview(db, queue, user, interview_id)
    except service.NotFound:
        raise NOT_FOUND from None
    except service.CannotRetry:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="这条复盘正在处理中或已完成，无需重试"
        ) from None
    return InterviewOut.model_validate(interview)


@router.delete("/interviews/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(
    interview_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    try:
        await service.delete_interview(db, storage, user, interview_id)
    except service.NotFound:
        raise NOT_FOUND from None


@router.get("/questions", response_model=list[QuestionBankItem])
async def list_questions(
    company: str | None = None,
    tag: str | None = None,
    mastery: Mastery | None = None,
    q: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_questions(db, user, company=company, tag=tag, mastery=mastery, q=q)


@router.patch("/questions/{question_id}", response_model=QuestionOut)
async def update_question(
    question_id: uuid.UUID,
    data: QuestionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await service.update_question(db, user, question_id, data.mastery)
    except service.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="题目不存在") from None

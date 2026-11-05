"""面试复盘与题库：请求侧的业务逻辑（创建、查询、重试、删除）。

真正的处理流程（转写、分析）在 interview_pipeline.py，由后台 Worker 执行。
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import PurePath

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, Interview, InterviewStatus, Mastery, Question, User
from app.repositories import applications as app_repo
from app.schemas.interview import (
    InterviewDetail,
    InterviewOut,
    QuestionBankItem,
    QuestionOut,
)
from app.storage import LocalStorage
from app.tasks import QueueUnavailable, TaskQueue

MIN_TEXT_CHARS = 30
MAX_TEXT_CHARS = 30000
MAX_AUDIO_BYTES = 100 * 1024 * 1024
AUDIO_SUFFIXES = {".webm", ".ogg", ".opus", ".mp3", ".wav", ".m4a", ".aac", ".amr", ".flac", ".mp4"}
# 处理中状态超过这个时间还没变化，视为 Worker 中途挂掉了，允许用户手动重试
STUCK_AFTER = timedelta(minutes=15)
IN_PROGRESS = (InterviewStatus.PENDING, InterviewStatus.TRANSCRIBING, InterviewStatus.ANALYZING)


class NotFound(Exception):
    pass


class InvalidInput(Exception):
    """输入不合法。message 可以直接展示给用户。"""


class CannotRetry(Exception):
    pass


@dataclass
class AudioUpload:
    filename: str
    data: bytes


# ---------- 创建与处理 ----------


async def create_interview(
    db: AsyncSession,
    storage: LocalStorage,
    queue: TaskQueue,
    user: User,
    app_id: uuid.UUID,
    *,
    round: str,
    held_on: date | None,
    text: str | None,
    audio: AudioUpload | None,
) -> Interview:
    if await app_repo.get_for_user(db, user.id, app_id) is None:
        raise NotFound
    round = round.strip()
    if not round or len(round) > 32:
        raise InvalidInput("请填写面试轮次（不超过 32 个字）")
    text = (text or "").strip() or None
    if (text is None) == (audio is None):
        raise InvalidInput("请输入文字回忆，或上传一段录音（二选一）")

    interview = Interview(
        user_id=user.id, application_id=app_id, round=round, held_on=held_on,
        input_type="text" if text else "audio",
    )  # fmt: skip
    if text:
        if len(text) < MIN_TEXT_CHARS:
            raise InvalidInput(f"回忆内容太短，至少写 {MIN_TEXT_CHARS} 个字")
        interview.raw_text = text[:MAX_TEXT_CHARS]
    else:
        suffix = PurePath(audio.filename).suffix.lower()
        if suffix not in AUDIO_SUFFIXES:
            raise InvalidInput("不支持这种文件格式，请上传常见的录音文件（如 m4a、mp3、wav、webm）")
        if len(audio.data) > MAX_AUDIO_BYTES:
            raise InvalidInput("录音文件不能超过 100 MB")
        if not audio.data:
            raise InvalidInput("录音文件是空的")
        interview.audio_path = storage.save(user.id, audio.data, suffix)
        interview.audio_filename = audio.filename[:255]

    db.add(interview)
    await db.commit()
    await db.refresh(interview)
    await _enqueue(db, queue, interview)
    return interview


async def _enqueue(db: AsyncSession, queue: TaskQueue, interview: Interview) -> None:
    try:
        await queue.enqueue_interview(interview.id)
    except QueueUnavailable:
        # 数据已经保存了，只是没能排进队列：标记失败并说明原因，等后台服务恢复后点“重试”即可
        interview.status = InterviewStatus.FAILED
        interview.error = "后台任务服务不可用（Redis 未启动），请稍后点击重试"
        await db.commit()


async def retry_interview(
    db: AsyncSession, queue: TaskQueue, user: User, interview_id: uuid.UUID
) -> Interview:
    interview = await _require(db, user, interview_id)
    stuck = (
        interview.status in IN_PROGRESS and datetime.now(UTC) - interview.updated_at > STUCK_AFTER
    )
    if interview.status != InterviewStatus.FAILED and not stuck:
        raise CannotRetry
    interview.status = InterviewStatus.PENDING
    interview.error = None
    await db.commit()
    await _enqueue(db, queue, interview)
    await db.refresh(interview)
    return interview


# ---------- 查询 ----------


async def _require(db: AsyncSession, user: User, interview_id: uuid.UUID) -> Interview:
    stmt = select(Interview).where(Interview.id == interview_id, Interview.user_id == user.id)
    interview = (await db.execute(stmt)).scalar_one_or_none()
    if interview is None:
        raise NotFound
    return interview


async def _question_counts(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    stmt = (
        select(Question.interview_id, func.count())
        .where(Question.interview_id.in_(ids))
        .group_by(Question.interview_id)
    )
    return dict((await db.execute(stmt)).all())


async def list_interviews(
    db: AsyncSession, user: User, app_id: uuid.UUID | None = None
) -> list[InterviewOut]:
    stmt = select(Interview).where(Interview.user_id == user.id)
    if app_id is not None:
        if await app_repo.get_for_user(db, user.id, app_id) is None:
            raise NotFound
        stmt = stmt.where(Interview.application_id == app_id)
    interviews = list((await db.execute(stmt.order_by(Interview.created_at.desc()))).scalars())
    counts = await _question_counts(db, [i.id for i in interviews])
    return [
        InterviewOut.model_validate(i).model_copy(update={"question_count": counts.get(i.id, 0)})
        for i in interviews
    ]


async def get_interview(db: AsyncSession, user: User, interview_id: uuid.UUID) -> InterviewDetail:
    interview = await _require(db, user, interview_id)
    app = await db.get(Application, interview.application_id)
    questions = list(
        (
            await db.execute(
                select(Question)
                .where(Question.interview_id == interview.id)
                .order_by(Question.position)
            )
        ).scalars()
    )
    return InterviewDetail(
        **InterviewOut.model_validate(interview).model_dump(exclude={"question_count"}),
        question_count=len(questions),
        company=app.company,
        role=app.role,
        raw_text=interview.raw_text,
        transcript=interview.transcript,
        summary=interview.summary,
        model=interview.model,
        questions=[QuestionOut.model_validate(q) for q in questions],
    )


async def delete_interview(
    db: AsyncSession, storage: LocalStorage, user: User, interview_id: uuid.UUID
) -> None:
    interview = await _require(db, user, interview_id)
    audio_path = interview.audio_path
    await db.delete(interview)  # 题目和薄弱点通过外键级联删除
    await db.commit()
    if audio_path:
        storage.delete(audio_path)  # 数据库删除成功后再删文件


# ---------- 题库 ----------


async def list_questions(
    db: AsyncSession,
    user: User,
    *,
    company: str | None = None,
    tag: str | None = None,
    mastery: Mastery | None = None,
    q: str | None = None,
) -> list[QuestionBankItem]:
    stmt = (
        select(Question, Application.company, Application.role, Interview.round)
        .join(Application, Question.application_id == Application.id)
        .join(Interview, Question.interview_id == Interview.id)
        .where(Question.user_id == user.id)
    )
    if company:
        stmt = stmt.where(Application.company == company)
    if mastery:
        stmt = stmt.where(Question.mastery == mastery)
    if tag:
        stmt = stmt.where(Question.tags.contains([tag]))  # JSONB 包含查询：tags @> '["缓存"]'
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(Question.question.ilike(pattern), Question.improved_answer.ilike(pattern))
        )
    # 没掌握的、分数低的排前面：最需要复习的题最先看到
    stmt = stmt.order_by(
        Question.mastery == Mastery.MASTERED, Question.score, Question.created_at.desc()
    )
    rows = (await db.execute(stmt)).all()
    return [
        QuestionBankItem(
            **QuestionOut.model_validate(question).model_dump(),
            company=company_,
            role=role,
            round=round_,
        )
        for question, company_, role, round_ in rows
    ]


async def update_question(
    db: AsyncSession, user: User, question_id: uuid.UUID, mastery: Mastery
) -> QuestionOut:
    stmt = select(Question).where(Question.id == question_id, Question.user_id == user.id)
    question = (await db.execute(stmt)).scalar_one_or_none()
    if question is None:
        raise NotFound
    question.mastery = mastery
    await db.commit()
    await db.refresh(question)
    return QuestionOut.model_validate(question)

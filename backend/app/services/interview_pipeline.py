"""面试复盘的后台处理流程（在 Worker 进程里运行）。

状态机：
    pending ──语音──> transcribing ──> analyzing ──> done
       └──────文字──────────────────────┘
    任何一步出错 → failed（记录原因，用户可以点“重试”）

为什么放到后台：转写 + 分析加起来要 30 秒到几分钟。如果在 HTTP 请求里同步处理，
用户要一直等着，关掉页面就前功尽弃，服务重启也会丢任务。放进任务队列后，请求立刻返回，
前端轮询状态；Worker 挂了重启后，用户也能点“重试”继续。
"""

import logging
import uuid
from collections.abc import Callable

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.asr import TranscribeError, Transcriber
from app.llm import LLMClient, LLMError
from app.llm.logging import logged_structured
from app.models import Application, Interview, InterviewStatus, Question, User, WeakPoint
from app.prompts import interview as interview_prompt
from app.schemas.interview import InterviewAnalysis
from app.storage import LocalStorage

log = logging.getLogger(__name__)

MAX_RECALL_CHARS = 30000


async def _set_status(db: AsyncSession, interview: Interview, status: InterviewStatus) -> None:
    interview.status = status
    await db.commit()  # 每一步都立刻提交：前端轮询时才能看到实时进度


async def process_interview(
    session_factory: async_sessionmaker[AsyncSession],
    llm_factory: Callable[[], LLMClient],
    transcriber_factory: Callable[[], Transcriber],
    storage: LocalStorage,
    interview_id: uuid.UUID,
) -> None:
    async with session_factory() as db:
        interview = await db.get(Interview, interview_id)
        if interview is None or interview.status == InterviewStatus.DONE:
            return  # 已被删除，或者重复投递的任务：直接跳过（保证幂等）
        app = await db.get(Application, interview.application_id)
        user = await db.get(User, interview.user_id)
        if app is None or user is None:
            return

        try:
            # ① 语音转写（只有语音输入才需要；重试时如果已经转写过就跳过，不重复花钱）
            if interview.input_type == "audio" and not interview.transcript:
                await _set_status(db, interview, InterviewStatus.TRANSCRIBING)
                result = await transcriber_factory().transcribe(storage.path(interview.audio_path))
                interview.transcript = result.text
                interview.audio_seconds = result.seconds
                await db.commit()

            # ② 大模型分析
            await _set_status(db, interview, InterviewStatus.ANALYZING)
            recall = (interview.recall_text or "").strip()[:MAX_RECALL_CHARS]
            analysis = await logged_structured(
                db,
                llm_factory(),
                user=user,
                feature="interview_review",
                system=interview_prompt.SYSTEM,
                prompt=interview_prompt.build_prompt(app, interview, recall),
                schema=InterviewAnalysis,
                effort="medium",
            )

            # ③ 写入结果。重试时先清掉上一次的结果，避免题库里出现重复的题
            await _save_analysis(db, interview, analysis.data, analysis.model)
        except (TranscribeError, LLMError) as exc:
            await _fail(db, interview_id, str(exc))
        except Exception:
            log.exception("处理面试复盘 %s 时出错", interview_id)
            await _fail(db, interview_id, "处理时发生未知错误，请稍后重试")


async def _save_analysis(
    db: AsyncSession, interview: Interview, data: InterviewAnalysis, model: str
) -> None:
    await db.execute(delete(Question).where(Question.interview_id == interview.id))
    await db.execute(delete(WeakPoint).where(WeakPoint.interview_id == interview.id))
    for i, q in enumerate(data.questions):
        db.add(
            Question(
                user_id=interview.user_id,
                interview_id=interview.id,
                application_id=interview.application_id,
                position=i,
                question=q.question,
                my_answer=q.my_answer,
                score=q.score,
                feedback=q.feedback,
                improved_answer=q.improved_answer,
                tags=[t.strip() for t in q.tags if t.strip()][:3],
            )
        )
    for w in data.weak_points:
        db.add(
            WeakPoint(
                user_id=interview.user_id,
                interview_id=interview.id,
                application_id=interview.application_id,
                topic=w.topic[:100],
                detail=w.detail,
            )
        )
    interview.summary = data.model_dump(mode="json", exclude={"questions"})
    interview.model = model
    interview.error = None
    interview.status = InterviewStatus.DONE
    await db.commit()


async def _fail(db: AsyncSession, interview_id: uuid.UUID, message: str) -> None:
    await db.rollback()  # 丢掉写了一半的结果
    interview = await db.get(Interview, interview_id)
    if interview is not None:
        interview.status = InterviewStatus.FAILED
        interview.error = message
        await db.commit()

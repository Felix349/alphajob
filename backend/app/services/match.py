"""岗位匹配分析（流式）与备考清单。"""

import json
import re
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm import LLMClient, LLMError, StreamDone, StreamReset, TextDelta
from app.llm.logging import logged_stream_structured
from app.models import Application, MatchReport, PrepItem, Resume, User
from app.models.resume import ResumeLanguage
from app.prompts import match as match_prompt
from app.repositories import applications as app_repo
from app.schemas.match import (
    MatchAnalysis,
    MatchReportOut,
    PrepItemCreate,
    PrepItemOut,
    PrepItemUpdate,
)
from app.services import resume as resume_service

# 只是防截断的“保险”：输出长度主要靠 schemas/match.py 里各字段的字数上限控制。
# DeepSeek 的思考也计入输出 token；评估集里真实简历的输出中位数约 1.2 万（加字数上限之前）
MATCH_MAX_TOKENS = 32768


class NotFound(Exception):
    pass


class MatchPrecondition(Exception):
    """开始分析前的检查没通过（没有简历、没有 JD）。message 可以直接展示给用户。"""


# ---------- 匹配分析 ----------


_LANGUAGE_NAMES = {"zh": "中文", "en": "英文"}
_CJK_CHAR = re.compile(r"[一-鿿]")
_LATIN_CHAR = re.compile(r"[A-Za-z]")


def _strings_in(value) -> list[str]:
    """取出 jd_parsed 里所有的字符串值（不要键名：键名是英文，会干扰语言判断）。"""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings_in(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings_in(v)]
    return []


def jd_language(app: Application) -> ResumeLanguage:
    """粗略判断 JD 是中文还是英文：汉字占字母的比例很低，就当作英文 JD。

    中文 JD 里常夹着 Python、Kubernetes 之类的英文词，所以不能“出现英文就算英文”，
    而是看汉字占多少：一个汉字信息量大约相当于几个英文字母，5% 是个足够宽松的分界线。
    """
    text = app.jd_text or " ".join(_strings_in(app.jd_parsed or {}))
    cjk = len(_CJK_CHAR.findall(text))
    latin = len(_LATIN_CHAR.findall(text))
    if latin == 0:
        return "zh"
    return "en" if cjk / (cjk + latin) < 0.05 else "zh"


def _pick_resume(
    resumes: dict[str, Resume], app: Application, requested: ResumeLanguage | None
) -> Resume:
    """选出这次分析用的简历。

    - 用户指定了语言：必须有那份简历，否则报错（不悄悄换成另一份，免得用户以为用的是英文简历）
    - 没指定：按 JD 的语言选；对应语言的简历没有，就退回另一份
    """
    if not resumes:
        raise MatchPrecondition("还没有上传简历，请先到“我的简历”页面上传")
    if requested is not None:
        if requested not in resumes:
            name = _LANGUAGE_NAMES[requested]
            raise MatchPrecondition(f"还没有上传{name}简历，请先到“我的简历”页面上传，或换一份简历")
        return resumes[requested]
    preferred = jd_language(app)
    return resumes.get(preferred) or next(iter(resumes.values()))


async def check_ready(
    db: AsyncSession, user: User, app_id: uuid.UUID, resume_language: ResumeLanguage | None
) -> None:
    """在开始流式响应之前检查条件，这样不满足时可以返回普通的 400，而不是开了流再报错。"""
    app = await app_repo.get_for_user(db, user.id, app_id)
    if app is None:
        raise NotFound
    if not (app.jd_text or app.jd_parsed):
        raise MatchPrecondition("这条投递还没有岗位描述（JD），请先在详情页补充")
    _pick_resume(await resume_service.list_resumes(db, user), app, resume_language)


def _to_out(report: MatchReport, resume: Resume | None) -> MatchReportOut:
    """resume：和这份分析同一语言的简历（可能已被删除），用来判断分析是否过时。"""
    return MatchReportOut(
        id=report.id,
        application_id=report.application_id,
        report=MatchAnalysis.from_stored(report.report),
        model=report.model,
        created_at=report.created_at,
        resume_updated_at=report.resume_updated_at,
        resume_language=report.resume_language,
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
    resume_language: ResumeLanguage | None = None,
) -> AsyncIterator[dict]:
    """生成 SSE 事件：delta（JSON 片段）、reset（结果作废、重新生成）、done（最终结果）、error。"""
    async with session_factory() as db:
        app = await app_repo.get_for_user(db, user.id, app_id)
        if app is None:  # 理论上 check_ready 已经挡住了，这里防并发删除
            yield _sse("error", {"detail": "投递记录已不存在"})
            return
        try:
            resume = _pick_resume(await resume_service.list_resumes(db, user), app, resume_language)
        except MatchPrecondition as exc:
            yield _sse("error", {"detail": str(exc)})
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
                # 输出很长（逐条对照 + 备考清单 + 简历修改建议），默认的 8192 很容易被截断
                max_tokens=MATCH_MAX_TOKENS,
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
        resume_language=resume.language,
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
    resume = await resume_service.get_resume(db, user, report.resume_language)
    return _to_out(report, resume)


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

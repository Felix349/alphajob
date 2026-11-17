"""岗位快速筛选：读取岗位 → 硬条件过滤 → 粗筛 → 补充 JD → 精排 → 推荐清单 → 加入投递记录。

两级筛选：列表页上的岗位动辄几百个，而精排要读完整 JD、逐个调用大模型，又慢又贵。
所以先用便宜的方法（只看岗位名的批量判断）把范围缩小到 N 个，只对这 N 个做精排。
设计见 docs/plans/岗位快速筛选.md。
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urljoin

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm import LLMClient, LLMError
from app.llm.logging import logged_structured
from app.models import Application, Resume, ScreeningBatch, ScreeningJob, User
from app.models.resume import ResumeLanguage
from app.prompts import screening as prompts
from app.schemas.application import ApplicationCreate
from app.schemas.screening import (
    MAX_JOBS_PER_BATCH,
    AddJobsResult,
    BatchCreate,
    BatchDetail,
    BatchOut,
    ExtractedJobs,
    JobIn,
    JobOut,
    QuickMatch,
    ScreeningFilters,
    ScreenResult,
    Triage,
)
from app.services import applications as app_service
from app.services import jd as jd_service
from app.services import resume as resume_service
from app.services.match import MatchPrecondition, pick_resume

# 每次粗筛调用最多放多少个岗位：岗位名很短，80 个大约 2–3 千 tokens，模型也不容易漏判
TRIAGE_CHUNK = 80
# 抽取岗位列表时，每次发给模型的页面文本上限（按行切分）
EXTRACT_CHUNK_CHARS = 12000
# 精排的并发数：每个岗位一次调用，约 10–15 秒
RANK_CONCURRENCY = 4
# 模型漏判的岗位先当作 2 分保留：粗筛宁可多留，漏掉的岗位后面再准也找不回来
MISSING_TRIAGE_SCORE = 2


class NotFound(Exception):
    pass


class Precondition(Exception):
    """开始某一步之前的检查没通过。message 可以直接展示给用户。"""


# ---------- 批次 ----------


async def _require_batch(db: AsyncSession, user: User, batch_id: uuid.UUID) -> ScreeningBatch:
    stmt = select(ScreeningBatch).where(
        ScreeningBatch.id == batch_id, ScreeningBatch.user_id == user.id
    )
    batch = (await db.execute(stmt)).scalar_one_or_none()
    if batch is None:
        raise NotFound
    return batch


async def _jobs_of(db: AsyncSession, batch_id: uuid.UUID) -> list[ScreeningJob]:
    stmt = (
        select(ScreeningJob)
        .where(ScreeningJob.batch_id == batch_id)
        .order_by(ScreeningJob.position)
    )
    return list((await db.execute(stmt)).scalars())


def _job_out(job: ScreeningJob) -> JobOut:
    return JobOut.model_validate(
        {**_fields(job, JobOut, skip={"has_jd"}), "has_jd": bool(job.jd_text)}
    )


def _fields(obj, schema, skip: set[str] = frozenset()) -> dict:
    """只读取接口需要的字段。不能读全部列：updated_at 由数据库在更新时生成，提交后会过期，
    在异步代码里访问过期属性会触发一次同步查询而报错（MissingGreenlet）。"""
    return {k: getattr(obj, k) for k in schema.model_fields if k not in skip and hasattr(obj, k)}


def _sort_key(job: ScreeningJob):
    """推荐清单的顺序：精排分数高的在前 → 进入精排但还没结果的 → 按粗筛分数 → 被过滤掉的。"""
    if job.score is not None:
        return (0, -job.score, job.position)
    if job.shortlisted:
        return (1, -(job.coarse_score or 0), job.position)
    if job.filtered_reason is None:
        return (2, -(job.coarse_score if job.coarse_score is not None else -1), job.position)
    return (3, job.position)


def _batch_out(batch: ScreeningBatch, jobs: list[ScreeningJob]) -> BatchOut:
    return BatchOut(
        **_fields(batch, BatchOut, skip={"total_jobs", "shortlisted_jobs", "ranked_jobs"}),
        total_jobs=len(jobs),
        shortlisted_jobs=sum(j.shortlisted for j in jobs),
        ranked_jobs=sum(j.score is not None for j in jobs),
    )


def _detail(batch: ScreeningBatch, jobs: list[ScreeningJob]) -> BatchDetail:
    return BatchDetail(
        **_batch_out(batch, jobs).model_dump(),
        jobs=[_job_out(j) for j in sorted(jobs, key=_sort_key)],
    )


async def create_batch(db: AsyncSession, user: User, data: BatchCreate) -> BatchDetail:
    batch = ScreeningBatch(
        user_id=user.id,
        company=data.company.strip(),
        source_url=data.source_url,
        filters=data.filters.model_dump(),
        resume_language=data.resume_language,
        top_n=data.top_n,
        status="collecting",
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return _detail(batch, [])


async def list_batches(db: AsyncSession, user: User) -> list[BatchOut]:
    stmt = (
        select(ScreeningBatch)
        .where(ScreeningBatch.user_id == user.id)
        .order_by(ScreeningBatch.created_at.desc())
    )
    batches = list((await db.execute(stmt)).scalars())
    jobs = (
        await db.execute(
            select(ScreeningJob).where(ScreeningJob.batch_id.in_([b.id for b in batches]))
        )
    ).scalars()
    by_batch: dict[uuid.UUID, list[ScreeningJob]] = {}
    for j in jobs:
        by_batch.setdefault(j.batch_id, []).append(j)
    return [_batch_out(b, by_batch.get(b.id, [])) for b in batches]


async def get_batch(db: AsyncSession, user: User, batch_id: uuid.UUID) -> BatchDetail:
    batch = await _require_batch(db, user, batch_id)
    return _detail(batch, await _jobs_of(db, batch.id))


async def delete_batch(db: AsyncSession, user: User, batch_id: uuid.UUID) -> None:
    batch = await _require_batch(db, user, batch_id)
    await db.delete(batch)
    await db.commit()


# ---------- 读取岗位 ----------


def _dedupe_key(url: str | None, title: str, location: str | None) -> str:
    # 有链接按链接去重；没有链接（粘贴的文本里常见）按“岗位名 + 地点”去重
    return f"url:{url}" if url else f"title:{title.strip().lower()}|{(location or '').strip()}"


async def add_jobs(
    db: AsyncSession, user: User, batch_id: uuid.UUID, jobs: list[JobIn]
) -> AddJobsResult:
    """追加岗位。翻页后再次读取会和已有的岗位去重，不会重复。"""
    batch = await _require_batch(db, user, batch_id)
    existing = await _jobs_of(db, batch.id)
    seen = {_dedupe_key(j.url, j.title, j.location) for j in existing}
    position = max((j.position for j in existing), default=-1) + 1
    added = duplicated = 0
    for job in jobs:
        url = urljoin(batch.source_url, job.url) if job.url and batch.source_url else job.url
        key = _dedupe_key(url, job.title, job.location)
        if key in seen:
            duplicated += 1
            continue
        if len(existing) + added >= MAX_JOBS_PER_BATCH:
            raise Precondition(f"一个批次最多 {MAX_JOBS_PER_BATCH} 个岗位")
        seen.add(key)
        db.add(
            ScreeningJob(
                batch_id=batch.id,
                user_id=user.id,
                position=position,
                **{**job.model_dump(), "url": url},
            )
        )
        position += 1
        added += 1
    if added:
        batch.status = "collecting"  # 有新岗位，需要重新粗筛
    await db.commit()
    return AddJobsResult(added=added, duplicated=duplicated, total=len(existing) + added)


def _chunks_by_lines(text: str, limit: int) -> list[str]:
    chunks, current = [], ""
    for line in text.splitlines():
        if current and len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = ""
        current += line[:limit] + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


async def extract_jobs(
    db: AsyncSession, llm: LLMClient, user: User, batch_id: uuid.UUID, text: str
) -> AddJobsResult:
    """从粘贴的页面文本里抽取岗位列表（没有插件时的输入方式，也用于插件不认识的页面）。"""
    await _require_batch(db, user, batch_id)
    extracted: list[JobIn] = []
    # 逐段调用：调用日志写在同一个数据库会话里，不能并发
    for chunk in _chunks_by_lines(text, EXTRACT_CHUNK_CHARS):
        result = await logged_structured(
            db,
            llm,
            user=user,
            feature="screening_extract",
            system=prompts.EXTRACT_SYSTEM,
            prompt=prompts.build_extract_prompt(chunk),
            schema=ExtractedJobs,
            effort="low",
        )
        for job in result.data.jobs:
            if job.title.strip():
                extracted.append(
                    JobIn(
                        title=job.title.strip()[:256],
                        location=(job.location or None) and job.location[:256],
                        category=(job.category or None) and job.category[:128],
                        job_type=job.job_type,
                        url=(job.url or None) and job.url[:1024],
                        snippet=(job.snippet or None) and job.snippet[:2000],
                    )
                )
    if not extracted:
        raise Precondition("没有从文本里找到岗位，请确认复制的是招聘列表页")
    return await add_jobs(db, user, batch_id, extracted)


# ---------- 硬条件过滤 + 粗筛 ----------


def filter_reason(job: ScreeningJob, filters: ScreeningFilters) -> str | None:
    """不满足硬条件的原因；满足则返回 None。字段缺失（如没写地点）时不过滤，交给后面判断。"""
    title = job.title.lower()
    for word in filters.exclude_keywords:
        if word.strip() and word.strip().lower() in title:
            return f"岗位名包含“{word.strip()}”"
    if filters.job_types and job.job_type and job.job_type not in filters.job_types:
        return f"招聘类型为{job.job_type}"
    if filters.cities and job.location:
        if not any(c.strip() and c.strip() in job.location for c in filters.cities):
            return f"地点为{job.location}"
    return None


async def _resumes(db: AsyncSession, user: User) -> dict[str, Resume]:
    resumes = await resume_service.list_resumes(db, user)
    if not resumes:
        raise Precondition("还没有上传简历，请先到“我的简历”页面上传")
    return resumes


def _resume_for(resumes: dict[str, Resume], text: str, requested: ResumeLanguage | None) -> Resume:
    """和匹配分析相同的选择规则：指定了就用指定的；否则按岗位文本的语言选。"""
    try:
        return pick_resume(resumes, Application(jd_text=text), requested)
    except MatchPrecondition as exc:
        raise Precondition(str(exc)) from None


async def screen(db: AsyncSession, llm: LLMClient, user: User, batch_id: uuid.UUID) -> ScreenResult:
    batch = await _require_batch(db, user, batch_id)
    jobs = await _jobs_of(db, batch.id)
    if not jobs:
        raise Precondition("这个批次还没有岗位，请先读取招聘列表")
    filters = ScreeningFilters.model_validate(batch.filters)
    titles = "\n".join(j.title for j in jobs)
    resume = _resume_for(await _resumes(db, user), titles, batch.resume_language)

    # 重新粗筛时清空上一轮的结果（精排结果保留：JD 没变，结果仍然有效）
    candidates = []
    for job in jobs:
        job.filtered_reason = filter_reason(job, filters)
        job.coarse_score = job.coarse_reason = None
        job.shortlisted = False
        if job.filtered_reason is None:
            candidates.append(job)

    for start in range(0, len(candidates), TRIAGE_CHUNK):
        chunk = candidates[start : start + TRIAGE_CHUNK]
        result = await logged_structured(
            db,
            llm,
            user=user,
            feature="screening_triage",
            system=prompts.TRIAGE_SYSTEM,
            prompt=prompts.build_triage_prompt(resume.content_md, chunk),
            schema=Triage,
            effort="low",
        )
        judged = {item.index: item for item in result.data.items if 0 <= item.index < len(chunk)}
        for i, job in enumerate(chunk):
            if (item := judged.get(i)) is not None:
                job.coarse_score, job.coarse_reason = item.score, item.reason[:256]
            else:
                job.coarse_score, job.coarse_reason = (
                    MISSING_TRIAGE_SCORE,
                    "模型未给出判断，暂时保留",
                )

    ranked = sorted(
        (j for j in candidates if (j.coarse_score or 0) >= 1),
        key=lambda j: (-(j.coarse_score or 0), j.position),
    )
    for job in ranked[: batch.top_n]:
        job.shortlisted = True
    batch.status = "screened"
    await db.commit()

    detail = _detail(batch, jobs)
    return ScreenResult(
        batch=detail, needs_jd=[j for j in detail.jobs if j.shortlisted and not j.has_jd]
    )


# ---------- 补充 JD ----------


async def _require_job(db: AsyncSession, user: User, job_id: uuid.UUID) -> ScreeningJob:
    stmt = select(ScreeningJob).where(ScreeningJob.id == job_id, ScreeningJob.user_id == user.id)
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise NotFound
    return job


async def set_jd(db: AsyncSession, user: User, job_id: uuid.UUID, jd_text: str) -> JobOut:
    job = await _require_job(db, user, job_id)
    if job.jd_text != jd_text.strip():
        job.jd_text = jd_text.strip()
        # JD 变了，之前的精排结果作废
        job.score = job.rank_result = job.rank_error = None
    await db.commit()
    return _job_out(job)


# ---------- 精排 ----------


async def check_rank_ready(db: AsyncSession, user: User, batch_id: uuid.UUID) -> None:
    """开流之前检查，不满足时返回普通的 400（和匹配分析一样，先检查、再开流）。"""
    batch = await _require_batch(db, user, batch_id)
    jobs = await _jobs_of(db, batch.id)
    if not any(j.shortlisted for j in jobs):
        raise Precondition("还没有粗筛，或粗筛没有留下岗位")
    if not any(j.shortlisted and j.jd_text for j in jobs):
        raise Precondition("进入精排的岗位都还没有 JD，请先补充岗位详情")
    await _resumes(db, user)


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False, default=str)}


async def _rank_one(
    session_factory: async_sessionmaker[AsyncSession],
    llm: LLMClient,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    company: str,
    requested: ResumeLanguage | None,
) -> JobOut:
    # 每个岗位用自己的数据库会话：几个岗位并发调用模型，一个会话不能同时被多个任务使用
    async with session_factory() as db:
        user = await db.get(User, user_id)
        job = await db.get(ScreeningJob, job_id)
        try:
            resume = _resume_for(await _resumes(db, user), job.jd_text or "", requested)
            result = await logged_structured(
                db,
                llm,
                user=user,
                feature="screening_rank",
                system=prompts.RANK_SYSTEM,
                prompt=prompts.build_rank_prompt(company, job, resume.content_md),
                schema=QuickMatch,
                effort="low",  # 排序要稳定：温度 0，同样的输入尽量给出同样的判断
            )
        except (LLMError, Precondition) as exc:
            # 一个岗位失败不影响其他岗位：记下原因，前端显示“分析失败”并可以重试
            job.rank_error = str(exc)[:256]
            await db.commit()
            return _job_out(job)
        match: QuickMatch = result.data
        job.rank_result = {**match.model_dump(mode="json"), "resume_language": resume.language}
        job.score = match.score
        job.rank_error = None
        await db.commit()
        return _job_out(job)


async def rank_batch(
    session_factory: async_sessionmaker[AsyncSession],
    llm: LLMClient,
    user: User,
    batch_id: uuid.UUID,
) -> AsyncIterator[dict]:
    """逐个精排进入名单、且有 JD 的岗位，每完成一个就推送一条 job 事件，最后推送 done。"""
    async with session_factory() as db:
        batch = await _require_batch(db, user, batch_id)
        targets = [j.id for j in await _jobs_of(db, batch.id) if j.shortlisted and j.jd_text]
        company, requested = batch.company, batch.resume_language
    yield _sse("start", {"total": len(targets)})

    sem = asyncio.Semaphore(RANK_CONCURRENCY)

    async def run(job_id: uuid.UUID) -> JobOut:
        async with sem:
            return await _rank_one(session_factory, llm, user.id, job_id, company, requested)

    tasks = [asyncio.create_task(run(job_id)) for job_id in targets]
    try:
        for done_count, task in enumerate(asyncio.as_completed(tasks), start=1):
            job = await task
            yield _sse("job", {"done": done_count, "total": len(targets), "job": job.model_dump()})
    finally:
        for t in tasks:  # 用户中途关闭页面：取消还没开始的调用，不再消耗 token
            t.cancel()

    async with session_factory() as db:
        batch = await _require_batch(db, user, batch_id)
        batch.status = "ranked"
        await db.commit()
        yield _sse("done", (_detail(batch, await _jobs_of(db, batch.id))).model_dump(mode="json"))


# ---------- 加入投递记录 ----------


async def import_job(
    db: AsyncSession, llm: LLMClient | None, user: User, job_id: uuid.UUID
) -> uuid.UUID:
    """把岗位加入投递记录（“想投”阶段）。重复点击不会重复创建。"""
    job = await _require_job(db, user, job_id)
    if job.application_id is not None:
        if await db.get(Application, job.application_id) is not None:
            return job.application_id
    batch = await db.get(ScreeningBatch, job.batch_id)

    parsed = None
    if llm is not None and job.jd_text:
        try:  # 顺便解析 JD；失败不影响加入投递记录，用户之后可以在详情页补
            parsed = await jd_service.parse_jd(db, llm, user, job.jd_text)
        except LLMError:
            parsed = None

    notes = None
    if job.rank_result:
        r = job.rank_result
        notes = f"来自岗位筛选：匹配度 {job.score}。优势：{r.get('strength')}；差距：{r.get('gap')}"
    detail = await app_service.create_application(
        db,
        user,
        ApplicationCreate(
            company=batch.company[:128],
            role=job.title[:128],
            location=job.location[:128] if job.location else None,
            channel="官网",
            job_url=job.url,
            jd_text=(job.jd_text or job.snippet or None) and (job.jd_text or job.snippet)[:20000],
            jd_parsed=parsed,
            notes=notes,
        ),
    )
    job = await _require_job(db, user, job_id)
    job.application_id = detail.id
    await db.commit()
    return detail.id

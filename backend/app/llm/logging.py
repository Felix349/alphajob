"""调用大模型并记录日志：耗时、token 用量、成败，用于成本统计和排查问题。"""

import time
from collections.abc import AsyncIterator

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import Effort, LLMClient, LLMError, StreamDone, StreamEvent, StructuredResult
from app.models import LLMCallLog, User


async def logged_structured[T: BaseModel](
    db: AsyncSession,
    llm: LLMClient,
    *,
    user: User,
    feature: str,
    system: str,
    prompt: str,
    schema: type[T],
    effort: Effort = "medium",
) -> StructuredResult[T]:
    start = time.perf_counter()
    log = LLMCallLog(user_id=user.id, feature=feature, provider=llm.provider, model=llm.model)
    try:
        result = await llm.structured(system=system, user=prompt, schema=schema, effort=effort)
    except LLMError as exc:
        log.success = False
        log.error = str(exc)
        raise
    else:
        log.model = result.model
        log.input_tokens = result.input_tokens
        log.output_tokens = result.output_tokens
        return result
    finally:
        log.latency_ms = int((time.perf_counter() - start) * 1000)
        db.add(log)
        await db.commit()


async def logged_stream_structured[T: BaseModel](
    db: AsyncSession,
    llm: LLMClient,
    *,
    user: User,
    feature: str,
    system: str,
    prompt: str,
    schema: type[T],
    effort: Effort = "medium",
) -> AsyncIterator[StreamEvent]:
    """流式版本：原样转发事件，结束（成功或失败）时写一条日志。

    用户中途关闭页面时，生成器会被取消（GeneratorExit），这种情况不记录日志：
    请求已经中断，此时再访问数据库也不安全。
    """
    start = time.perf_counter()
    log = LLMCallLog(user_id=user.id, feature=feature, provider=llm.provider, model=llm.model)
    try:
        async for event in llm.stream_structured(
            system=system, user=prompt, schema=schema, effort=effort
        ):
            if isinstance(event, StreamDone):
                log.model = event.result.model
                log.input_tokens = event.result.input_tokens
                log.output_tokens = event.result.output_tokens
            yield event
    except LLMError as exc:
        log.success = False
        log.error = str(exc)
        await _save(db, log, start)
        raise
    await _save(db, log, start)


async def _save(db: AsyncSession, log: LLMCallLog, start: float) -> None:
    log.latency_ms = int((time.perf_counter() - start) * 1000)
    db.add(log)
    await db.commit()

"""任务队列：把耗时任务交给后台 Worker（ARQ + Redis）。

业务代码只依赖 TaskQueue 接口；测试时替换成“立即执行”的实现，不需要启动 Redis 和 Worker。
"""

import uuid
from typing import Protocol

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings


class QueueUnavailable(Exception):
    pass


class TaskQueue(Protocol):
    async def enqueue_interview(self, interview_id: uuid.UUID) -> None: ...


class ArqTaskQueue:
    def __init__(self, redis_url: str):
        self._settings = RedisSettings.from_dsn(redis_url)
        self._pool: ArqRedis | None = None

    async def _get_pool(self) -> ArqRedis:
        # 第一次用到时才连接 Redis：没有 Redis 时，其他不需要后台任务的接口照样能用
        if self._pool is None:
            self._pool = await create_pool(self._settings)
        return self._pool

    async def enqueue_interview(self, interview_id: uuid.UUID) -> None:
        try:
            pool = await self._get_pool()
            await pool.enqueue_job("process_interview", str(interview_id))
        except (OSError, ConnectionError) as exc:  # Redis 没启动、连不上
            self._pool = None
            raise QueueUnavailable from exc


_queue: ArqTaskQueue | None = None


def get_task_queue() -> TaskQueue:
    global _queue
    if _queue is None:
        _queue = ArqTaskQueue(get_settings().redis_url)
    return _queue

"""后台 Worker 进程入口。

启动：uv run arq app.worker.WorkerSettings
（和 API 服务是两个独立的进程：API 只负责收请求、把任务放进 Redis；Worker 从 Redis 取任务执行。）
"""

import logging
import signal
import sys
import uuid

from arq import func
from arq.connections import RedisSettings

from app.asr.factory import build_transcriber
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.llm.factory import get_llm_client
from app.services.interview_pipeline import process_interview
from app.storage import get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# Windows 兼容：ARQ 在关闭时会调用 handle_sig(signal.SIGUSR1)，而 Windows 没有 SIGUSR1，
# 导致 Worker 退出时报错（任务本身已经正常完成）。handle_sig 只用这个信号打日志、取消剩余任务，
# 所以映射成 Windows 上存在的 SIGTERM 即可。Linux（以及之后的 Docker 部署）不受影响。
if sys.platform == "win32" and not hasattr(signal, "SIGUSR1"):
    signal.SIGUSR1 = signal.SIGTERM  # type: ignore[attr-defined]


async def process_interview_job(ctx: dict, interview_id: str) -> None:
    await process_interview(
        SessionLocal, get_llm_client, build_transcriber, get_storage(), uuid.UUID(interview_id)
    )


class WorkerSettings:
    functions = [
        # max_tries=1：失败不自动重试。失败原因会写进数据库，由用户决定是否点“重试”，
        # 避免 API Key 失效这类问题被反复重试、白白消耗额度
        func(process_interview_job, name="process_interview", timeout=900, max_tries=1),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4  # 同时处理的任务数
    keep_result = 3600
    # Windows 的事件循环不支持 add_signal_handler，交给 Ctrl+C 默认处理即可
    handle_signals = sys.platform != "win32"

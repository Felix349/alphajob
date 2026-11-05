"""所有表模型在这里汇总导入，Alembic 通过 Base.metadata 发现它们。"""

from app.models.application import Application, Event, EventType, Stage
from app.models.base import Base
from app.models.llm_call_log import LLMCallLog
from app.models.match import MatchReport, PrepCategory, PrepItem
from app.models.resume import Resume
from app.models.user import User

__all__ = [
    "Application",
    "Base",
    "Event",
    "EventType",
    "LLMCallLog",
    "MatchReport",
    "PrepCategory",
    "PrepItem",
    "Resume",
    "Stage",
    "User",
]

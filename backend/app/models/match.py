"""岗位匹配分析与备考清单。"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class PrepCategory(StrEnum):
    KNOWLEDGE = "knowledge"  # 知识点
    PROJECT = "project"  # 项目经历的准备
    QUESTION = "question"  # 刷题 / 练习题
    OTHER = "other"


class MatchReport(IdMixin, TimestampMixin, Base):
    """一次匹配分析的结果。保留历史记录，页面上展示最新的一份。"""

    __tablename__ = "match_reports"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    report: Mapped[dict[str, Any]] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(String(128))
    # 分析时所用简历的更新时间：之后简历再改过，就提示“简历已更新，建议重新分析”
    resume_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PrepItem(IdMixin, TimestampMixin, Base):
    """备考清单的一项。可以来自 AI（匹配分析生成），也可以由用户手动添加。"""

    __tablename__ = "prep_items"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(String(500))
    category: Mapped[PrepCategory] = mapped_column(
        Enum(
            PrepCategory,
            name="prep_category",
            native_enum=False,
            length=16,
            values_callable=lambda x: [m.value for m in x],
        ),
        default=PrepCategory.OTHER,
    )
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1 最优先
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # ai / manual
    position: Mapped[float] = mapped_column(Float, default=0.0)

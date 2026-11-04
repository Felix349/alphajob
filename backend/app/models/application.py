"""投递记录与日程事件。整个产品的核心数据：备考、复盘、Agent 规划都挂在 Application 上。"""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Stage(StrEnum):
    """投递阶段，也就是看板的列。面试轮次（一面/二面）用日程事件记录，不单独占一列。"""

    WISHLIST = "wishlist"  # 待投递
    APPLIED = "applied"  # 已投递
    WRITTEN_TEST = "written_test"  # 笔试
    INTERVIEWING = "interviewing"  # 面试中
    HR = "hr"  # HR 面
    OFFER = "offer"  # Offer
    ENDED = "ended"  # 已结束（未通过 / 放弃）


class EventType(StrEnum):
    WRITTEN_TEST = "written_test"  # 笔试
    INTERVIEW = "interview"  # 面试
    DEADLINE = "deadline"  # 截止日期
    OTHER = "other"


def _enum(e: type[StrEnum], name: str) -> Enum:
    # native_enum=False：存成 varchar + CHECK 约束，以后加枚举值不需要改数据库类型
    return Enum(
        e, name=name, native_enum=False, length=32, values_callable=lambda x: [m.value for m in x]
    )


class Application(IdMixin, TimestampMixin, Base):
    __tablename__ = "applications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    company: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(128))
    channel: Mapped[str | None] = mapped_column(String(64))  # 官网 / 内推 / 牛客 / Boss ...
    job_url: Mapped[str | None] = mapped_column(String(1024))
    jd_text: Mapped[str | None] = mapped_column(Text)
    # 大模型从 JD 中解析出的结构化信息（职责、要求、技术栈等），W3 岗位匹配会用到
    jd_parsed: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    stage: Mapped[Stage] = mapped_column(_enum(Stage, "application_stage"), default=Stage.WISHLIST)
    # 同一列内的排序：用浮点数，拖到两张卡片之间时取中间值，不必重排整列
    position: Mapped[float] = mapped_column(Float, default=0.0)
    applied_at: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    events: Mapped[list["Event"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="Event.start_at",
        lazy="raise",  # 禁止隐式懒加载：异步环境下懒加载会报错，必须显式 selectinload
    )


class Event(IdMixin, TimestampMixin, Base):
    __tablename__ = "events"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    # 冗余存一份 user_id：日历按时间范围查询时不用 join，权限过滤也更直接
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[EventType] = mapped_column(_enum(EventType, "event_type"))
    title: Mapped[str] = mapped_column(String(128))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    link: Mapped[str | None] = mapped_column(String(1024))  # 会议链接 / 笔试链接
    note: Mapped[str | None] = mapped_column(Text)

    application: Mapped[Application] = relationship(back_populates="events", lazy="raise")

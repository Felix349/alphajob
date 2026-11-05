"""面试复盘、个人题库与薄弱点。"""

import uuid
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


def _enum(e: type[StrEnum], name: str) -> Enum:
    return Enum(
        e, name=name, native_enum=False, length=16, values_callable=lambda x: [m.value for m in x]
    )


class InterviewStatus(StrEnum):
    """处理流程的状态机：pending → (transcribing) → analyzing → done，任何一步出错都进入 failed。"""

    PENDING = "pending"  # 已排队，等待 Worker 处理
    TRANSCRIBING = "transcribing"  # 语音转文字中（只有语音输入才有这一步）
    ANALYZING = "analyzing"  # 大模型分析中
    DONE = "done"
    FAILED = "failed"


class Mastery(StrEnum):
    NEW = "new"  # 刚从复盘中提取，还没复习
    REVIEWING = "reviewing"  # 复习中
    MASTERED = "mastered"  # 已掌握


class Interview(IdMixin, TimestampMixin, Base):
    __tablename__ = "interviews"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    round: Mapped[str] = mapped_column(String(32))  # 一面 / 二面 / HR 面……
    held_on: Mapped[date | None] = mapped_column(Date)  # 面试日期
    input_type: Mapped[str] = mapped_column(String(8))  # text / audio
    raw_text: Mapped[str | None] = mapped_column(Text)  # 用户直接输入的回忆
    audio_path: Mapped[str | None] = mapped_column(String(512))  # 存储里的相对路径
    audio_filename: Mapped[str | None] = mapped_column(String(255))
    audio_seconds: Mapped[float | None] = mapped_column(Float)
    transcript: Mapped[str | None] = mapped_column(Text)  # 语音转写结果
    status: Mapped[InterviewStatus] = mapped_column(
        _enum(InterviewStatus, "interview_status"), default=InterviewStatus.PENDING, index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    # 大模型的分析结果（总结、亮点、下一轮建议）；逐题结果另存到 questions 表，便于检索和复习
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(String(128))

    @property
    def recall_text(self) -> str | None:
        """交给大模型分析的文本：语音输入用转写结果，文字输入用原文。"""
        return self.transcript if self.input_type == "audio" else self.raw_text


class Question(IdMixin, TimestampMixin, Base):
    """个人题库里的一道题：真实被问过的问题、你当时的回答、评估与改进版回答。"""

    __tablename__ = "questions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    # 冗余存一份投递 id：题库按公司筛选时不用多 join 一层
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    my_answer: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer)  # 1–5
    feedback: Mapped[str] = mapped_column(Text)
    improved_answer: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    mastery: Mapped[Mastery] = mapped_column(
        _enum(Mastery, "question_mastery"), default=Mastery.NEW
    )
    position: Mapped[int] = mapped_column(Integer, default=0)  # 在本场面试中的顺序


class WeakPoint(IdMixin, TimestampMixin, Base):
    """从复盘中发现的薄弱点。W6 的求职 Agent 会读取未解决的薄弱点来安排复习。"""

    __tablename__ = "weak_points"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), index=True
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    topic: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open / resolved

"""岗位快速筛选：从一家公司的招聘列表里，挑出和简历最匹配的几个岗位。

流程：读取岗位列表 → 硬条件过滤 → 粗筛（几百个 → N 个）→ 补充 JD → 精排 → 推荐清单。
设计见 docs/plans/岗位快速筛选.md。
"""

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class ScreeningBatch(IdMixin, TimestampMixin, Base):
    """一次筛选：通常对应一家公司的一个招聘列表页（翻页读取的内容会追加到同一个批次）。"""

    __tablename__ = "screening_batches"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    company: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(String(1024))
    # 硬条件：{"cities": [...], "job_types": [...], "exclude_keywords": [...]}
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # 用哪份简历：zh / en；None 表示按岗位语言自动选
    resume_language: Mapped[str | None] = mapped_column(String(8))
    # 精排的岗位数（粗筛后保留前 N 个）
    top_n: Mapped[int] = mapped_column(Integer, default=15)
    # collecting（读取中）/ screened（粗筛完成，待补充 JD）/ ranked（精排完成）
    status: Mapped[str] = mapped_column(String(16), default="collecting")


class ScreeningJob(IdMixin, TimestampMixin, Base):
    """批次里的一个岗位。各阶段的结果都记在这一行上，方便回看“为什么被筛掉”。"""

    __tablename__ = "screening_jobs"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("screening_batches.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # 在列表页上的顺序：粗筛分数相同时，按原顺序排
    position: Mapped[int] = mapped_column(Integer, default=0)

    # ---- 列表页上读到的信息 ----
    title: Mapped[str] = mapped_column(String(256))
    location: Mapped[str | None] = mapped_column(String(256))
    category: Mapped[str | None] = mapped_column(String(128))
    job_type: Mapped[str | None] = mapped_column(String(16))  # 校招 / 实习 / 社招
    url: Mapped[str | None] = mapped_column(String(1024))
    snippet: Mapped[str | None] = mapped_column(Text)
    # 详情页的 JD 正文：只有进入精排的岗位才需要
    jd_text: Mapped[str | None] = mapped_column(Text)

    # ---- 硬条件过滤 ----
    filtered_reason: Mapped[str | None] = mapped_column(String(128))  # 不为空表示被过滤掉

    # ---- 粗筛 ----
    coarse_score: Mapped[int | None] = mapped_column(Integer)  # 0–3
    coarse_reason: Mapped[str | None] = mapped_column(String(256))
    shortlisted: Mapped[bool] = mapped_column(Boolean, default=False)  # 进入精排

    # ---- 精排 ----
    score: Mapped[int | None] = mapped_column(Integer)  # 按规则计算的匹配度 0–100
    rank_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rank_error: Mapped[str | None] = mapped_column(String(256))

    # ---- 加入投递记录 ----
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )

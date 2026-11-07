"""求职 Agent：待确认的写操作、生成的计划。"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class AgentAction(IdMixin, TimestampMixin, Base):
    """Agent 想要执行的一个“写操作”（改阶段、加日程……）。

    Agent 永远不直接修改数据：它只能提出建议，存成一条 pending 记录；
    用户在界面上点“确认”之后，才真正执行。这样即使模型理解错了，也不会弄乱用户的数据。
    """

    __tablename__ = "agent_actions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    tool: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB)
    description: Mapped[str] = mapped_column(Text)  # 给用户看的一句话说明
    # pending（待确认）/ done（已执行）/ cancelled（已取消）/ failed（执行失败）
    status: Mapped[str] = mapped_column(String(16), default="pending")
    result: Mapped[str | None] = mapped_column(Text)


class AgentPlan(IdMixin, TimestampMixin, Base):
    """生成的今日 / 本周计划。保存下来，避免每次打开页面都重新调用模型。"""

    __tablename__ = "agent_plans"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(8))  # today / week
    plan_date: Mapped[date] = mapped_column(Date)  # 今日计划是当天，本周计划是周一
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # 已完成的计划项下标：用来统计“计划被采纳的比例”（PRD 的成功指标之一）
    done_items: Mapped[list[int]] = mapped_column(JSONB, default=list)
    model: Mapped[str] = mapped_column(String(128))

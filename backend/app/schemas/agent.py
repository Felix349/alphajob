"""求职 Agent：计划的输出格式（字段描述就是提示词）与接口格式。"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------- 大模型输出：今日计划 ----------


class PlanItem(BaseModel):
    title: str = Field(
        description="一件具体、今天能做完的事，以动词开头，不超过 30 字，例如“复习 Raft 选主流程并画出时序图”"
    )
    reason: str = Field(
        description="为什么今天要做它：必须引用上下文里的具体数据（哪场面试、哪个备考项、哪个薄弱点、哪个截止日期），不超过 60 字"
    )
    minutes: int = Field(description="预计用时（分钟），15–180")
    priority: Literal[1, 2, 3] = Field(description="1 最紧急重要，3 可以往后放")
    application_id: str | None = Field(
        description="相关投递的 id，必须是上下文里出现过的 id；和具体投递无关就填 null"
    )

    @field_validator("minutes", mode="before")
    @classmethod
    def clamp_minutes(cls, v):
        return max(15, min(180, int(v)))


class TodayPlan(BaseModel):
    focus: str = Field(description="今天的重点，一句话，不超过 30 字")
    items: list[PlanItem] = Field(
        description="3–6 件事，按优先级排序。总用时要现实，一般不超过 5 小时"
    )

    @field_validator("items", mode="after")
    @classmethod
    def truncate(cls, v):
        return v[:6]


# ---------- 大模型输出：本周计划 ----------


class WeekDay(BaseModel):
    date: str = Field(description="日期，YYYY-MM-DD")
    focus: str = Field(description="这一天的重点，一句话；没有安排就写“机动 / 休息”")
    tasks: list[str] = Field(description="0–4 件具体的事，以动词开头")

    @field_validator("tasks", mode="after")
    @classmethod
    def truncate(cls, v):
        return v[:4]


class WeekPlan(BaseModel):
    overview: str = Field(description="本周整体安排的思路，不超过 80 字")
    key_dates: list[str] = Field(description="本周的关键节点，例如“周五 14:00 北辰云二面”，0–8 条")
    days: list[WeekDay] = Field(description="从本周一到周日，正好 7 天")


# ---------- 接口 ----------


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    """对话历史由前端保存并整段发来：服务端不存聊天记录，实现简单，也不必考虑多设备同步。"""

    messages: list[ChatMessageIn] = Field(min_length=1, max_length=30)
    timezone: str | None = Field(
        default=None, max_length=64, description="浏览器时区，如 Asia/Shanghai"
    )

    @field_validator("messages", mode="after")
    @classmethod
    def last_is_user(cls, v):
        if v[-1].role != "user":
            raise ValueError("最后一条消息必须来自用户")
        return v


class PlanRequest(BaseModel):
    kind: Literal["today", "week"]
    timezone: str | None = Field(default=None, max_length=64)


class PlanItemToggle(BaseModel):
    index: int = Field(ge=0, le=20)
    done: bool


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: Literal["today", "week"]
    plan_date: date
    plan: dict
    done_items: list[int]
    model: str
    created_at: datetime


class AgentActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tool: str
    description: str
    status: Literal["pending", "done", "cancelled", "failed"]
    result: str | None

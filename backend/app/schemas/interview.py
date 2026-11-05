"""面试复盘：大模型的输出格式（字段描述就是提示词）与接口格式。"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import InterviewStatus, Mastery

# ---------- 大模型输出 ----------


class AnalyzedQuestion(BaseModel):
    question: str = Field(description="面试官问的问题，整理成一句完整、清楚的问句")
    my_answer: str | None = Field(
        description="求职者当时的回答要点，只根据回忆内容概括；回忆里没提到怎么答的就填 null，不要编造"
    )
    score: Literal[1, 2, 3, 4, 5] = Field(
        description="当时回答的质量：1 没答上来，2 答得很浅或有明显错误，3 基本正确但不够深入，4 较好，5 非常好。回忆里没说怎么答的就按 2 处理"
    )
    feedback: str = Field(description="具体指出回答哪里好、哪里不足，不超过 80 字")
    improved_answer: str = Field(
        description="一个更好的回答，按面试时口头回答的方式组织：先给结论，再分点展开，150–300 字"
    )
    tags: list[str] = Field(
        description="1–3 个知识点标签，例如“缓存”“Agent 记忆”“系统设计”“项目深挖”"
    )


class WeakPointOut(BaseModel):
    topic: str = Field(description="薄弱点的主题，2–10 个字，例如“Agent 评测方法”")
    detail: str = Field(description="具体表现，以及接下来该补什么，不超过 80 字")


LIMITS = {"questions": 20, "highlights": 5, "weak_points": 6, "next_round_advice": 6}


class InterviewAnalysis(BaseModel):
    questions: list[AnalyzedQuestion] = Field(
        description="按面试顺序整理出的所有问题，不要遗漏，也不要合并不同的问题"
    )
    summary: str = Field(description="本场面试的整体总结：考察重点、整体表现，不超过 150 字")
    highlights: list[str] = Field(description="本场表现好的地方，0–5 条")
    weak_points: list[WeakPointOut] = Field(description="暴露出的薄弱点，0–6 条，要具体到知识点")
    next_round_advice: list[str] = Field(
        description="针对下一轮面试的具体准备建议，2–6 条，每条以动词开头"
    )

    @field_validator("questions", "highlights", "weak_points", "next_round_advice", mode="after")
    @classmethod
    def truncate(cls, value: list, info) -> list:
        return value[: LIMITS[info.field_name]]


# ---------- 接口 ----------


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    interview_id: uuid.UUID
    application_id: uuid.UUID
    question: str
    my_answer: str | None
    score: int
    feedback: str
    improved_answer: str
    tags: list[str]
    mastery: Mastery
    created_at: datetime


class QuestionBankItem(QuestionOut):
    """题库列表：带上公司、岗位和轮次，前端不用再单独请求。"""

    company: str
    role: str
    round: str


class QuestionUpdate(BaseModel):
    mastery: Mastery


class InterviewSummaryOut(BaseModel):
    summary: str
    highlights: list[str]
    weak_points: list[WeakPointOut]
    next_round_advice: list[str]


class InterviewOut(BaseModel):
    """列表用：不含转写全文和逐题结果。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    round: str
    held_on: date | None
    input_type: Literal["text", "audio"]
    audio_filename: str | None
    audio_seconds: float | None
    status: InterviewStatus
    error: str | None
    created_at: datetime
    question_count: int = 0


class InterviewDetail(InterviewOut):
    company: str
    role: str
    raw_text: str | None
    transcript: str | None
    summary: InterviewSummaryOut | None
    model: str | None
    questions: list[QuestionOut]

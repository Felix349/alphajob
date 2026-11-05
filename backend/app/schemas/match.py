"""岗位匹配分析：既是大模型的输出格式（字段描述就是提示词），也是接口的返回格式。"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import PrepCategory

# ---------- 大模型输出 ----------


class RequirementMatch(BaseModel):
    requirement: str = Field(description="岗位的一项核心要求，来自 JD，用一句话概括")
    level: Literal["strong", "partial", "missing"] = Field(
        description=(
            "strong：简历中有明确、直接的证据；partial：有相关经历但不完全对口或深度不够；"
            "missing：简历中找不到依据"
        )
    )
    evidence: str | None = Field(
        description=(
            "简历中支撑这项判断的依据，引用或概括简历原文（写清楚是哪段经历）。"
            "level 为 missing 时填 null。绝对不要编造简历里没有的内容"
        )
    )
    advice: str = Field(
        description="具体建议：strong 写面试时怎么讲出亮点；partial / missing 写怎么在面试前补上或如何坦诚应对"
    )


class PrepSuggestion(BaseModel):
    content: str = Field(
        description="一条具体、可执行、能在 1–3 天内完成的备考任务，以动词开头，例如“复习 Raft 选主流程并能画出时序图”"
    )
    category: PrepCategory = Field(
        description="knowledge：知识点；project：项目经历的准备；question：刷题或练习题；other：其他"
    )
    priority: Literal[1, 2, 3] = Field(
        description="1 最优先（直接对应 missing 的核心要求），3 最次要"
    )


LIMITS = {"highlights": 5, "requirements": 10, "prep_items": 12, "interview_questions": 8}


class MatchAnalysis(BaseModel):
    score: int = Field(
        description="整体匹配度，0–100 的整数。要克制：大部分要求都是 strong 才给 80 以上"
    )
    summary: str = Field(
        description="一段话总评：这个岗位最看重什么、你的优势和最大的差距，不超过 120 字"
    )
    highlights: list[str] = Field(
        description="最值得在面试中重点讲的 2–5 个亮点，每条都要能对应到简历中的具体经历"
    )
    requirements: list[RequirementMatch] = Field(
        description="逐条对照岗位的核心要求，5–10 条，按重要程度排序"
    )
    prep_items: list[PrepSuggestion] = Field(
        description="备考清单，5–12 条，优先覆盖 missing 和 partial 的要求"
    )
    interview_questions: list[str] = Field(
        description="结合 JD 和简历，最可能被问到的 3–8 个面试问题（包括针对简历经历的追问）"
    )

    @field_validator("score", mode="before")
    @classmethod
    def clamp_score(cls, v):
        # 模型偶尔会给出 105 或 -5 这样的值：夹到 0–100，而不是报错重试
        return max(0, min(100, int(v)))

    @field_validator(*LIMITS, mode="after")
    @classmethod
    def truncate(cls, value: list, info) -> list:
        return value[: LIMITS[info.field_name]]


# ---------- 接口 ----------


class MatchRequest(BaseModel):
    notes: str | None = Field(
        default=None, max_length=10000, description="可选：用户粘贴的面经、内推人透露的信息等"
    )


class MatchReportOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    report: MatchAnalysis
    model: str
    created_at: datetime
    resume_updated_at: datetime
    # 生成这份分析之后，简历又被修改过
    stale: bool


class PrepItemCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    category: PrepCategory = PrepCategory.OTHER
    priority: Literal[1, 2, 3] = 2


class PrepItemUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=500)
    done: bool | None = None
    priority: Literal[1, 2, 3] | None = None


class PrepItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    content: str
    category: PrepCategory
    priority: int
    done: bool
    source: str
    created_at: datetime

"""岗位匹配分析：既是大模型的输出格式（字段描述就是提示词），也是接口的返回格式。"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.models import PrepCategory
from app.models.resume import ResumeLanguage

# ---------- 大模型输出 ----------


class RequirementMatch(BaseModel):
    requirement: str = Field(description="岗位的一项要求，来自 JD，用一句话概括，不超过 30 字")
    importance: Literal["required", "preferred"] = Field(
        description=(
            "required：必备要求（JD 里的“任职要求”“必须”“熟悉”等）；"
            "preferred：加分项（JD 里的“优先”“加分”“者更佳”“nice to have”“is a plus”等）"
        )
    )
    level: Literal["strong", "partial", "missing"] = Field(
        description=(
            "strong：简历中有明确、直接的证据；partial：有相关经历但不完全对口或深度不够；"
            "missing：简历中找不到依据"
        )
    )
    evidence: str | None = Field(
        description=(
            "简历中支撑这项判断的依据：写明是哪段经历，引用最关键的一句，不超过 60 字。"
            "level 为 missing 时填 null。绝对不要编造简历里没有的内容"
        )
    )
    advice: str = Field(
        description=(
            "具体建议，不超过 80 字：strong 写面试时怎么讲出亮点；"
            "partial / missing 写怎么在面试前补上或如何坦诚应对"
        )
    )


class PrepSuggestion(BaseModel):
    content: str = Field(
        description=(
            "一条具体、可执行、能在 1–3 天内完成的备考任务，以动词开头，不超过 50 字，"
            "例如“复习 Raft 选主流程并能画出时序图”"
        )
    )
    category: PrepCategory = Field(
        description="knowledge：知识点；project：项目经历的准备；question：刷题或练习题；other：其他"
    )
    priority: Literal[1, 2, 3] = Field(
        description="1 最优先（直接对应 missing 的核心要求），3 最次要"
    )


class ResumeEdit(BaseModel):
    section: str = Field(
        description="改的是简历哪一部分，例如“项目经历：多 Agent 论文助手”“技能”“个人总结”"
    )
    original: str | None = Field(
        description="要修改的简历原句，逐字引用简历原文；如果是建议新增一句（原来没有），填 null"
    )
    suggestion: str = Field(
        description=(
            "修改后的写法，可以直接替换进简历，篇幅和原句相当（新增一句时不超过 100 字或 60 个英文单词）。"
            "用简历本身的语言写（英文简历就写英文）。"
            "只能重新组织、强调简历里已有的事实；需要求职者补充的信息（如数据量、提升幅度）"
            "用【待补充：……】占位，绝不能编造数字或经历"
        )
    )
    reason: str = Field(
        description="为什么这样改：对应 JD 的哪项要求、改了之后好在哪里，不超过 50 字"
    )


LIMITS = {
    "highlights": 5,
    "requirements": 10,
    "prep_items": 12,
    "interview_questions": 8,
    "resume_edits": 8,
}


# ---------- 匹配度的计算规则 ----------
# 分数不让模型直接给：模型给的分数说不清依据，同样的结果两次打分也可能差很多。
# 模型只做逐条判断（level、importance），分数由下面的规则算出，页面上可以完整展示计算过程。
# 改动这里时，记得同步修改前端 match-panel.tsx 里的规则说明。
LEVEL_POINTS = {"strong": 100, "partial": 50, "missing": 0}
IMPORTANCE_WEIGHT = {"required": 2, "preferred": 1}


def compute_score(requirements: list[RequirementMatch]) -> int:
    """各条要求得分的加权平均：匹配 100、部分匹配 50、缺失 0；必备要求权重 2，加分项权重 1。"""
    total_weight = sum(IMPORTANCE_WEIGHT[r.importance] for r in requirements)
    if total_weight == 0:
        return 0
    points = sum(IMPORTANCE_WEIGHT[r.importance] * LEVEL_POINTS[r.level] for r in requirements)
    # 四舍五入（Python 的 round 是“银行家舍入”，62.5 会变成 62，和直觉不一致）
    return int(points / total_weight + 0.5)


class MatchAnalysis(BaseModel):
    summary: str = Field(
        description="一段话总评：这个岗位最看重什么、你的优势和最大的差距，不超过 120 字"
    )
    highlights: list[str] = Field(
        description="最值得在面试中重点讲的 2–5 个亮点，每条不超过 40 字，都要能对应到简历中的具体经历"
    )
    requirements: list[RequirementMatch] = Field(
        description=(
            "逐条对照岗位要求，5–8 条：先列必备要求，再列加分项，各自按重要程度排序；"
            "相近的要求合并成一条"
        )
    )
    prep_items: list[PrepSuggestion] = Field(
        description="备考清单，5–10 条，优先覆盖 missing 和 partial 的要求"
    )
    interview_questions: list[str] = Field(
        description="结合 JD 和简历，最可能被问到的 3–8 个面试问题（包括针对简历经历的追问），每个不超过 40 字"
    )
    resume_edits: list[ResumeEdit] = Field(
        description=(
            "针对这个岗位的简历修改建议，3–6 条，按收益从高到低排序：把和 JD 相关的经历写得更突出、"
            "用 JD 里的关键词描述已有的经历、补上缺失的量化结果、删减或弱化无关内容"
        )
    )

    # computed_field 只出现在“输出”里：发给模型的 Schema（校验模式）不包含它，模型不用打分；
    # 接口返回、存进数据库的结果里都有它
    @computed_field(description="匹配度 0–100，由 requirements 按固定规则计算（见 compute_score）")
    @property
    def score(self) -> int:
        return compute_score(self.requirements)

    @field_validator(*LIMITS, mode="after")
    @classmethod
    def truncate(cls, value: list, info) -> list:
        return value[: LIMITS[info.field_name]]

    @classmethod
    def from_stored(cls, raw: dict) -> "MatchAnalysis":
        """读取数据库里存的分析，兼容旧版本的数据。

        - 加简历修改建议之前的分析没有 resume_edits：补成空列表
        - 改为按规则计分之前的分析没有 importance：都当作必备要求；旧的、由模型给出的
          score 会被忽略，统一按现在的规则重新计算，保证页面上的说明和分数对得上
        """
        requirements = [{"importance": "required", **r} for r in raw.get("requirements", [])]
        return cls.model_validate({"resume_edits": [], **raw, "requirements": requirements})


# ---------- 接口 ----------


class MatchRequest(BaseModel):
    notes: str | None = Field(
        default=None, max_length=10000, description="可选：用户粘贴的面经、内推人透露的信息等"
    )
    resume_language: ResumeLanguage | None = Field(
        default=None,
        description="用哪份简历分析：zh / en；不填则自动选择（英文 JD 优先用英文简历）",
    )


class MatchReportOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    report: MatchAnalysis
    model: str
    created_at: datetime
    resume_updated_at: datetime
    resume_language: ResumeLanguage
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

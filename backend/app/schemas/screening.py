"""岗位快速筛选：大模型的输出格式（字段描述就是提示词）和接口格式。"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.models.resume import ResumeLanguage
from app.schemas.match import compute_score

JobType = Literal["校招", "实习", "社招"]
MAX_JOBS_PER_BATCH = 500

# ---------- 大模型输出：从页面文本里抽取岗位列表 ----------


class ExtractedJob(BaseModel):
    title: str = Field(description="岗位名称，照抄页面原文")
    location: str | None = Field(description="工作地点，多个城市用 / 分隔；页面没写填 null")
    category: str | None = Field(description="岗位类别，如“技术”“产品”“算法”；页面没写填 null")
    job_type: JobType | None = Field(
        description="招聘类型：校招 / 实习 / 社招；页面没有明确写出时填 null，不要猜"
    )
    url: str | None = Field(description="岗位详情页链接，只能取页面里出现的链接；没有填 null")
    snippet: str | None = Field(description="列表上显示的岗位简介，不超过 150 字；没有填 null")


class ExtractedJobs(BaseModel):
    jobs: list[ExtractedJob] = Field(
        description="页面上的全部岗位，按页面顺序；导航栏、筛选项、页脚等不是岗位，不要列出"
    )


# ---------- 大模型输出：粗筛 ----------


class TriageItem(BaseModel):
    index: int = Field(description="岗位编号，和输入里的编号一致")
    score: Literal[0, 1, 2, 3] = Field(
        description=(
            "和求职者简历的相关度。3：方向高度对口，简历里有直接相关的经历；"
            "2：相关，值得点开看 JD；1：沾边，大概率不合适；0：方向不对（如销售、财务、硬件工艺）"
        )
    )
    reason: str = Field(description="一句话理由，不超过 20 字")


class Triage(BaseModel):
    items: list[TriageItem] = Field(description="对输入里的每一个岗位都给出判断，一个都不能少")


# ---------- 大模型输出：精排 ----------


class QuickRequirement(BaseModel):
    requirement: str = Field(description="岗位的一项要求，来自 JD，不超过 25 字")
    importance: Literal["required", "preferred"] = Field(
        description="required：必备要求；preferred：加分项（JD 里的“优先”“加分”“is a plus”等）"
    )
    level: Literal["strong", "partial", "missing"] = Field(
        description=(
            "strong：简历中有明确、直接的证据；partial：有相关经历但不完全对口或深度不够；"
            "missing：简历中找不到依据"
        )
    )
    evidence: str | None = Field(
        description="简历中的依据，不超过 30 字；missing 时填 null。绝对不要编造简历里没有的内容"
    )


class QuickMatch(BaseModel):
    """精简版的匹配分析：只要逐条判断和一句话总结，不生成备考清单、修改建议。"""

    requirements: list[QuickRequirement] = Field(
        description="逐条对照岗位要求，4–8 条：先列必备要求，再列加分项；相近的要求合并成一条"
    )
    strength: str = Field(description="这份简历投这个岗位最大的优势，不超过 40 字")
    gap: str = Field(description="最大的差距，不超过 40 字")

    @field_validator("requirements", mode="after")
    @classmethod
    def truncate(cls, value: list) -> list:
        return value[:10]

    @computed_field(description="匹配度 0–100：与完整匹配分析相同的规则计算")
    @property
    def score(self) -> int:
        return compute_score(self.requirements)


# ---------- 接口 ----------


class ScreeningFilters(BaseModel):
    cities: list[str] = Field(
        default_factory=list, max_length=20, description="只保留这些城市的岗位；为空表示不限"
    )
    job_types: list[JobType] = Field(
        default_factory=list, description="只保留这些招聘类型；为空表示不限"
    )
    exclude_keywords: list[str] = Field(
        default_factory=list, max_length=50, description="岗位名包含这些词的直接排除"
    )


class BatchCreate(BaseModel):
    company: str = Field(min_length=1, max_length=128)
    source_url: str | None = Field(default=None, max_length=1024)
    resume_language: ResumeLanguage | None = Field(
        default=None, description="用哪份简历；不填则按岗位语言自动选"
    )
    filters: ScreeningFilters = Field(default_factory=ScreeningFilters)
    top_n: int = Field(default=15, ge=1, le=30, description="粗筛后进入精排的岗位数")


class JobIn(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    location: str | None = Field(default=None, max_length=256)
    category: str | None = Field(default=None, max_length=128)
    job_type: JobType | None = None
    url: str | None = Field(default=None, max_length=1024)
    snippet: str | None = Field(default=None, max_length=2000)


class JobsIn(BaseModel):
    jobs: list[JobIn] = Field(min_length=1, max_length=MAX_JOBS_PER_BATCH)


class ExtractRequest(BaseModel):
    text: str = Field(min_length=10, max_length=60000, description="招聘列表页的文本（复制整页）")


class JdIn(BaseModel):
    jd_text: str = Field(min_length=20, max_length=20000)


class AddJobsResult(BaseModel):
    added: int
    duplicated: int
    total: int


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    title: str
    location: str | None
    category: str | None
    job_type: str | None
    url: str | None
    snippet: str | None
    has_jd: bool
    filtered_reason: str | None
    coarse_score: int | None
    coarse_reason: str | None
    shortlisted: bool
    score: int | None
    rank_result: dict[str, Any] | None
    rank_error: str | None
    application_id: uuid.UUID | None


class BatchOut(BaseModel):
    id: uuid.UUID
    company: str
    source_url: str | None
    filters: ScreeningFilters
    resume_language: ResumeLanguage | None
    top_n: int
    status: str
    created_at: datetime
    total_jobs: int
    shortlisted_jobs: int
    ranked_jobs: int


class BatchDetail(BatchOut):
    # 排序：精排分数高的在前；然后是进入精排但还没出结果的；再是粗筛分数；最后是被过滤掉的
    jobs: list[JobOut]


class ScreenResult(BaseModel):
    batch: BatchDetail
    # 进入精排、但还没有 JD 正文的岗位：插件据此逐个打开详情页（P1 阶段手动粘贴）
    needs_jd: list[JobOut]

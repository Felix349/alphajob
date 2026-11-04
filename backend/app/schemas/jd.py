from datetime import date

from pydantic import BaseModel, Field


class ParsedJD(BaseModel):
    """大模型从岗位描述（JD）中提取的结构化信息。

    这个模型同时是给大模型的输出格式（JSON Schema），所以每个字段都写清楚描述：
    描述就是给模型看的提示词。
    """

    company: str | None = Field(description="公司名称；JD 中没有明确写出时为 null，不要猜测")
    role: str | None = Field(description="岗位名称，例如“后端开发工程师（校招）”")
    location: str | None = Field(description="工作地点，多个城市用顿号分隔；没有则为 null")
    job_type: str | None = Field(description="招聘类型：校招 / 实习 / 社招；无法判断时为 null")
    salary: str | None = Field(description="薪资范围，保留原文写法；没有则为 null")
    deadline: date | None = Field(description="投递截止日期（YYYY-MM-DD）；没有则为 null")
    responsibilities: list[str] = Field(description="岗位职责，每条一句话，最多 8 条")
    requirements: list[str] = Field(description="任职要求（必须具备的条件），每条一句话，最多 8 条")
    bonus: list[str] = Field(description="加分项（优先考虑的条件）；没有则为空数组")
    tech_stack: list[str] = Field(
        description="JD 中提到的具体技术、语言、框架或工具，例如 Python、PyTorch、Kubernetes"
    )
    summary: str = Field(description="用一句话概括这个岗位最看重什么，不超过 40 字")


class ParseJDRequest(BaseModel):
    jd_text: str = Field(min_length=20, max_length=20000)

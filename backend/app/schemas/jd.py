from datetime import date

from pydantic import BaseModel, Field, field_validator

# 列表字段的条数上限。字段描述里也写了，但描述对模型只是“建议”，模型偶尔会多给。
# 这里在校验时直接截断，而不是报错：多一两条不是错误，没必要为此重试一次、多花一次调用。
LIST_LIMITS = {"responsibilities": 8, "requirements": 8, "bonus": 6, "tech_stack": 15}


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
    bonus: list[str] = Field(description="加分项（优先考虑的条件），最多 6 条；没有则为空数组")
    tech_stack: list[str] = Field(
        description=(
            "JD 中明确出现的具体技术名词，最多 15 个："
            "编程语言、框架、库、数据库、中间件、工具、平台，例如 Python、PyTorch、Kubernetes。"
            "不要列领域或概念（如 大模型、AI Agent、机器学习、推荐系统），"
            "也不要列泛称（如 Profiling 工具、深度学习框架）"
        )
    )
    summary: str = Field(description="用一句话概括这个岗位最看重什么，不超过 40 字")

    @field_validator(*LIST_LIMITS, mode="after")
    @classmethod
    def truncate_lists(cls, value: list[str], info) -> list[str]:
        # 去掉空白项和重复项（保持原顺序），再按上限截断
        seen: dict[str, None] = {}
        for item in value:
            if (s := item.strip()) and s not in seen:
                seen[s] = None
        return list(seen)[: LIST_LIMITS[info.field_name]]


class ParseJDRequest(BaseModel):
    jd_text: str = Field(min_length=20, max_length=20000)

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel

Effort = Literal["low", "medium", "high"]


class LLMError(Exception):
    """调用失败（网络、限流、模型拒答、输出不合格式等）。message 是可以展示给用户的中文说明。"""


class LLMNotConfigured(LLMError):
    """没有配置对应服务商的 API Key。"""


@dataclass
class StructuredResult[T: BaseModel]:
    data: T
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class LLMClient(Protocol):
    """所有模型适配器实现的统一接口。W3 起会再加入流式输出，W6 加入工具调用。"""

    provider: str
    model: str

    async def structured[T: BaseModel](
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        effort: Effort = "medium",
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        """让模型按 schema 输出 JSON，并校验成 Pydantic 对象。"""
        ...

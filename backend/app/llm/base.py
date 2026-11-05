from collections.abc import AsyncIterator
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


# ---------- 流式输出的事件 ----------


@dataclass
class TextDelta:
    """模型新生成的一小段文本（对结构化输出来说，就是 JSON 的一个片段）。"""

    text: str


@dataclass
class StreamReset:
    """流式输出的结果不合格，正在重新生成：前端应清空已显示的内容。"""

    reason: str


@dataclass
class StreamDone[T: BaseModel]:
    """生成结束，附带校验通过的最终结果。"""

    result: StructuredResult[T]


StreamEvent = TextDelta | StreamReset | StreamDone


class LLMClient(Protocol):
    """所有模型适配器实现的统一接口。W6 会再加入工具调用。"""

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

    def stream_structured[T: BaseModel](
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        effort: Effort = "medium",
        max_tokens: int = 8192,
    ) -> AsyncIterator[StreamEvent]:
        """流式版本：边生成边产出 TextDelta，最后产出一个 StreamDone。

        用途：生成时间较长的分析（10–30 秒），让用户能看到内容一点点出现，而不是干等。
        """
        ...

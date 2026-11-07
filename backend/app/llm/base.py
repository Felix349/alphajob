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


# ---------- 工具调用（W6 的 Agent 使用）----------


@dataclass
class ToolSpec:
    """提供给模型的一个工具：名字、用途说明（模型靠它决定什么时候调用）、参数的 JSON Schema。"""

    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    id: str  # 模型生成的调用 id，回传结果时要对上
    name: str
    arguments: dict
    # 参数不是合法 JSON 时记下原因，让 Agent 把错误反馈给模型修正，而不是直接崩溃
    parse_error: str | None = None


@dataclass
class ToolResult:
    call_id: str
    content: str  # 一般是 JSON 字符串
    is_error: bool = False


@dataclass
class AssistantTurn:
    """模型的一次回复：可能只有文字（说完了），也可能带着若干个工具调用（还要继续）。"""

    text: str
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int


@dataclass
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


class ToolSession(Protocol):
    """一段带工具的对话。各家模型的消息格式差别很大（OpenAI 用 role=tool 的消息回传结果，
    Claude 用 tool_result 内容块，还要原样回传思考块），所以由各个适配器用自己的原生格式保存历史，
    Agent 循环只需要反复调用 step() 和 add_tool_results()，不用关心这些差异。"""

    async def step(self) -> AssistantTurn:
        """请求模型回复一次，并把回复追加进历史。"""
        ...

    def add_tool_results(self, results: list[ToolResult]) -> None:
        """把这一轮所有工具的执行结果追加进历史（必须在下一次 step() 之前调用）。"""
        ...


class LLMClient(Protocol):
    """所有模型适配器实现的统一接口。"""

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

    def tool_session(
        self, *, system: str, history: list[ChatMessage], tools: list[ToolSpec]
    ) -> ToolSession:
        """开始一段可以调用工具的对话。history 的最后一条应当是用户消息。"""
        ...

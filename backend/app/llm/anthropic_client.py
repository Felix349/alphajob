"""Claude 适配器：使用官方 anthropic SDK 的结构化输出。

和 OpenAI 兼容接口不同，Claude 的结构化输出由服务端按 JSON Schema 约束生成，
SDK 会直接返回校验好的 Pydantic 对象，所以这里不需要“校验失败再重试”的循环。
"""

from collections.abc import AsyncIterator

import anthropic
from pydantic import BaseModel, ValidationError

from app.llm.base import (
    AssistantTurn,
    ChatMessage,
    Effort,
    LLMError,
    StreamDone,
    StreamEvent,
    StructuredResult,
    TextDelta,
    ToolCall,
    ToolResult,
    ToolSpec,
)

# 安全分类器误判拒答时，由服务端自动换模型重试
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _error(exc: Exception) -> LLMError:
    if isinstance(exc, anthropic.AuthenticationError):
        return LLMError("Anthropic API Key 无效")
    if isinstance(exc, anthropic.RateLimitError):
        return LLMError("Claude 请求过于频繁，请稍后再试")
    if isinstance(exc, anthropic.BadRequestError):
        return LLMError(f"Claude 请求参数错误：{exc.message}")
    if isinstance(exc, anthropic.APIStatusError):
        return LLMError(f"Claude 返回错误（{exc.status_code}）")
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMError("无法连接 Claude，请检查网络")
    if isinstance(exc, ValidationError):
        return LLMError("Claude 输出的结果不符合格式")
    return LLMError("Claude 调用失败")


def _result[T: BaseModel](resp) -> StructuredResult[T]:
    if resp.stop_reason == "refusal":
        raise LLMError("模型拒绝处理这段内容")
    if resp.stop_reason == "max_tokens":
        raise LLMError("模型输出超出长度上限被截断，请重试")
    if resp.parsed_output is None:
        raise LLMError("Claude 没有返回结构化结果")
    return StructuredResult(
        data=resp.parsed_output,
        provider="anthropic",
        model=resp.model,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
    )


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, *, api_key: str, model: str):
        self.model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=300)

    def _params(self, system: str, user: str, schema: type[BaseModel], effort: Effort, max_tokens):
        return {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_format": schema,
            # effort 控制思考深度和 token 消耗：提取任务用 low，分析任务用 medium
            "output_config": {"effort": effort},
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }

    async def structured[T: BaseModel](
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        effort: Effort = "medium",
        max_tokens: int = 16000,
    ) -> StructuredResult[T]:
        params = self._params(system, user, schema, effort, max(max_tokens, 16000))
        try:
            resp = await self._client.beta.messages.parse(**params)
        except (anthropic.AnthropicError, ValidationError) as exc:
            raise _error(exc) from exc
        return _result(resp)

    def tool_session(
        self, *, system: str, history: list[ChatMessage], tools: list[ToolSpec]
    ) -> "AnthropicToolSession":
        return AnthropicToolSession(self, system, history, tools)

    async def stream_structured[T: BaseModel](
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        effort: Effort = "medium",
        max_tokens: int = 32000,
    ) -> AsyncIterator[StreamEvent]:
        # 输出可能较长：用流式请求，既能实时展示，也避免长请求触发 HTTP 超时
        params = self._params(system, user, schema, effort, max(max_tokens, 32000))
        try:
            async with self._client.beta.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    yield TextDelta(text)
                final = await stream.get_final_message()
        except (anthropic.AnthropicError, ValidationError) as exc:
            raise _error(exc) from exc
        yield StreamDone(_result(final))


class AnthropicToolSession:
    """Claude 的工具对话。必须遵守两条规则：

    1. 助手回复的 content 要原样追加回历史：里面有思考块，改动或删掉会导致后续请求报错、丢失推理；
    2. 同一轮里所有工具的结果，要放在“同一条”用户消息里一起回传。
    """

    def __init__(
        self,
        client: AnthropicClient,
        system: str,
        history: list[ChatMessage],
        tools: list[ToolSpec],
    ):
        self._client = client
        self._system = system
        self._tools = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]
        self._messages: list[dict] = [{"role": m.role, "content": m.content} for m in history]

    async def step(self) -> AssistantTurn:
        try:
            resp = await self._client._client.beta.messages.create(
                model=self._client.model,
                max_tokens=16000,
                system=self._system,
                messages=self._messages,
                tools=self._tools,
                output_config={"effort": "medium"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.AnthropicError as exc:
            raise _error(exc) from exc
        if resp.stop_reason == "refusal":
            raise LLMError("模型拒绝处理这个请求")
        if resp.stop_reason == "max_tokens":
            raise LLMError("模型输出被截断")

        self._messages.append({"role": "assistant", "content": resp.content})  # 原样回传
        return AssistantTurn(
            text="".join(b.text for b in resp.content if b.type == "text"),
            tool_calls=[
                ToolCall(b.id, b.name, b.input if isinstance(b.input, dict) else {})
                for b in resp.content
                if b.type == "tool_use"
            ],
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.call_id,
                        "content": r.content,
                        "is_error": r.is_error,
                    }
                    for r in results
                ],
            }
        )

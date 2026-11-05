"""OpenAI 兼容接口适配器：DeepSeek、通义千问、OpenAI 都走这里，只是 base_url 和模型名不同。"""

import json
from collections.abc import AsyncIterator

import openai
from pydantic import BaseModel, ValidationError

from app.llm.base import (
    Effort,
    LLMError,
    StreamDone,
    StreamEvent,
    StreamReset,
    StructuredResult,
    TextDelta,
)

# 校验失败时把错误信息反馈给模型重试的次数
MAX_REPAIR_ATTEMPTS = 2
# OpenAI 兼容接口没有统一的 effort 参数，这里把它映射成温度：
# low 用于信息提取这类“要稳定、不要创造性”的任务，温度设为 0，让同样的输入尽量得到同样的输出
TEMPERATURE_BY_EFFORT: dict[Effort, float] = {"low": 0.0, "medium": 0.3, "high": 0.7}
JSON_INSTRUCTION = "只输出一个 JSON 对象，必须符合以下 JSON Schema："
REPAIR_INSTRUCTION = "上面的 JSON 不符合 Schema，错误如下，请修正后只输出 JSON："


class OpenAICompatibleClient:
    def __init__(self, *, provider: str, api_key: str, base_url: str | None, model: str):
        self.provider = provider
        self.model = model
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=120)

    def _messages(self, system: str, user: str, schema: type[BaseModel]) -> list[dict[str, str]]:
        # 不是所有兼容服务都支持严格的 json_schema 模式（DeepSeek 只支持 json_object），
        # 所以统一用 json_object + 在提示词里给出 JSON Schema，再用 Pydantic 校验兜底。
        schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        return [
            {"role": "system", "content": f"{system}\n\n{JSON_INSTRUCTION}\n{schema_text}"},
            {"role": "user", "content": user},
        ]

    def _error(self, exc: openai.OpenAIError) -> LLMError:
        """把 SDK 的异常翻译成可以展示给用户的中文说明。"""
        if isinstance(exc, openai.AuthenticationError):
            return LLMError(f"{self.provider} API Key 无效")
        if isinstance(exc, openai.RateLimitError):
            return LLMError(f"{self.provider} 请求过于频繁或额度不足，请稍后再试")
        if isinstance(exc, openai.APIConnectionError):
            return LLMError(f"无法连接 {self.provider}，请检查网络")
        if isinstance(exc, openai.APIStatusError):
            return LLMError(f"{self.provider} 返回错误（{exc.status_code}）")
        return LLMError(f"{self.provider} 调用失败")

    async def structured[T: BaseModel](
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        effort: Effort = "medium",
        max_tokens: int = 4096,
        messages: list[dict[str, str]] | None = None,
    ) -> StructuredResult[T]:
        messages = messages or self._messages(system, user, schema)
        total_in = total_out = 0

        for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
            try:
                resp = await self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # type: ignore[arg-type]
                    response_format={"type": "json_object"},
                    max_tokens=max_tokens,
                    temperature=TEMPERATURE_BY_EFFORT[effort],
                )
            except openai.OpenAIError as exc:
                raise self._error(exc) from exc

            if resp.usage:
                total_in += resp.usage.prompt_tokens
                total_out += resp.usage.completion_tokens
            choice = resp.choices[0]
            content = choice.message.content or ""
            if choice.finish_reason == "length":
                raise LLMError("模型输出被截断，请缩短输入内容后重试")

            try:
                data = schema.model_validate_json(content)
            except ValidationError as exc:
                if attempt == MAX_REPAIR_ATTEMPTS:
                    raise LLMError("模型多次输出了不符合格式的结果") from exc
                # 把模型的错误输出和校验错误一起发回去，让它自己修正
                messages = [
                    *messages,
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": f"{REPAIR_INSTRUCTION}\n{exc}"},
                ]
                continue

            return StructuredResult(
                data=data,
                provider=self.provider,
                model=resp.model or self.model,
                input_tokens=total_in,
                output_tokens=total_out,
            )

        raise AssertionError("unreachable")

    async def stream_structured[T: BaseModel](
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        effort: Effort = "medium",
        max_tokens: int = 8192,
    ) -> AsyncIterator[StreamEvent]:
        messages = self._messages(system, user, schema)
        parts: list[str] = []
        usage = None
        finish_reason = None
        model = self.model

        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                temperature=TEMPERATURE_BY_EFFORT[effort],
                stream=True,
                stream_options={"include_usage": True},  # 最后一个分块里带上 token 用量
            )
            async for chunk in stream:
                model = chunk.model or model
                if chunk.usage:
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                finish_reason = choice.finish_reason or finish_reason
                if choice.delta.content:
                    parts.append(choice.delta.content)
                    yield TextDelta(choice.delta.content)
        except openai.OpenAIError as exc:
            raise self._error(exc) from exc

        if finish_reason == "length":
            raise LLMError("模型输出被截断，请缩短输入内容后重试")

        content = "".join(parts)
        try:
            data = schema.model_validate_json(content)
        except ValidationError as exc:
            # 流式结果不合格：告诉前端清空，再走非流式的“反馈错误、让模型修正”流程
            yield StreamReset("输出格式有误，正在修正")
            repaired = await self.structured(
                system=system,
                user=user,
                schema=schema,
                effort=effort,
                max_tokens=max_tokens,
                messages=[
                    *messages,
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": f"{REPAIR_INSTRUCTION}\n{exc}"},
                ],
            )
            if usage:
                repaired.input_tokens += usage.prompt_tokens
                repaired.output_tokens += usage.completion_tokens
            yield StreamDone(repaired)
            return

        yield StreamDone(
            StructuredResult(
                data=data,
                provider=self.provider,
                model=model,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            )
        )

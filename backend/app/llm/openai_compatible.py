"""OpenAI 兼容接口适配器：DeepSeek、通义千问、OpenAI 都走这里，只是 base_url 和模型名不同。"""

import json

import openai
from pydantic import BaseModel, ValidationError

from app.llm.base import Effort, LLMError, StructuredResult

# 校验失败时把错误信息反馈给模型重试的次数
MAX_REPAIR_ATTEMPTS = 2
JSON_INSTRUCTION = "只输出一个 JSON 对象，必须符合以下 JSON Schema："
REPAIR_INSTRUCTION = "上面的 JSON 不符合 Schema，错误如下，请修正后只输出 JSON："


class OpenAICompatibleClient:
    def __init__(self, *, provider: str, api_key: str, base_url: str | None, model: str):
        self.provider = provider
        self.model = model
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60)

    async def structured[T: BaseModel](
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        effort: Effort = "medium",  # OpenAI 兼容接口没有统一的 effort 参数，这里忽略
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        # 不是所有兼容服务都支持严格的 json_schema 模式（DeepSeek 只支持 json_object），
        # 所以统一用 json_object + 在提示词里给出 JSON Schema，再用 Pydantic 校验兜底。
        schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": f"{system}\n\n{JSON_INSTRUCTION}\n{schema_text}",
            },
            {"role": "user", "content": user},
        ]
        total_in = total_out = 0

        for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
            try:
                resp = await self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # type: ignore[arg-type]
                    response_format={"type": "json_object"},
                    max_tokens=max_tokens,
                )
            except openai.AuthenticationError as exc:
                raise LLMError(f"{self.provider} API Key 无效") from exc
            except openai.RateLimitError as exc:
                raise LLMError(f"{self.provider} 请求过于频繁或额度不足，请稍后再试") from exc
            except openai.APIConnectionError as exc:
                raise LLMError(f"无法连接 {self.provider}，请检查网络") from exc
            except openai.APIStatusError as exc:
                raise LLMError(f"{self.provider} 返回错误（{exc.status_code}）") from exc

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
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": f"{REPAIR_INSTRUCTION}\n{exc}",
                    },
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

"""Claude 适配器：使用官方 anthropic SDK 的结构化输出。

和 OpenAI 兼容接口不同，Claude 的结构化输出由服务端按 JSON Schema 约束生成，
SDK 的 parse() 会直接返回校验好的 Pydantic 对象，所以这里不需要“校验失败再重试”的循环。
"""

import anthropic
from pydantic import BaseModel, ValidationError

from app.llm.base import Effort, LLMError, StructuredResult


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, *, api_key: str, model: str):
        self.model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=120)

    async def structured[T: BaseModel](
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        effort: Effort = "medium",
        max_tokens: int = 16000,
    ) -> StructuredResult[T]:
        try:
            resp = await self._client.beta.messages.parse(
                model=self.model,
                max_tokens=max(max_tokens, 16000),
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                # effort 控制思考深度和 token 消耗；JD 解析这类提取任务用 low 就够了
                output_config={"effort": effort},
                # 安全分类器误判拒答时，由服务端自动换模型重试
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic API Key 无效") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Claude 请求过于频繁，请稍后再试") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"Claude 请求参数错误：{exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Claude 返回错误（{exc.status_code}）") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("无法连接 Claude，请检查网络") from exc
        except ValidationError as exc:
            raise LLMError("Claude 输出的结果不符合格式") from exc

        if resp.stop_reason == "refusal":
            raise LLMError("模型拒绝处理这段内容")
        if resp.stop_reason == "max_tokens":
            raise LLMError("模型输出被截断，请缩短输入内容后重试")
        if resp.parsed_output is None:
            raise LLMError("Claude 没有返回结构化结果")

        return StructuredResult(
            data=resp.parsed_output,
            provider=self.provider,
            model=resp.model,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )

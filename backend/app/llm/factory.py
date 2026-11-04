"""根据配置创建 LLMClient。路由通过依赖注入拿到它，测试时可以替换成假的实现。"""

from app.core.config import Settings, get_settings
from app.llm.anthropic_client import AnthropicClient
from app.llm.base import LLMClient, LLMNotConfigured
from app.llm.openai_compatible import OpenAICompatibleClient


def build_llm_client(settings: Settings) -> LLMClient:
    provider = settings.llm_provider
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMNotConfigured("未配置 ANTHROPIC_API_KEY")
        return AnthropicClient(api_key=settings.anthropic_api_key, model=settings.anthropic_model)

    # 其余都是 OpenAI 兼容接口
    table = {
        "deepseek": (
            settings.deepseek_api_key,
            settings.deepseek_base_url,
            settings.deepseek_model,
        ),
        "qwen": (settings.dashscope_api_key, settings.qwen_base_url, settings.qwen_model),
        "openai": (settings.openai_api_key, None, settings.openai_model),
    }
    api_key, base_url, model = table[provider]
    if not api_key:
        raise LLMNotConfigured(f"未配置 {provider} 的 API Key")
    if not model:
        raise LLMNotConfigured(f"未配置 {provider} 使用的模型名")
    return OpenAICompatibleClient(
        provider=provider, api_key=api_key, base_url=base_url, model=model
    )


def get_llm_client() -> LLMClient:
    """FastAPI 依赖。每个请求新建一个客户端开销很小；W3 引入流式输出后再考虑复用。"""
    return build_llm_client(get_settings())

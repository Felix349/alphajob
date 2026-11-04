"""大模型抽象层。

业务代码只依赖 LLMClient 接口；具体用哪家模型由配置决定：
- OpenAICompatibleClient：DeepSeek、通义千问、OpenAI（都提供 OpenAI 兼容接口）
- AnthropicClient：Claude（官方 anthropic SDK）
"""

from app.llm.base import LLMClient, LLMError, LLMNotConfigured, StructuredResult

__all__ = ["LLMClient", "LLMError", "LLMNotConfigured", "StructuredResult"]

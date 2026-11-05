"""应用配置：从环境变量和仓库根目录的 .env 文件读取，带类型校验。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py → 仓库根目录
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env 里还有给 docker compose 用的变量，这里忽略
    )

    app_env: str = "development"

    database_url: str = (
        "postgresql+asyncpg://alphajob:alphajob_dev_password@127.0.0.1:5432/alphajob"
    )
    test_database_url: str = (
        "postgresql+asyncpg://alphajob:alphajob_dev_password@127.0.0.1:5432/alphajob_test"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    cookie_name: str = "alphajob_token"
    cookie_secure: bool = False

    # 逗号分隔的字符串，例如 "http://localhost:3000,http://127.0.0.1:3000"
    cors_origins: str = "http://localhost:3000"

    # ---- 大模型 ----
    # 默认使用哪家：deepseek / qwen / openai / anthropic
    llm_provider: Literal["deepseek", "qwen", "openai", "anthropic"] = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # 通义千问与语音转写共用阿里云百炼的 Key
    dashscope_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    openai_api_key: str = ""
    openai_model: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"

    # ---- 语音转写（阿里云百炼）----
    # 可选：百炼工作空间 ID。配置后走工作空间专属网关，更稳定；不配置则走公共网关
    dashscope_workspace: str = ""
    # 支持直接读取本地文件、时长不限的实时识别模型（录音文件识别类模型要求公网 URL，不适合本地部署）
    asr_model: str = "paraformer-realtime-v2"

    # ---- 文件存储 ----
    upload_dir: Path = REPO_ROOT / "data" / "uploads"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

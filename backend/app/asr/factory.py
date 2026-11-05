from app.asr.base import TranscribeError, Transcriber
from app.asr.dashscope_asr import DashScopeTranscriber
from app.core.config import Settings, get_settings


def build_transcriber(settings: Settings | None = None) -> Transcriber:
    settings = settings or get_settings()
    if not settings.dashscope_api_key:
        raise TranscribeError("未配置 DASHSCOPE_API_KEY，暂时无法处理语音，请改用文字输入")
    return DashScopeTranscriber(
        api_key=settings.dashscope_api_key,
        model=settings.asr_model,
        workspace=settings.dashscope_workspace,
    )

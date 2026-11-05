"""语音转写。

业务代码只依赖 Transcriber 接口，具体实现可以替换：阿里云、本地 Whisper、测试用的假实现。
"""

from app.asr.base import TranscribeError, Transcriber, TranscriptResult

__all__ = ["TranscribeError", "Transcriber", "TranscriptResult"]

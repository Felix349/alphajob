from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class TranscribeError(Exception):
    """转写失败。message 是可以展示给用户的中文说明。"""


@dataclass
class TranscriptResult:
    text: str
    seconds: float  # 音频时长


class Transcriber(Protocol):
    name: str

    async def transcribe(self, path: Path) -> TranscriptResult: ...

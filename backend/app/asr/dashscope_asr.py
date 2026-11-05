"""阿里云百炼语音转写。

模型选择：paraformer-realtime-v2。它能直接读取本地文件、时长不限；
而“录音文件识别”类模型（paraformer-v2、fun-asr 等）要求音频放在公网 URL 上，不适合本地部署。

它支持的格式有限（wav / mp3 / ogg-opus / aac / amr 等），
浏览器录音的 webm、手机录音的 m4a 都不在其中，
所以统一先用 ffmpeg 转成 16 kHz 单声道 PCM WAV：这也是语音识别最标准的输入格式。
"""

import asyncio
import subprocess
import tempfile
import wave
from pathlib import Path

import dashscope
import imageio_ffmpeg

from app.asr.base import TranscribeError, TranscriptResult

SAMPLE_RATE = 16000
MAX_SECONDS = 30 * 60  # 单次复盘的录音上限：30 分钟


def to_wav_16k(src: Path, dst: Path) -> float:
    """任意音频 → 16 kHz 单声道 WAV，返回时长（秒）。

    ffmpeg 来自 imageio-ffmpeg 自带的二进制，无需在系统里另外安装。
    """
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-loglevel", "error", "-y",
        "-i", str(src),
        "-vn",  # 丢掉视频轨（有人会上传录屏）
        "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
        # 超长音频只转前 30 分钟多一点：足够判断是否超限，又不会白白处理几小时的文件
        "-t", str(MAX_SECONDS + 1),
        str(dst),
    ]  # fmt: skip
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as exc:
        raise TranscribeError("无法识别这个音频文件，请确认它是有效的录音") from exc
    except subprocess.TimeoutExpired as exc:
        raise TranscribeError("音频转换超时") from exc
    with wave.open(str(dst), "rb") as w:
        seconds = w.getnframes() / w.getframerate()
    if seconds < 1:
        raise TranscribeError("录音太短，没有可识别的内容")
    if seconds > MAX_SECONDS:
        raise TranscribeError("录音超过 30 分钟，请分成几段上传")
    return seconds


class DashScopeTranscriber:
    name = "dashscope"

    def __init__(self, *, api_key: str, model: str, workspace: str = ""):
        self.model = model
        self._client = dashscope.Client(api_key=api_key, workspace=workspace or None)

    def _recognize(self, wav: Path) -> str:
        """同步调用：SDK 通过 WebSocket 把文件流式发出去，逐句返回识别结果。在线程里执行。"""
        sentences: list[str] = []
        try:
            for event in self._client.audio.asr.recognize_file(
                str(wav), model=self.model, format="wav", sample_rate=SAMPLE_RATE
            ):
                sentence = (event.get("payload") or {}).get("output", {}).get("sentence") or {}
                # 识别过程中会不断返回“中间结果”，只取每句话的最终版本
                if sentence.get("sentence_end") and sentence.get("text"):
                    sentences.append(sentence["text"])
        except Exception as exc:  # SDK 的网络、鉴权错误类型较多，统一转成用户能看懂的提示
            msg = str(exc)
            if "401" in msg or "InvalidApiKey" in msg or "auth" in msg.lower():
                raise TranscribeError("阿里云 API Key 无效，请检查 DASHSCOPE_API_KEY") from exc
            raise TranscribeError("语音识别服务调用失败，请稍后重试") from exc
        return "".join(sentences)

    async def transcribe(self, path: Path) -> TranscriptResult:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            # ffmpeg 转换和识别都是阻塞操作，放到线程里，不卡住 Worker 的事件循环
            seconds = await asyncio.to_thread(to_wav_16k, path, wav)
            text = await asyncio.to_thread(self._recognize, wav)
        if not text.strip():
            raise TranscribeError("没有识别出文字，请确认录音里有清晰的人声")
        return TranscriptResult(text=text, seconds=seconds)

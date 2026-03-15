from __future__ import annotations

"""ASR 服务：加载 faster-whisper 并把音频转写为分段文本。"""

from pathlib import Path

from faster_whisper import WhisperModel

from app.core.config import get_settings
from app.services.text_processing import RawSegment

settings = get_settings()

_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    """
    功能：获取 get_model 对应的数据或对象。
    参数：
    - 无。
    返回值：
    - WhisperModel：函数处理结果。
    """
    global _model
    if _model is None:
        _model = WhisperModel(
            settings.asr_model_size,
            device=settings.asr_device,
            compute_type=settings.asr_compute_type,
        )
    return _model


def transcribe_audio(audio_path: Path) -> tuple[list[RawSegment], str]:
    """
    功能：执行 transcribe_audio 的核心业务逻辑。
    参数：
    - audio_path：输入参数。
    返回值：
    - tuple[list[RawSegment], str]：函数处理结果。
    """
    model = get_model()
    segments, info = model.transcribe(str(audio_path), beam_size=1, vad_filter=True)

    result: list[RawSegment] = []
    lang = info.language or "unknown"
    for seg in segments:
        result.append(
            RawSegment(
                text=seg.text,
                start_ms=int(seg.start * 1000),
                end_ms=int(seg.end * 1000),
                lang=lang,
            )
        )

    return result, lang

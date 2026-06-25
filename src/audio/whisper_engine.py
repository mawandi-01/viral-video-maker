"""音频引擎 · 基于 mlx-whisper 的 ASR（语音转文字）。

mlx-whisper 是 OpenAI Whisper 的 Apple Silicon 优化版，
用 MLX 框架重写，在 M 系列芯片上比原版快 4-6 倍。

首次运行会自动下载模型权重（约 1.5GB medium 模型），
缓存到 ~/.cache/huggingface/，之后不再下载。

用法:
    from src.audio.whisper_engine import WhisperEngine
    engine = WhisperEngine()
    result = engine.transcribe("/path/to/audio.mp3")
    print(result.text)        # 全文
    print(result.segments)    # 带时间戳的分段
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


@dataclass
class ASRSegment:
    """一段语音的文字 + 时间戳。"""
    start: float          # 开始时间（秒）
    end: float            # 结束时间（秒）
    text: str             # 这段说的话


@dataclass
class ASRResult:
    """ASR 转写结果。"""
    success: bool
    text: str = ""                                        # 全文（拼接）
    segments: list[ASRSegment] = field(default_factory=list)  # 分段
    language: str = ""                                    # 检测到的语种
    duration: float = 0.0                                 # 音频总时长（秒）
    error: str = ""


class WhisperEngine:
    """mlx-whisper 封装。

    模型选型:
    - tiny    (~150MB):  最快, 准确率低, 不推荐中文
    - base    (~290MB):  快, 准确率一般
    - small   (~960MB):  平衡, 中文尚可
    - medium  (~1.5GB):  慢一点, 中文好 ← 默认推荐
    - large   (~3GB):    最慢, 最好, M1 Air 可能吃力
    """

    # mlx-whisper 模型名称格式: mlx-community/whisper-medium-mlx
    # medium 是中文效果和速度的最佳平衡点
    DEFAULT_MODEL = "mlx-community/whisper-medium-mlx-4bit"

    def __init__(self, model: Optional[str] = None) -> None:
        self._model = model or self.DEFAULT_MODEL
        logger.info(f"WhisperEngine init: model={self._model}")

    def transcribe(self, audio_path: str) -> ASRResult:
        """转写音频文件为文字。

        支持 mp3 / wav / m4a / flac 等常见格式。
        首次运行会下载模型（约 1.5GB），耐心等待。

        Args:
            audio_path: 音频文件路径

        Returns:
            ASRResult, success=False 时看 error 字段
        """
        if not os.path.exists(audio_path):
            return ASRResult(success=False, error=f"audio not found: {audio_path}")

        logger.info(f"ASR start: {audio_path}")

        try:
            import mlx_whisper
            result = mlx_whisper.transcribe(
                audio_path,
                path_or_hf_repo=self._model,
                language="zh",       # 指定中文, 避免误判语种
                initial_prompt=None, # 可加领域提示词提升专有名词识别
                verbose=False,
            )
        except Exception as e:
            logger.error(f"ASR failed: {e}")
            return ASRResult(success=False, error=str(e))

        segments: list[ASRSegment] = []
        for seg in result.get("segments", []):
            segments.append(ASRSegment(
                start=float(seg.get("start", 0)),
                end=float(seg.get("end", 0)),
                text=seg.get("text", "").strip(),
            ))

        text = result.get("text", "").strip()
        language = result.get("language", "zh")

        logger.info(
            f"ASR done: {len(segments)} segments, "
            f"{len(text)} chars, lang={language}"
        )

        return ASRResult(
            success=True,
            text=text,
            segments=segments,
            language=language,
            duration=segments[-1].end if segments else 0,
        )


_engine: Optional[WhisperEngine] = None


def get_engine() -> WhisperEngine:
    global _engine
    if _engine is None:
        _engine = WhisperEngine()
    return _engine

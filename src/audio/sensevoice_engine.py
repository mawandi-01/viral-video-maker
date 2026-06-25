"""音频引擎 · 基于 SenseVoice 的 ASR（阿里达摩院，中文优化）。

SenseVoice 是阿里达摩院开源的语音理解模型，相比 Whisper:
- 中文识别更准（专为中文优化）
- 自动加标点
- 同时识别情绪（开心/生气/悲伤/惊讶）
- 同时识别音效（笑声/掌声/音乐）
- 速度更快

首次运行会自动从 ModelScope 下载模型（约 900MB），
缓存到 ~/.cache/modelscope/，之后不再下载。

用法:
    from src.audio.sensevoice_engine import SenseVoiceEngine
    engine = SenseVoiceEngine()
    result = engine.transcribe("/path/to/audio.wav")
    print(result.text)          # 全文
    print(result.segments)      # 带时间戳的分段
    print(result.emotions)      # 情绪标注
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


@dataclass
class SenseVoiceSegment:
    """一段语音的文字 + 时间戳 + 情绪。"""
    start: float          # 开始时间（秒）
    end: float            # 结束时间（秒）
    text: str             # 这段说的话
    emotion: str = ""     # 情绪: happy/angry/sad/surprised/neutral


@dataclass
class SenseVoiceResult:
    """SenseVoice 转写结果。"""
    success: bool
    text: str = ""                                              # 全文
    segments: list[SenseVoiceSegment] = field(default_factory=list)
    language: str = ""                                          # 语种
    duration: float = 0.0                                       # 音频总时长
    emotions: list[str] = field(default_factory=list)           # 出现过的情绪
    audio_events: list[str] = field(default_factory=list)       # 音效事件
    error: str = ""


class SenseVoiceEngine:
    """FunASR / SenseVoice 封装。

    SenseVoice 模型特点:
    - 5 种情绪识别 (happy/angry/sad/surprised/neutral)
    - 音效事件检测 (laughter/applause/music)
    - 多语种 (中/英/粤/日/韩)
    - 自动标点

    模型选择:
    - iic/SenseVoiceSmall: 标准版 (推荐, ~900MB)
    """

    # ModelScope 上的 SenseVoice Small 模型
    DEFAULT_MODEL = "iic/SenseVoiceSmall"

    def __init__(self, model: Optional[str] = None) -> None:
        self._model = model or self.DEFAULT_MODEL
        self._auto_model = None  # 懒加载
        logger.info(f"SenseVoiceEngine init: model={self._model}")

    def _ensure_model(self) -> None:
        """懒加载模型（首次调用时下载，约 900MB）。"""
        if self._auto_model is not None:
            return

        logger.info(f"loading SenseVoice model (首次会下载约 900MB)...")
        from funasr import AutoModel

        self._auto_model = AutoModel(
            model=self._model,
            trust_remote_code=True,
            remote_code="./model.py",  # FunASR 内部使用
            vad_model="fsmn-vad",      # VAD 语音活动检测, 用于分段
            vad_kwargs={"max_single_segment_time": 30000},
            device="cpu",              # M1 Mac 用 cpu (mps 支持不稳)
            disable_update=True,
        )
        logger.info("SenseVoice model loaded")

    def transcribe(self, audio_path: str) -> SenseVoiceResult:
        """转写音频文件为文字 + 情绪 + 音效。

        注意: SenseVoice 要求 16kHz wav 格式效果最好。
        如果输入是 mp3, 建议先用 ffmpeg 转成 16kHz wav。

        Args:
            audio_path: 音频文件路径 (wav 推荐)

        Returns:
            SenseVoiceResult
        """
        if not os.path.exists(audio_path):
            return SenseVoiceResult(success=False, error=f"audio not found: {audio_path}")

        try:
            self._ensure_model()
        except Exception as e:
            logger.error(f"SenseVoice model load failed: {e}")
            return SenseVoiceResult(success=False, error=f"model load failed: {e}")

        logger.info(f"SenseVoice ASR start: {audio_path}")

        try:
            res = self._auto_model.generate(
                input=audio_path,
                cache={},
                language="zh",          # 指定中文 (auto/zh/en/yue/ja/ko)
                use_itn=True,           # 逆文本归一化 (数字转阿拉伯数字)
                batch_size_s=60,        # 每批 60 秒
                merge_vad=True,         # 合并 VAD 片段
                merge_length_s=15,      # 合并到 15 秒一段
            )
        except Exception as e:
            logger.error(f"SenseVoice ASR failed: {e}")
            return SenseVoiceResult(success=False, error=str(e))

        # 解析结果
        segments: list[SenseVoiceSegment] = []
        emotions_set: set = set()
        events_set: set = set()
        full_text_parts: list[str] = []

        for item in res:
            # SenseVoice 输出格式: <|happy|><|Speech|><|withitn|>文字内容
            raw_text = item.get("text", "")
            timestamp = item.get("timestamp", [[0, 0]])

            # 解析情绪和事件标签
            emotion, events, clean_text = self._parse_tags(raw_text)

            # timestamp 是 [[start_ms, end_ms], ...] 格式
            for ts in timestamp:
                start_s = ts[0] / 1000.0
                end_s = ts[1] / 1000.0
                segments.append(SenseVoiceSegment(
                    start=start_s,
                    end=end_s,
                    text=clean_text,
                    emotion=emotion,
                ))

            full_text_parts.append(clean_text)
            if emotion:
                emotions_set.add(emotion)
            events_set.update(events)

        full_text = "".join(full_text_parts)
        last_end = segments[-1].end if segments else 0

        logger.info(
            f"SenseVoice done: {len(segments)} segments, "
            f"{len(full_text)} chars, emotions={list(emotions_set)}"
        )

        return SenseVoiceResult(
            success=True,
            text=full_text,
            segments=segments,
            language="zh",
            duration=last_end,
            emotions=list(emotions_set),
            audio_events=list(events_set),
        )

    @staticmethod
    def _parse_tags(text: str) -> tuple[str, list[str], str]:
        """解析 SenseVoice 输出的标签。

        格式: <|happy|><|Speech|><|withitn|>实际文字
        返回: (emotion, events, clean_text)
        """
        emotion = ""
        events: list[str] = []
        clean = text

        # 情绪标签
        emotion_tags = ["happy", "angry", "sad", "surprised", "neutral"]
        for tag in emotion_tags:
            tag_str = f"<|{tag}|>"
            if tag_str in clean:
                emotion = tag
                clean = clean.replace(tag_str, "")

        # 音效事件标签
        event_tags = ["Speech", "BGM", "Laughter", "Applause", "Noise"]
        for tag in event_tags:
            tag_str = f"<|{tag}|>"
            if tag_str in clean:
                events.append(tag)
                clean = clean.replace(tag_str, "")

        # 其他特殊标签
        clean = clean.replace("<|withitn|>", "")
        clean = clean.replace("<|woitn|>", "")
        clean = clean.strip()

        return emotion, events, clean


_engine: Optional[SenseVoiceEngine] = None


def get_engine() -> SenseVoiceEngine:
    global _engine
    if _engine is None:
        _engine = SenseVoiceEngine()
    return _engine

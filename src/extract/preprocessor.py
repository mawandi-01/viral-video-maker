"""预处理层 · 用 ffmpeg 把视频拆成三种原料。

输入: 视频文件路径（本地，非 OSS）
输出: 关键帧 JPG 列表 + 16kHz wav 音频 + 字幕文本

用法:
    from src.extract.preprocessor import VideoPreprocessor
    pp = VideoPreprocessor()
    result = pp.process("/path/to/video.mp4")
    print(result.frames)      # ["/tmp/xxx/frame_001.jpg", ...]
    print(result.audio_path)  # "/tmp/xxx/audio.wav"
    print(result.subtitle)    # "字幕文本" 或 ""
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger

from config.settings import settings


@dataclass
class PreprocessResult:
    """预处理结果。"""
    frames: list[str] = field(default_factory=list)  # JPG 路径列表
    audio_path: str = ""                               # wav 路径
    subtitle: str = ""                                 # 字幕文本（纯文本，无时间戳）
    subtitle_path: str = ""                            # 字幕文件路径（srt/vtt）
    duration: float = 0.0                              # 视频总时长（秒）
    error: str = ""


class VideoPreprocessor:
    """ffmpeg 预处理封装。"""

    def __init__(self) -> None:
        self._frame_interval = settings.extract.frame_interval
        self._max_frames = settings.extract.max_frames
        self._sample_rate = settings.extract.audio_sample_rate

    def process(self, video_path: str, work_dir: Optional[str] = None) -> PreprocessResult:
        """完整预处理：抽帧 + 抽音频 + 抽字幕。

        Args:
            video_path: 本地视频文件路径
            work_dir: 工作目录（存帧图和音频），None 则用临时目录

        Returns:
            PreprocessResult
        """
        if not os.path.exists(video_path):
            return PreprocessResult(error=f"video not found: {video_path}")

        work_dir = work_dir or tempfile.mkdtemp(prefix="extract_")
        os.makedirs(work_dir, exist_ok=True)

        result = PreprocessResult()

        # 先拿时长
        result.duration = self._get_duration(video_path)

        # 1. 抽帧
        result.frames = self._extract_frames(video_path, work_dir)
        if not result.frames:
            result.error = "frame extraction failed"
            return result

        # 2. 抽音频
        result.audio_path = self._extract_audio(video_path, work_dir)

        # 3. 抽字幕（可选，失败不阻塞）
        result.subtitle, result.subtitle_path = self._extract_subtitle(video_path, work_dir)

        logger.info(
            f"preprocess done: {len(result.frames)} frames, "
            f"audio={'yes' if result.audio_path else 'no'}, "
            f"subtitle={'yes' if result.subtitle else 'no'}, "
            f"duration={result.duration:.1f}s"
        )
        return result

    def _get_duration(self, video_path: str) -> float:
        """用 ffprobe 获取视频时长。"""
        try:
            r = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                capture_output=True, text=True, timeout=30,
            )
            return float(r.stdout.strip() or 0)
        except Exception as e:
            logger.warning(f"get duration failed: {e}")
            return 0.0

    def _extract_frames(self, video_path: str, work_dir: str) -> list[str]:
        """抽关键帧，每 N 秒一帧，上限 max_frames。"""
        frames_dir = os.path.join(work_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)

        # 算实际抽帧间隔（如果视频很长，按 max_frames 限制）
        duration = self._get_duration(video_path)
        if duration > 0:
            ideal_frame_count = duration / self._frame_interval
            if ideal_frame_count > self._max_frames:
                actual_interval = duration / self._max_frames
            else:
                actual_interval = self._frame_interval
        else:
            actual_interval = self._frame_interval

        output_pattern = os.path.join(frames_dir, "frame_%04d.jpg")
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", f"fps=1/{actual_interval}",
            "-q:v", "2",  # JPEG 质量 (2=高质量)
            "-y",
            output_pattern,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
        except subprocess.CalledProcessError as e:
            logger.error(f"frame extraction failed: {e.stderr[:300]}")
            return []
        except subprocess.TimeoutExpired:
            logger.error("frame extraction timeout")
            return []

        # 收集生成的帧文件
        frames = sorted([
            os.path.join(frames_dir, f)
            for f in os.listdir(frames_dir)
            if f.endswith(".jpg")
        ])
        logger.info(f"extracted {len(frames)} frames (interval={actual_interval:.1f}s)")
        return frames

    def _extract_audio(self, video_path: str, work_dir: str) -> str:
        """抽 16kHz 单声道 wav 音频。"""
        audio_path = os.path.join(work_dir, "audio.wav")
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vn",                    # 不要视频
            "-acodec", "pcm_s16le",   # 16bit PCM
            "-ar", str(self._sample_rate),  # 采样率
            "-ac", "1",               # 单声道
            "-y",
            audio_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
            logger.info(f"audio extracted: {audio_path}")
            return audio_path
        except subprocess.CalledProcessError as e:
            logger.warning(f"audio extraction failed: {e.stderr[:300]}")
            return ""
        except subprocess.TimeoutExpired:
            logger.warning("audio extraction timeout")
            return ""

    def _extract_subtitle(self, video_path: str, work_dir: str) -> tuple[str, str]:
        """抽字幕（如有）。返回 (纯文本, 文件路径)。"""
        sub_path = os.path.join(work_dir, "subtitle.srt")
        cmd = [
            "ffmpeg", "-i", video_path,
            "-map", "0:s:0?",    # 第一条字幕流（?表示没有也不报错）
            "-f", "srt",
            "-y",
            sub_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
            if not os.path.exists(sub_path) or os.path.getsize(sub_path) == 0:
                return "", ""
            text = self._srt_to_text(sub_path)
            logger.info(f"subtitle extracted: {len(text)} chars")
            return text, sub_path
        except Exception:
            # 没字幕很正常，不报错
            return "", ""

    @staticmethod
    def _srt_to_text(srt_path: str) -> str:
        """把 srt 字幕文件转成纯文本。"""
        lines = []
        with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                # 跳过序号行、时间戳行、空行
                if not line or line.isdigit() or "-->" in line:
                    continue
                lines.append(line)
        return "".join(lines)


_preprocessor: Optional[VideoPreprocessor] = None


def get_preprocessor() -> VideoPreprocessor:
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = VideoPreprocessor()
    return _preprocessor

"""对比测试 Whisper vs SenseVoice 两个 ASR 引擎。

用同一个音频文件，分别跑两个引擎，输出对比结果。
首次运行两个引擎都会下载模型（Whisper ~1.5GB + SenseVoice ~900MB）。

用法:
  cd /Users/ma/WorkBuddy/my-project
  source .venv/bin/activate

  # 1. 用音频文件对比
  python scripts/test_asr_compare.py --audio /path/to/audio.wav

  # 2. 从视频提取音频再对比
  python scripts/test_asr_compare.py --video /path/to/video.mp4
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.logger import logger


def extract_audio(video_path: str, output_path: str) -> bool:
    """用 ffmpeg 从视频提取 16kHz wav 音频。"""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000",      # 16kHz, SenseVoice 推荐
        "-ac", "1",          # 单声道
        "-y",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg 失败: {e.stderr[:200]}")
        return False
    except FileNotFoundError:
        print("ffmpeg 未安装, 请先运行: bash scripts/install_ffmpeg.sh")
        return False


def test_whisper(audio_path: str) -> dict:
    """测试 mlx-whisper, 返回结果字典。"""
    print("\n" + "=" * 60)
    print("【Whisper (mlx-whisper)】")
    print("=" * 60)
    print("模型: mlx-community/whisper-medium-mlx-4bit (~1.5GB)")
    print("首次运行会下载模型，请耐心等待...")
    print()

    try:
        from src.audio.whisper_engine import WhisperEngine
        engine = WhisperEngine()
        t0 = time.time()
        result = engine.transcribe(audio_path)
        elapsed = time.time() - t0
        return {
            "name": "Whisper",
            "success": result.success,
            "text": result.text,
            "segments": result.segments,
            "elapsed": elapsed,
            "error": result.error,
        }
    except Exception as e:
        return {"name": "Whisper", "success": False, "error": str(e), "elapsed": 0}


def test_sensevoice(audio_path: str) -> dict:
    """测试 SenseVoice, 返回结果字典。"""
    print("\n" + "=" * 60)
    print("【SenseVoice (FunASR)】")
    print("=" * 60)
    print("模型: iic/SenseVoiceSmall (~900MB)")
    print("首次运行会下载模型，请耐心等待...")
    print()

    try:
        from src.audio.sensevoice_engine import SenseVoiceEngine
        engine = SenseVoiceEngine()
        t0 = time.time()
        result = engine.transcribe(audio_path)
        elapsed = time.time() - t0
        return {
            "name": "SenseVoice",
            "success": result.success,
            "text": result.text,
            "segments": result.segments,
            "elapsed": elapsed,
            "emotions": result.emotions,
            "events": result.audio_events,
            "error": result.error,
        }
    except Exception as e:
        return {"name": "SenseVoice", "success": False, "error": str(e), "elapsed": 0}


def print_comparison(w: dict, s: dict) -> None:
    """打印对比结果。"""
    print("\n" + "=" * 60)
    print("对比结果")
    print("=" * 60)

    # 基本信息
    print(f"\n{'指标':<20} {'Whisper':<25} {'SenseVoice':<25}")
    print("-" * 70)

    print(f"{'状态':<20}", end="")
    print(f"{'✓ 成功' if w['success'] else '✗ 失败':<25}", end="")
    print(f"{'✓ 成功' if s['success'] else '✗ 失败':<25}")

    print(f"{'耗时(秒)':<20}", end="")
    print(f"{w.get('elapsed', 0):<25.1f}", end="")
    print(f"{s.get('elapsed', 0):<25.1f}")

    if w["success"] and s["success"]:
        print(f"{'字数':<20}", end="")
        print(f"{len(w['text']):<25}", end="")
        print(f"{len(s['text']):<25}")

        print(f"{'分段数':<20}", end="")
        print(f"{len(w['segments']):<25}", end="")
        print(f"{len(s['segments']):<25}")

        print(f"{'情绪识别':<20}", end="")
        print(f"{'不支持':<25}", end="")
        print(f"{', '.join(s.get('emotions', [])) or '无':<25}")

        print(f"{'音效识别':<20}", end="")
        print(f"{'不支持':<25}", end="")
        print(f"{', '.join(s.get('events', [])) or '无':<25}")

    # 全文对比
    if w["success"] and s["success"]:
        print("\n" + "-" * 60)
        print("Whisper 全文:")
        print(w["text"])
        print()
        print("-" * 60)
        print("SenseVoice 全文:")
        print(s["text"])
        print()

        # 分段对比（前 5 段）
        print("-" * 60)
        print("分段对比（前 5 段）:")
        print(f"{'Whisper':<50} | {'SenseVoice':<50}")
        print("-" * 100)
        max_segs = max(len(w["segments"]), len(s["segments"]))
        for i in range(min(5, max_segs)):
            w_text = w["segments"][i].text[:45] if i < len(w["segments"]) else ""
            s_text = s["segments"][i].text[:45] if i < len(s["segments"]) else ""
            print(f"{w_text:<50} | {s_text:<50}")
        if max_segs > 5:
            print(f"... 还有 {max_segs - 5} 段")

    # 错误信息
    if not w["success"]:
        print(f"\nWhisper 错误: {w.get('error', '')}")
    if not s["success"]:
        print(f"\nSenseVoice 错误: {s.get('error', '')}")


def main() -> None:
    ap = argparse.ArgumentParser(description="compare Whisper vs SenseVoice")
    ap.add_argument("--audio", help="音频文件路径 (16kHz wav 最佳)")
    ap.add_argument("--video", help="视频文件路径 (先提取音频再测)")
    args = ap.parse_args()

    if not args.audio and not args.video:
        ap.print_help()
        sys.exit(1)

    # 处理视频输入
    if args.video:
        if not os.path.exists(args.video):
            print(f"文件不存在: {args.video}")
            sys.exit(1)
        tmp_dir = tempfile.mkdtemp(prefix="asr_compare_")
        audio_path = os.path.join(tmp_dir, "audio_16k.wav")
        print(f"从视频提取音频: {args.video}")
        if not extract_audio(args.video, audio_path):
            sys.exit(1)
        size = os.path.getsize(audio_path)
        print(f"音频提取成功: {size // 1024}KB")
    else:
        audio_path = args.audio
        if not os.path.exists(audio_path):
            print(f"文件不存在: {audio_path}")
            sys.exit(1)

    print(f"\n测试音频: {audio_path}")
    print(f"文件大小: {os.path.getsize(audio_path) // 1024}KB")

    # 跑两个引擎
    w_result = test_whisper(audio_path)
    s_result = test_sensevoice(audio_path)

    # 对比输出
    print_comparison(w_result, s_result)


if __name__ == "__main__":
    main()

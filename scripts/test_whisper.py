"""测试 Whisper ASR 引擎。

用法:
  cd /Users/ma/WorkBuddy/my-project
  source .venv/bin/activate

  # 1. 只验证安装（不跑 ASR）
  python scripts/test_whisper.py --check

  # 2. 用音频文件测试（首次会下载模型约 1.5GB）
  python scripts/test_whisper.py --audio /path/to/audio.mp3

  # 3. 从视频提取音频再测试（需要 ffmpeg）
  python scripts/test_whisper.py --video /path/to/video.mp4
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.logger import logger


def check_install() -> None:
    """验证 mlx-whisper 安装是否成功。"""
    print("=" * 50)
    print("检查 mlx-whisper 安装")
    print("=" * 50)

    try:
        import mlx_whisper
        print(f"✓ mlx_whisper 版本: {mlx_whisper.__version__}")
    except ImportError as e:
        print(f"✗ mlx_whisper 导入失败: {e}")
        print("  请运行: pip install mlx-whisper")
        sys.exit(1)

    try:
        import mlx
        print(f"✓ mlx 已安装")
    except ImportError:
        print("⚠ mlx 未找到（可能有问题）")

    try:
        import torch
        print(f"✓ torch 版本: {torch.__version__}")
    except ImportError:
        print("⚠ torch 未找到")

    # 检查模型缓存
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    if os.path.exists(cache_dir):
        models = os.listdir(cache_dir)
        whisper_models = [m for m in models if "whisper" in m.lower()]
        if whisper_models:
            print(f"✓ 已缓存的 whisper 模型: {whisper_models}")
        else:
            print("ℹ 尚未下载 whisper 模型（首次运行会自动下载）")
    else:
        print("ℹ 尚未下载任何模型（首次运行会自动下载）")

    print()
    print("安装检查通过 ✓")
    print("模型会在首次 ASR 调用时自动下载（约 1.5GB）")


def test_with_audio(audio_path: str) -> None:
    """用音频文件测试 ASR。"""
    from src.audio.whisper_engine import WhisperEngine

    if not os.path.exists(audio_path):
        print(f"✗ 文件不存在: {audio_path}")
        sys.exit(1)

    print("=" * 50)
    print(f"ASR 测试: {audio_path}")
    print("=" * 50)
    print("首次运行会下载模型（约 1.5GB），请耐心等待...")
    print()

    engine = WhisperEngine()
    result = engine.transcribe(audio_path)

    if not result.success:
        print(f"✗ ASR 失败: {result.error}")
        sys.exit(1)

    print(f"✓ 语种: {result.language}")
    print(f"✓ 时长: {result.duration:.1f}s")
    print(f"✓ 分段数: {len(result.segments)}")
    print(f"✓ 全文长度: {len(result.text)} 字")
    print()
    print("-" * 50)
    print("全文:")
    print(result.text)
    print()
    print("-" * 50)
    print("分段（前 10 段）:")
    for i, seg in enumerate(result.segments[:10]):
        print(f"  [{seg.start:6.1f}s → {seg.end:6.1f}s] {seg.text}")
    if len(result.segments) > 10:
        print(f"  ... 还有 {len(result.segments) - 10} 段")


def test_with_video(video_path: str) -> None:
    """从视频提取音频再测试。"""
    import subprocess

    if not os.path.exists(video_path):
        print(f"✗ 文件不存在: {video_path}")
        sys.exit(1)

    # 用 ffmpeg 提取音频
    tmp_dir = tempfile.mkdtemp(prefix="whisper_test_")
    audio_path = os.path.join(tmp_dir, "audio.mp3")

    print("=" * 50)
    print(f"从视频提取音频: {video_path}")
    print("=" * 50)

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn",                    # 不要视频
        "-acodec", "libmp3lame",
        "-ab", "128k",
        "-ar", "16000",          # 16kHz 够 ASR 用, 减小文件
        "-y",                    # 覆盖
        audio_path,
    ]
    print(f"运行: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"✗ ffmpeg 提取音频失败: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("✗ ffmpeg 未安装")
        print("  请运行: bash scripts/install_ffmpeg.sh")
        sys.exit(1)

    size = os.path.getsize(audio_path)
    print(f"✓ 音频提取成功: {size // 1024}KB")
    print()

    test_with_audio(audio_path)

    # 清理
    try:
        os.remove(audio_path)
        os.rmdir(tmp_dir)
    except OSError:
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="test whisper ASR engine")
    ap.add_argument("--check", action="store_true", help="只检查安装, 不跑 ASR")
    ap.add_argument("--audio", help="音频文件路径 (mp3/wav/m4a)")
    ap.add_argument("--video", help="视频文件路径 (先提取音频再测)")
    args = ap.parse_args()

    if args.check:
        check_install()
    elif args.audio:
        test_with_audio(args.audio)
    elif args.video:
        test_with_video(args.video)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()

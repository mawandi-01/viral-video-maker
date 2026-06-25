#!/bin/bash
# ffmpeg 安装脚本（macOS Apple Silicon / arm64）
# 用途：B站视频用 DASH 格式（音视频分离），yt-dlp 需要 ffmpeg 合并成单个 mp4
#
# 用法：
#   cd /Users/ma/WorkBuddy/my-project
#   bash scripts/install_ffmpeg.sh
#
# 安装位置：/usr/local/bin/ffmpeg 和 /usr/local/bin/ffprobe
# 安装后 yt-dlp 会自动检测到，无需改代码

set -e

echo "=========================================="
echo "  ffmpeg 安装脚本 (macOS arm64)"
echo "=========================================="
echo ""

# 检查是否已安装
if command -v ffmpeg &>/dev/null; then
    echo "[✓] ffmpeg 已安装：$(which ffmpeg)"
    ffmpeg -version | head -1
    echo "无需重复安装。"
    exit 0
fi

echo "[1/4] 检查架构..."
ARCH=$(uname -m)
echo "    架构: $ARCH"
if [ "$ARCH" != "arm64" ]; then
    echo "    ⚠️ 本脚本仅支持 arm64 (Apple Silicon)。"
    echo "    Intel Mac 请用: brew install ffmpeg"
    echo "    或从 https://evermeet.cx/ffmpeg/ 下载 Intel 版本"
    exit 1
fi

echo ""
echo "[2/4] 下载 ffmpeg + ffprobe 静态二进制..."
TMPDIR_FF=$(mktemp -d)
cd "$TMPDIR_FF"

echo "    下载 ffmpeg..."
curl -L --progress-bar -o ffmpeg \
    "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1/ffmpeg-darwin-arm64"

echo "    下载 ffprobe..."
curl -L --progress-bar -o ffprobe \
    "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1/ffprobe-darwin-arm64"

chmod +x ffmpeg ffprobe

echo ""
echo "[3/4] 安装到 /usr/local/bin/（需要 sudo 密码）..."
# 创建 /usr/local/bin 如果不存在
if [ ! -d /usr/local/bin ]; then
    sudo mkdir -p /usr/local/bin
fi

sudo mv ffmpeg /usr/local/bin/ffmpeg
sudo mv ffprobe /usr/local/bin/ffprobe

echo ""
echo "[4/4] 验证安装..."
if command -v ffmpeg &>/dev/null; then
    echo ""
    echo "=========================================="
    echo "  ✅ 安装成功！"
    echo "=========================================="
    echo ""
    ffmpeg -version | head -3
    echo ""
    ffprobe -version | head -1
    echo ""
    echo "现在可以重新运行 worker 下载 B站视频了："
    echo "  cd /Users/ma/WorkBuddy/my-project"
    echo "  source .venv/bin/activate"
    echo "  python scripts/run_worker.py --queue default --burst"
else
    echo "❌ 安装似乎失败，请检查 /usr/local/bin 是否在 PATH 中："
    echo "  echo \$PATH"
    echo "  ls -la /usr/local/bin/ffmpeg"
fi

# 清理
cd /
rm -rf "$TMPDIR_FF"

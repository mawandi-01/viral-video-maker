#!/bin/bash
# 预下载 Whisper 模型（使用国内镜像，避免 HuggingFace 连接失败）
#
# 用法:
#   cd /Users/ma/WorkBuddy/my-project
#   source .venv/bin/activate
#   bash scripts/download_whisper_model.sh

echo "=========================================="
echo "  下载 Whisper 模型 (国内镜像)"
echo "=========================================="
echo ""

# 使用 HuggingFace 国内镜像
export HF_ENDPOINT=https://hf-mirror.com

echo "[1/2] 设置镜像: $HF_ENDPOINT"
echo ""

echo "[2/2] 下载模型 mlx-community/whisper-medium-mlx-4bit (约 1.5GB)"
echo "      首次下载需要 5-15 分钟，取决于网速"
echo "      下载后会缓存到 ~/.cache/huggingface/"
echo ""

python -c "
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
print('开始下载 whisper 模型...')
from huggingface_hub import snapshot_download
path = snapshot_download(
    repo_id='mlx-community/whisper-medium-mlx-4bit',
    repo_type='model',
)
print(f'✅ 模型已下载到: {path}')
print('之后跑 ASR 不再需要联网下载')
" 2>&1

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "  ✅ 下载完成！"
    echo "=========================================="
    echo ""
    echo "现在可以跑提取了："
    echo "  python scripts/extract_video.py --video-id BV1zb7K6bEiA --platform bilibili"
else
    echo ""
    echo "=========================================="
    echo "  ❌ 下载失败"
    echo "=========================================="
    echo ""
    echo "可能的原因："
    echo "  1. 网络不稳定 → 重试几次"
    echo "  2. 镜像也不通 → 尝试用代理下载"
    echo "  3. 磁盘空间不足 → 清理后重试"
    echo ""
    echo "或者跳过 ASR，只用字幕："
    echo "  whisper_engine.py 里改 DEFAULT_MODEL 或跳过 ASR 步骤"
fi

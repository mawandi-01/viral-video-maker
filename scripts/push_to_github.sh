#!/bin/bash
# 推送项目到 GitHub
#
# 用法:
#   cd /Users/ma/WorkBuddy/my-project
#   bash scripts/push_to_github.sh

set -e

TOKEN="YOUR_GITHUB_TOKEN_HERE"
REPO="mawandi-01/viral-video-maker"
REMOTE_URL="https://${TOKEN}@github.com/${REPO}.git"

echo "=========================================="
echo "  推送项目到 GitHub"
echo "=========================================="
echo "仓库: https://github.com/${REPO}"
echo ""

cd /Users/ma/WorkBuddy/my-project

# 初始化 git（如果还没有的话）
if [ ! -d .git ]; then
    echo "[1/5] 初始化 git..."
    git init
    git branch -M main
else
    echo "[1/5] git 已初始化"
fi

# 添加远程
echo "[2/5] 添加远程仓库..."
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"

# 添加文件
echo "[3/5] 添加文件..."
git add -A

# 检查是否有文件待提交
if git diff --cached --quiet; then
    echo "没有文件需要提交（可能已经提交过了）"
else
    echo "[4/5] 提交..."
    git commit -m "feat: 爆款视频AI生成流水线

- 视频采集：yt-dlp + B站/YouTube 热门发现
- 多模态拆解：Claude 看帧 + Whisper ASR + 文案分析
- 融合引擎：跨模态对齐 + 爆款归因
- 模板抽象：去主题留结构，可复用配方
- Prompt 生成：策略模式（ModeB 同主题换形式 / ModeD 跨主题迁移）
- Web 界面：仿抖音深色主题前端 + FastAPI 后端
- 全流程 0 API 成本（CLIProxyAPI 中转站 + 本地 Whisper）"
fi

# 推送
echo "[5/5] 推送到 GitHub..."
git push -u origin main

echo ""
echo "=========================================="
echo "  ✅ 推送完成！"
echo "=========================================="
echo ""
echo "仓库地址: https://github.com/${REPO}"
echo ""
echo "提示: token 已嵌入 remote URL，后续 git push 不需要再输密码。"
echo "如果 token 过期，运行:"
echo "  git remote set-url origin https://<新token>@github.com/${REPO}.git"

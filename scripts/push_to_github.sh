#!/bin/bash
# 推送项目到 GitHub
#
# 安全说明：Token 不硬编码在本脚本里。
#   - 优先读环境变量 GITHUB_TOKEN
#   - 没设置就交互式提示输入（输入时不回显）
#
# 用法:
#   cd /Users/ma/WorkBuddy/my-project
#   # 方式一：环境变量
#   GITHUB_TOKEN=ghp_xxx bash scripts/push_to_github.sh
#   # 方式二：交互输入
#   bash scripts/push_to_github.sh
#   # 方式三：指定 commit 信息
#   bash scripts/push_to_github.sh -m "fix: 修复报告页"
#   # 方式四：只提交不推送（本地 commit）
#   bash scripts/push_to_github.sh --no-push

set -e

REPO="mawandi-01/viral-video-maker"
PROJECT_DIR="/Users/ma/WorkBuddy/my-project"
COMMIT_MSG=""
NO_PUSH=0

# 解析参数
while [ $# -gt 0 ]; do
    case "$1" in
        -m) shift; COMMIT_MSG="$1" ;;
        --no-push) NO_PUSH=1 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
    shift
done

echo "=========================================="
echo "  推送项目到 GitHub"
echo "=========================================="
echo "仓库: https://github.com/${REPO}"
echo ""

# 1. 获取 Token（不硬编码）
TOKEN="${GITHUB_TOKEN:-}"
if [ -z "$TOKEN" ]; then
    echo "未检测到环境变量 GITHUB_TOKEN，请手动输入："
    printf "GitHub Personal Access Token: "
    read -s TOKEN
    echo ""
    if [ -z "$TOKEN" ]; then
        echo "❌ Token 不能为空"
        exit 1
    fi
fi

# 校验 token 格式（ghp_ 开头）
if [[ ! "$TOKEN" =~ ^ghp_ ]]; then
    echo "⚠️  Token 格式看起来不对（通常以 ghp_ 开头），仍继续尝试..."
fi

cd "$PROJECT_DIR"

REMOTE_URL="https://${TOKEN}@github.com/${REPO}.git"

# 2. 初始化 git（如果还没有的话）
if [ ! -d .git ]; then
    echo "[1/5] 初始化 git..."
    git init
    git branch -M main
else
    echo "[1/5] git 已初始化"
fi

# 3. 添加远程（每次重设，确保 token 最新）
echo "[2/5] 配置远程仓库..."
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"

# 4. 添加文件
echo "[3/5] 添加文件..."
git add -A

# 5. 检查是否有文件待提交
if git diff --cached --quiet; then
    echo "没有文件需要提交（工作区干净）"
else
    echo "[4/5] 提交..."
    if [ -z "$COMMIT_MSG" ]; then
        COMMIT_MSG="feat: 更新代码 $(date '+%Y-%m-%d %H:%M')"
    fi
    git commit -m "$COMMIT_MSG"
    echo "提交信息: $COMMIT_MSG"
fi

# 6. 推送
if [ "$NO_PUSH" -eq 1 ]; then
    echo "[5/5] 跳过推送（--no-push）"
else
    echo "[5/5] 推送到 GitHub..."
    git push -u origin main
fi

echo ""
echo "=========================================="
echo "  ✅ 完成！"
echo "=========================================="
echo ""
echo "仓库地址: https://github.com/${REPO}"

# 清理：从 git config 里移除 token，避免残留在 .git/config
# 注意：remote URL 里仍含 token，下面把它换掉
git remote set-url origin "https://github.com/${REPO}.git" 2>/dev/null || true
echo ""
echo "安全提示："
echo "  - 已从 remote URL 移除 token（避免残留在 .git/config）"
echo "  - 后续 git push 需要重新配置 token 或用 credential helper"
echo "  - 推荐：git config --global credential.helper osxkeychain"

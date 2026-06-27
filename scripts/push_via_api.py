#!/usr/bin/env python3
"""通过 GitHub Git Database API 推送文件（绕过本地 git index.lock 问题）。

用 requests 库 + 重试逻辑。

用法:
  cd /Users/ma/WorkBuddy/my-project
  GITHUB_TOKEN=ghp_xxx python scripts/push_via_api.py
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import requests

REPO = "mawandi-01/viral-video-maker"
BRANCH = "main"
PROJECT_DIR = Path(__file__).resolve().parent.parent

TOKEN = os.environ.get("GITHUB_TOKEN", "")
if not TOKEN:
    print("❌ 请设置 GITHUB_TOKEN 环境变量")
    sys.exit(1)

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "viral-video-maker-push",
})
API = f"https://api.github.com/repos/{REPO}/git"


def api_call(method: str, url: str, json_data: dict | None = None, retries: int = 3) -> dict:
    """调用 GitHub API，带重试。"""
    full_url = url if url.startswith("http") else f"{API}/{url.lstrip('/')}"
    for attempt in range(1, retries + 1):
        try:
            r = SESSION.request(method, full_url, json=json_data, timeout=120)
            if r.status_code == 409 and "Git Repository is empty" in r.text:
                return {}
            if r.status_code >= 400:
                print(f"  HTTP {r.status_code}: {r.text[:200]}")
                if r.status_code in (404, 403) and attempt == 1:
                    raise RuntimeError(f"API error {r.status_code}")
                if attempt < retries:
                    time.sleep(3 * attempt)
                    continue
                raise RuntimeError(f"API error {r.status_code}: {r.text[:200]}")
            return r.json() if r.text else {}
        except (requests.Timeout, requests.ConnectionError) as e:
            print(f"  网络错误 (尝试 {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(5 * attempt)
            else:
                raise


def get_head_tree() -> tuple[str | None, str | None]:
    """获取远程 main 的 commit SHA 和 tree SHA。"""
    try:
        ref = api_call("GET", f"https://api.github.com/repos/{REPO}/git/refs/heads/{BRANCH}")
        commit_sha = ref["object"]["sha"]
        commit = api_call("GET", f"https://api.github.com/repos/{REPO}/git/commits/{commit_sha}")
        return commit_sha, commit["tree"]["sha"]
    except Exception as e:
        print(f"  ⚠️ 获取远程状态失败: {e}")
        return None, None


def create_blob(content: bytes, path: str) -> str:
    b64 = base64.b64encode(content).decode()
    r = api_call("POST", "/blobs", {"content": b64, "encoding": "base64"})
    return r["sha"]


def collect_files() -> list[dict]:
    """收集要推送的文件。"""
    ignore_dirs = {".venv", "__pycache__", "logs", "cookies", "bin", "node_modules",
                   "dist", "build", ".idea", ".git", ".extract_cache", "htmlcov",
                   ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".workbuddy"}
    ignore_names = {".env", ".env.local", ".DS_Store"}
    ignore_exts = (".pyc", ".mp4", ".jpg", ".jpeg", ".wav", ".mp3", ".log",
                   ".coverage", ".lock")

    files = []
    for root, dirs, fnames in os.walk(PROJECT_DIR):
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".extract_")]
        for fn in fnames:
            if fn in ignore_names:
                continue
            if fn.endswith(ignore_exts):
                continue
            fp = Path(root) / fn
            try:
                size = fp.stat().st_size
            except OSError:
                continue
            if size > 10 * 1024 * 1024:
                print(f"  ⏭️  跳过大文件: {fp.relative_to(PROJECT_DIR)} ({size//1024}KB)")
                continue
            rel = fp.relative_to(PROJECT_DIR).as_posix()
            try:
                content = fp.read_bytes()
            except Exception:
                continue
            files.append({"path": rel, "content": content, "mode": "100644"})
    return files


def main():
    print(f"=== 推送到 GitHub (via API) ===")
    print(f"仓库: {REPO} / 分支: {BRANCH}")
    print()

    print("[1/5] 收集本地文件...")
    files = collect_files()
    print(f"  共 {len(files)} 个文件")

    print("[2/5] 获取远程 main 当前状态...")
    parent_sha, base_tree = get_head_tree()
    if parent_sha:
        print(f"  parent: {parent_sha[:8]}, tree: {base_tree[:8]}")
    else:
        print("  （空仓库或首次推送）")

    print("[3/5] 上传文件 blobs...")
    tree_items = []
    total = len(files)
    for i, f in enumerate(files, 1):
        try:
            sha = create_blob(f["content"], f["path"])
            tree_items.append({
                "path": f["path"], "mode": f["mode"],
                "type": "blob", "sha": sha,
            })
        except Exception as e:
            print(f"  ❌ blob 失败 {f['path']}: {e}")
            return
        if i % 20 == 0 or i == total:
            print(f"  blob: {i}/{total}")

    print("[4/5] 创建 tree...")
    tree_data = {"tree": tree_items}
    if base_tree:
        tree_data["base_tree"] = base_tree
    new_tree = api_call("POST", "/trees", tree_data)
    print(f"  new tree: {new_tree['sha'][:8]}")

    print("[5/5] 创建 commit 并更新分支...")
    commit_data = {
        "message": "feat: V2 爆款制造机 - 归因+分类+3场景+质量闭环 + 报告页修复\n\n"
                    "V2: 归因引擎+分类器+3场景+质量闭环+SLS+idealab\n"
                    "报告页: V1归因兜底+双主题展示+回填脚本\n"
                    "推送脚本: 去硬编码token改环境变量输入",
        "tree": new_tree["sha"],
    }
    if parent_sha:
        commit_data["parents"] = [parent_sha]
    new_commit = api_call("POST", "/commits", commit_data)
    print(f"  new commit: {new_commit['sha'][:8]}")

    api_call("PATCH", f"https://api.github.com/repos/{REPO}/git/refs/heads/{BRANCH}",
             {"sha": new_commit["sha"], "force": False})

    print()
    print(f"✅ 推送完成！")
    print(f"   commit: {new_commit['sha']}")
    print(f"   文件数: {len(files)}")
    print(f"   仓库: https://github.com/{REPO}")


if __name__ == "__main__":
    main()

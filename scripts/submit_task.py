"""提交采集任务。

用法:
  python scripts/submit_task.py --url "https://www.douyin.com/video/123"
  python scripts/submit_task.py --url "https://www.youtube.com/watch?v=abc123"
  python scripts/submit_task.py --file urls.txt     # 批量
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.platforms import parse_url
from src.queue.task_queue import get_queue
from src.utils.logger import logger


def submit_one(url: str) -> None:
    q = get_queue()
    task = q.submit_url(url)
    logger.info(f"submitted: url={url} task={task.task_id}")


def main() -> None:
    ap = argparse.ArgumentParser(description="submit video collection tasks")
    ap.add_argument("--url", help="single video URL")
    ap.add_argument("--file", help="file with one URL per line")
    args = ap.parse_args()

    urls: list[str] = []
    if args.url:
        urls.append(args.url)
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            urls.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))

    if not urls:
        ap.print_help()
        sys.exit(1)

    for u in urls:
        submit_one(u)


if __name__ == "__main__":
    main()

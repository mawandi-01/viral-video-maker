"""扫描临时性失败的视频,把仍可重试的重新入队。

适合 cron 每小时跑一次:
  0 * * * * cd /path/to/my-project && .venv/bin/python scripts/retry_failed.py

筛选条件:
  download_status = 'failed_transient'
  AND download_attempts < MAX_DOWNLOAD_ATTEMPTS
  AND last_attempt_at < now() - RETRY_COOLDOWN_HOURS

每条命中的记录会被重新提交到 default 队列。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.platforms import Platform
from config.settings import settings
from src.queue.task_queue import get_queue
from src.storage.db import get_db
from src.utils.logger import logger


def main() -> None:
    ap = argparse.ArgumentParser(description="re-enqueue transient-failed videos")
    ap.add_argument("--limit", type=int, default=200, help="max records per run")
    ap.add_argument(
        "--max-attempts",
        type=int,
        default=settings.worker.max_download_attempts,
        help="overrides MAX_DOWNLOAD_ATTEMPTS",
    )
    ap.add_argument(
        "--cooldown-hours",
        type=int,
        default=settings.worker.retry_cooldown_hours,
        help="overrides RETRY_COOLDOWN_HOURS",
    )
    ap.add_argument("--dry-run", action="store_true", help="only print, do not enqueue")
    args = ap.parse_args()

    db = get_db()
    rows = db.list_retryable_videos(
        max_attempts=args.max_attempts,
        cooldown_hours=args.cooldown_hours,
        limit=args.limit,
    )
    if not rows:
        logger.info("no retryable videos")
        return

    logger.info(
        f"found {len(rows)} retryable videos "
        f"(max_attempts={args.max_attempts}, cooldown={args.cooldown_hours}h)"
    )

    if args.dry_run:
        for r in rows:
            logger.info(f"  [dry-run] {r['platform']}:{r['video_id']} {r['url']}")
        return

    q = get_queue()
    submitted = 0
    for r in rows:
        try:
            platform = Platform(r["platform"])
        except ValueError:
            logger.warning(f"unknown platform '{r['platform']}', skip")
            continue
        try:
            task = q.enqueue_download(platform, r["video_id"], r["url"])
            logger.info(f"  re-enqueued: {platform.value}:{r['video_id']} task={task.task_id[:8]}")
            submitted += 1
        except Exception as e:
            logger.warning(f"  enqueue failed for {r['url']}: {e}")

    logger.info(f"retry sweep done. re-enqueued {submitted}/{len(rows)}")


if __name__ == "__main__":
    main()

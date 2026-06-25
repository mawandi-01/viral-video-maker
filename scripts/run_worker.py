"""启动 Worker 消费队列。

用法:
  python scripts/run_worker.py --queue default       # 持续消费
  python scripts/run_worker.py --queue high --burst   # 处理完即退出
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.queue.task_queue import get_queue
from src.storage.db import get_db
from src.utils.logger import logger


def main() -> None:
    ap = argparse.ArgumentParser(description="run a worker to consume task queue")
    ap.add_argument(
        "--queue",
        default="default",
        choices=["high", "default", "low"],
        help="which queue to consume",
    )
    ap.add_argument("--burst", action="store_true", help="exit when queue is empty")
    args = ap.parse_args()

    # 启动前确保 schema 是最新的（幂等：ALTER TABLE ADD COLUMN IF NOT EXISTS）
    # 这样旧库升级时不会因为缺字段报错
    try:
        get_db().init_schema()
        logger.info("schema check ok")
    except Exception as e:
        logger.warning(f"init_schema failed (non-fatal, continuing): {e}")

    logger.info(f"starting worker on queue={args.queue}")
    get_queue().run_worker(queue_name=args.queue, burst=args.burst)


if __name__ == "__main__":
    main()

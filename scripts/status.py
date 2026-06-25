"""查询任务状态。

用法:
  python scripts/status.py                          # 列出最近 20 个任务
  python scripts/status.py --task <task_id>         # 查单个任务
  python scripts/status.py --viral                  # 列出爆款视频
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.db import get_db
from src.utils.logger import logger


def list_tasks(limit: int = 20) -> None:
    db = get_db()
    tasks = db.list_pending_tasks(limit=limit)
    if not tasks:
        print("no pending tasks")
        return
    print(f"{'task_id':36} {'type':20} {'platform':10} {'status':10} {'video_id':20}")
    print("-" * 100)
    for t in tasks:
        print(f"{t.task_id:36} {t.task_type.value:20} {t.platform.value:10} "
              f"{t.status.value:10} {t.video_id:20}")


def show_task(task_id: str) -> None:
    db = get_db()
    t = db.get_task(task_id)
    if not t:
        print(f"task not found: {task_id}")
        return
    for k, v in t.model_dump().items():
        print(f"  {k:20} {v}")


def list_viral() -> None:
    from psycopg2.extras import RealDictCursor
    db = get_db()
    with db.conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT platform, video_id, title, play_count, interaction_rate, is_viral "
                "FROM videos WHERE is_viral = TRUE ORDER BY interaction_rate DESC LIMIT 20"
            )
            rows = cur.fetchall()
    if not rows:
        print("no viral videos yet")
        return
    print(f"{'platform':10} {'video_id':20} {'play':>10} {'rate':>8} title")
    print("-" * 100)
    for r in rows:
        print(f"{r['platform']:10} {r['video_id']:20} {r['play_count']:>10} "
              f"{r['interaction_rate']:>8.4f} {r['title'][:40]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="query task/video status")
    ap.add_argument("--task", help="show single task by id")
    ap.add_argument("--viral", action="store_true", help="list viral videos")
    ap.add_argument("--limit", type=int, default=20, help="list limit")
    args = ap.parse_args()

    if args.task:
        show_task(args.task)
    elif args.viral:
        list_viral()
    else:
        list_tasks(args.limit)


if __name__ == "__main__":
    main()

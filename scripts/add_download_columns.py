"""手动在 PG 上执行 SQL，加缺失的下载状态列。

用法:
  cd /Users/ma/WorkBuddy/my-project
  source .venv/bin/activate
  python scripts/add_download_columns.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.db import get_db
from src.utils.logger import logger


# 单独的 ALTER TABLE 语句，每条一个事务，避免混合 DDL+DML 的事务回滚问题
_STATEMENTS = [
    # 1. 加 4 个下载状态列
    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS download_status TEXT DEFAULT 'pending'",
    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS download_attempts INT DEFAULT 0",
    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ",
    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS download_error TEXT DEFAULT ''",
    # 2. 加索引
    "CREATE INDEX IF NOT EXISTS idx_videos_download_status ON videos(download_status, last_attempt_at)",
]


def main() -> None:
    db = get_db()
    for sql in _STATEMENTS:
        try:
            with db.conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
            logger.info(f"OK: {sql[:80]}")
        except Exception as e:
            logger.error(f"FAIL: {sql[:80]}\n  -> {e}")

    # 验证列已加上
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'videos'
                  AND column_name IN ('download_status','download_attempts','last_attempt_at','download_error')
                ORDER BY column_name
                """
            )
            cols = [r[0] for r in cur.fetchall()]
            print("\n========================================")
            print("videos 表已有的下载状态列:")
            print("----------------------------------------")
            for c in cols:
                print(f"  ✓ {c}")
            print("========================================")
            expected = {'download_status','download_attempts','last_attempt_at','download_error'}
            missing = expected - set(cols)
            if missing:
                print(f"\n⚠️  仍缺失: {missing}")
                sys.exit(1)
            else:
                print("\n✅ 4 个列全部就位，可以重跑 worker 了。")


if __name__ == "__main__":
    main()

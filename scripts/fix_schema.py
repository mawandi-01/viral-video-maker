"""初始化 / 修复 PG schema。

幂等：可以重复跑，ALTER TABLE ADD COLUMN IF NOT EXISTS 不会影响已有列。
旧库升级时跑一次即可补齐缺失字段。

用法:
  python scripts/fix_schema.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.db import get_db
from src.utils.logger import logger


def main() -> None:
    logger.info("initializing / fixing PG schema ...")
    db = get_db()
    db.init_schema()
    logger.info("done. schema is up to date.")

    # 顺便打印一下 videos 表的列，确认字段补齐
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'videos'
                ORDER BY ordinal_position
                """
            )
            print("\nvideos 表当前字段：")
            print("-" * 50)
            for name, dtype in cur.fetchall():
                print(f"  {name:<25} {dtype}")


if __name__ == "__main__":
    main()

"""初始化数据库表。运行: python scripts/init_db.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.db import get_db
from src.utils.logger import logger


def main() -> None:
    logger.info("initializing database schema...")
    db = get_db()
    db.init_schema()
    logger.info("done. tables: collect_tasks, videos, interaction_snapshots, comments")


if __name__ == "__main__":
    main()

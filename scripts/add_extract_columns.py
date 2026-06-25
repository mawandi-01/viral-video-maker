"""加 JSONB 列 + 建 prompt_templates 表。

幂等，可以重复跑。
不动 db.py 的 init_schema，独立执行。

用法:
  cd /Users/ma/WorkBuddy/my-project
  source .venv/bin/activate
  python scripts/add_extract_columns.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.db import get_db
from src.utils.logger import logger


_STATEMENTS = [
    # 1. videos 表加 4 个 JSONB 列
    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS visual_features JSONB DEFAULT '{}'",
    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS audio_features JSONB DEFAULT '{}'",
    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS text_features JSONB DEFAULT '{}'",
    "ALTER TABLE videos ADD COLUMN IF NOT EXISTS template_features JSONB DEFAULT '{}'",
]


_PROMPT_TEMPLATES_SQL = """
CREATE TABLE IF NOT EXISTS prompt_templates (
    template_id      TEXT PRIMARY KEY,
    source_video_id  TEXT NOT NULL,
    source_platform  TEXT NOT NULL,
    template_schema  JSONB NOT NULL,
    category         TEXT DEFAULT '',
    sub_type         TEXT DEFAULT '',
    quality_score    REAL DEFAULT 0,
    usage_count      INT DEFAULT 0,
    created_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_templates_category ON prompt_templates(category, quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_templates_source ON prompt_templates(source_platform, source_video_id);
"""


def main() -> None:
    db = get_db()

    # 1. 加 JSONB 列
    logger.info("adding JSONB columns to videos table ...")
    for sql in _STATEMENTS:
        try:
            with db.conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
            logger.info(f"OK: {sql[:80]}")
        except Exception as e:
            logger.error(f"FAIL: {sql[:80]}\n  -> {e}")

    # 2. 建 prompt_templates 表
    logger.info("creating prompt_templates table ...")
    try:
        with db.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(_PROMPT_TEMPLATES_SQL)
        logger.info("OK: prompt_templates table created")
    except Exception as e:
        logger.error(f"FAIL: prompt_templates\n  -> {e}")

    # 3. 验证
    logger.info("verifying ...")
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'videos'
                  AND column_name IN ('visual_features','audio_features','text_features','template_features')
                ORDER BY column_name
                """
            )
            cols = [r[0] for r in cur.fetchall()]

            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'prompt_templates'
                ORDER BY ordinal_position
                """
            )
            template_cols = [r[0] for r in cur.fetchall()]

    print("\n" + "=" * 50)
    print("videos 表新增的 JSONB 列:")
    print("-" * 50)
    expected = {'visual_features', 'audio_features', 'text_features', 'template_features'}
    for c in cols:
        print(f"  ✓ {c}")
    missing = expected - set(cols)
    if missing:
        print(f"\n⚠️  仍缺失: {missing}")
    else:
        print("\n✅ 4 个 JSONB 列全部就位")

    print("\n" + "=" * 50)
    print("prompt_templates 表字段:")
    print("-" * 50)
    for c in template_cols:
        print(f"  ✓ {c}")
    if template_cols:
        print(f"\n✅ prompt_templates 表就绪（{len(template_cols)} 列）")
    else:
        print("\n⚠️  prompt_templates 表未创建")

    print("\n" + "=" * 50)
    if not missing and template_cols:
        print("✅ 全部就绪，可以跑提取流程了")
    else:
        print("⚠️  有问题，请检查上面的日志")
    print("=" * 50)


if __name__ == "__main__":
    main()

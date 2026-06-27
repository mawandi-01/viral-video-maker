"""V2 数据库升级脚本。

新增表:
- viral_attributions: 爆款归因（因子权重+反事实+迁移指导）
- generation_records: 生成记录+用户反馈

升级表:
- prompt_templates: 加 video_type / attribution_id / generation_count / adoption_count / avg_generated_rate / quality_score_v2

幂等，可以重复跑。

用法:
  cd /Users/ma/WorkBuddy/my-project
  source .venv/bin/activate
  python scripts/add_v2_tables.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.db import get_db
from src.utils.logger import logger


# 新建表
_CREATE_TABLES = [
    # 爆款归因表
    """
    CREATE TABLE IF NOT EXISTS viral_attributions (
        attribution_id      TEXT PRIMARY KEY,
        source_video_id     TEXT NOT NULL,
        source_platform     TEXT NOT NULL,
        video_type          TEXT DEFAULT '',
        primary_factor      TEXT DEFAULT '',
        primary_weight      REAL DEFAULT 0,
        factors             JSONB DEFAULT '[]',
        critical_factors    JSONB DEFAULT '[]',
        removable_factors   JSONB DEFAULT '[]',
        migration_guide     JSONB DEFAULT '{}',
        created_at          TIMESTAMPTZ DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_attr_video ON viral_attributions(source_platform, source_video_id)",
    "CREATE INDEX IF NOT EXISTS idx_attr_type ON viral_attributions(video_type)",

    # 生成记录表（质量闭环）
    """
    CREATE TABLE IF NOT EXISTS generation_records (
        record_id           TEXT PRIMARY KEY,
        template_id         TEXT,
        attribution_id      TEXT,
        scene_type          TEXT DEFAULT '',
        video_type          TEXT DEFAULT '',
        user_theme          TEXT DEFAULT '',
        user_input          JSONB DEFAULT '{}',
        selected_factors    JSONB DEFAULT '[]',
        prompt_package      JSONB DEFAULT '{}',
        status              TEXT DEFAULT 'generated',
        feedback            TEXT DEFAULT '',
        published_url       TEXT DEFAULT '',
        published_platform  TEXT DEFAULT '',
        actual_play_count   BIGINT DEFAULT 0,
        actual_like_count   BIGINT DEFAULT 0,
        actual_interaction_rate REAL DEFAULT 0,
        expected_rate       REAL DEFAULT 0,
        surprise_score      REAL DEFAULT 0,
        created_at          TIMESTAMPTZ DEFAULT now(),
        collected_at        TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_gen_template ON generation_records(template_id)",
    "CREATE INDEX IF NOT EXISTS idx_gen_status ON generation_records(status)",
]

# prompt_templates 升级（加字段）
_ALTER_TEMPLATES = [
    "ALTER TABLE prompt_templates ADD COLUMN IF NOT EXISTS video_type TEXT DEFAULT ''",
    "ALTER TABLE prompt_templates ADD COLUMN IF NOT EXISTS attribution_id TEXT DEFAULT ''",
    "ALTER TABLE prompt_templates ADD COLUMN IF NOT EXISTS generation_count INT DEFAULT 0",
    "ALTER TABLE prompt_templates ADD COLUMN IF NOT EXISTS adoption_count INT DEFAULT 0",
    "ALTER TABLE prompt_templates ADD COLUMN IF NOT EXISTS avg_generated_rate REAL DEFAULT 0",
    "ALTER TABLE prompt_templates ADD COLUMN IF NOT EXISTS quality_score_v2 REAL DEFAULT 0",
]


def main() -> None:
    db = get_db()

    logger.info("=== V2 数据库升级 ===")

    # 1. 新建表
    for sql in _CREATE_TABLES:
        try:
            with db.conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
            logger.info(f"OK: {sql.strip()[:80]}")
        except Exception as e:
            logger.error(f"FAIL: {e}")

    # 2. 升级 prompt_templates
    for sql in _ALTER_TEMPLATES:
        try:
            with db.conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
            logger.info(f"OK: {sql.strip()[:80]}")
        except Exception as e:
            logger.error(f"FAIL: {e}")

    # 3. 验证
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name IN ('viral_attributions','generation_records')
            """)
            tables = [r[0] for r in cur.fetchall()]

            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'prompt_templates'
                  AND column_name IN ('video_type','attribution_id','generation_count',
                                      'adoption_count','avg_generated_rate','quality_score_v2')
            """)
            cols = [r[0] for r in cur.fetchall()]

    print("\n" + "=" * 50)
    print("V2 数据库升级结果")
    print("=" * 50)
    print(f"\n新增表: {tables}")
    print(f"prompt_templates 新增字段: {cols}")
    expected = {'video_type','attribution_id','generation_count','adoption_count','avg_generated_rate','quality_score_v2'}
    if set(tables) == {'viral_attributions','generation_records'} and set(cols) == expected:
        print("\n✅ 全部就绪")
    else:
        print("\n⚠️ 部分缺失，检查日志")


if __name__ == "__main__":
    main()

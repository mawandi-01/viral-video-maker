"""回填脚本 · 给已拆解但缺 V2 归因的视频补跑爆款归因。

V1 拆解的视频只有 template_features，没有 attribution。
本脚本读取这些视频的 template_features，调用 AttributionEngine 生成归因，
写入 viral_attributions 表，并把 attribution_id 回填到 prompt_templates。

幂等：已经有 attribution 的视频会跳过。

用法:
  cd /Users/ma/WorkBuddy/my-project
  source .venv/bin/activate
  python scripts/backfill_attribution.py            # 跑全部
  python scripts/backfill_attribution.py --limit 2  # 只跑前2个
  python scripts/backfill_attribution.py --dry-run  # 只看会跑哪些
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage.db import get_db
from src.extract.attribution_engine import AttributionEngine
from src.utils.logger import logger


def list_candidates(limit: int):
    """列出已拆解但缺归因的视频。

    返回 [(platform, video_id, template_features), ...]
    """
    db = get_db()
    with db.conn() as conn:
        with conn.cursor() as cur:
            # 已拆解的视频 (有 template_features)，且对应 template 还没 attribution_id
            cur.execute(
                """
                SELECT v.platform, v.video_id, v.template_features
                FROM videos v
                JOIN prompt_templates t
                  ON t.source_platform = v.platform AND t.source_video_id = v.video_id
                WHERE v.template_features IS NOT NULL
                  AND v.template_features::text NOT IN ('null', '{}', '[]')
                  AND (t.attribution_id IS NULL OR t.attribution_id = '')
                ORDER BY v.collected_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    out = []
    for r in rows:
        tf = r[2]
        if isinstance(tf, str):
            try:
                tf = json.loads(tf or "{}")
            except Exception:
                tf = {}
        out.append((r[0], r[1], tf))
    return out


def save_attribution(platform: str, video_id: str, attribution: dict) -> str:
    """写入归因，返回 attribution_id。"""
    if not attribution:
        return ""
    from psycopg2.extras import Json
    db = get_db()
    attribution_id = str(uuid4())
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO viral_attributions
                   (attribution_id, source_video_id, source_platform,
                    video_type, primary_factor, primary_weight,
                    factors, critical_factors, removable_factors, migration_guide)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    attribution_id, video_id, platform,
                    attribution.get("video_type", ""),
                    attribution.get("primary_factor", ""),
                    float(attribution.get("primary_weight", 0) or 0),
                    Json(attribution.get("factors", [])),
                    Json(attribution.get("critical_factors", [])),
                    Json(attribution.get("removable_factors", [])),
                    Json(attribution.get("migration_guide", {})),
                ),
            )
            # 回填到 prompt_templates
            cur.execute(
                """UPDATE prompt_templates
                   SET attribution_id = %s,
                       video_type = COALESCE(NULLIF(video_type, ''), %s)
                   WHERE source_platform = %s AND source_video_id = %s""",
                (
                    attribution_id,
                    attribution.get("video_type", ""),
                    platform, video_id,
                ),
            )
    return attribution_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50, help="最多跑多少个视频")
    ap.add_argument("--dry-run", action="store_true", help="只列出不执行")
    args = ap.parse_args()

    logger.info("=== 回填爆款归因 ===")
    cands = list_candidates(args.limit)
    logger.info(f"待回填视频数: {len(cands)}")

    if args.dry_run:
        for p, vid, tf in cands:
            title = (tf or {}).get("video_topic", "") or vid
            print(f"  - {p}/{vid}  {title}")
        return

    if not cands:
        print("没有需要回填的视频，全部已有归因 ✅")
        return

    engine = AttributionEngine()
    ok, fail = 0, 0
    for i, (platform, video_id, tf) in enumerate(cands, 1):
        title = (tf or {}).get("video_topic", "") or video_id
        logger.info(f"[{i}/{len(cands)}] {platform}/{video_id} - {title}")
        try:
            attribution = engine.analyze(tf or {})
            if not attribution or not attribution.get("factors"):
                logger.warning(f"  归因为空，跳过")
                fail += 1
                continue
            aid = save_attribution(platform, video_id, attribution)
            logger.info(
                f"  ✅ aid={aid[:8]} type={attribution.get('video_type','N/A')} "
                f"primary={attribution.get('primary_factor','N/A')} "
                f"({(float(attribution.get('primary_weight',0) or 0)*100):.0f}%)"
            )
            ok += 1
        except Exception as e:
            logger.error(f"  ❌ 失败: {e}")
            fail += 1

    print("\n" + "=" * 50)
    print(f"回填完成: 成功 {ok} / 失败 {fail} / 共 {len(cands)}")
    if ok > 0:
        print("现在可以打开 http://localhost:8765 → 我的视频 → 查看拆解报告，看到「为什么能火」了")


if __name__ == "__main__":
    main()

"""阶段一入口 · 对已下载的视频跑多模态提取。

用法:
  cd /Users/ma/WorkBuddy/my-project
  source .venv/bin/activate

  # 对单个视频跑提取
  python scripts/extract_video.py --video-id BV1zb7K6bEiA --platform bilibili

  # 批量跑所有已下载但未提取的视频
  python scripts/extract_video.py --all

  # 列出可提取的视频（不实际跑）
  python scripts/extract_video.py --list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.platforms import Platform
from src.storage.db import get_db
from src.utils.logger import logger


def list_extractable() -> None:
    """列出已下载但未提取的视频。"""
    db = get_db()
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT platform, video_id, title, oss_key, template_features
                FROM videos
                WHERE oss_key <> ''
                ORDER BY collected_at DESC
                """
            )
            rows = cur.fetchall()

    print("\n" + "=" * 80)
    print(f"已下载视频（共 {len(rows)} 个）")
    print("=" * 80)
    for platform, video_id, title, oss_key, tf in rows:
        extracted = bool(tf and tf != '{}')
        status = "✓ 已提取" if extracted else "✗ 未提取"
        title_short = (title or "")[:30]
        print(f"  [{platform}] {video_id}  {title_short}  {status}")

    unextracted = [r for r in rows if not (r[4] and r[4] != '{}')]
    print(f"\n未提取: {len(unextracted)} 个")
    if unextracted:
        print("可以跑: python scripts/extract_video.py --all")


def extract_one(platform: str, video_id: str) -> bool:
    """对单个视频跑提取。"""
    from src.workers.extract_worker import ExtractWorker

    logger.info(f"=== extract: {platform}/{video_id} ===")
    worker = ExtractWorker()
    return worker.execute(Platform(platform), video_id)


def extract_all() -> None:
    """批量提取所有未提取的视频。"""
    db = get_db()
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT platform, video_id
                FROM videos
                WHERE oss_key <> ''
                  AND (template_features = '{}'::jsonb OR template_features IS NULL)
                ORDER BY collected_at ASC
                """
            )
            rows = cur.fetchall()

    if not rows:
        print("没有未提取的视频")
        return

    print(f"\n将提取 {len(rows)} 个视频")
    print("=" * 60)

    success = 0
    failed = 0
    for i, (platform, video_id) in enumerate(rows, 1):
        print(f"\n[{i}/{len(rows)}] {platform}/{video_id}")
        try:
            ok = extract_one(platform, video_id)
            if ok:
                success += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"extract failed: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"完成: 成功 {success}, 失败 {failed}")


def main() -> None:
    ap = argparse.ArgumentParser(description="run multimodal extraction on videos")
    ap.add_argument("--video-id", help="single video ID")
    ap.add_argument("--platform", default="bilibili", help="platform (default: bilibili)")
    ap.add_argument("--all", action="store_true", help="extract all unextracted videos")
    ap.add_argument("--list", action="store_true", help="list extractable videos")
    args = ap.parse_args()

    if args.list:
        list_extractable()
    elif args.all:
        extract_all()
    elif args.video_id:
        ok = extract_one(args.platform, args.video_id)
        print(f"\n{'✅ 成功' if ok else '❌ 失败'}")
        sys.exit(0 if ok else 1)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()

"""爆款发现脚本。

用法:
  # 跑所有启用的平台（默认 bilibili + youtube）
  python scripts/run_discovery.py

  # 只跑指定平台
  python scripts/run_discovery.py --platforms bilibili
  python scripts/run_discovery.py --platforms bilibili,youtube,douyin

  # 限制每个平台拉多少条
  python scripts/run_discovery.py --top-n 20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from src.discovery import run_discovery
from src.discovery.base_discoverer import BaseDiscoverer
from src.discovery.bilibili_discoverer import BilibiliDiscoverer
from src.discovery.youtube_discoverer import YouTubeDiscoverer
from src.discovery.douyin_discoverer import DouyinDiscoverer
from src.utils.logger import logger


_DISCOVERERS = {
    "bilibili": BilibiliDiscoverer,
    "youtube": YouTubeDiscoverer,
    "douyin": DouyinDiscoverer,
}


def main() -> None:
    ap = argparse.ArgumentParser(description="discover viral videos from platforms")
    ap.add_argument(
        "--platforms",
        help=f"comma-separated platform names (default: {settings.discovery.enabled_platforms})",
    )
    ap.add_argument("--top-n", type=int, default=0, help="limit per platform (0=use config)")
    args = ap.parse_args()

    platforms = (args.platforms or settings.discovery.enabled_platforms).split(",")
    platforms = [p.strip().lower() for p in platforms if p.strip()]

    logger.info(f"discovery start, platforms={platforms} top_n={args.top_n or '(config)'}")

    total = 0
    breakdown = {}
    for name in platforms:
        cls = _DISCOVERERS.get(name)
        if not cls:
            logger.warning(f"unknown platform: {name}")
            continue
        logger.info(f"=== discovering {name} ===")
        try:
            submitted = cls().discover_and_submit(top_n=args.top_n or 50)
            breakdown[name] = submitted
            total += submitted
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            breakdown[name] = 0

    logger.info(f"=== discovery done ===")
    logger.info(f"total submitted: {total}")
    logger.info(f"breakdown: {breakdown}")


if __name__ == "__main__":
    main()

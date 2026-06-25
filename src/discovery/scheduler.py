"""爆款发现调度器。

按配置启用的平台,并行/串行跑各平台发现器,提交下载任务。
"""
from __future__ import annotations

from typing import Optional
from loguru import logger

from config.settings import settings
from src.discovery.base_discoverer import BaseDiscoverer
from src.discovery.bilibili_discoverer import BilibiliDiscoverer
from src.discovery.youtube_discoverer import YouTubeDiscoverer
from src.discovery.douyin_discoverer import DouyinDiscoverer


_DISCOVERERS: dict[str, type[BaseDiscoverer]] = {
    "bilibili": BilibiliDiscoverer,
    "youtube": YouTubeDiscoverer,
    "douyin": DouyinDiscoverer,
}


def run_discovery(
    platforms: Optional[list[str]] = None,
    top_n: int = 0,
) -> dict[str, int]:
    """跑指定平台的爆款发现。

    Args:
        platforms: 要跑的平台名列表(bilibili/youtube/douyin)。None 时读 settings。
        top_n: 每个平台抓取上限。0 时用各平台默认配置。

    Returns:
        {platform_name: submitted_count}
    """
    if platforms:
        enabled = [p.strip().lower() for p in platforms if p and p.strip()]
    else:
        enabled = [
            p.strip().lower()
            for p in settings.discovery.enabled_platforms.split(",")
            if p.strip()
        ]
    logger.info(f"discovery started, platforms={enabled} top_n={top_n or '(config)'}")

    results: dict[str, int] = {}
    for name in enabled:
        cls = _DISCOVERERS.get(name)
        if not cls:
            logger.warning(f"unknown platform: {name}, skip")
            continue

        logger.info(f"=== discovering {name} ===")
        try:
            submitted = cls().discover_and_submit(top_n=top_n or 50)
            results[name] = submitted
        except Exception as e:
            logger.error(f"{name} discovery failed: {e}")
            results[name] = 0

    total = sum(results.values())
    logger.info(f"discovery done. total submitted: {total}, breakdown: {results}")
    return results


if __name__ == "__main__":
    run_discovery()

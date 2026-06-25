"""抖音爆款发现器。

抖音没有公开热门 API，0-1 阶段用「URL 池」模式：
- 你手动维护一个 config/douyin_hot.txt 文件，每行一个抖音视频 URL
- 来源：抖音 APP 热榜页截图后 OCR，或手动从抖音网页版热榜页复制
- 发现器读取该文件，解析 URL，提交下载

规模化阶段：接入第三方数据 API（飞瓜/蝉妈妈）后，本类改为从 API 拉热门列表。
"""
from __future__ import annotations

import os
from loguru import logger

from config.platforms import Platform, parse_url
from config.settings import settings
from src.discovery.base_discoverer import BaseDiscoverer, HotVideo


class DouyinDiscoverer(BaseDiscoverer):
    platform = Platform.DOUYIN

    def fetch_hot(self, top_n: int = 50) -> list[HotVideo]:
        cfg = settings.discovery
        top_n = top_n or cfg.douyin_top_n
        pool_file = cfg.douyin_url_pool

        if not os.path.exists(pool_file):
            logger.warning(
                f"douyin url pool not found: {pool_file}\n"
                f"create it with one URL per line, e.g.:\n"
                f"  https://www.douyin.com/video/7234567890123456\n"
                f"  https://www.douyin.com/discover?modal_id=7234567890123456"
            )
            return []

        results: list[HotVideo] = []
        with open(pool_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parsed = parse_url(line)
                if parsed.platform != Platform.DOUYIN or not parsed.video_id:
                    logger.warning(f"skip invalid douyin url: {line}")
                    continue

                results.append(HotVideo(
                    platform=self.platform,
                    video_id=parsed.video_id,
                    url=parsed.raw_url,
                ))

                if len(results) >= top_n:
                    break

        logger.info(f"douyin url pool loaded: {len(results)} urls from {pool_file}")
        return results

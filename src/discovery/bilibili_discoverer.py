"""B站爆款发现器。

B站有公开的热门视频 API，无需任何鉴权即可拿到 top 100 热门视频的元数据。
API: https://api.bilibili.com/x/web-interface/popular?ps=20&pn=1
"""
from __future__ import annotations

import httpx
from loguru import logger

from config.platforms import Platform
from config.settings import settings
from src.discovery.base_discoverer import BaseDiscoverer, HotVideo


class BilibiliDiscoverer(BaseDiscoverer):
    platform = Platform.BILIBILI

    API_URL = "https://api.bilibili.com/x/web-interface/popular"

    def fetch_hot(self, top_n: int = 50) -> list[HotVideo]:
        cfg = settings.discovery
        top_n = top_n or cfg.bilibili_top_n

        ps = 20  # 每页 20 条
        pages = (top_n + ps - 1) // ps
        results: list[HotVideo] = []

        with httpx.Client(timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as client:
            for pn in range(1, pages + 1):
                try:
                    r = client.get(self.API_URL, params={"ps": ps, "pn": pn})
                    r.raise_for_status()
                    data = r.json()
                except Exception as e:
                    logger.warning(f"bilibili popular pn={pn} failed: {e}")
                    continue

                if data.get("code") != 0:
                    logger.warning(f"bilibili api error: {data.get('message')}")
                    continue

                for item in data.get("data", {}).get("list", []):
                    stat = item.get("stat", {})
                    owner = item.get("owner", {})
                    bvid = item.get("bvid", "")
                    if not bvid:
                        continue

                    results.append(HotVideo(
                        platform=self.platform,
                        video_id=bvid,
                        url=f"https://www.bilibili.com/video/{bvid}",
                        title=item.get("title", ""),
                        author_name=owner.get("name", ""),
                        play_count=int(stat.get("view", 0) or 0),
                        like_count=int(stat.get("like", 0) or 0),
                        comment_count=int(stat.get("reply", 0) or 0),
                        share_count=int(stat.get("share", 0) or 0),
                        duration=int(item.get("duration", 0) or 0),
                    ))

                    if len(results) >= top_n:
                        return results

        return results

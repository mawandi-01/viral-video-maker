"""YouTube 爆款发现器。

用 yt-dlp 拉 YouTube Trending 列表，再用 YouTube Data API v3 补互动数据。
0-1 阶段无 API key 时，仅用 yt-dlp 提取的字段（部分指标缺失）。
"""
from __future__ import annotations

from typing import Optional
from loguru import logger
import yt_dlp

from config.platforms import Platform
from config.settings import settings
from src.discovery.base_discoverer import BaseDiscoverer, HotVideo


class YouTubeDiscoverer(BaseDiscoverer):
    platform = Platform.YOUTUBE

    TRENDING_URL = "https://www.youtube.com/feed/trending"

    def fetch_hot(self, top_n: int = 50) -> list[HotVideo]:
        cfg = settings.discovery
        top_n = top_n or cfg.youtube_top_n

        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,  # 只提取列表，不下载
            "skip_download": True,
            "playlistend": top_n,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.TRENDING_URL, download=False)
        except Exception as e:
            logger.error(f"youtube trending extract failed: {e}")
            return []

        entries = info.get("entries", []) if info else []
        results: list[HotVideo] = []

        for e in entries:
            if not e:
                continue
            vid = e.get("id", "")
            if not vid:
                continue

            results.append(HotVideo(
                platform=self.platform,
                video_id=vid,
                url=f"https://www.youtube.com/watch?v={vid}",
                title=e.get("title", ""),
                author_name=e.get("uploader", "") or e.get("channel", ""),
                play_count=int(e.get("view_count", 0) or 0),
                like_count=0,  # flat 模式拿不到，需后续补
                comment_count=0,
                share_count=0,
                duration=int(e.get("duration", 0) or 0),
            ))

            if len(results) >= top_n:
                break

        # 如果配了 YouTube API key，补互动数据
        if settings.youtube_api_key and results:
            self._enrich_with_api(results)

        return results

    def _enrich_with_api(self, videos: list[HotVideo]) -> None:
        """用 YouTube Data API v3 批量补点赞/评论数。"""
        import httpx

        api_key = settings.youtube_api_key
        ids = [v.video_id for v in videos if v.video_id]

        # API 单次最多 50 个 ID
        for i in range(0, len(ids), 50):
            batch = ids[i:i + 50]
            try:
                r = httpx.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={
                        "key": api_key,
                        "id": ",".join(batch),
                        "part": "statistics",
                    },
                    timeout=15,
                )
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                logger.warning(f"youtube api batch {i} failed: {e}")
                continue

            stat_map = {
                item["id"]: item.get("statistics", {})
                for item in data.get("items", [])
            }
            for v in videos:
                if v.video_id in stat_map:
                    s = stat_map[v.video_id]
                    v.like_count = int(s.get("likeCount", 0) or 0)
                    v.comment_count = int(s.get("commentCount", 0) or 0)
                    if not v.play_count:
                        v.play_count = int(s.get("viewCount", 0) or 0)

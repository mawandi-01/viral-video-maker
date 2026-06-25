"""YouTube Data API v3。官方合规，需 Google API Key。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from loguru import logger

from config.settings import settings
from config.platforms import Platform
from src.apis.base_api import BaseDataAPI
from src.models.video import VideoMeta
from src.models.comment import Comment


class YouTubeAPI(BaseDataAPI):
    name = "youtube"
    BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(self) -> None:
        self.api_key = settings.youtube.api_key

    def fetch_meta(self, platform: Platform, video_id: str, url: str) -> Optional[VideoMeta]:
        if platform != Platform.YOUTUBE or not self.api_key:
            return None
        data = self._get(
            f"{self.BASE}/videos",
            params={
                "key": self.api_key,
                "id": video_id,
                "part": "snippet,statistics,contentDetails",
            },
        )
        if not data or not data.get("items"):
            return None
        item = data["items"][0]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        cd = item.get("contentDetails", {})

        play = int(stats.get("viewCount", 0))
        like = int(stats.get("likeCount", 0))
        comment_n = int(stats.get("commentCount", 0))
        interaction_rate = (like + comment_n) / play if play > 0 else 0

        duration = 0
        iso = cd.get("duration", "")
        if iso:
            duration = self._parse_iso_duration(iso)

        return VideoMeta(
            video_id=video_id,
            platform=platform,
            url=url,
            title=snippet.get("title", ""),
            desc=snippet.get("description", ""),
            author_name=snippet.get("channelTitle", ""),
            author_id=snippet.get("channelId", ""),
            cover_url=(snippet.get("thumbnails") or {}).get("high", {}).get("url", ""),
            duration=duration,
            tags=snippet.get("tags") or [],
            published_at=datetime.fromisoformat(
                snippet.get("publishedAt", "").replace("Z", "+00:00")
            ) if snippet.get("publishedAt") else None,
            play_count=play,
            like_count=like,
            comment_count=comment_n,
            interaction_rate=round(interaction_rate, 4),
            data_source="youtube_api",
        )

    def fetch_comments(self, platform: Platform, video_id: str, limit: int = 100) -> list[Comment]:
        if platform != Platform.YOUTUBE or not self.api_key:
            return []
        comments: list[Comment] = []
        page_token = ""
        while len(comments) < limit:
            params = {
                "key": self.api_key,
                "videoId": video_id,
                "part": "snippet",
                "maxResults": 50,
                "order": "relevance",
                "textFormat": "plainText",
            }
            if page_token:
                params["pageToken"] = page_token
            data = self._get(f"{self.BASE}/commentThreads", params=params)
            if not data:
                break
            for item in data.get("items", []):
                top = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                published_at = None
                if top.get("publishedAt"):
                    published_at = datetime.fromisoformat(
                        top["publishedAt"].replace("Z", "+00:00")
                    )
                comments.append(Comment(
                    video_id=video_id,
                    platform=platform,
                    comment_id=item.get("id", ""),
                    author_name=top.get("authorDisplayName", ""),
                    author_id=top.get("authorChannelId", {}).get("value", ""),
                    content=top.get("textDisplay", ""),
                    like_count=int(top.get("likeCount", 0)),
                    reply_count=int(item.get("snippet", {}).get("totalReplyCount", 0)),
                    is_top=True,
                    published_at=published_at,
                ))
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break
        return comments[:limit]

    @staticmethod
    def _parse_iso_duration(iso: str) -> int:
        import re
        m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
        if not m:
            return 0
        h, mi, s = m.groups()
        return int(h or 0) * 3600 + int(mi or 0) * 60 + int(s or 0)

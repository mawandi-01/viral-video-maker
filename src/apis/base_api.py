"""第三方数据 API 基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
import httpx
from loguru import logger

from src.models.video import VideoMeta
from src.models.comment import Comment
from config.platforms import Platform


class BaseDataAPI(ABC):
    """第三方/官方数据 API 的统一接口。"""

    name: str = "base"

    @abstractmethod
    def fetch_meta(self, platform: Platform, video_id: str, url: str) -> Optional[VideoMeta]:
        ...

    @abstractmethod
    def fetch_comments(
        self, platform: Platform, video_id: str, limit: int = 100
    ) -> list[Comment]:
        ...

    def _get(self, url: str, **kwargs) -> Optional[dict]:
        try:
            r = httpx.get(url, timeout=20, follow_redirects=True, **kwargs)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"[{self.name}] GET {url} failed: {e}")
            return None

    def _post(self, url: str, **kwargs) -> Optional[dict]:
        try:
            r = httpx.post(url, timeout=20, **kwargs)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"[{self.name}] POST {url} failed: {e}")
            return None

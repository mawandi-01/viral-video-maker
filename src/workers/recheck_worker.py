"""Worker D · 72h 互动数据回抓（0-1 阶段不启用）。

数据源：yt-dlp 重跑同一 URL 拿当前互动值（不依赖任何 API）。
规模化阶段启用，用于爆款归因（SHAP）和模板评分。
0-1 阶段不被调度，保留代码骨架。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from config.platforms import Platform
from config.settings import settings
from src.models.task import CollectTask, TaskType
from src.models.video import InteractionSnapshot
from src.storage.db import get_db
from src.workers.base_worker import BaseWorker


class RecheckWorker(BaseWorker):
    """用 yt-dlp 重跑同一 URL 拿 72h 后的互动稳定值。"""

    task_type = TaskType.RECHECK_INTERACTION

    @classmethod
    def execute(cls, platform: Platform, video_id: str, task_id: str) -> bool:
        task = cls._start(task_id)
        if not task:
            return False
        try:
            db = get_db()
            meta = db.get_video_meta(platform.value, video_id)
            if not meta:
                raise RuntimeError("meta not found, run VideoWorker first")

            # 用 yt-dlp 重跑（只提取 info，不下载）
            fresh = cls._refetch_via_ytdlp(platform, video_id, meta.url)
            if not fresh:
                raise RuntimeError("yt-dlp re-fetch returned empty")

            play = fresh.get("view_count", 0) or 0
            like = fresh.get("like_count", 0) or 0
            comment_n = fresh.get("comment_count", 0) or 0
            share = fresh.get("repost_count", 0) or 0
            interaction_rate = (like + comment_n + share) / play if play > 0 else 0

            snap = InteractionSnapshot(
                video_id=video_id,
                platform=platform,
                play_count=play,
                like_count=like,
                comment_count=comment_n,
                share_count=share,
                interaction_rate=round(interaction_rate, 4),
                snapshot_at=datetime.now(timezone.utc),
                hours_after_publish=cls._hours_since_publish(meta),
            )
            db.upsert_interaction_snapshot(snap)

            meta.play_count = play
            meta.like_count = like
            meta.comment_count = comment_n
            meta.share_count = share
            meta.interaction_rate = round(interaction_rate, 4)
            db.upsert_video_meta(meta)

            cls._succeed(
                task,
                f"play={play} like={like} rate={interaction_rate:.4f} viral={meta.is_viral}",
            )
            return True
        except Exception as e:
            cls._fail(task, str(e))
            return False

    @staticmethod
    def _refetch_via_ytdlp(platform: Platform, video_id: str, url: str) -> Optional[dict]:
        """用 yt-dlp 只提取 info，不下载文件。"""
        import yt_dlp
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            logger.error(f"recheck yt-dlp failed for {url}: {e}")
            return None

    @staticmethod
    def _hours_since_publish(meta) -> int:
        if not meta.published_at:
            return 72
        if meta.published_at.tzinfo is None:
            meta.published_at = meta.published_at.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - meta.published_at
        return int(delta.total_seconds() // 3600)


def run_recheck_interaction(platform_str: str, video_id: str, task_id: str) -> bool:
    """rq 入口函数。"""
    platform = Platform(platform_str)
    return RecheckWorker.execute(platform, video_id, task_id)

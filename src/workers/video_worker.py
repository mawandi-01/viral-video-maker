"""Worker B · 视频下载 + 元数据提取 + OSS 上传。

yt-dlp 的 extract_info() 一次返回：视频文件 + 封面 + 标题/作者/播放量/点赞/评论数/时长/标签。
0-1 阶段无需第三方数据 API，本 Worker 即可完成 Tier A + Tier B 大部分字段。
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from config.platforms import Platform
from config.settings import settings
from src.downloaders import get_downloader
from src.models.task import CollectTask, TaskType
from src.models.video import VideoFile, VideoMeta
from src.storage.db import get_db
from src.storage.oss_storage import get_oss, OSSStorage
from src.workers.base_worker import BaseWorker
from src.workers.error_classifier import is_permanent
from src.queue.task_queue import get_queue


class VideoWorker(BaseWorker):
    task_type = TaskType.DOWNLOAD_VIDEO

    @classmethod
    def execute(
        cls,
        platform: Platform,
        video_id: str,
        url: str,
        task_id: str,
        oss: Optional[OSSStorage] = None,
    ) -> bool:
        task = cls._start(task_id)
        if not task:
            return False
        oss = oss or get_oss()
        db = get_db()
        download_dir = tempfile.mkdtemp(prefix="vc_")

        # 记录一次下载尝试(attempts+1, last_attempt_at=now, status=running)
        # discovery 已经 upsert 过 metadata 行了,这里只更新状态字段
        try:
            db.mark_download_attempt(platform.value, video_id)
        except Exception as e:
            logger.warning(f"mark_download_attempt failed: {e}")

        try:
            downloader = get_downloader(
                platform,
                download_dir=download_dir,
                timeout=settings.worker.download_timeout,
            )
            result = downloader.download(url, video_id=video_id)
            if not result.success:
                raise RuntimeError(result.error or "download failed")

            oss_key = oss.upload_video(result.video_path, platform.value, video_id)
            cover_oss_key = ""
            if result.cover_path and os.path.exists(result.cover_path):
                cover_oss_key = oss.upload_cover(result.cover_path, platform.value, video_id)

            md5 = OSSStorage.file_md5(result.video_path)
            vf = VideoFile(
                video_id=video_id,
                platform=platform,
                oss_key=oss_key,
                oss_bucket=settings.oss.bucket_name,
                file_size=result.file_size,
                file_md5=md5,
                format="mp4",
                duration=result.duration,
                width=result.width,
                height=result.height,
                cover_oss_key=cover_oss_key,
            )
            db.update_video_file(vf)

            meta = cls._extract_meta(platform, video_id, url, result)
            if meta:
                db.upsert_video_meta(meta)
                logger.info(
                    f"meta extracted from yt-dlp: play={meta.play_count} "
                    f"like={meta.like_count} viral={meta.is_viral}"
                )

            db.mark_download_status(platform.value, video_id, "success", "")
            cls._succeed(task, f"oss={oss_key} size={result.file_size // 1024}KB md5={md5[:8]}")
            cls._schedule_next(task, meta)
            cls._cleanup(result.video_path, result.cover_path, download_dir)
            return True
        except Exception as e:
            err = str(e)
            permanent = is_permanent(err)
            if permanent:
                # 永久失败:DB 标永久,task 标 success(避免 rq 继续重试)
                db.mark_download_status(platform.value, video_id, "failed_permanent", err)
                cls._succeed(task, f"skipped (permanent): {err[:120]}")
                logger.warning(f"[{platform.value}:{video_id}] permanent failure: {err[:200]}")
            else:
                # 临时失败:DB 标临时,task 走原重试
                db.mark_download_status(platform.value, video_id, "failed_transient", err)
                cls._fail(task, err)
            cls._cleanup_dir(download_dir)
            return False

    @staticmethod
    def _extract_meta(
        platform: Platform, video_id: str, url: str, result
    ) -> Optional[VideoMeta]:
        """从 yt-dlp 返回的 info dict 提取元数据。"""
        info = result.raw_info or {}
        if not info:
            return None

        published_at = None
        ts = info.get("timestamp") or info.get("upload_date")
        if ts:
            try:
                if isinstance(ts, (int, float)):
                    published_at = datetime.fromtimestamp(ts, tz=timezone.utc)
                elif isinstance(ts, str) and len(ts) == 8:
                    published_at = datetime.strptime(ts, "%Y%m%d").replace(tzinfo=timezone.utc)
            except Exception:
                pass

        return VideoMeta(
            video_id=video_id,
            platform=platform,
            url=url,
            title=info.get("title", "") or result.title,
            desc=info.get("description", "") or "",
            author_name=info.get("uploader", "") or info.get("channel", "") or "",
            author_id=str(info.get("uploader_id", "") or info.get("channel_id", "") or ""),
            author_fans=int(info.get("channel_follower_count", 0) or 0),
            published_at=published_at,
            duration=int(info.get("duration", 0) or 0) or result.duration,
            cover_url=info.get("thumbnail", "") or "",
            tags=info.get("tags", []) or [],
            play_count=int(info.get("view_count", 0) or 0),
            like_count=int(info.get("like_count", 0) or 0),
            comment_count=int(info.get("comment_count", 0) or 0),
            share_count=int(info.get("repost_count", 0) or 0),
            collect_count=0,
            data_source="yt-dlp",
        )

    @staticmethod
    def _schedule_next(task: CollectTask, meta: Optional[VideoMeta]) -> None:
        """下载完成后调度后续任务。"""
        q = get_queue()
        if meta and settings.worker.enable_comment_worker:
            q.enqueue_comments(task.platform, task.video_id, depends_on=task.task_id)
        if meta and meta.published_at:
            from datetime import timedelta
            age = datetime.now(timezone.utc) - meta.published_at
            if age > timedelta(hours=72):
                q.enqueue_recheck(task.platform, task.video_id)
            else:
                delay = timedelta(hours=72) - age
                logger.info(f"recheck scheduled in {delay} for {task.video_id}")

    @staticmethod
    def _cleanup(*paths: str) -> None:
        for p in paths:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    @staticmethod
    def _cleanup_dir(d: str) -> None:
        import shutil
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


def run_download_video(platform_str: str, video_id: str, url: str, task_id: str) -> bool:
    """rq 入口函数。"""
    platform = Platform(platform_str)
    return VideoWorker.execute(platform, video_id, url, task_id)

"""爆款发现基类。

各平台子类实现 `fetch_hot()` 拿热门列表 → `is_viral()` 筛爆款 → `submit()` 入队下载。
包含：去重（PG 查询 + 跨平台标题相似度）、时长过滤、爆款初筛。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Iterable, Optional
from loguru import logger

from config.platforms import Platform
from config.settings import settings
from src.models.video import VideoMeta


@dataclass
class HotVideo:
    """热门列表里的一条视频记录。"""
    platform: Platform
    video_id: str
    url: str
    title: str = ""
    author_name: str = ""
    author_id: str = ""
    play_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    duration: int = 0
    desc: str = ""
    cover_url: str = ""
    tags: list[str] = None
    published_at: Optional[datetime] = None
    is_repost: bool = False  # 跨平台软去重标注：疑似搬运

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    @property
    def interaction_rate(self) -> float:
        if self.play_count <= 0:
            return 0.0
        return round(
            (self.like_count + self.comment_count + self.share_count) / self.play_count, 4
        )

    @property
    def is_viral(self) -> bool:
        """爆款初筛（宽松版，0-1 阶段多采样本）：
        - 播放 > 5w 且 互动率 > 3%
        - 或 点赞 > 5000（兜底）
        """
        cfg = settings.discovery
        if self.play_count >= cfg.min_play_count and self.interaction_rate >= cfg.min_interaction_rate:
            return True
        if self.like_count >= cfg.min_like_count:
            return True
        return False

    @property
    def duration_ok(self) -> bool:
        """时长过滤：10s - 30min，排除非内容视频。"""
        cfg = settings.discovery
        if self.duration <= 0:
            return True  # 拿不到时长时不过滤
        return cfg.min_duration <= self.duration <= cfg.max_duration

    def to_video_meta(self) -> VideoMeta:
        """发现阶段直接落库用,download_status=pending,等 worker 补 oss_key。"""
        return VideoMeta(
            video_id=self.video_id,
            platform=self.platform,
            url=self.url,
            title=self.title,
            desc=self.desc,
            author_name=self.author_name,
            author_id=self.author_id,
            cover_url=self.cover_url,
            duration=self.duration,
            tags=self.tags or [],
            published_at=self.published_at,
            play_count=self.play_count,
            like_count=self.like_count,
            comment_count=self.comment_count,
            share_count=self.share_count,
            data_source=f"{self.platform.value}_trending",
        )


class BaseDiscoverer(ABC):
    """各平台爆款发现器基类。"""

    platform: Platform = Platform.UNKNOWN

    @abstractmethod
    def fetch_hot(self, top_n: int = 50) -> list[HotVideo]:
        """从平台热门榜单拉取 top N 视频。"""
        ...

    def discover_and_submit(self, top_n: int = 50) -> int:
        """拉热门 → 去重 → 时长过滤 → 筛爆款 → 跨平台软去重 → 写元数据 → 入队下载。"""
        try:
            hot = self.fetch_hot(top_n=top_n)
        except Exception as e:
            logger.error(f"[{self.platform.value}] fetch_hot failed: {e}")
            return 0

        logger.info(f"[{self.platform.value}] fetched {len(hot)} hot videos")

        # 第 1 层：智能去重(已成功 / 永久失败 / 临时失败但未到冷却期 → 跳过)
        fresh = self._filter_already_collected(hot)
        logger.info(f"[{self.platform.value}] dedup: {len(fresh)}/{len(hot)} new or retryable")

        # 第 2 层：时长过滤
        duration_ok = [v for v in fresh if v.duration_ok]
        logger.info(f"[{self.platform.value}] duration filter: {len(duration_ok)}/{len(fresh)}")

        # 第 3 层：爆款初筛
        viral = [v for v in duration_ok if v.is_viral]
        logger.info(
            f"[{self.platform.value}] viral filter: {len(viral)}/{len(duration_ok)} "
            f"(play>{settings.discovery.min_play_count} rate>{settings.discovery.min_interaction_rate} "
            f"or like>{settings.discovery.min_like_count})"
        )

        # 第 4 层：跨平台软去重（标注疑似搬运，但都采）
        if settings.discovery.enable_cross_platform_dedup:
            self._mark_cross_platform_reposts(viral)

        from src.queue.task_queue import get_queue
        from src.storage.db import get_db
        q = get_queue()
        db = get_db()

        submitted = 0
        seen = set()
        for v in viral:
            key = f"{v.platform.value}:{v.video_id}"
            if key in seen:
                continue
            seen.add(key)

            # 先把热榜返回的元数据落库,即使下载失败也保留这一行
            try:
                db.upsert_video_meta(v.to_video_meta())
            except Exception as e:
                logger.warning(f"  upsert_video_meta failed for {v.url}: {e}")
                continue

            repost_tag = " [repost?]" if v.is_repost else ""
            try:
                task = q.submit_url(v.url)
                logger.info(
                    f"  submitted: {v.title[:30]}{repost_tag} "
                    f"play={v.play_count} rate={v.interaction_rate:.3f} "
                    f"task={task.task_id[:8]}"
                )
                submitted += 1
            except Exception as e:
                logger.warning(f"  submit failed for {v.url}: {e}")

        logger.info(f"[{self.platform.value}] submitted {submitted} viral videos")
        return submitted

    @staticmethod
    def _filter_already_collected(videos: list[HotVideo]) -> list[HotVideo]:
        """按 download_status 智能过滤:
        - success: 已下载,跳过
        - failed_permanent: 永久失败,跳过
        - failed_transient + 已达上限: 跳过
        - failed_transient + 冷却期内: 跳过(等 cron 拉)
        - failed_transient + 冷却已过 + 未达上限: 放行,本次重新入队
        - 其它(无记录 / pending / running): 通过
        """
        from datetime import datetime, timedelta, timezone
        from src.storage.db import get_db
        db = get_db()
        cfg = settings.worker
        now = datetime.now(timezone.utc)
        cooldown = timedelta(hours=cfg.retry_cooldown_hours)
        result = []
        for v in videos:
            st = db.get_video_download_status(v.platform.value, v.video_id)
            if st is None:
                result.append(v)
                continue

            status = st["status"]
            if status == "success":
                logger.debug(f"  skip success: {v.platform.value}:{v.video_id}")
                continue
            if status == "failed_permanent":
                logger.debug(f"  skip permanent: {v.platform.value}:{v.video_id}")
                continue
            if status == "failed_transient":
                if (st["attempts"] or 0) >= cfg.max_download_attempts:
                    logger.debug(f"  skip transient(max attempts): {v.platform.value}:{v.video_id}")
                    continue
                last = st.get("last_attempt_at")
                if last is not None:
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    if now - last < cooldown:
                        logger.debug(f"  skip transient(in cooldown): {v.platform.value}:{v.video_id}")
                        continue
                # 冷却已过且未达上限,放行重试
                logger.debug(f"  retry transient(cooldown passed): {v.platform.value}:{v.video_id}")
                result.append(v)
                continue
            # status in (pending, running) — 任务在飞,不重复入队
            logger.debug(f"  skip in-flight({status}): {v.platform.value}:{v.video_id}")
        return result

    @staticmethod
    def _mark_cross_platform_reposts(videos: list[HotVideo]) -> None:
        """跨平台标题相似度去重：相似度 > 阈值的标注 is_repost=True，但都采。"""
        if len(videos) < 2:
            return

        threshold = settings.discovery.dedup_title_similarity
        for i, v1 in enumerate(videos):
            if not v1.title:
                continue
            for j in range(i + 1, len(videos)):
                v2 = videos[j]
                if v1.platform == v2.platform:
                    continue  # 同平台不在此处理
                if not v2.title:
                    continue
                sim = SequenceMatcher(None, v1.title.lower(), v2.title.lower()).ratio()
                if sim >= threshold:
                    v2.is_repost = True
                    logger.info(
                        f"  cross-platform repost detected: "
                        f"'{v1.title[:20]}' ({v1.platform.value}) ~ "
                        f"'{v2.title[:20]}' ({v2.platform.value}) sim={sim:.2f}"
                    )

"""视频元数据模型。对应 PostgreSQL `videos` 表。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from config.platforms import Platform


class VideoMeta(BaseModel):
    """Tier A + Tier B 字段，由 Worker A 从第三方 API 获取。"""
    video_id: str = Field(..., description="平台原生视频 ID")
    platform: Platform
    url: str

    title: str = ""
    desc: str = ""
    author_name: str = ""
    author_id: str = ""
    author_fans: int = 0

    cover_url: str = ""
    duration: int = 0  # 秒
    width: int = 0
    height: int = 0
    tags: list[str] = Field(default_factory=list)
    published_at: Optional[datetime] = None

    # Tier C 互动数据（采集时刻）
    play_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    collect_count: int = 0
    forward_count: int = 0
    completion_rate: float = 0.0  # 完播率，平台提供时
    interaction_rate: float = 0.0  # (赞+评+转)/播放

    # 采集元信息
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    data_source: str = "yt-dlp"  # yt-dlp | youtube_api | bilibili_trending | youtube_trending

    @property
    def is_viral(self) -> bool:
        """爆款初筛：互动率 > 5% 且播放 > 10w。可按平台调参。"""
        return self.interaction_rate > 0.05 and self.play_count > 100_000

    @model_validator(mode="after")
    def _compute_interaction_rate(self) -> "VideoMeta":
        """若未显式提供 interaction_rate，则按公式自动计算。"""
        if self.interaction_rate == 0.0 and self.play_count > 0:
            self.interaction_rate = round(
                (self.like_count + self.comment_count + self.share_count) / self.play_count, 4
            )
        return self


class VideoFile(BaseModel):
    """Tier A 视频本体，由 Worker B 下载并上传 OSS 后回填。"""
    video_id: str
    platform: Platform
    oss_key: str
    oss_bucket: str
    file_size: int = 0  # bytes
    file_md5: str = ""
    format: str = "mp4"
    duration: int = 0
    width: int = 0
    height: int = 0
    downloaded_at: datetime = Field(default_factory=datetime.utcnow)
    cover_oss_key: str = ""


class InteractionSnapshot(BaseModel):
    """Tier C 72h 稳定值，由 Worker D 回抓。"""
    video_id: str
    platform: Platform
    play_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    collect_count: int = 0
    forward_count: int = 0
    interaction_rate: float = 0.0
    snapshot_at: datetime = Field(default_factory=datetime.utcnow)
    hours_after_publish: int = 72

"""评论数据模型。对应 PostgreSQL `comments` 表。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from config.platforms import Platform


class Comment(BaseModel):
    video_id: str
    platform: Platform
    comment_id: str
    author_name: str = ""
    author_id: str = ""
    content: str
    like_count: int = 0
    reply_count: int = 0
    is_top: bool = False  # 置顶评论
    is_author_reply: bool = False  # 作者回复
    published_at: Optional[datetime] = None
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    sentiment: Optional[str] = None  # positive | negative | neutral，下游 LLM 标注

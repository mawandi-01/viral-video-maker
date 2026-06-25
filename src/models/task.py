"""采集任务模型。对应 PostgreSQL `collect_tasks` 表 + Redis Queue。"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from config.platforms import Platform


class TaskType(str, Enum):
    FETCH_META = "fetch_meta"        # Worker A
    DOWNLOAD_VIDEO = "download_video"  # Worker B
    FETCH_COMMENTS = "fetch_comments"  # Worker C
    RECHECK_INTERACTION = "recheck"   # Worker D


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class CollectTask(BaseModel):
    task_id: str = Field(..., description="UUID")
    task_type: TaskType
    platform: Platform
    video_id: str = ""
    url: str = ""

    priority: int = 0  # 0=普通, 1=高, 2=紧急
    max_retries: int = 3
    retry_count: int = 0
    last_error: str = ""

    status: TaskStatus = TaskStatus.PENDING
    queued_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # 依赖：B 依赖 A 完成（需要 meta 才能下载），C 依赖 A，D 依赖 A + 发布后72h
    depends_on: Optional[str] = None  # 前置 task_id

    # 结果
    result_summary: str = ""

    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.SUCCESS, TaskStatus.FAILED)

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

"""Worker C · 评论补全（0-1 阶段不启用）。

规模化阶段使用。数据源：第三方数据 API 或自建评论采集（不依赖官方开放 API）。
0-1 阶段 ENABLE_COMMENT_WORKER=false，此 Worker 不被调度。

保留代码骨架，等接入第三方数据 API 后启用。
"""
from __future__ import annotations

from typing import Optional
from loguru import logger

from config.platforms import Platform
from config.settings import settings
from src.models.task import CollectTask, TaskType
from src.storage.db import get_db
from src.workers.base_worker import BaseWorker


class CommentWorker(BaseWorker):
    """0-1 阶段空实现，规模化阶段接入第三方数据 API 后补全。"""

    task_type = TaskType.FETCH_COMMENTS

    @classmethod
    def execute(cls, platform: Platform, video_id: str, task_id: str) -> bool:
        task = cls._start(task_id)
        if not task:
            return False
        # 0-1 阶段没有评论数据源，直接标记成功跳过
        cls._succeed(task, "comment worker not enabled in 0-1 phase")
        return True


def run_fetch_comments(platform_str: str, video_id: str, task_id: str) -> bool:
    """rq 入口函数。"""
    platform = Platform(platform_str)
    return CommentWorker.execute(platform, video_id, task_id)

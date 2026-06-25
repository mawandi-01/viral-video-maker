"""Worker 基类。统一处理状态流转、重试、错误捕获。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from loguru import logger

from src.models.task import CollectTask, TaskStatus, TaskType
from src.storage.db import get_db


class BaseWorker:
    task_type: TaskType = TaskType.FETCH_META

    @classmethod
    def _start(cls, task_id: str) -> Optional[CollectTask]:
        db = get_db()
        task = db.get_task(task_id)
        if not task:
            logger.error(f"task not found: {task_id}")
            return None
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        db.upsert_task(task)
        logger.info(f"[{cls.task_type.value}] start task={task_id} video={task.video_id}")
        return task

    @classmethod
    def _succeed(cls, task: CollectTask, summary: str = "") -> None:
        task.status = TaskStatus.SUCCESS
        task.finished_at = datetime.utcnow()
        task.result_summary = summary
        task.last_error = ""
        get_db().upsert_task(task)
        logger.info(f"[{cls.task_type.value}] success task={task.task_id} {summary}")

    @classmethod
    def _fail(cls, task: CollectTask, error: str) -> None:
        task.retry_count += 1
        task.last_error = error[:500]
        if task.can_retry:
            task.status = TaskStatus.RETRYING
        else:
            task.status = TaskStatus.FAILED
        task.finished_at = datetime.utcnow()
        get_db().upsert_task(task)
        logger.error(f"[{cls.task_type.value}] fail task={task.task_id} err={error}")

    @classmethod
    def _next(cls, task: CollectTask) -> None:
        """子类覆写：完成后触发下游任务。"""
        pass

"""基于 redis-queue (rq) 的任务队列。

队列分级:
- queue:high    优先任务（爆款池回抓）
- queue:default  常规任务（视频下载、元数据）
- queue:low     低优先任务（72h 回抓）
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4
from loguru import logger
from rq import Queue
from rq.job import Job
import redis

from config.settings import settings
from config.platforms import Platform
from src.models.task import CollectTask, TaskType, TaskStatus
from src.storage.db import get_db

_QUEUE_NAMES = {"high": "high", "default": "default", "low": "low"}


class TaskQueue:
    def __init__(self) -> None:
        self._conn = redis.from_url(
            settings.redis.url,
            socket_timeout=15,
            socket_connect_timeout=15,
            protocol=2,  # 阿里云 Redis 不支持 HELLO 命令，强制 RESP2
        )
        self._queues = {
            name: Queue(name, connection=self._conn)
            for name in _QUEUE_NAMES
        }

    @staticmethod
    def _pick_queue(task: CollectTask) -> str:
        if task.priority >= 2:
            return "high"
        if task.task_type == TaskType.RECHECK_INTERACTION:
            return "low"
        return "default"

    def enqueue(self, task: CollectTask, func, *args, **kwargs) -> Optional[Job]:
        qname = self._pick_queue(task)
        q = self._queues[qname]
        task.status = TaskStatus.QUEUED
        task.queued_at = datetime.utcnow()
        get_db().upsert_task(task)
        job = q.enqueue(
            func, *args, **kwargs,
            job_id=task.task_id,
            job_timeout=settings.worker.ttl,
            result_ttl=86400,
            failure_ttl=86400,
        )
        logger.info(f"enqueued {task.task_type.value} [{qname}] task={task.task_id}")
        return job

    def submit_url(self, url: str) -> CollectTask:
        """提交 URL 的入口：解析平台 → 直接入队下载。
        0-1 阶段只有 VideoWorker 一个 Worker，下载时 yt-dlp 自动提取元数据。"""
        from config.platforms import parse_url
        parsed = parse_url(url)
        if not parsed.video_id:
            raise ValueError(f"cannot parse video URL: {url}")
        return self.enqueue_download(parsed.platform, parsed.video_id, url)

    def enqueue_download(self, platform: Platform, video_id: str, url: str,
                          depends_on: Optional[str] = None) -> CollectTask:
        from src.workers.video_worker import run_download_video
        task = CollectTask(
            task_id=str(uuid4()),
            task_type=TaskType.DOWNLOAD_VIDEO,
            platform=platform,
            video_id=video_id,
            url=url,
            priority=1,
            depends_on=depends_on,
        )
        self.enqueue(task, run_download_video, platform.value, video_id, url, task.task_id)
        return task

    def enqueue_comments(self, platform: Platform, video_id: str,
                          depends_on: Optional[str] = None) -> CollectTask:
        from src.workers.comment_worker import run_fetch_comments
        task = CollectTask(
            task_id=str(uuid4()),
            task_type=TaskType.FETCH_COMMENTS,
            platform=platform,
            video_id=video_id,
            depends_on=depends_on,
        )
        self.enqueue(task, run_fetch_comments, platform.value, video_id, task.task_id)
        return task

    def enqueue_recheck(self, platform: Platform, video_id: str) -> CollectTask:
        from src.workers.recheck_worker import run_recheck_interaction
        task = CollectTask(
            task_id=str(uuid4()),
            task_type=TaskType.RECHECK_INTERACTION,
            platform=platform,
            video_id=video_id,
            priority=0,
        )
        self.enqueue(task, run_recheck_interaction, platform.value, video_id, task.task_id)
        return task

    def run_worker(self, queue_name: str = "default", burst: bool = False) -> None:
        """启动 worker。
        macOS 用 SimpleWorker（不 fork），避免 Objective-C runtime 冲突。
        Linux 可用标准 Worker（fork 模式，性能更好）。
        """
        import platform
        q = self._queues.get(queue_name)
        if not q:
            raise ValueError(f"unknown queue: {queue_name}")

        if platform.system() == "Darwin":
            # macOS: SimpleWorker 在主进程执行任务，不 fork，避免 objc 崩溃
            from rq import SimpleWorker
            worker = SimpleWorker([q], connection=self._conn)
            logger.info(f"SimpleWorker started on queue={queue_name} burst={burst} (macOS no-fork mode)")
        else:
            from rq import Worker
            worker = Worker([q], connection=self._conn)
            logger.info(f"Worker started on queue={queue_name} burst={burst}")
        worker.work(with_scheduler=True, burst=burst)


_queue: Optional[TaskQueue] = None


def get_queue() -> TaskQueue:
    global _queue
    if _queue is None:
        _queue = TaskQueue()
    return _queue

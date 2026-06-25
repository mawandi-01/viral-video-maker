"""PostgreSQL 数据库访问层。连接池 + CRUD。"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Optional, Iterator
from loguru import logger
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json

from config.settings import settings
from src.models.video import VideoMeta, VideoFile, InteractionSnapshot
from src.models.comment import Comment
from src.models.task import CollectTask, TaskStatus


class Database:
    def __init__(self) -> None:
        self._pool = pool.SimpleConnectionPool(
            minconn=2, maxconn=10, dsn=settings.pg.dsn
        )
        logger.info(f"PG pool ready: {settings.pg.host}:{settings.pg.port}/{settings.pg.db}")

    @contextmanager
    def conn(self) -> Iterator:
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def init_schema(self) -> None:
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(_SCHEMA_SQL)
        logger.info("DB schema initialized")

    # ---- Task CRUD ----

    def upsert_task(self, task: CollectTask) -> None:
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO collect_tasks
                        (task_id, task_type, platform, video_id, url, priority,
                         max_retries, retry_count, last_error, status,
                         queued_at, started_at, finished_at, depends_on,
                         result_summary, created_at)
                    VALUES (%(task_id)s, %(task_type)s, %(platform)s, %(video_id)s,
                            %(url)s, %(priority)s, %(max_retries)s, %(retry_count)s,
                            %(last_error)s, %(status)s, %(queued_at)s, %(started_at)s,
                            %(finished_at)s, %(depends_on)s, %(result_summary)s, %(created_at)s)
                    ON CONFLICT (task_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        retry_count = EXCLUDED.retry_count,
                        last_error = EXCLUDED.last_error,
                        started_at = EXCLUDED.started_at,
                        finished_at = EXCLUDED.finished_at,
                        result_summary = EXCLUDED.result_summary
                    """,
                    {
                        "task_id": task.task_id,
                        "task_type": task.task_type.value,
                        "platform": task.platform.value,
                        "video_id": task.video_id,
                        "url": task.url,
                        "priority": task.priority,
                        "max_retries": task.max_retries,
                        "retry_count": task.retry_count,
                        "last_error": task.last_error,
                        "status": task.status.value,
                        "queued_at": task.queued_at,
                        "started_at": task.started_at,
                        "finished_at": task.finished_at,
                        "depends_on": task.depends_on,
                        "result_summary": task.result_summary,
                        "created_at": task.created_at,
                    },
                )

    def get_task(self, task_id: str) -> Optional[CollectTask]:
        with self.conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM collect_tasks WHERE task_id = %s", (task_id,))
                row = cur.fetchone()
                if not row:
                    return None
                return CollectTask(**dict(row))

    def list_pending_tasks(self, task_type: Optional[str] = None, limit: int = 50) -> list[CollectTask]:
        sql = "SELECT * FROM collect_tasks WHERE status IN %s"
        params: list = [(TaskStatus.PENDING.value, TaskStatus.RETRYING.value)]
        if task_type:
            sql += " AND task_type = %s"
            params.append(task_type)
        sql += " ORDER BY priority DESC, created_at ASC LIMIT %s"
        params.append(limit)
        with self.conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, tuple(params))
                return [CollectTask(**dict(r)) for r in cur.fetchall()]

    # ---- Video Meta CRUD ----

    def upsert_video_meta(self, meta: VideoMeta) -> None:
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO videos
                        (video_id, platform, url, title, description, author_name, author_id,
                         author_fans, cover_url, duration, width, height, tags, published_at,
                         play_count, like_count, comment_count, share_count, collect_count,
                         forward_count, completion_rate, interaction_rate,
                         collected_at, data_source, is_viral)
                    VALUES (%(video_id)s, %(platform)s, %(url)s, %(title)s, %(desc)s,
                            %(author_name)s, %(author_id)s, %(author_fans)s, %(cover_url)s,
                            %(duration)s, %(width)s, %(height)s, %(tags)s, %(published_at)s,
                            %(play_count)s, %(like_count)s, %(comment_count)s, %(share_count)s,
                            %(collect_count)s, %(forward_count)s, %(completion_rate)s,
                            %(interaction_rate)s, %(collected_at)s, %(data_source)s, %(is_viral)s)
                    ON CONFLICT (platform, video_id) DO UPDATE SET
                        title = COALESCE(NULLIF(EXCLUDED.title, ''), videos.title),
                        description = COALESCE(NULLIF(EXCLUDED.description, ''), videos.description),
                        author_name = COALESCE(NULLIF(EXCLUDED.author_name, ''), videos.author_name),
                        cover_url = COALESCE(NULLIF(EXCLUDED.cover_url, ''), videos.cover_url),
                        duration = GREATEST(EXCLUDED.duration, videos.duration),
                        published_at = COALESCE(EXCLUDED.published_at, videos.published_at),
                        play_count = GREATEST(EXCLUDED.play_count, videos.play_count),
                        like_count = GREATEST(EXCLUDED.like_count, videos.like_count),
                        comment_count = GREATEST(EXCLUDED.comment_count, videos.comment_count),
                        share_count = GREATEST(EXCLUDED.share_count, videos.share_count),
                        interaction_rate = GREATEST(EXCLUDED.interaction_rate, videos.interaction_rate),
                        is_viral = EXCLUDED.is_viral OR videos.is_viral,
                        collected_at = EXCLUDED.collected_at
                    """,
                    {
                        "video_id": meta.video_id,
                        "platform": meta.platform.value,
                        "url": meta.url,
                        "title": meta.title,
                        "desc": meta.desc,
                        "author_name": meta.author_name,
                        "author_id": meta.author_id,
                        "author_fans": meta.author_fans,
                        "cover_url": meta.cover_url,
                        "duration": meta.duration,
                        "width": meta.width,
                        "height": meta.height,
                        "tags": Json(meta.tags),
                        "published_at": meta.published_at,
                        "play_count": meta.play_count,
                        "like_count": meta.like_count,
                        "comment_count": meta.comment_count,
                        "share_count": meta.share_count,
                        "collect_count": meta.collect_count,
                        "forward_count": meta.forward_count,
                        "completion_rate": meta.completion_rate,
                        "interaction_rate": meta.interaction_rate,
                        "collected_at": meta.collected_at,
                        "data_source": meta.data_source,
                        "is_viral": meta.is_viral,
                    },
                )

    def update_video_file(self, vf: VideoFile) -> None:
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE videos SET
                        oss_key = %s, oss_bucket = %s, file_size = %s, file_md5 = %s,
                        format = %s, downloaded_at = %s, cover_oss_key = %s
                    WHERE platform = %s AND video_id = %s
                    """,
                    (
                        vf.oss_key, vf.oss_bucket, vf.file_size, vf.file_md5,
                        vf.format, vf.downloaded_at, vf.cover_oss_key,
                        vf.platform.value, vf.video_id,
                    ),
                )

    def upsert_interaction_snapshot(self, snap: InteractionSnapshot) -> None:
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO interaction_snapshots
                        (video_id, platform, play_count, like_count, comment_count,
                         share_count, collect_count, forward_count, interaction_rate,
                         snapshot_at, hours_after_publish)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        snap.video_id, snap.platform.value, snap.play_count,
                        snap.like_count, snap.comment_count, snap.share_count,
                        snap.collect_count, snap.forward_count, snap.interaction_rate,
                        snap.snapshot_at, snap.hours_after_publish,
                    ),
                )

    # ---- Comment CRUD ----

    def batch_insert_comments(self, comments: list[Comment]) -> int:
        if not comments:
            return 0
        rows = [
            (
                c.video_id, c.platform.value, c.comment_id, c.author_name,
                c.author_id, c.content, c.like_count, c.reply_count,
                c.is_top, c.is_author_reply, c.published_at, c.collected_at,
            )
            for c in comments
        ]
        with self.conn() as conn:
            with conn.cursor() as cur:
                from psycopg2.extras import execute_values
                execute_values(
                    cur,
                    """
                    INSERT INTO comments
                        (video_id, platform, comment_id, author_name, author_id,
                         content, like_count, reply_count, is_top, is_author_reply,
                         published_at, collected_at)
                    VALUES %s
                    ON CONFLICT (platform, comment_id) DO NOTHING
                    """,
                    rows,
                )
                return cur.rowcount

    def get_video_meta(self, platform: str, video_id: str) -> Optional[VideoMeta]:
        with self.conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM videos WHERE platform = %s AND video_id = %s",
                    (platform, video_id),
                )
                row = cur.fetchone()
                if not row:
                    return None
                d = dict(row)
                d["desc"] = d.pop("description")
                d["tags"] = d.get("tags") or []
                return VideoMeta(**d)

    def video_exists(self, platform: str, video_id: str) -> bool:
        """快速检查视频是否已采集（去重用）。"""
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM videos WHERE platform = %s AND video_id = %s",
                    (platform, video_id),
                )
                return cur.fetchone() is not None

    # ---- Download status ----

    def get_video_download_status(self, platform: str, video_id: str) -> Optional[dict]:
        """返回 {status, attempts, last_attempt_at, error},不存在返回 None。"""
        with self.conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT download_status AS status,
                              download_attempts AS attempts,
                              last_attempt_at,
                              download_error AS error
                       FROM videos WHERE platform = %s AND video_id = %s""",
                    (platform, video_id),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def mark_download_attempt(self, platform: str, video_id: str) -> None:
        """worker 开始下载时调用:attempts+1, last_attempt_at=now, status=running。"""
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE videos
                       SET download_attempts = download_attempts + 1,
                           last_attempt_at   = now(),
                           download_status   = 'running'
                       WHERE platform = %s AND video_id = %s""",
                    (platform, video_id),
                )

    def mark_download_status(
        self,
        platform: str,
        video_id: str,
        status: str,
        error: str = "",
    ) -> None:
        """worker 结束时调用。status: success / failed_transient / failed_permanent。"""
        with self.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE videos
                       SET download_status = %s,
                           download_error  = %s
                       WHERE platform = %s AND video_id = %s""",
                    (status, error[:1000], platform, video_id),
                )

    def list_retryable_videos(
        self,
        max_attempts: int,
        cooldown_hours: int,
        limit: int = 200,
    ) -> list[dict]:
        """cron 用:返回临时失败、未达上限、冷却已过的视频。"""
        with self.conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT platform, video_id, url
                       FROM videos
                       WHERE download_status = 'failed_transient'
                         AND download_attempts < %s
                         AND (last_attempt_at IS NULL
                              OR last_attempt_at < now() - (%s || ' hours')::interval)
                       ORDER BY last_attempt_at NULLS FIRST
                       LIMIT %s""",
                    (max_attempts, cooldown_hours, limit),
                )
                return [dict(r) for r in cur.fetchall()]


_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS collect_tasks (
    task_id          TEXT PRIMARY KEY,
    task_type        TEXT NOT NULL,
    platform         TEXT NOT NULL,
    video_id         TEXT,
    url              TEXT,
    priority         INT DEFAULT 0,
    max_retries      INT DEFAULT 3,
    retry_count      INT DEFAULT 0,
    last_error       TEXT DEFAULT '',
    status           TEXT DEFAULT 'pending',
    queued_at        TIMESTAMPTZ,
    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    depends_on       TEXT,
    result_summary   TEXT DEFAULT '',
    created_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON collect_tasks(status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_type   ON collect_tasks(task_type, status);

CREATE TABLE IF NOT EXISTS videos (
    platform         TEXT NOT NULL,
    video_id         TEXT NOT NULL,
    url              TEXT,
    title            TEXT DEFAULT '',
    description      TEXT DEFAULT '',
    author_name      TEXT DEFAULT '',
    author_id        TEXT DEFAULT '',
    author_fans      INT DEFAULT 0,
    cover_url        TEXT DEFAULT '',
    duration         INT DEFAULT 0,
    width            INT DEFAULT 0,
    height           INT DEFAULT 0,
    tags             JSONB DEFAULT '[]',
    published_at     TIMESTAMPTZ,
    play_count       BIGINT DEFAULT 0,
    like_count       BIGINT DEFAULT 0,
    comment_count    BIGINT DEFAULT 0,
    share_count      BIGINT DEFAULT 0,
    collect_count    BIGINT DEFAULT 0,
    forward_count    BIGINT DEFAULT 0,
    completion_rate  REAL DEFAULT 0,
    interaction_rate REAL DEFAULT 0,
    collected_at     TIMESTAMPTZ DEFAULT now(),
    data_source      TEXT DEFAULT '',
    is_viral         BOOLEAN DEFAULT FALSE,
    oss_key          TEXT DEFAULT '',
    oss_bucket       TEXT DEFAULT '',
    file_size        BIGINT DEFAULT 0,
    file_md5         TEXT DEFAULT '',
    format           TEXT DEFAULT '',
    downloaded_at    TIMESTAMPTZ,
    cover_oss_key    TEXT DEFAULT '',
    download_status     TEXT DEFAULT 'pending',
    download_attempts   INT  DEFAULT 0,
    last_attempt_at     TIMESTAMPTZ,
    download_error      TEXT DEFAULT '',
    PRIMARY KEY (platform, video_id)
);
CREATE INDEX IF NOT EXISTS idx_videos_viral ON videos(is_viral, interaction_rate DESC);
CREATE INDEX IF NOT EXISTS idx_videos_collected ON videos(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_videos_download_status ON videos(download_status, last_attempt_at);

ALTER TABLE videos ADD COLUMN IF NOT EXISTS download_status   TEXT DEFAULT 'pending';
ALTER TABLE videos ADD COLUMN IF NOT EXISTS download_attempts INT  DEFAULT 0;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS last_attempt_at   TIMESTAMPTZ;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS download_error    TEXT DEFAULT '';
UPDATE videos SET download_status = 'success' WHERE oss_key <> '' AND download_status = 'pending';

CREATE TABLE IF NOT EXISTS interaction_snapshots (
    id                   BIGSERIAL PRIMARY KEY,
    video_id             TEXT NOT NULL,
    platform             TEXT NOT NULL,
    play_count           BIGINT DEFAULT 0,
    like_count           BIGINT DEFAULT 0,
    comment_count        BIGINT DEFAULT 0,
    share_count          BIGINT DEFAULT 0,
    collect_count        BIGINT DEFAULT 0,
    forward_count        BIGINT DEFAULT 0,
    interaction_rate     REAL DEFAULT 0,
    snapshot_at          TIMESTAMPTZ DEFAULT now(),
    hours_after_publish  INT DEFAULT 72
);
CREATE INDEX IF NOT EXISTS idx_snap_video ON interaction_snapshots(platform, video_id, snapshot_at);

CREATE TABLE IF NOT EXISTS comments (
    platform          TEXT NOT NULL,
    comment_id        TEXT NOT NULL,
    video_id          TEXT NOT NULL,
    author_name       TEXT DEFAULT '',
    author_id         TEXT DEFAULT '',
    content           TEXT,
    like_count        INT DEFAULT 0,
    reply_count       INT DEFAULT 0,
    is_top            BOOLEAN DEFAULT FALSE,
    is_author_reply   BOOLEAN DEFAULT FALSE,
    published_at      TIMESTAMPTZ,
    collected_at      TIMESTAMPTZ DEFAULT now(),
    sentiment         TEXT,
    PRIMARY KEY (platform, comment_id)
);
CREATE INDEX IF NOT EXISTS idx_comments_video ON comments(platform, video_id, published_at);
"""

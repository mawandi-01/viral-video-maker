"""SLS 日志 Sink · 把 loguru 日志推送到阿里云 SLS。

用法:
    from loguru import logger
    from src.utils.sls_handler import create_sls_sink
    sink = create_sls_sink()
    if sink:
        logger.add(sink, level="INFO")
"""
from __future__ import annotations

import os
import time
import threading
from typing import Optional
from loguru import logger as _logger

from aliyun.log import LogClient, LogItem, PutLogsRequest


class SLSSink:
    """loguru 的自定义 sink，批量推送日志到 SLS。

    内部用 buffer 攒日志，每 flush_interval 秒或 buffer 满 flush_size 条时批量写入。
    写入在后台线程执行，不阻塞业务。
    """

    def __init__(
        self,
        endpoint: str,
        access_key_id: str,
        access_key_secret: str,
        project: str,
        logstore: str,
        flush_interval: int = 5,
        flush_size: int = 50,
    ) -> None:
        self._client = LogClient(endpoint, access_key_id, access_key_secret)
        self._project = project
        self._logstore = logstore
        self._flush_interval = flush_interval
        self._flush_size = flush_size
        self._buffer: list[LogItem] = []
        self._lock = threading.Lock()
        self._last_flush = time.time()
        # 启动后台定时 flush
        self._timer: Optional[threading.Timer] = None
        self._start_timer()

    def write(self, message) -> None:
        """loguru sink 入口。每条日志调一次。"""
        record = message.record
        log_item = LogItem()
        log_item.set_time(int(record["time"].timestamp()))
        log_item.set_contents([
            ("level", record["level"].name),
            ("module", record["module"] or ""),
            ("function", record["function"] or ""),
            ("line", str(record["line"])),
            ("message", str(record["message"])),
            ("logger_name", record["name"] or ""),
            ("thread", str(record["thread"].id)),
        ])
        # 如果有 exception 信息
        if record["exception"] is not None:
            log_item.push_back("exception", str(record["exception"]))

        with self._lock:
            self._buffer.append(log_item)
            if len(self._buffer) >= self._flush_size:
                self._flush_locked()

    def _start_timer(self) -> None:
        """启动定时 flush 的后台线程。"""
        self._timer = threading.Timer(self._flush_interval, self._timed_flush)
        self._timer.daemon = True
        self._timer.start()

    def _timed_flush(self) -> None:
        """定时回调：flush buffer 并重启 timer。"""
        with self._lock:
            self._flush_locked()
        self._start_timer()

    def _flush_locked(self) -> None:
        """在锁内 flush（调用者必须持有 self._lock）。"""
        if not self._buffer:
            self._last_flush = time.time()
            return
        items = list(self._buffer)
        self._buffer.clear()
        self._last_flush = time.time()
        try:
            req = PutLogsRequest(self._project, self._logstore, "", "", items)
            self._client.put_logs(req)
        except Exception as e:
            # SLS 写入失败不影响业务，只打 stderr
            import sys
            print(f"[SLS] flush failed: {e}", file=sys.stderr)

    def close(self) -> None:
        """关闭 sink，flush 剩余日志。"""
        if self._timer:
            self._timer.cancel()
        with self._lock:
            self._flush_locked()


def create_sls_sink():
    """从环境变量创建 SLSSink。缺少配置时返回 None（静默跳过）。"""
    endpoint = os.getenv("SLS_ENDPOINT", "")
    project = os.getenv("SLS_PROJECT", "")
    logstore = os.getenv("SLS_LOGSTORE", "")
    ak = os.getenv("SLS_ACCESS_KEY_ID", "")
    sk = os.getenv("SLS_ACCESS_KEY_SECRET", "")

    if not all([endpoint, project, logstore, ak, sk]):
        return None

    try:
        sink = SLSSink(
            endpoint=endpoint,
            access_key_id=ak,
            access_key_secret=sk,
            project=project,
            logstore=logstore,
        )
        return sink
    except Exception as e:
        import sys
        print(f"[SLS] init failed: {e}", file=sys.stderr)
        return None

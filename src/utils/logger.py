"""日志工具。基于 loguru，统一格式。输出到 stderr + 文件 + SLS。"""
from __future__ import annotations

import os
import sys
from loguru import logger

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | "
           "<cyan>{name}</cyan> | <level>{message}</level>",
    level="INFO",
    colorize=True,
)

# 文件日志：仅在 logs 目录可写时启用
_log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
try:
    os.makedirs(_log_dir, exist_ok=True)
    logger.add(
        os.path.join(_log_dir, "collector_{time:YYYY-MM-DD}.log"),
        rotation="00:00",
        retention="14 days",
        level="DEBUG",
        encoding="utf-8",
    )
except (PermissionError, OSError):
    pass  # logs 目录不可写时跳过文件日志

# SLS 日志：从环境变量读取配置，配置不全时静默跳过
try:
    from src.utils.sls_handler import create_sls_sink
    _sls_sink = create_sls_sink()
    if _sls_sink:
        logger.add(_sls_sink, level="INFO", format="{message}")
        logger.info("SLS logging enabled: project={}, logstore={}",
                    os.getenv("SLS_PROJECT"), os.getenv("SLS_LOGSTORE"))
except Exception as _e:
    print(f"[SLS] setup skipped: {_e}", file=sys.stderr)

__all__ = ["logger"]

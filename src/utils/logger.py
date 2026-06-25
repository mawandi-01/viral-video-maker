"""日志工具。基于 loguru，统一格式。"""
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

__all__ = ["logger"]

"""重试装饰器。基于 tenacity。"""
from __future__ import annotations

from functools import wraps
from typing import Callable, Type, Tuple
import tenacity
from loguru import logger


def retry(
    max_attempts: int = 3,
    wait_seconds: int = 5,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """同步函数重试。指数退避。"""

    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            retryer = tenacity.Retrying(
                stop=tenacity.stop_after_attempt(max_attempts),
                wait=tenacity.wait_exponential(multiplier=wait_seconds, max=60),
                retry=tenacity.retry_if_exception_type(exceptions),
                before_sleep=tenacity.before_sleep_log(logger, "WARNING"),
                reraise=True,
            )
            return retryer(fn, *args, **kwargs)

        return wrapper

    return decorator


def async_retry(
    max_attempts: int = 3,
    wait_seconds: int = 5,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """异步函数重试。"""

    def decorator(fn: Callable):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            retryer = tenacity.AsyncRetrying(
                stop=tenacity.stop_after_attempt(max_attempts),
                wait=tenacity.wait_exponential(multiplier=wait_seconds, max=60),
                retry=tenacity.retry_if_exception_type(exceptions),
                before_sleep=tenacity.before_sleep_log(logger, "WARNING"),
                reraise=True,
            )
            return await retryer(fn, *args, **kwargs)

        return wrapper

    return decorator

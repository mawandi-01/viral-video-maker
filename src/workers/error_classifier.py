"""下载失败原因分类。

permanent  视频本身不可下载(删除/私有/付费/地区/格式不支持),不应再重试
transient  网络/限流/cookie/平台抖动,值得 cron 重试
"""
from __future__ import annotations

# 命中其中任一关键词即视为永久失败,大小写不敏感
_PERMANENT_PATTERNS = (
    # 通用 HTTP / yt-dlp
    "video unavailable",
    "this video is unavailable",
    "video has been removed",
    "video is private",
    "private video",
    "is not available",
    "no longer available",
    "this video is no longer available",
    "removed by the uploader",
    "removed by the user",
    "account associated with this video has been terminated",
    "deleted by the uploader",

    # 权限 / 付费 / 会员
    "members-only",
    "premium-only",
    "this is a members-only video",
    "sign in to confirm your age",
    "age-restricted",
    "login required",
    "需要登录",
    "付费视频",
    "需要会员",
    "充电专属",

    # 地区
    "not available in your country",
    "geo restricted",
    "geo-restricted",
    "region locked",
    "地区限制",
    "区域限制",

    # 视频不存在
    "http error 404",
    "http error 410",
    "video does not exist",
    "稿件不存在",
    "稿件已失效",
    "作品不存在",
    "笔记不存在",

    # yt-dlp 不支持
    "unsupported url",
    "no video formats found",
    "no suitable formats",
    "requested format is not available",
)


def is_permanent(error_msg: str) -> bool:
    if not error_msg:
        return False
    msg = error_msg.lower()
    return any(p in msg for p in _PERMANENT_PATTERNS)


def classify(error_msg: str) -> str:
    return "permanent" if is_permanent(error_msg) else "transient"

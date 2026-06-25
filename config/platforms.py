"""平台标识与 URL 解析。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class Platform(str, Enum):
    DOUYIN = "douyin"
    KUAISHOU = "kuaishou"
    BILIBILI = "bilibili"
    XHS = "xhs"  # 小红书
    YOUTUBE = "youtube"
    UNKNOWN = "unknown"


@dataclass
class ParsedURL:
    platform: Platform
    video_id: str
    raw_url: str


_PATTERNS = [
    (Platform.DOUYIN, re.compile(r"douyin\.com/video/(\d+)")),
    (Platform.DOUYIN, re.compile(r"iesdouyin\.com/share/video/(\d+)")),
    (Platform.DOUYIN, re.compile(r"v\.douyin\.com/([A-Za-z0-9]+)")),
    (Platform.KUAISHOU, re.compile(r"kuaishou\.com/short-video/([A-Za-z0-9_-]+)")),
    (Platform.KUAISHOU, re.compile(r"chenzhongtech\.com/.*\?photoId=([A-Za-z0-9_-]+)")),
    (Platform.BILIBILI, re.compile(r"bilibili\.com/video/(BV[A-Za-z0-9]+)")),
    (Platform.XHS, re.compile(r"xiaohongshu\.com/(?:explore|discovery/item)/([A-Za-z0-9]+)")),
    (Platform.YOUTUBE, re.compile(r"youtube\.com/watch\?v=([A-Za-z0-9_-]{11})")),
    (Platform.YOUTUBE, re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})")),
]


def parse_url(raw_url: str) -> ParsedURL:
    """从 URL 解析平台和视频 ID。短链需先由下载器重定向解析。"""
    for platform, pattern in _PATTERNS:
        m = pattern.search(raw_url)
        if m:
            return ParsedURL(platform=platform, video_id=m.group(1), raw_url=raw_url)
    host = urlparse(raw_url).netloc.lower()
    if "douyin" in host:
        return ParsedURL(platform=Platform.DOUYIN, video_id="", raw_url=raw_url)
    if "kuaishou" in host or "chenzhongtech" in host:
        return ParsedURL(platform=Platform.KUAISHOU, video_id="", raw_url=raw_url)
    if "bilibili" in host or "b23.tv" in host:
        return ParsedURL(platform=Platform.BILIBILI, video_id="", raw_url=raw_url)
    if "xiaohongshu" in host or "xhslink" in host:
        return ParsedURL(platform=Platform.XHS, video_id="", raw_url=raw_url)
    if "youtube" in host or "youtu.be" in host:
        return ParsedURL(platform=Platform.YOUTUBE, video_id="", raw_url=raw_url)
    return ParsedURL(platform=Platform.UNKNOWN, video_id="", raw_url=raw_url)

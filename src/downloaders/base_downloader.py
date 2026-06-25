"""基于 yt-dlp 的多平台视频下载器基类。"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger
import yt_dlp

from config.platforms import Platform


def _make_impersonate_target(client: str = "chrome"):
    """yt-dlp 2026+ 要求 impersonate 是 ImpersonateTarget 对象，不是字符串。"""
    try:
        from yt_dlp.networking.impersonate import ImpersonateTarget
        return ImpersonateTarget(client=client)
    except (ImportError, TypeError):
        # 旧版 yt-dlp 用字符串
        return client


@dataclass
class DownloadResult:
    success: bool
    platform: Platform
    video_id: str
    video_path: str = ""
    cover_path: str = ""
    title: str = ""
    duration: int = 0
    width: int = 0
    height: int = 0
    file_size: int = 0
    error: str = ""
    raw_info: dict = field(default_factory=dict)


class BaseDownloader:
    """yt-dlp 封装。子类可覆写 _build_opts 定制各平台参数。"""

    platform: Platform = Platform.UNKNOWN

    def __init__(self, download_dir: Optional[str] = None, timeout: int = 300) -> None:
        self.download_dir = download_dir or tempfile.gettempdir()
        self.timeout = timeout

    def download(self, url: str, video_id: str = "") -> DownloadResult:
        opts = self._build_opts(video_id or "%(id)s")
        logger.info(f"[{self.platform.value}] start download: {url}")

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"[{self.platform.value}] download failed: {e}")
            return DownloadResult(
                success=False,
                platform=self.platform,
                video_id=video_id,
                error=str(e),
            )

        video_path = self._find_downloaded_file(info, video_id)
        if not video_path or not os.path.exists(video_path):
            return DownloadResult(
                success=False,
                platform=self.platform,
                video_id=video_id,
                error="downloaded file not found",
                raw_info=info,
            )

        cover_path = self._download_cover(info, video_id)
        file_size = os.path.getsize(video_path)

        logger.info(
            f"[{self.platform.value}] download ok: {video_path} "
            f"({file_size // 1024}KB, {info.get('duration', 0)}s)"
        )
        return DownloadResult(
            success=True,
            platform=self.platform,
            video_id=video_id or str(info.get("id", "")),
            video_path=video_path,
            cover_path=cover_path,
            title=info.get("title", ""),
            duration=int(info.get("duration", 0) or 0),
            width=int(info.get("width", 0) or 0),
            height=int(info.get("height", 0) or 0),
            file_size=file_size,
            raw_info=info,
        )

    def _build_opts(self, video_id_template: str) -> dict:
        outtmpl = os.path.join(self.download_dir, f"{self.platform.value}_{video_id_template}.%(ext)s")
        opts = {
            "outtmpl": outtmpl,
            # 优先单文件格式（不需要 ffmpeg），fallback 到合并格式
            "format": "best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": self.timeout,
            "retries": 3,
            "fragment_retries": 3,
            "writesubtitles": False,
            "writeautomaticsub": False,
            "writethumbnail": True,
        }
        # Cookie 策略：优先用 cookie 文件，没有则从 Safari 浏览器读
        cookie_file = self._cookie_file()
        if cookie_file:
            opts["cookiefile"] = cookie_file
        else:
            # macOS Safari 直接读 cookie（需要终端有"完全磁盘访问"权限）
            opts["cookiesfrombrowser"] = ("safari",)

        # B站需要 impersonate chrome 绕过 412 反爬
        if self.platform == Platform.BILIBILI:
            opts["impersonate"] = _make_impersonate_target("chrome")
        return opts

    def _cookie_file(self) -> Optional[str]:
        path = os.path.join(os.path.dirname(__file__), "..", "..", "cookies", f"{self.platform.value}.txt")
        path = os.path.abspath(path)
        return path if os.path.exists(path) else None

    def _find_downloaded_file(self, info: dict, video_id: str) -> str:
        if info.get("requested_downloads"):
            for d in info["requested_downloads"]:
                if d.get("filepath"):
                    return d["filepath"]
        ext = info.get("ext", "mp4")
        candidate = os.path.join(
            self.download_dir, f"{self.platform.value}_{video_id or info.get('id', '')}.{ext}"
        )
        return candidate if os.path.exists(candidate) else ""

    def _download_cover(self, info: dict, video_id: str) -> str:
        thumbnail = info.get("thumbnail") or ""
        thumbnails = info.get("thumbnails") or []
        if not thumbnail and thumbnails:
            thumbnail = thumbnails[-1].get("url", "")
        if not thumbnail:
            return ""

        import httpx
        cover_path = os.path.join(self.download_dir, f"{self.platform.value}_{video_id}_cover.jpg")
        try:
            r = httpx.get(thumbnail, timeout=15, follow_redirects=True)
            r.raise_for_status()
            with open(cover_path, "wb") as f:
                f.write(r.content)
            return cover_path
        except Exception as e:
            logger.warning(f"cover download failed: {e}")
            return ""

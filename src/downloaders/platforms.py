"""各平台下载器。仅 platform 标识不同，yt-dlp 自动处理。"""
from __future__ import annotations

from config.platforms import Platform
from src.downloaders.base_downloader import BaseDownloader


class DouyinDownloader(BaseDownloader):
    platform = Platform.DOUYIN

    def _build_opts(self, video_id_template: str) -> dict:
        opts = super()._build_opts(video_id_template)
        opts["extractor_args"] = {"douyin": {"ua": "mobile"}}
        return opts


class KuaishouDownloader(BaseDownloader):
    platform = Platform.KUAISHOU


class BilibiliDownloader(BaseDownloader):
    platform = Platform.BILIBILI

    def _build_opts(self, video_id_template: str) -> dict:
        opts = super()._build_opts(video_id_template)
        opts["format"] = "bestvideo+bestaudio/best"
        return opts


class XHSDownloader(BaseDownloader):
    platform = Platform.XHS


class YouTubeDownloader(BaseDownloader):
    platform = Platform.YOUTUBE

    def _build_opts(self, video_id_template: str) -> dict:
        opts = super()._build_opts(video_id_template)
        opts["format"] = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
        return opts


_DOWNLOADERS = {
    Platform.DOUYIN: DouyinDownloader,
    Platform.KUAISHOU: KuaishouDownloader,
    Platform.BILIBILI: BilibiliDownloader,
    Platform.XHS: XHSDownloader,
    Platform.YOUTUBE: YouTubeDownloader,
}


def get_downloader(platform: Platform, download_dir: str = "", timeout: int = 300) -> BaseDownloader:
    cls = _DOWNLOADERS.get(platform, BaseDownloader)
    return cls(download_dir=download_dir or None, timeout=timeout)

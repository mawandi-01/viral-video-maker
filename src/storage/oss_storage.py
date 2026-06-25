"""阿里云 OSS 存储。视频文件 + 封面图上传。"""
from __future__ import annotations

import hashlib
import os
from typing import Optional
from loguru import logger
import oss2

from config.settings import settings


class OSSStorage:
    def __init__(self) -> None:
        self._auth = oss2.Auth(settings.oss.access_key_id, settings.oss.access_key_secret)
        self._bucket = oss2.Bucket(self._auth, settings.oss.endpoint, settings.oss.bucket_name)
        self._video_prefix = settings.oss.video_prefix
        self._cover_prefix = settings.oss.cover_prefix

    def upload_video(self, local_path: str, platform: str, video_id: str) -> str:
        """上传视频文件，返回 OSS key。key 格式: videos/raw/{platform}/{video_id}.mp4"""
        ext = os.path.splitext(local_path)[1] or ".mp4"
        key = f"{self._video_prefix}/{platform}/{video_id}{ext}"
        logger.info(f"OSS upload video: {local_path} -> {key}")
        self._bucket.put_object_from_file(key, local_path)
        return key

    def upload_cover(self, local_path: str, platform: str, video_id: str) -> str:
        ext = os.path.splitext(local_path)[1] or ".jpg"
        key = f"{self._cover_prefix}/{platform}/{video_id}{ext}"
        logger.info(f"OSS upload cover: {local_path} -> {key}")
        self._bucket.put_object_from_file(key, local_path)
        return key

    def upload_bytes(self, data: bytes, key: str) -> str:
        self._bucket.put_object(key, data)
        return key

    def exists(self, key: str) -> bool:
        return self._bucket.object_exists(key)

    def sign_url(self, key: str, expires: int = 3600) -> str:
        """生成临时签名 URL，用于下游多模态引擎拉取。"""
        return self._bucket.sign_url("GET", key, expires)

    def delete(self, key: str) -> None:
        self._bucket.delete_object(key)

    @staticmethod
    def file_md5(local_path: str) -> str:
        h = hashlib.md5()
        with open(local_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()


_oss: Optional[OSSStorage] = None


def get_oss() -> OSSStorage:
    global _oss
    if _oss is None:
        _oss = OSSStorage()
    return _oss

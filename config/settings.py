"""全局配置加载。从环境变量或 .env 文件读取。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class PostgresConfig:
    host: str = field(default_factory=lambda: _env("PG_HOST", "localhost"))
    port: int = field(default_factory=lambda: _env_int("PG_PORT", 5432))
    db: str = field(default_factory=lambda: _env("PG_DB", "video_collector"))
    user: str = field(default_factory=lambda: _env("PG_USER", "postgres"))
    password: str = field(default_factory=lambda: _env("PG_PASSWORD", "postgres"))

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )


@dataclass
class RedisConfig:
    host: str = field(default_factory=lambda: _env("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: _env_int("REDIS_PORT", 6379))
    db: int = field(default_factory=lambda: _env_int("REDIS_DB", 0))
    password: str = field(default_factory=lambda: _env("REDIS_PASSWORD", ""))
    username: str = field(default_factory=lambda: _env("REDIS_USERNAME", ""))

    @property
    def url(self) -> str:
        if self.username and self.password:
            auth = f"{self.username}:{self.password}@"
        elif self.password:
            auth = f":{self.password}@"
        else:
            auth = ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


@dataclass
class OSSConfig:
    access_key_id: str = field(default_factory=lambda: _env("OSS_ACCESS_KEY_ID"))
    access_key_secret: str = field(default_factory=lambda: _env("OSS_ACCESS_KEY_SECRET"))
    endpoint: str = field(default_factory=lambda: _env("OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com"))
    bucket_name: str = field(default_factory=lambda: _env("OSS_BUCKET_NAME"))
    video_prefix: str = field(default_factory=lambda: _env("OSS_VIDEO_PREFIX", "videos/raw"))
    cover_prefix: str = field(default_factory=lambda: _env("OSS_COVER_PREFIX", "covers/raw"))


@dataclass
class YouTubeConfig:
    api_key: str = field(default_factory=lambda: _env("YOUTUBE_API_KEY"))


@dataclass
class WorkerConfig:
    ttl: int = field(default_factory=lambda: _env_int("WORKER_TTL", 600))
    download_timeout: int = field(default_factory=lambda: _env_int("DOWNLOAD_TIMEOUT", 300))
    download_retries: int = field(default_factory=lambda: _env_int("DOWNLOAD_RETRIES", 3))
    max_concurrent: int = field(default_factory=lambda: _env_int("MAX_CONCURRENT_DOWNLOADS", 3))
    enable_comment_worker: bool = field(default_factory=lambda: _env("ENABLE_COMMENT_WORKER", "false").lower() == "true")
    # 临时性失败的最大重试上限(超过则不再被 cron 拉起)
    max_download_attempts: int = field(default_factory=lambda: _env_int("MAX_DOWNLOAD_ATTEMPTS", 5))
    # cron 重试冷却:最近一次尝试至少 N 小时前才会被重新入队
    retry_cooldown_hours: int = field(default_factory=lambda: _env_int("RETRY_COOLDOWN_HOURS", 1))


@dataclass
class DiscoveryConfig:
    """爆款发现配置。各平台热门榜单抓取参数 + 爆款阈值。"""
    # 爆款初筛阈值（0-1 阶段宽松版，多采样本给下游拆解练手）
    min_play_count: int = field(default_factory=lambda: _env_int("VIRAL_MIN_PLAY", 50_000))
    min_interaction_rate: float = field(default_factory=lambda: float(_env("VIRAL_MIN_RATE", "0.03")))
    min_like_count: int = field(default_factory=lambda: _env_int("VIRAL_MIN_LIKE", 5_000))

    # 时长过滤（秒），排除非内容视频
    min_duration: int = field(default_factory=lambda: _env_int("MIN_DURATION", 10))
    max_duration: int = field(default_factory=lambda: _env_int("MAX_DURATION", 1800))

    # 跨平台软去重
    enable_cross_platform_dedup: bool = field(default_factory=lambda: _env("ENABLE_CROSS_PLATFORM_DEDUP", "true").lower() == "true")
    dedup_title_similarity: float = field(default_factory=lambda: float(_env("DEDUP_TITLE_SIMILARITY", "0.8")))

    # 各平台抓取数量上限
    bilibili_top_n: int = field(default_factory=lambda: _env_int("BILIBILI_TOP_N", 50))
    youtube_top_n: int = field(default_factory=lambda: _env_int("YOUTUBE_TOP_N", 50))
    douyin_top_n: int = field(default_factory=lambda: _env_int("DOUYIN_TOP_N", 50))

    # 抖音 URL 池文件（手动维护的热门 URL 列表，每行一个 URL）
    douyin_url_pool: str = field(default_factory=lambda: _env("DOUYIN_URL_POOL", "config/douyin_hot.txt"))

    # 启用的平台（逗号分隔，如 "bilibili,youtube,douyin"）
    enabled_platforms: str = field(default_factory=lambda: _env("DISCOVERY_PLATFORMS", "bilibili,youtube"))


@dataclass
class AIConfig:
    """AI 服务配置 · CLIProxyAPI 中转站。"""
    base_url: str = field(default_factory=lambda: _env("CLIPROXY_BASE_URL", "http://localhost:8317"))
    api_key: str = field(default_factory=lambda: _env("CLIPROXY_API_KEY", "sk-cliproxy-local-dev-key-2024"))
    model: str = field(default_factory=lambda: _env("CLIPROXY_MODEL", "claude-sonnet-4"))
    timeout: int = field(default_factory=lambda: _env_int("CLIPROXY_TIMEOUT", 180))
    max_retries: int = field(default_factory=lambda: _env_int("CLIPROXY_MAX_RETRIES", 3))


@dataclass
class ExtractConfig:
    """多模态提取引擎配置。"""
    frame_interval: int = field(default_factory=lambda: _env_int("EXTRACT_FRAME_INTERVAL", 3))
    max_frames: int = field(default_factory=lambda: _env_int("EXTRACT_MAX_FRAMES", 30))
    vision_batch: int = field(default_factory=lambda: _env_int("EXTRACT_VISION_BATCH", 3))
    audio_sample_rate: int = field(default_factory=lambda: _env_int("EXTRACT_AUDIO_SAMPLE_RATE", 16000))


@dataclass
class Settings:
    pg: PostgresConfig = field(default_factory=PostgresConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    oss: OSSConfig = field(default_factory=OSSConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    extract: ExtractConfig = field(default_factory=ExtractConfig)

    @property
    def youtube_api_key(self) -> str:
        return self.youtube.api_key


settings = Settings()

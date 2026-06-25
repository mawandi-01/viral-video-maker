"""ExtractWorker · 编排多模态提取全流程。

接收任务: extract_video(platform, video_id)
执行顺序:
1. 从 OSS 下载视频到临时目录
2. VideoPreprocessor 抽帧 + 抽音频
3. VisualEngine (Claude看帧) + WhisperEngine (ASR) 并行
4. TextEngine (Claude拆文案)
5. FusionEngine (Claude跨模态对齐) → template_features
6. TemplateEngine (Claude去主题) → template_schema
7. 落库: videos 表 4 列 + prompt_templates 表
8. 清理临时文件
"""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from loguru import logger

from config.platforms import Platform
from src.ai.claude_client import ClaudeClient
from src.audio.whisper_engine import WhisperEngine, get_engine as get_whisper
from src.extract.preprocessor import VideoPreprocessor
from src.extract.visual_engine import VisualEngine
from src.extract.text_engine import TextEngine
from src.extract.fusion_engine import FusionEngine
from src.extract.template_engine import TemplateEngine
from src.storage.db import get_db
from src.storage.oss_storage import get_oss


class ExtractWorker:
    """编排多模态提取全流程。"""

    def __init__(self, client: Optional[ClaudeClient] = None) -> None:
        self._claude = client or ClaudeClient()
        self._preprocessor = VideoPreprocessor()
        self._whisper = WhisperEngine()
        self._visual = VisualEngine(client=self._claude)
        self._text = TextEngine(client=self._claude)
        self._fusion = FusionEngine(client=self._claude)
        self._template = TemplateEngine(client=self._claude)
        self._oss = get_oss()
        self._db = get_db()

    def execute(self, platform: Platform, video_id: str) -> bool:
        """对单个视频执行完整提取流程。

        Args:
            platform: 平台
            video_id: 视频 ID

        Returns:
            True 成功，False 失败
        """
        logger.info(f"[extract] start: {platform.value}/{video_id}")
        work_dir = tempfile.mkdtemp(prefix=f"extract_{video_id}_")

        try:
            # 1. 从 OSS 下载视频
            video_path = self._download_from_oss(platform, video_id, work_dir)
            if not video_path:
                return False

            # 2. 预处理
            pp_result = self._preprocessor.process(video_path, work_dir)
            if pp_result.error:
                logger.error(f"[extract] preprocess failed: {pp_result.error}")
                return False

            # 3a. 视觉引擎
            logger.info("[extract] step 3a: visual engine")
            visual_features = self._visual.analyze(pp_result.frames)

            # 3b. 音频引擎 (ASR)
            logger.info("[extract] step 3b: audio engine (whisper)")
            audio_features = self._run_whisper(pp_result.audio_path)

            # 4. 文案引擎
            logger.info("[extract] step 4: text engine")
            text_features = self._text.analyze(audio_features)

            # 5. 融合引擎
            logger.info("[extract] step 5: fusion engine")
            template_features = self._fusion.fuse(visual_features, audio_features, text_features)

            # 6. 模板抽象
            logger.info("[extract] step 6: template engine")
            template_schema = self._template.abstract(template_features)

            # 7. 落库
            logger.info("[extract] step 7: save to DB")
            self._save_results(
                platform, video_id,
                visual_features, audio_features, text_features,
                template_features, template_schema,
            )

            logger.info(f"[extract] done: {platform.value}/{video_id}")
            return True

        except Exception as e:
            logger.error(f"[extract] failed: {e}", exc_info=True)
            return False
        finally:
            # 8. 清理
            shutil.rmtree(work_dir, ignore_errors=True)

    def _download_from_oss(self, platform: Platform, video_id: str, work_dir: str) -> Optional[str]:
        """从 OSS 下载视频到本地。"""
        oss_key = f"videos/raw/{platform.value}/{video_id}.mp4"
        local_path = os.path.join(work_dir, f"{video_id}.mp4")
        try:
            self._oss._bucket.get_object_to_file(oss_key, local_path)
            size = os.path.getsize(local_path)
            logger.info(f"[extract] downloaded from OSS: {oss_key} ({size // 1024}KB)")
            return local_path
        except Exception as e:
            logger.error(f"[extract] OSS download failed: {e}")
            return None

    def _run_whisper(self, audio_path: str) -> dict:
        """跑 Whisper ASR。"""
        if not audio_path or not os.path.exists(audio_path):
            return {"transcript": "", "segments": [], "language": "", "duration": 0}

        result = self._whisper.transcribe(audio_path)
        if not result.success:
            logger.warning(f"[extract] whisper failed: {result.error}")
            return {"transcript": "", "segments": [], "language": "", "duration": 0}

        return {
            "transcript": result.text,
            "segments": [
                {"start": s.start, "end": s.end, "text": s.text}
                for s in result.segments
            ],
            "language": result.language,
            "duration": result.duration,
        }

    def _save_results(
        self,
        platform: Platform,
        video_id: str,
        visual_features: dict,
        audio_features: dict,
        text_features: dict,
        template_features: dict,
        template_schema: dict,
    ) -> None:
        """保存结果到 PG。长时间运行后连接可能失效，这里重建连接池。"""
        from psycopg2.extras import Json

        # 重建 DB 连接（长时间运行后连接池里的连接可能超时失效）
        try:
            self._db = get_db()
        except Exception:
            pass

        # 1. 更新 videos 表的 4 个 JSONB 列
        try:
            with self._db.conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """UPDATE videos
                           SET visual_features = %s,
                               audio_features = %s,
                               text_features = %s,
                               template_features = %s
                           WHERE platform = %s AND video_id = %s""",
                        (
                            Json(visual_features),
                            Json(audio_features),
                            Json(text_features),
                            Json(template_features),
                            platform.value,
                            video_id,
                        ),
                    )
            logger.info("[extract] updated videos table: 4 JSONB columns")
        except Exception as e:
            logger.error(f"[extract] save to videos table failed: {e}")
            raise

        # 2. 写 prompt_templates 表
        template_id = str(uuid4())
        category = template_schema.get("category", "")
        sub_type = template_schema.get("sub_type", "")

        # quality_score 用原视频的 interaction_rate
        quality_score = 0.0
        try:
            meta = self._db.get_video_meta(platform.value, video_id)
            if meta:
                quality_score = meta.interaction_rate
        except Exception as e:
            logger.warning(f"[extract] get_video_meta failed (non-fatal): {e}")

        try:
            with self._db.conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO prompt_templates
                            (template_id, source_video_id, source_platform,
                             template_schema, category, sub_type, quality_score, created_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (template_id) DO NOTHING""",
                        (
                            template_id,
                            video_id,
                            platform.value,
                            Json(template_schema),
                            category,
                            sub_type,
                            quality_score,
                            datetime.now(timezone.utc),
                        ),
                    )
            logger.info(
                f"[extract] saved prompt_templates: id={template_id}, "
                f"category={category}/{sub_type}, score={quality_score:.4f}"
            )
        except Exception as e:
            logger.error(f"[extract] save to prompt_templates failed: {e}")
            raise


def run_extract_video(platform_str: str, video_id: str) -> bool:
    """同步入口函数。"""
    platform = Platform(platform_str)
    return ExtractWorker().execute(platform, video_id)

"""质量闭环 · 生成记录 CRUD + 反馈 + 质量分计算。

0-1 阶段被动闭环:
- 记录每次生成
- 用户 👍/👎 反馈
- 用户选填发布 URL
- 回采发布视频数据
- 更新配方质量分: 源视频×0.3 + 历史生成×0.5 + 采纳率×0.2
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from loguru import logger

from src.storage.db import get_db


class QualityLoop:
    """质量闭环管理。"""

    def __init__(self) -> None:
        self._db = get_db()

    def record_generation(
        self,
        template_id: str,
        scene_type: str,
        video_type: str,
        user_theme: str,
        user_input: dict,
        selected_factors: list[str],
        prompt_package: dict,
        attribution_id: str = "",
    ) -> str:
        """记录一次生成。

        Returns:
            record_id
        """
        record_id = str(uuid4())
        from psycopg2.extras import Json

        with self._db.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO generation_records
                        (record_id, template_id, attribution_id, scene_type, video_type,
                         user_theme, user_input, selected_factors, prompt_package,
                         status, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'generated', %s)""",
                    (
                        record_id, template_id, attribution_id, scene_type, video_type,
                        user_theme, Json(user_input), Json(selected_factors),
                        Json(prompt_package), datetime.now(timezone.utc),
                    ),
                )
                # 更新配方的 generation_count
                if template_id:
                    cur.execute(
                        """UPDATE prompt_templates
                           SET generation_count = generation_count + 1
                           WHERE template_id = %s""",
                        (template_id,),
                    )
        logger.info(f"quality: recorded generation {record_id} for template {template_id}")
        return record_id

    def update_feedback(self, record_id: str, feedback: str, published_url: str = "", published_platform: str = "") -> bool:
        """用户反馈（👍/👎 + 选填发布 URL）。"""
        with self._db.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE generation_records
                       SET feedback = %s,
                           published_url = %s,
                           published_platform = %s,
                           status = CASE WHEN %s != '' THEN 'published' ELSE status END
                       WHERE record_id = %s""",
                    (feedback, published_url, published_platform, published_url, record_id),
                )
                # 采纳率更新
                if feedback == "👍" or published_url:
                    cur.execute(
                        """UPDATE prompt_templates
                           SET adoption_count = adoption_count + 1
                           WHERE template_id = (
                               SELECT template_id FROM generation_records WHERE record_id = %s
                           )""",
                        (record_id,),
                    )
        logger.info(f"quality: feedback updated for {record_id}: {feedback}")
        return True

    def update_actual_metrics(
        self,
        record_id: str,
        play_count: int,
        like_count: int,
        interaction_rate: float,
    ) -> None:
        """回采发布视频的实际数据后更新。"""
        # 计算 surprise_score
        expected = 0.0
        with self._db.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT expected_rate FROM generation_records WHERE record_id = %s",
                    (record_id,),
                )
                row = cur.fetchone()
                if row:
                    expected = float(row[0] or 0)

        surprise = interaction_rate - expected

        with self._db.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE generation_records
                       SET actual_play_count = %s,
                           actual_like_count = %s,
                           actual_interaction_rate = %s,
                           surprise_score = %s,
                           collected_at = %s
                       WHERE record_id = %s""",
                    (play_count, like_count, interaction_rate, surprise,
                     datetime.now(timezone.utc), record_id),
                )

        # 更新配方的 avg_generated_rate + quality_score_v2
        self._recompute_template_quality(record_id)

    def _recompute_template_quality(self, record_id: str) -> None:
        """重算配方质量分: 源视频×0.3 + 历史生成×0.5 + 采纳率×0.2"""
        with self._db.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT template_id FROM generation_records WHERE record_id = %s",
                    (record_id,),
                )
                row = cur.fetchone()
                if not row or not row[0]:
                    return
                template_id = row[0]

                # 源视频质量（原视频的 interaction_rate）
                cur.execute(
                    """SELECT v.interaction_rate
                       FROM prompt_templates t
                       JOIN videos v ON v.platform = t.source_platform AND v.video_id = t.source_video_id
                       WHERE t.template_id = %s""",
                    (template_id,),
                )
                src_row = cur.fetchone()
                src_quality = float(src_row[0] or 0) if src_row else 0

                # 历史生成效果（已回采记录的平均互动率）
                cur.execute(
                    """SELECT AVG(actual_interaction_rate), COUNT(*)
                       FROM generation_records
                       WHERE template_id = %s AND collected_at IS NOT NULL""",
                    (template_id,),
                )
                gen_row = cur.fetchone()
                avg_generated = float(gen_row[0] or 0) if gen_row else 0
                gen_count = int(gen_row[1] or 0) if gen_row else 0

                # 采纳率
                cur.execute(
                    """SELECT adoption_count, generation_count
                       FROM prompt_templates WHERE template_id = %s""",
                    (template_id,),
                )
                adopt_row = cur.fetchone()
                adoption = float(adopt_row[0] or 0) / max(int(adopt_row[1] or 1), 1) if adopt_row else 0

                # 质量分公式
                quality_v2 = src_quality * 0.3 + avg_generated * 0.5 + adoption * 0.2

                cur.execute(
                    """UPDATE prompt_templates
                       SET avg_generated_rate = %s, quality_score_v2 = %s
                       WHERE template_id = %s""",
                    (avg_generated, quality_v2, template_id),
                )
        logger.info(f"quality: recomputed template {template_id}: score_v2={quality_v2:.4f}")

    def list_records(self, limit: int = 50) -> list[dict]:
        """列出生成记录。"""
        with self._db.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT record_id, template_id, scene_type, video_type,
                              user_theme, selected_factors, status, feedback,
                              published_url, actual_interaction_rate, surprise_score,
                              created_at
                       FROM generation_records
                       ORDER BY created_at DESC LIMIT %s""",
                    (limit,),
                )
                return [
                    {
                        "record_id": r[0], "template_id": r[1], "scene_type": r[2],
                        "video_type": r[3], "user_theme": r[4], "selected_factors": r[5],
                        "status": r[6], "feedback": r[7], "published_url": r[8],
                        "actual_interaction_rate": float(r[9] or 0),
                        "surprise_score": float(r[10] or 0),
                        "created_at": r[11].isoformat() if r[11] else None,
                    }
                    for r in cur.fetchall()
                ]


_loop: Optional[QualityLoop] = None


def get_loop() -> QualityLoop:
    global _loop
    if _loop is None:
        _loop = QualityLoop()
    return _loop

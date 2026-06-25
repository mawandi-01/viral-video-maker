"""Prompt 生成基类 · 处理公共逻辑。

子类只需实现 _do_generate()，专注"怎么构造 prompt 给 Claude"。
"""
from __future__ import annotations

import os
from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient
from src.extract.prompt.context import GenerateContext, PromptPackage, SegmentPrompt
from src.storage.db import get_db


class BaseGenerator:
    """Prompt 生成基类。"""

    # 子类定义: 给 Claude 的 prompt 模板文件名（在 prompts/ 目录下）
    PROMPT_FILE: str = ""

    def __init__(self, client: Optional[ClaudeClient] = None) -> None:
        self._claude = client or ClaudeClient()
        self._db = get_db()

    def generate(self, ctx: GenerateContext) -> PromptPackage:
        """主入口: 加载模板 → 子类生成 → 格式化输出。"""
        logger.info(f"[{self.__class__.__name__}] generate: mode={ctx.mode}, theme={ctx.theme}")

        # 1. 从 PG 加载模板
        template = self._load_template(ctx.template_id)
        if not template:
            raise ValueError(f"template not found: {ctx.template_id}")

        # 2. 子类实现具体生成
        claude_resp = self._do_generate(ctx, template)

        # 3. 解析 Claude 返回，构造 PromptPackage
        package = self._build_package(ctx, claude_resp)
        logger.info(
            f"[{self.__class__.__name__}] done: "
            f"{len(package.segments)} segments, topic={package.video_topic}"
        )
        return package

    def _do_generate(self, ctx: GenerateContext, template: dict) -> dict:
        """子类实现: 调 Claude 生成，返回原始 JSON。"""
        raise NotImplementedError

    def _load_template(self, template_id: str) -> Optional[dict]:
        """从 PG 加载 template_schema + template_features。"""
        with self._db.conn() as conn:
            with conn.cursor() as cur:
                # prompt_templates 表拿 template_schema
                cur.execute(
                    """SELECT template_id, source_video_id, source_platform,
                              template_schema, category, sub_type, quality_score
                       FROM prompt_templates WHERE template_id = %s""",
                    (template_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                import json
                template_schema = row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}")

                # 从 videos 表拿 template_features（完整描述，ModeB 用作参考）
                source_video_id = row[1]
                source_platform = row[2]
                cur.execute(
                    """SELECT template_features FROM videos
                       WHERE platform = %s AND video_id = %s""",
                    (source_platform, source_video_id),
                )
                v_row = cur.fetchone()
                template_features = {}
                if v_row and v_row[0]:
                    template_features = v_row[0] if isinstance(v_row[0], dict) else json.loads(v_row[0])

                return {
                    "template_id": row[0],
                    "source_video_id": source_video_id,
                    "source_platform": source_platform,
                    "template_schema": template_schema,
                    "template_features": template_features,
                    "category": row[4] or "",
                    "sub_type": row[5] or "",
                    "quality_score": row[6] or 0.0,
                }

    def _load_prompt_template(self) -> str:
        """加载 prompts/ 目录下的 prompt 模板文件。"""
        prompt_dir = os.path.join(os.path.dirname(__file__), "prompts")
        path = os.path.join(prompt_dir, self.PROMPT_FILE)
        if not os.path.exists(path):
            raise FileNotFoundError(f"prompt template not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _build_package(self, ctx: GenerateContext, claude_resp: dict) -> PromptPackage:
        """把 Claude 返回转成 PromptPackage。"""
        segments = []
        for i, seg in enumerate(claude_resp.get("segments", [])):
            segments.append(SegmentPrompt(
                index=i + 1,
                duration=int(seg.get("duration", 5)),
                shot=seg.get("shot", ""),
                dialogue=seg.get("dialogue", ""),
                action=seg.get("action", ""),
                transition=seg.get("transition", "硬切"),
            ))

        # 默认约束（0-1 阶段固定值）
        constraints = {
            "aspect_ratio": "9:16",   # 竖屏
            "resolution": "1080p",
            "negative": "不出现品牌logo, 不出现真人面孔(除主播), 不用版权音乐",
        }

        return PromptPackage(
            template_id=ctx.template_id,
            mode=ctx.mode,
            video_topic=claude_resp.get("video_topic", ctx.theme),
            global_prompt=claude_resp.get("global_prompt", ""),
            segments=segments,
            constraints=constraints,
            target_model=ctx.target_model,
            raw_claude_response=claude_resp,
        )

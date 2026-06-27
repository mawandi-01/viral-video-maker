"""场景 2 生成器 · 用户有完整内容，用爆款设计包装。

用户输入: 完整文案 + 风格
流程: 推荐同类型配方 → 勾选爆款设计 → AI 用爆款节奏包装用户内容
"""
from __future__ import annotations

import json
from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient
from src.extract.prompt.base import BaseGenerator
from src.extract.prompt.context import GenerateContext


_SCENE2_PROMPT = """你是一个爆款短视频导演。用户已经写好了完整内容，请用爆款设计来包装它。

【用户的内容】
标题: {user_title}
文案/台词:
{user_content}
想要的风格: {user_style}

【参考爆款配方】（同类型）
{template_schema}

【爆款设计选项】（用户勾选了这些）
{selected_factors}

【迁移指导】
{migration_guide}

【要求】
1. 内容是用户的，不要改写台词，只负责"用爆款设计包装"
2. 按爆款配方的节奏切分用户文案（哪些放钩子段、哪些放信息点段）
3. 给每段配镜头/画面/转场
4. 钩子段落用爆款手法重新包装用户的开场白
5. 保留用户文案的原话，不要替换内容
6. 按勾选的爆款设计来安排镜头和转场

输出 JSON:
{{
  "video_topic": "视频主题",
  "global_prompt": "全局视觉风格",
  "segments": [
    {{"duration": 3, "shot": "镜头", "dialogue": "用户原话", "action": "画面", "transition": "转场"}}
  ],
  "packaging_notes": "包装说明（怎么把用户内容套进爆款结构的）"
}}

只输出 JSON。"""


class Scene2Generator(BaseGenerator):
    """场景 2 · 有完整内容 → 爆款设计包装。"""

    PROMPT_FILE = "scene2.txt"

    def _do_generate(self, ctx: GenerateContext, template: dict) -> dict:
        template_schema = template.get("template_schema", {})
        attribution = template.get("attribution", {})

        selected = ctx.selected_factors or []
        migration = attribution.get("migration_guide", {})
        selected_migration = {k: v for k, v in migration.items() if k in selected}

        user_input = ctx.user_input or {}
        prompt = _SCENE2_PROMPT.format(
            user_title=user_input.get("title", ctx.theme),
            user_content=user_input.get("content", ""),
            user_style=user_input.get("style", ""),
            template_schema=json.dumps(template_schema, ensure_ascii=False, indent=2),
            selected_factors=json.dumps(selected, ensure_ascii=False),
            migration_guide=json.dumps(selected_migration, ensure_ascii=False, indent=2),
        )

        logger.info(f"[Scene2] calling Claude: factors={len(selected)}")
        result = self._client.chat_json(prompt, temperature=0.6, max_tokens=4096)
        logger.info(f"[Scene2] done: {len(result.get('segments', []))} segments")
        return result

"""场景 3 生成器 · 用户有完整 prompt，可选加爆款因子。

用户输入: 完整 prompt 脚本
流程: 用户手动选视频类型 → 推荐该类型爆款因子 → 用户勾选 → AI 增强现有 prompt

注意: 不用 AI 分析视频类型，用户手动选。
"""
from __future__ import annotations

import json
from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient
from src.extract.prompt.base import BaseGenerator
from src.extract.prompt.context import GenerateContext


_SCENE3_PROMPT = """你是一个爆款视频优化师。用户已经有完整的视频 prompt，请根据用户选定的爆款因子来增强它。

【用户的完整 prompt】
{user_prompt}

【视频类型】（用户手动选定）
{video_type}

【用户选定要加入的爆款因子】
{selected_factors}

【迁移指导】（这些因子怎么融入）
{migration_guide}

【要求】
1. 尊重用户已有的 prompt，只做"加料"不做"重写"
2. 把勾选的爆款因子融入现有 prompt 的对应位置
3. 钩子段落: 如果用户勾了钩子类因子，优化开场
4. 节奏段落: 如果用户勾了节奏类因子，调整切分
5. 结尾段落: 如果用户勾了收尾类因子，优化 CTA
6. 输出"增强版 prompt"，保留用户原意

输出 JSON:
{{
  "video_topic": "视频主题",
  "global_prompt": "增强后的全局风格",
  "segments": [
    {{"duration": 3, "shot": "镜头", "dialogue": "台词", "action": "画面", "transition": "转场"}}
  ],
  "enhancement_notes": "增强说明（加了什么、改了什么）"
}}

只输出 JSON。"""


class Scene3Generator(BaseGenerator):
    """场景 3 · 有完整 prompt → 可选加爆款因子。"""

    PROMPT_FILE = "scene3.txt"

    def _do_generate(self, ctx: GenerateContext, template: dict) -> dict:
        # 场景3 不一定需要 template，可能只用 attribution
        attribution = template.get("attribution", {})

        selected = ctx.selected_factors or []
        migration = attribution.get("migration_guide", {})
        selected_migration = {k: v for k, v in migration.items() if k in selected}

        user_prompt = (ctx.user_input or {}).get("prompt", "")

        prompt = _SCENE3_PROMPT.format(
            user_prompt=user_prompt,
            video_type=ctx.video_type or "通用",
            selected_factors=json.dumps(selected, ensure_ascii=False),
            migration_guide=json.dumps(selected_migration, ensure_ascii=False, indent=2),
        )

        logger.info(f"[Scene3] calling Claude: type={ctx.video_type}, factors={len(selected)}")
        result = self._client.chat_json(prompt, temperature=0.5, max_tokens=4096)
        logger.info(f"[Scene3] done: {len(result.get('segments', []))} segments")
        return result

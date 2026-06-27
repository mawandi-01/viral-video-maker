"""场景 1 生成器 · 用户只有大方向，AI 帮写完整脚本。

用户输入: 一句话方向（如"基金理财入门"）
流程: 推荐配方 → 勾选爆款因子 → 输入新主题 → AI 生成完整分镜

和 ModeD 的区别:
- ModeD 盲复制骨架
- Scene1 必须勾选爆款因子，AI 按勾选的因子约束生成
"""
from __future__ import annotations

import json
from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient
from src.extract.prompt.base import BaseGenerator
from src.extract.prompt.context import GenerateContext


_SCENE1_PROMPT = """你是一个爆款短视频编剧。请基于以下爆款配方和用户选定的爆款因子，创作新视频脚本。

【爆款配方】（已抽象，不含原主题）
{template_schema}

【爆款归因】（这个视频为什么爆）
{attribution}

【用户选定要继承的爆款因子】（只继承这些）
{selected_factors}

【迁移指导】（每个因子怎么用到新主题）
{migration_guide}

【新主题】
{theme}

【要求】
1. 严格继承用户勾选的爆款因子（没勾的不要用）
2. 按迁移指导把每个因子落实到新主题
3. 保留配方的分镜结构（时长/段落作用）
4. 台词/画面/镜头全部重新生成，符合新主题
5. 钩子必须用勾选的因子手法，结合新主题领域知识
6. 确保内容专业准确，不空泛

输出 JSON:
{{
  "video_topic": "新视频主题",
  "global_prompt": "全局视觉风格",
  "segments": [
    {{"duration": 3, "shot": "镜头", "dialogue": "台词", "action": "画面", "transition": "转场"}}
  ],
  "used_factors": ["实际用到的因子"]
}}

只输出 JSON。"""


class Scene1Generator(BaseGenerator):
    """场景 1 · 大方向 → AI 帮写。"""

    PROMPT_FILE = "scene1.txt"

    def _do_generate(self, ctx: GenerateContext, template: dict) -> dict:
        template_schema = template.get("template_schema", {})
        attribution = template.get("attribution", {})

        selected = ctx.selected_factors or []
        migration = attribution.get("migration_guide", {})

        # 过滤迁移指导，只保留用户勾选的因子
        selected_migration = {k: v for k, v in migration.items() if k in selected}

        prompt = _SCENE1_PROMPT.format(
            template_schema=json.dumps(template_schema, ensure_ascii=False, indent=2),
            attribution=json.dumps(attribution, ensure_ascii=False, indent=2),
            selected_factors=json.dumps(selected, ensure_ascii=False),
            migration_guide=json.dumps(selected_migration, ensure_ascii=False, indent=2),
            theme=ctx.theme,
        )

        logger.info(f"[Scene1] calling Claude: theme={ctx.theme}, factors={len(selected)}")
        result = self._client.chat_json(prompt, temperature=0.7, max_tokens=4096)
        logger.info(f"[Scene1] done: {len(result.get('segments', []))} segments")
        return result

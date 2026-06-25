"""模式 D · 跨主题迁移。

场景: 原视频是咖啡爆款，用户要做"基金理财科普"
保留: 钩子手法 + 节奏结构 + 内容结构
替换: 整个主题领域

输入: template_schema（骨架）+ 新主题
输出: 新视频的 PromptPackage

和 ModeB 区别: ModeD 不给 template_features（原视频完整描述），
因为跨主题时原视频具体内容参考意义不大，只给抽象配方。
"""
from __future__ import annotations

import json
from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient
from src.extract.prompt.base import BaseGenerator
from src.extract.prompt.context import GenerateContext


class ModeDGenerator(BaseGenerator):
    """跨主题迁移生成器。"""

    PROMPT_FILE = "mode_d.txt"

    def _do_generate(self, ctx: GenerateContext, template: dict) -> dict:
        """调 Claude 生成。"""
        prompt_template = self._load_prompt_template()
        template_schema = template.get("template_schema", {})

        prompt = prompt_template.format(
            template_schema=json.dumps(template_schema, ensure_ascii=False, indent=2),
            hook_recipe=template_schema.get("hook_recipe", "N/A"),
            content_recipe=template_schema.get("content_recipe", "N/A"),
            viral_factors=", ".join(template_schema.get("viral_factors", [])) or "N/A",
            theme=ctx.theme,
        )

        logger.info(f"[ModeD] calling Claude: theme={ctx.theme}")
        result = self._claude.chat_json(prompt, temperature=0.7, max_tokens=4096)
        logger.info(f"[ModeD] Claude returned: {len(result.get('segments', []))} segments")
        return result

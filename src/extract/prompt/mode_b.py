"""模式 B · 同主题换形式。

场景: 原视频是咖啡爆款，用户要做"奶茶知识科普"
保留: 画面分镜结构 + 内容结构
替换: 具体台词词汇 + 画面元素

输入: template_schema（骨架）+ template_features（原视频参考）+ 新主题
输出: 新视频的 PromptPackage
"""
from __future__ import annotations

import json
from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient
from src.extract.prompt.base import BaseGenerator
from src.extract.prompt.context import GenerateContext


class ModeBGenerator(BaseGenerator):
    """同主题换形式生成器。"""

    PROMPT_FILE = "mode_b.txt"

    def _do_generate(self, ctx: GenerateContext, template: dict) -> dict:
        """调 Claude 生成。"""
        prompt_template = self._load_prompt_template()

        prompt = prompt_template.format(
            template_schema=json.dumps(template.get("template_schema", {}), ensure_ascii=False, indent=2),
            template_features=json.dumps(template.get("template_features", {}), ensure_ascii=False, indent=2),
            theme=ctx.theme,
        )

        logger.info(f"[ModeB] calling Claude: theme={ctx.theme}")
        result = self._claude.chat_json(prompt, temperature=0.7, max_tokens=4096)
        logger.info(f"[ModeB] Claude returned: {len(result.get('segments', []))} segments")
        return result

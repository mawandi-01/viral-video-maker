"""模板抽象 · 把融合结果去主题，留可复用结构。

输入: template_features (含具体内容，如"咖啡")
输出: template_schema (半抽象，不含具体主题，但保留内容结构)

template_schema 是"配方"，可以套到任意新主题上。
"""
from __future__ import annotations

from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient


_TEMPLATE_PROMPT = """你是一个爆款视频模板设计师。下面是一个爆款视频的完整拆解（含具体内容），请把它抽象成可复用的"模板配方"。

【完整拆解】
{template_features}

请抽象出这个视频的"结构骨架"(template_schema)，要求:
1. 去掉具体主题词（如"咖啡"→"某事物"），但保留内容结构（如"成本揭秘"）
2. 识别视频分类（category）和子类型（sub_type）
3. 把 segments 抽象: 保留时长/作用/手法/内容结构，去掉具体内容
4. 提炼钩子配方（hook_recipe）和内容配方（content_recipe）
5. 保留爆款因子（viral_factors）

输出严格 JSON:
{{
  "category": "大类（知识科普/剧情/口播/混剪/其他）",
  "sub_type": "子类型（如：成本揭秘/清单推荐/反差对比）",
  "segments": [
    {{
      "duration": 3,
      "shot_type": "镜头类型描述（抽象，如：主播近景举着相关物品）",
      "purpose": "段落作用（钩子/铺垫/信息点/高潮/CTA）",
      "technique": "表现手法（如：反常识数字）",
      "content_structure": "内容结构描述（如：抛出某事物真实成本远低于直觉的事实）"
    }}
  ],
  "pacing": {{
    "avg_segment_sec": 9.3,
    "cut_frequency": "高/中/低"
  }},
  "hook_recipe": "钩子配方描述（如：反常识数字 + 相关物品展示）",
  "content_recipe": "内容配方描述（如：成本拆解清单 + 特写字幕）",
  "viral_factors": ["爆款因子1", "爆款因子2"]
}}

重要: 不要出现具体内容词（如咖啡/2块钱），只保留结构。

只输出 JSON，不要其他文字。"""


class TemplateEngine:
    """模板抽象引擎 · Claude 去主题留结构。"""

    def __init__(self, client: Optional[ClaudeClient] = None) -> None:
        self._client = client or ClaudeClient()

    def abstract(self, template_features: dict) -> dict:
        """把完整拆解抽象成模板配方。

        Args:
            template_features: FusionEngine 输出（含具体内容）

        Returns:
            template_schema (半抽象，可复用)
        """
        logger.info("template engine: abstracting to schema")

        import json
        prompt = _TEMPLATE_PROMPT.format(
            template_features=json.dumps(template_features, ensure_ascii=False, indent=2)
        )

        result = self._client.chat_json(prompt, temperature=0.2, max_tokens=3072)

        segments = result.get("segments", [])
        logger.info(
            f"template engine done: category={result.get('category', 'N/A')}/"
            f"{result.get('sub_type', 'N/A')}, "
            f"{len(segments)} segments, "
            f"hook={result.get('hook_recipe', 'N/A')[:30]}"
        )
        return result


_engine: Optional[TemplateEngine] = None


def get_engine(client: Optional[ClaudeClient] = None) -> TemplateEngine:
    global _engine
    if _engine is None or client is not None:
        _engine = TemplateEngine(client=client)
    return _engine

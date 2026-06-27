"""爆款归因引擎 · 分析视频为什么爆，提炼可选择性继承的爆款因子。

输入: template_features（融合引擎输出，含具体内容）
输出: 归因结果（因子权重 + 反事实 + 迁移指导）

归因结果结构:
{
  "video_type": "知识科普",
  "primary_factor": "反常识钩子",
  "primary_weight": 0.45,
  "factors": [
    {"name": "反常识钩子", "weight": 0.45, "evidence": "...", "applicable": true}
  ],
  "critical_factors": ["反常识钩子", "成本拆解清单"],
  "removable_factors": ["暖色调画面"],
  "migration_guide": {
    "反常识钩子": "新主题里找一个反直觉的数字/事实作开场"
  }
}
"""
from __future__ import annotations

import json
from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient


_ATTRIBUTION_PROMPT = """你是一个爆款视频分析师。下面是一个爆款视频的完整拆解，请分析它为什么爆，提炼出可选择性继承的爆款因子。

【完整拆解】
{template_features}

请输出以下内容：

1. video_type: 视频类型（从以下选一个）:
   知识科普 / 剧情短片 / 口播观点 / 影视混剪 / 测评对比 / 教程技能 / 美食探店 / Vlog生活 / 情感共鸣 / 悬念解密

2. factors: 爆款因子列表（按权重从高到低排序，权重之和≈1.0）
   每个因子包含:
   - name: 因子名称（如"反常识钩子""快节奏剪辑""金句收尾"）
   - weight: 权重（0-1，表示对爆款的贡献度）
   - evidence: 证据（这个因子在视频里的具体表现）
   - applicable: 是否可迁移到其他主题（true/false）

3. critical_factors: 关键因子列表（去掉这些就不爆了）
4. removable_factors: 可去掉的因子（去掉影响不大）
5. migration_guide: 迁移指导（每个可迁移因子怎么用到新主题）

输出严格 JSON:
{{
  "video_type": "知识科普",
  "primary_factor": "反常识钩子",
  "primary_weight": 0.45,
  "factors": [
    {{
      "name": "反常识钩子",
      "weight": 0.45,
      "evidence": "前3秒'咖啡2块钱'违背常识",
      "applicable": true
    }},
    {{
      "name": "成本拆解清单",
      "weight": 0.25,
      "evidence": "信息密度高，逐项拆解易传播",
      "applicable": true
    }}
  ],
  "critical_factors": ["反常识钩子", "成本拆解清单"],
  "removable_factors": ["暖色调画面"],
  "migration_guide": {{
    "反常识钩子": "新主题里找一个反直觉的数字/事实作开场",
    "成本拆解清单": "把新主题拆成3-5个成本/构成要素逐项展示"
  }}
}}

只输出 JSON，不要其他文字。"""


class AttributionEngine:
    """爆款归因引擎。"""

    def __init__(self, client: Optional[ClaudeClient] = None) -> None:
        self._client = client or ClaudeClient()

    def analyze(self, template_features: dict) -> dict:
        """分析爆款原因。

        Args:
            template_features: 融合引擎输出（含具体内容的完整描述）

        Returns:
            归因结果 dict
        """
        logger.info("attribution engine: analyzing viral factors")

        prompt = _ATTRIBUTION_PROMPT.format(
            template_features=json.dumps(template_features, ensure_ascii=False, indent=2)
        )

        result = self._client.chat_json(prompt, temperature=0.3, max_tokens=4096)

        factors = result.get("factors", [])
        logger.info(
            f"attribution done: type={result.get('video_type', 'N/A')}, "
            f"{len(factors)} factors, primary={result.get('primary_factor', 'N/A')}"
        )
        return result


_engine: Optional[AttributionEngine] = None


def get_engine(client: Optional[ClaudeClient] = None) -> AttributionEngine:
    global _engine
    if _engine is None or client is not None:
        _engine = AttributionEngine(client=client)
    return _engine

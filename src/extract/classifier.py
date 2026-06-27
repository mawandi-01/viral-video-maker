"""视频类型分类器 · 10 种类型分类。

类型: 知识科普/剧情短片/口播观点/影视混剪/测评对比/教程技能/美食探店/Vlog生活/情感共鸣/悬念解密

分类策略: 主类型单选 + 辅助标签多选
- 主类型: 10 选 1（决定用哪个抽象策略）
- 辅助标签: 可多选（如"知识科普"视频可能也带"情感共鸣"标签）
"""
from __future__ import annotations

import json
from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient


# 10 种视频类型
VIDEO_TYPES = [
    "知识科普", "剧情短片", "口播观点", "影视混剪", "测评对比",
    "教程技能", "美食探店", "Vlog生活", "情感共鸣", "悬念解密",
]


_CLASSIFY_PROMPT = """你是一个视频分类专家。请根据以下视频拆解数据，判断视频类型。

【视频拆解数据】
{features}

可选类型（选一个主类型）:
1. 知识科普 - 讲解知识/揭秘/科普（如"咖啡成本2元"）
2. 剧情短片 - 有剧情的短剧/段子/反转故事
3. 口播观点 - 主播对着镜头输出观点/价值观/洞察
4. 影视混剪 - 影视素材二创/高燃混剪/名场面
5. 测评对比 - 产品测评/横评/避坑
6. 教程技能 - 教学/怎么做/步骤拆解
7. 美食探店 - 美食制作/探店/吃播
8. Vlog生活 - 日常/旅行/开箱
9. 情感共鸣 - 治愈/励志/情感故事
10. 悬念解密 - 真实案件/历史解密/谜题

输出 JSON:
{{
  "primary_type": "知识科普",
  "secondary_types": ["情感共鸣"],
  "confidence": 0.9,
  "reasoning": "视频讲解咖啡成本构成，属于知识科普；结尾有情感升华，也带情感共鸣标签"
}}

只输出 JSON，不要其他文字。"""


class VideoClassifier:
    """视频类型分类器。"""

    def __init__(self, client: Optional[ClaudeClient] = None) -> None:
        self._client = client or ClaudeClient()

    def classify(self, visual_features: dict, text_features: dict, template_features: dict = None) -> dict:
        """分类视频类型。

        Args:
            visual_features: 视觉引擎输出
            text_features: 文案引擎输出
            template_features: 融合引擎输出（可选，有则更准）

        Returns:
            {
              "primary_type": "知识科普",
              "secondary_types": ["情感共鸣"],
              "confidence": 0.9,
              "reasoning": "..."
            }
        """
        logger.info("classifier: classifying video type")

        features = {
            "visual": visual_features,
            "text": text_features,
        }
        if template_features:
            features["fusion"] = template_features

        prompt = _CLASSIFY_PROMPT.format(
            features=json.dumps(features, ensure_ascii=False, indent=2)
        )

        result = self._client.chat_json(prompt, temperature=0.2, max_tokens=1024)

        primary = result.get("primary_type", "")
        if primary not in VIDEO_TYPES:
            logger.warning(f"classifier: unknown type '{primary}', defaulting to 知识科普")
            result["primary_type"] = "知识科普"

        logger.info(
            f"classifier done: primary={result.get('primary_type')}, "
            f"secondary={result.get('secondary_types', [])}, "
            f"confidence={result.get('confidence', 0)}"
        )
        return result


_classifier: Optional[VideoClassifier] = None


def get_classifier(client: Optional[ClaudeClient] = None) -> VideoClassifier:
    global _classifier
    if _classifier is None or client is not None:
        _classifier = VideoClassifier(client=client)
    return _classifier

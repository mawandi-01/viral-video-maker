"""模板抽象 · V2 分类抽象引擎。

V1 用统一 prompt 处理所有视频。
V2 先判断视频类型，再用对应的抽象策略。

10 种类型 × 10 个抽象策略：
- 知识科普: 抽象「反常识钩子 + 信息密度 + 清单结构」
- 剧情短片: 抽象「情绪曲线 + 反转点位置 + 冲突结构」
- 口播观点: 抽象「金句位置 + 痛点共鸣 + 立场强度」
- 影视混剪: 抽象「音画卡点 + 转场密度 + BGM情绪」
- 测评对比: 抽象「对比维度 + 评分结构 + 悬念节奏」
- 教程技能: 抽象「步骤切分 + 难点标注 + 成果展示」
- 美食探店: 抽象「食欲钩子 + 节奏 + 沉浸感设计」
- Vlog生活: 抽象「叙事节奏 + 情绪点 + 日常升华」
- 情感共鸣: 抽象「共鸣触发 + 情绪递进 + 金句收尾」
- 悬念解密: 抽象「悬念钩子 + 信息释放节奏 + 揭秘时机」
"""
from __future__ import annotations

import json
from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient


# 10 种类型的抽象策略（每种类型关注不同的维度）
_TYPE_STRATEGIES = {
    "知识科普": "重点抽象: 反常识钩子手法 + 信息密度节奏 + 清单/拆解结构 + 数据可视化方式",
    "剧情短片": "重点抽象: 情绪曲线起伏 + 反转点出现时机 + 人物冲突结构 + 结尾落点",
    "口播观点": "重点抽象: 金句出现位置 + 痛点共鸣触发 + 立场鲜明度 + CTA设计",
    "影视混剪": "重点抽象: 音画卡点精准度 + 转场密度 + BGM情绪匹配 + 高潮堆叠手法",
    "测评对比": "重点抽象: 对比维度设计 + 评分结构 + 悬念设置节奏 + 结论意外性",
    "教程技能": "重点抽象: 痛点开场 + 步骤切分粒度 + 难点标注方式 + 成果对比展示",
    "美食探店": "重点抽象: 食欲钩子设计 + 节奏控制 + 沉浸感营造 + 惊喜感设置",
    "Vlog生活": "重点抽象: 叙事节奏 + 情绪点分布 + 日常仪式感 + 升华收尾",
    "情感共鸣": "重点抽象: 共鸣触发点 + 情绪递进曲线 + 金句收尾位置 + 治愈感设计",
    "悬念解密": "重点抽象: 悬念钩子强度 + 信息释放节奏 + 揭秘时机 + 反转设计",
}


_TEMPLATE_PROMPT_V2 = """你是一个爆款视频模板设计师。下面是一个【{video_type}】类爆款视频的完整拆解，请按该类型的抽象策略提炼可复用配方。

【视频类型】{video_type}
【抽象策略】{strategy}

【完整拆解】
{template_features}

请抽象出"结构骨架"(template_schema)，要求:
1. 去掉具体主题词（如"咖啡"→"某事物"），但保留内容结构
2. 严格按【抽象策略】关注的维度来抽象
3. segments 保留时长/作用/手法/内容结构，去掉具体内容
4. 提炼钩子配方（hook_recipe）和内容配方（content_recipe）
5. 保留爆款因子（viral_factors）

输出严格 JSON:
{{
  "video_type": "{video_type}",
  "category": "大类",
  "sub_type": "子类型",
  "segments": [
    {{
      "duration": 3,
      "shot_type": "镜头类型（抽象）",
      "purpose": "段落作用",
      "technique": "表现手法",
      "content_structure": "内容结构描述"
    }}
  ],
  "pacing": {{"avg_segment_sec": 9.3, "cut_frequency": "高"}},
  "hook_recipe": "钩子配方",
  "content_recipe": "内容配方",
  "viral_factors": ["因子1", "因子2"],
  "type_specific": "该类型特有的抽象维度详情"
}}

重要: 不要出现具体内容词，只保留结构。

只输出 JSON，不要其他文字。"""


class TemplateEngine:
    """V2 分类模板抽象引擎。"""

    def __init__(self, client: Optional[ClaudeClient] = None) -> None:
        self._client = client or ClaudeClient()

    def abstract(self, template_features: dict, video_type: str = "") -> dict:
        """把完整拆解抽象成模板配方（按类型用不同策略）。

        Args:
            template_features: 融合引擎输出（含具体内容）
            video_type: 视频类型（来自分类器或归因引擎）。空则用通用策略。

        Returns:
            template_schema (半抽象，带类型标签)
        """
        logger.info(f"template engine V2: abstracting type={video_type or '通用'}")

        strategy = _TYPE_STRATEGIES.get(video_type, "通用抽象: 保留结构，去掉具体内容")
        prompt = _TEMPLATE_PROMPT_V2.format(
            video_type=video_type or "通用",
            strategy=strategy,
            template_features=json.dumps(template_features, ensure_ascii=False, indent=2),
        )

        result = self._client.chat_json(prompt, temperature=0.2, max_tokens=3072)
        # 确保类型标签写入
        if not result.get("video_type"):
            result["video_type"] = video_type or "通用"

        segments = result.get("segments", [])
        logger.info(
            f"template engine V2 done: type={result.get('video_type')}, "
            f"category={result.get('category', 'N/A')}/"
            f"{result.get('sub_type', 'N/A')}, "
            f"{len(segments)} segments"
        )
        return result


_engine: Optional[TemplateEngine] = None


def get_engine(client: Optional[ClaudeClient] = None) -> TemplateEngine:
    global _engine
    if _engine is None or client is not None:
        _engine = TemplateEngine(client=client)
    return _engine

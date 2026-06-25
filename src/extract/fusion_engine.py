"""融合引擎 · 跨模态分析，把三引擎结果对齐成完整描述。

输入: visual_features + audio_features + text_features
输出: template_features (含具体内容的完整描述)

这层保留具体内容（知道视频讲了什么），是后续模板抽象的输入。
"""
from __future__ import annotations

from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient


_FUSION_PROMPT = """你是一个爆款视频分析师。下面是一个视频的多模态拆解结果，请把它们融合成"逐秒还原"的完整描述。

【视觉特征】
{visual_features}

【音频特征（ASR）】
{audio_features}

【文案特征】
{text_features}

请输出融合后的完整分析，要求:
1. 把画面、台词、文案作用按时间对齐
2. 还原每个 segment: 画面是什么 + 说了什么 + 这段的作用
3. 分析爆款因子（为什么这个视频能爆）
4. 保留具体内容（不要抽象，比如"咖啡"就是"咖啡"，不要写成"某事物"）

输出严格 JSON:
{{
  "video_topic": "视频主题（如：咖啡成本揭秘）",
  "segments": [
    {{
      "time": "0-3s",
      "shot": "画面描述（如：主播近景举着咖啡）",
      "dialogue": "这段说的话",
      "purpose": "段落作用（钩子/铺垫/信息点/高潮/CTA）",
      "technique": "表现手法（如：反常识数字）",
      "content_summary": "这段内容摘要",
      "emotion": "情绪（惊讶/平静/激动等）"
    }}
  ],
  "viral_analysis": {{
    "hook_strength": "高/中/低",
    "pacing": "快/中/慢",
    "info_density": "信息密度描述",
    "viral_factors": ["爆款因子1", "爆款因子2"]
  }}
}}

只输出 JSON，不要其他文字。"""


class FusionEngine:
    """融合引擎 · 跨模态分析。"""

    def __init__(self, client: Optional[ClaudeClient] = None) -> None:
        self._client = client or ClaudeClient()

    def fuse(
        self,
        visual_features: dict,
        audio_features: dict,
        text_features: dict,
    ) -> dict:
        """融合三引擎结果。

        Args:
            visual_features: VisualEngine 输出
            audio_features: WhisperEngine 输出
            text_features: TextEngine 输出

        Returns:
            template_features (含具体内容的完整描述)
        """
        logger.info("fusion engine: fusing 3 modalities")

        import json
        prompt = _FUSION_PROMPT.format(
            visual_features=json.dumps(visual_features, ensure_ascii=False, indent=2),
            audio_features=json.dumps(audio_features, ensure_ascii=False, indent=2),
            text_features=json.dumps(text_features, ensure_ascii=False, indent=2),
        )

        result = self._client.chat_json(prompt, temperature=0.3, max_tokens=8192)

        # 如果 JSON 解析失败（被截断），尝试用 chat 拿原始文本再处理
        if not result.get("segments"):
            logger.warning("fusion: JSON parse returned empty, retrying with raw text")
            raw = self._client.chat(prompt, temperature=0.3, max_tokens=8192)
            result = self._client._extract_json(raw)
            if not result.get("segments"):
                logger.warning(f"fusion: still no segments, raw length={len(raw)}")
                # 至少保留原始文本，不阻塞后续流程
                result = {
                    "video_topic": "解析失败（保留原始文本）",
                    "segments": [],
                    "viral_analysis": {"viral_factors": []},
                    "_raw_text": raw[:2000],
                }

        segments = result.get("segments", [])
        viral = result.get("viral_analysis", {})
        logger.info(
            f"fusion engine done: {len(segments)} segments, "
            f"topic={result.get('video_topic', 'N/A')}, "
            f"viral_factors={len(viral.get('viral_factors', []))}"
        )
        return result


_engine: Optional[FusionEngine] = None


def get_engine(client: Optional[ClaudeClient] = None) -> FusionEngine:
    global _engine
    if _engine is None or client is not None:
        _engine = FusionEngine(client=client)
    return _engine

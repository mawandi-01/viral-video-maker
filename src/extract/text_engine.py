"""文案引擎 · 用 claude-sonnet-4 对 ASR 文本做结构化拆解。

输入: ASR 文本（带时间戳的分段）
输出: text_features JSONB

提取: 钩子类型/内容结构/关键词/金句/CTA 位置
"""
from __future__ import annotations

from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient


_TEXT_PROMPT = """你是一个爆款短视频文案分析师。请分析以下视频的语音转写文本，提取文案结构。

【转写文本】（带时间戳）
{transcript}

请提取以下信息，输出严格 JSON:

1. hook: 前3-5秒的钩子
   - type: 钩子类型（反常识数字/悬念提问/痛点共鸣/故事开场/冲突展示）
   - text: 钩子原文
   - duration: 钩子时长（秒，估算）

2. structure: 内容结构（标签列表，如 ["钩子","铺垫","信息点1","高潮","CTA"]）

3. keywords: 关键词列表（3-8个，主题词+情绪词）

4. golden_lines: 金句列表（可能被二次传播的句子，1-3句）

5. cta: 行动召唤
   - text: CTA 文案
   - at_sec: 出现在第几秒

6. content_summary: 全文内容摘要（一句话）

输出格式:
{{
  "hook": {{"type": "...", "text": "...", "duration": 3}},
  "structure": ["钩子", "铺垫", "信息点1", "CTA"],
  "keywords": ["关键词1", "关键词2"],
  "golden_lines": ["金句1"],
  "cta": {{"text": "...", "at_sec": 175}},
  "content_summary": "一句话摘要"
}}

只输出 JSON，不要其他文字。"""


class TextEngine:
    """文案引擎 · Claude 拆文案。"""

    def __init__(self, client: Optional[ClaudeClient] = None) -> None:
        self._client = client or ClaudeClient()

    def analyze(self, audio_features: dict) -> dict:
        """分析 ASR 结果，提取文案结构。

        Args:
            audio_features: WhisperEngine 的输出
                {
                  "transcript": "全文",
                  "segments": [{"start", "end", "text"}]
                }

        Returns:
            text_features dict
        """
        transcript = audio_features.get("transcript", "") or audio_features.get("text", "")
        if not transcript:
            logger.warning("text engine: empty transcript, skipping")
            return {
                "hook": {},
                "structure": [],
                "keywords": [],
                "golden_lines": [],
                "cta": {},
                "content_summary": "",
            }

        # 构造带时间戳的转写文本
        segments = audio_features.get("segments", [])
        if segments:
            transcript_with_ts = "\n".join(
                f"[{seg.get('start', 0):.1f}s-{seg.get('end', 0):.1f}s] {seg.get('text', '')}"
                for seg in segments
            )
        else:
            transcript_with_ts = transcript

        logger.info(f"text engine: analyzing {len(transcript)} chars, {len(segments)} segments")

        prompt = _TEXT_PROMPT.replace("{transcript}", transcript_with_ts)
        result = self._client.chat_json(prompt, temperature=0.3, max_tokens=2048)

        logger.info(
            f"text engine done: hook_type={result.get('hook', {}).get('type', 'N/A')}, "
            f"keywords={len(result.get('keywords', []))}, "
            f"golden_lines={len(result.get('golden_lines', []))}"
        )
        return result


_engine: Optional[TextEngine] = None


def get_engine(client: Optional[ClaudeClient] = None) -> TextEngine:
    global _engine
    if _engine is None or client is not None:
        _engine = TextEngine(client=client)
    return _engine

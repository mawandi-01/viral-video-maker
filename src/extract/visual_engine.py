"""视觉引擎 · 用 claude-sonnet-4 看视频关键帧。

输入: 关键帧 JPG 列表
输出: visual_features JSONB

每 N 帧一批调 Claude 看图，让 Claude 描述每帧的画面元素/镜头/风格。
"""
from __future__ import annotations

import os
from typing import Optional
from loguru import logger

from src.ai.claude_client import ClaudeClient


# 给 Claude 的视觉分析 prompt
_VISUAL_PROMPT = """你是一个专业的视频画面分析师。请分析这些视频关键帧，输出结构化 JSON。

对每一帧，提取:
- time: 该帧出现的时间点（如果能从顺序推断）
- shot_type: 镜头类型（近景/中景/全景/特写）
- elements: 画面中的主要元素（人物/物品/场景/文字）
- style: 视觉风格标签（真人出镜/动画/混剪/vlog/口播）
- transition: 与上一帧的转场方式（硬切/淡入淡出/特效）
- on_screen_text: 画面中出现的文字（如有）

最后还要输出:
- global_style: 全局视觉风格标签列表

输出严格 JSON 格式:
{
  "frames": [
    {
      "frame_index": 1,
      "shot_type": "近景",
      "elements": ["主播", "咖啡杯"],
      "style": ["真人出镜"],
      "transition": "硬切",
      "on_screen_text": ""
    }
  ],
  "global_style": ["暖色调", "快剪", "真人出镜"]
}

只输出 JSON，不要其他文字。"""


class VisualEngine:
    """视觉引擎 · Claude 看帧。"""

    def __init__(self, client: Optional[ClaudeClient] = None) -> None:
        self._client = client or ClaudeClient()
        self._batch_size = 12  # 每次请求带 12 张图（减少 API 调用次数，适配限流）

    def analyze(self, frames: list[str]) -> dict:
        """分析关键帧列表，返回 visual_features。

        Args:
            frames: JPG 文件路径列表

        Returns:
            {
              "frames": [{"frame_index", "shot_type", "elements", ...}],
              "global_style": ["真人出镜", "暖色调", ...]
            }
        """
        if not frames:
            return {"frames": [], "global_style": []}

        logger.info(f"visual engine: analyzing {len(frames)} frames, batch={self._batch_size}")

        all_frames_result = []
        global_styles: set = set()

        # 分批处理
        for i in range(0, len(frames), self._batch_size):
            batch = frames[i:i + self._batch_size]
            batch_num = i // self._batch_size + 1
            logger.info(f"visual batch {batch_num}: frames {i+1}-{i+len(batch)}")

            try:
                images = [(f, "image/jpeg") for f in batch]
                # 在 prompt 里告诉 Claude 这是第几帧到第几帧
                frame_info = f"这是第 {i+1} 到 {i+len(batch)} 帧（共 {len(frames)} 帧）。"
                resp_text = self._client.see_image(
                    images=images,
                    prompt=frame_info + "\n" + _VISUAL_PROMPT,
                    max_tokens=2048,
                )
                batch_result = self._client._extract_json(resp_text)

                # 合并结果
                for frame_data in batch_result.get("frames", []):
                    frame_data["frame_index"] = i + frame_data.get("frame_index", 1)
                    all_frames_result.append(frame_data)
                global_styles.update(batch_result.get("global_style", []))

            except Exception as e:
                logger.error(f"visual batch {batch_num} failed: {e}")
                # 失败的批次填占位
                for j in range(len(batch)):
                    all_frames_result.append({
                        "frame_index": i + j + 1,
                        "shot_type": "未知",
                        "elements": [],
                        "style": [],
                        "transition": "未知",
                        "on_screen_text": "",
                        "error": str(e)[:200],
                    })

        result = {
            "frames": all_frames_result,
            "global_style": list(global_styles),
            "frame_count": len(all_frames_result),
        }
        logger.info(f"visual engine done: {len(all_frames_result)} frames analyzed, styles={list(global_styles)}")
        return result


_engine: Optional[VisualEngine] = None


def get_engine(client: Optional[ClaudeClient] = None) -> VisualEngine:
    global _engine
    if _engine is None or client is not None:
        _engine = VisualEngine(client=client)
    return _engine

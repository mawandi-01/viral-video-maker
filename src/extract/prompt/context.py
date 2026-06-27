"""Prompt 生成的数据结构 V2。

GenerateContext: 统一输入上下文（V2 新增 selected_factors / user_input / video_type）
PromptPackage: 统一输出
SegmentPrompt: 分段 prompt
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GenerateContext:
    """Prompt 生成的统一输入上下文 V2。

    3 种场景按需取字段:
    - 场景1 (大方向): template_id + theme + selected_factors
    - 场景2 (有内容): template_id + user_input{title,content,style} + selected_factors
    - 场景3 (有prompt): user_input{prompt} + video_type(用户手选) + selected_factors(可选)
    """
    template_id: str = ""                  # 配方ID（场景1/2必填，场景3可选）
    mode: str = ""                         # 兼容旧接口
    scene: str = "1"                       # 场景: 1/2/3
    theme: str = ""                        # 新主题（场景1需要）
    selected_factors: list[str] = field(default_factory=list)  # 勾选的爆款因子
    user_input: dict = field(default_factory=dict)  # 用户输入（场景2/3用）
    video_type: str = ""                   # 视频类型（场景3用户手选）
    target_model: str = "kling"            # 目标视频模型
    # 兼容旧字段
    style: str = ""
    character: str = ""
    target_duration: int = 0


@dataclass
class SegmentPrompt:
    """单段 prompt。"""
    index: int
    duration: int
    shot: str = ""
    dialogue: str = ""
    action: str = ""
    transition: str = ""

    def to_text(self) -> str:
        parts = [f"[段{self.index} · {self.duration}s]"]
        if self.shot: parts.append(f"镜头: {self.shot}")
        if self.dialogue: parts.append(f"台词: {self.dialogue}")
        if self.action: parts.append(f"画面: {self.action}")
        if self.transition: parts.append(f"转场: {self.transition}")
        return " ".join(parts)


@dataclass
class PromptPackage:
    """Prompt 生成的统一输出。"""
    template_id: str = ""
    mode: str = ""
    scene: str = ""
    video_topic: str = ""
    global_prompt: str = ""
    segments: list[SegmentPrompt] = field(default_factory=list)
    constraints: dict = field(default_factory=dict)
    target_model: str = "kling"
    used_factors: list[str] = field(default_factory=list)  # 实际用到的因子
    enhancement_notes: str = ""  # 场景3的增强说明
    raw_claude_response: dict = field(default_factory=dict)

    def to_summary(self) -> str:
        lines = [
            f"=== PromptPackage ===",
            f"场景: {self.scene}",
            f"模板: {self.template_id or '无'}",
            f"主题: {self.video_topic}",
            f"目标模型: {self.target_model}",
            f"继承因子: {', '.join(self.used_factors) if self.used_factors else '无'}",
            f"",
            f"全局风格: {self.global_prompt}",
            f"",
            f"分段 ({len(self.segments)} 段):",
        ]
        for seg in self.segments:
            lines.append(f"  {seg.to_text()}")
        if self.enhancement_notes:
            lines.append(f"\n增强说明: {self.enhancement_notes}")
        return "\n".join(lines)

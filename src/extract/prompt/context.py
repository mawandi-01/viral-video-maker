"""Prompt 生成的数据结构。

GenerateContext: 统一输入上下文
PromptPackage: 统一输出
SegmentPrompt: 分段 prompt
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GenerateContext:
    """Prompt 生成的统一输入上下文。

    各模式按需取字段:
    - Mode B (同主题换形式): template_id + theme
    - Mode D (跨主题迁移): template_id + theme
    - Mode A (翻拍复刻): template_id + character (0-1阶段不做)
    - Mode E (风格混搭): template_id + style (0-1阶段不做)
    - Mode F (时长重铸): template_id + target_duration (0-1阶段不做)
    """
    template_id: str               # 必填：用哪个模板
    mode: str                      # 必填：A/B/C/D/E/F
    theme: str = ""                # 新主题（B/C/D 需要）
    style: str = ""                # 新风格（E 需要）
    character: str = ""            # 人物替换（A 需要）
    target_duration: int = 0       # 目标时长秒（F 需要）
    target_model: str = "kling"    # 目标视频模型（适配用）


@dataclass
class SegmentPrompt:
    """单段 prompt。"""
    index: int                     # 段序号（从1开始）
    duration: int                  # 时长（秒）
    shot: str = ""                 # 镜头描述
    dialogue: str = ""             # 台词
    action: str = ""               # 画面动作
    transition: str = ""           # 转场方式

    def to_text(self) -> str:
        """转成纯文本描述（给视频生成模型用）。"""
        parts = [f"[段{self.index} · {self.duration}s]"]
        if self.shot:
            parts.append(f"镜头: {self.shot}")
        if self.dialogue:
            parts.append(f"台词: {self.dialogue}")
        if self.action:
            parts.append(f"画面: {self.action}")
        if self.transition:
            parts.append(f"转场: {self.transition}")
        return " ".join(parts)


@dataclass
class PromptPackage:
    """Prompt 生成的统一输出。"""
    template_id: str               # 用的哪个模板
    mode: str                      # 用的哪个模式
    video_topic: str = ""          # 生成的视频主题
    global_prompt: str = ""        # 全局风格描述
    segments: list[SegmentPrompt] = field(default_factory=list)  # 分段 prompt
    constraints: dict = field(default_factory=dict)              # 约束（时长/比例/负面）
    target_model: str = "kling"    # 目标模型
    raw_claude_response: dict = field(default_factory=dict)      # Claude 原始返回（调试用）

    def to_summary(self) -> str:
        """转成人类可读的摘要。"""
        lines = [
            f"=== PromptPackage ===",
            f"模板: {self.template_id}",
            f"模式: {self.mode}",
            f"主题: {self.video_topic}",
            f"目标模型: {self.target_model}",
            f"",
            f"全局风格: {self.global_prompt}",
            f"",
            f"分段 ({len(self.segments)} 段):",
        ]
        for seg in self.segments:
            lines.append(f"  {seg.to_text()}")
        if self.constraints:
            lines.append(f"")
            lines.append(f"约束: {self.constraints}")
        return "\n".join(lines)

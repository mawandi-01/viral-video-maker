"""Prompt 生成器工厂 V2。

V2 支持 3 种场景:
- scene1: 大方向 → AI 帮写（含爆款因子勾选）
- scene2: 有完整内容 → 爆款设计包装
- scene3: 有完整 prompt → 可选加爆款因子（用户手选视频类型）

兼容旧接口: mode=B/D 仍可用（映射到 scene1）。
"""
from __future__ import annotations

from typing import Optional

from src.ai.claude_client import ClaudeClient
from src.extract.prompt.base import BaseGenerator
from src.extract.prompt.mode_b import ModeBGenerator
from src.extract.prompt.mode_d import ModeDGenerator
from src.extract.prompt.scene1 import Scene1Generator
from src.extract.prompt.scene2 import Scene2Generator
from src.extract.prompt.scene3 import Scene3Generator


class PromptGeneratorFactory:
    """根据场景/模式创建 Generator。"""

    # V2 场景
    _scenes = {
        "1": Scene1Generator,   # 大方向 → AI 帮写
        "2": Scene2Generator,   # 有完整内容 → 爆款设计包装
        "3": Scene3Generator,   # 有完整 prompt → 可选加爆款因子
    }

    # 兼容 V1 模式
    _legacy_modes = {
        "B": ModeBGenerator,    # 同主题换形式
        "D": ModeDGenerator,    # 跨主题迁移
    }

    @classmethod
    def create(cls, mode_or_scene: str, client: Optional[ClaudeClient] = None) -> BaseGenerator:
        """创建生成器。

        Args:
            mode_or_scene: 场景(1/2/3) 或 旧模式(B/D)
            client: ClaudeClient 实例（可选）

        Returns:
            BaseGenerator 子类实例
        """
        key = mode_or_scene.upper() if mode_or_scene.upper() in cls._legacy_modes else mode_or_scene

        gen_class = cls._scenes.get(key) or cls._legacy_modes.get(key.upper())
        if not gen_class:
            supported = list(cls._scenes.keys()) + list(cls._legacy_modes.keys())
            raise ValueError(f"unsupported: {mode_or_scene}, supported: {supported}")
        return gen_class(client=client)

    @classmethod
    def supported_scenes(cls) -> list[str]:
        return list(cls._scenes.keys())

    @classmethod
    def scene_descriptions(cls) -> dict:
        return {
            "1": "💡 大方向 → AI 帮写（选配方+勾因子+输入主题）",
            "2": "📝 有完整内容 → 用爆款设计包装",
            "3": "✨ 有完整 prompt → 可选加爆款因子（手选类型）",
        }

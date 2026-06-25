"""Prompt 生成器工厂。

根据 mode 创建对应的 Generator。
0-1 阶段只支持 B 和 D，其他模式预留接口。
"""
from __future__ import annotations

from typing import Optional

from src.ai.claude_client import ClaudeClient
from src.extract.prompt.base import BaseGenerator
from src.extract.prompt.mode_b import ModeBGenerator
from src.extract.prompt.mode_d import ModeDGenerator


class PromptGeneratorFactory:
    """根据 mode 创建 Generator。"""

    _generators = {
        "B": ModeBGenerator,
        "D": ModeDGenerator,
        # 预留（0-1 阶段不实现）:
        # "A": ModeAGenerator,  # 翻拍复刻
        # "C": ModeCGenerator,  # 同主题全创新
        # "E": ModeEGenerator,  # 风格混搭
        # "F": ModeFGenerator,  # 时长重铸
    }

    @classmethod
    def create(cls, mode: str, client: Optional[ClaudeClient] = None) -> BaseGenerator:
        """创建指定模式的生成器。

        Args:
            mode: 模式标识（A/B/C/D/E/F）
            client: ClaudeClient 实例（可选，默认新建）

        Returns:
            BaseGenerator 子类实例

        Raises:
            ValueError: 不支持的 mode
        """
        gen_class = cls._generators.get(mode.upper())
        if not gen_class:
            supported = list(cls._generators.keys())
            raise ValueError(f"unsupported mode: {mode}, supported: {supported}")
        return gen_class(client=client)

    @classmethod
    def supported_modes(cls) -> list[str]:
        """返回支持的 mode 列表。"""
        return list(cls._generators.keys())

    @classmethod
    def mode_descriptions(cls) -> dict:
        """返回各 mode 的描述。"""
        return {
            "B": "同主题换形式 - 保留分镜+内容结构，替换词汇+画面元素",
            "D": "跨主题迁移 - 保留钩子+节奏+内容结构，替换整个主题领域",
        }

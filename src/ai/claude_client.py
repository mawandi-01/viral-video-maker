"""AI 客户端 · 封装 CLIProxyAPI 调用 Claude。

CLIProxyAPI 是本地中转站 (localhost:8317)，代理 claude-sonnet-4 等。
- 文本对话: POST /v1/chat/completions (OpenAI 兼容格式)
- 视觉理解: POST /v1/messages (Anthropic 原生格式 + base64 图片)

两个方法:
- chat(): 纯文本对话，用于文案引擎/融合引擎/模板抽象/prompt生成
- see_image(): 看图理解，用于视觉引擎

用法:
    from src.ai.claude_client import ClaudeClient
    client = ClaudeClient()
    text = client.chat("你好")                      # 文本
    desc = client.see_image([("/path/to.jpg", "描述这张图")])  # 看图
"""
from __future__ import annotations

import base64
import json
import os
import time
from typing import Optional
from loguru import logger
import httpx

from config.settings import settings


class ClaudeClient:
    """封装 CLIProxyAPI 的 Claude 调用。"""

    def __init__(self) -> None:
        self._base_url = settings.ai.base_url.rstrip("/")
        self._api_key = settings.ai.api_key
        self._model = settings.ai.model
        self._timeout = settings.ai.timeout
        self._max_retries = settings.ai.max_retries

    def chat(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """纯文本对话。

        Args:
            prompt: 用户输入
            system: 系统提示词（可选）
            temperature: 0-1，越高越随机
            max_tokens: 最大输出 token 数

        Returns:
            Claude 的回复文本
        """
        messages = [{"role": "user", "content": prompt}]
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system

        resp = self._post("/v1/chat/completions", payload)
        # OpenAI 兼容格式: choices[0].message.content
        choices = resp.get("choices", [])
        if not choices:
            logger.warning(f"chat: empty choices, raw={resp}")
            return ""
        return choices[0].get("message", {}).get("content", "").strip()

    def chat_json(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict:
        """文本对话，要求返回 JSON。自动提取 JSON 块。

        Returns:
            解析后的 dict。解析失败返回空 dict。
        """
        text = self.chat(prompt, system=system, temperature=temperature, max_tokens=max_tokens)
        return self._extract_json(text)

    def see_image(
        self,
        images: list[tuple[str, str]],
        prompt: str = "请描述这些图片的内容。",
        max_tokens: int = 1024,
    ) -> str:
        """视觉理解 · 让 Claude 看图片。

        走 Anthropic 原生 /v1/messages 端点，因为 OpenAI 兼容格式传图有问题。

        Args:
            images: [(图片路径, 媒体类型), ...]
                    媒体类型: "image/jpeg" / "image/png"
            prompt: 给 Claude 的指令

        Returns:
            Claude 的描述文本
        """
        # 构造 Anthropic messages 格式
        content: list[dict] = []
        for img_path, media_type in images:
            if not os.path.exists(img_path):
                logger.warning(f"image not found: {img_path}")
                continue
            with open(img_path, "rb") as f:
                img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": img_b64,
                },
            })
        if not content:
            return ""

        content.append({"type": "text", "text": prompt})

        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }

        resp = self._post("/v1/messages", payload, anthropic=True)
        # Anthropic 格式: content[0].text
        content_list = resp.get("content", [])
        if not content_list:
            logger.warning(f"see_image: empty content, raw={resp}")
            return ""
        return content_list[0].get("text", "").strip()

    def see_image_batch(
        self,
        images: list[tuple[str, str]],
        prompt: str = "请描述这些图片的内容。",
        max_tokens: int = 2048,
    ) -> str:
        """批量看图（一次请求带多张图）。"""
        return self.see_image(images, prompt, max_tokens)

    def _post(self, path: str, payload: dict, anthropic: bool = False) -> dict:
        """POST 请求，带重试。500 错误时等更久再重试。"""
        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if anthropic:
            headers["anthropic-version"] = "2023-06-01"

        last_err = ""
        for attempt in range(self._max_retries):
            try:
                with httpx.Client(timeout=self._timeout, trust_env=False) as client:
                    r = client.post(url, json=payload, headers=headers)
                    r.raise_for_status()
                    return r.json()
            except Exception as e:
                last_err = str(e)
                # 500/503 错误等更久（上游可能临时过载）
                if "500" in last_err or "503" in last_err:
                    wait = (attempt + 1) * 15  # 15s, 30s, 45s
                else:
                    wait = (attempt + 1) * 2
                logger.warning(f"API call failed (attempt {attempt+1}/{self._max_retries}): {last_err[:200]}, retry in {wait}s")
                time.sleep(wait)

        logger.error(f"API call exhausted retries: {last_err}")
        raise RuntimeError(f"Claude API call failed after {self._max_retries} retries: {last_err}")

    @staticmethod
    def _extract_json(text: str) -> dict:
        """从 Claude 回复中提取 JSON。

        Claude 经常在 JSON 前后加 markdown 标记（```json ... ```），需要清理。
        """
        if not text:
            return {}
        # 去掉 markdown 代码块标记
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # 去掉首行 ```json 和末行 ```
            start = 1
            end = len(lines)
            if lines[-1].strip() == "```":
                end = -1
            cleaned = "\n".join(lines[start:end] if end > 0 else lines[1:])

        # 尝试直接解析
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 尝试找到第一个 { 和最后一个 } 之间的内容
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first != -1 and last != -1 and last > first:
            try:
                return json.loads(cleaned[first:last+1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"failed to extract JSON from: {text[:200]}")
        return {}


_client: Optional[ClaudeClient] = None


def get_client() -> ClaudeClient:
    global _client
    if _client is None:
        _client = ClaudeClient()
    return _client

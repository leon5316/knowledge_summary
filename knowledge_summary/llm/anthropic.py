"""Anthropic Claude 客户端。"""
from __future__ import annotations

import time
from typing import Dict, List

import requests

from .base import BaseLLM, LLMError


class AnthropicLLM(BaseLLM):
    name = "anthropic"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.api_key = cfg.get("llm", "api_key", "") or ""
        self.model = cfg.get("llm", "model", "") or "claude-3-5-haiku-latest"
        if not self.api_key:
            raise LLMError(
                "llm.provider=anthropic 但未设置 API Key，"
                f"请设置环境变量 {cfg.get('llm', 'api_key_env', 'LLM_API_KEY')}。"
            )

    def chat(self, messages, temperature=None, max_tokens=None) -> str:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        user_msgs = [{"role": m["role"], "content": m["content"]}
                     for m in messages if m["role"] != "system"]
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": user_msgs,
        }
        if system:
            payload["system"] = system
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                if resp.status_code != 200:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                blocks = resp.json().get("content", [])
                content = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
                if not content:
                    raise LLMError("Anthropic 返回空内容")
                return content.strip()
            except LLMError:
                raise
            except Exception as e:
                last_err = e
                if attempt < self.retries:
                    time.sleep(0.5 * (2 ** attempt))
        raise LLMError(f"Anthropic 调用失败: {last_err}")

"""Ollama 本地 LLM 客户端。"""
from __future__ import annotations

import time
from typing import Dict, List

import requests

from .base import BaseLLM, LLMError


class OllamaLLM(BaseLLM):
    name = "ollama"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.base_url = (cfg.get("llm", "base_url", "") or "").rstrip("/") or "http://localhost:11434"
        self.model = cfg.get("llm", "model", "") or "qwen2.5:7b"

    def chat(self, messages, temperature=None, max_tokens=None) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else self.temperature,
                "num_predict": max_tokens or self.max_tokens,
            },
        }
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = requests.post(url, json=payload, timeout=self.timeout)
                if resp.status_code != 200:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                content = resp.json().get("message", {}).get("content", "")
                if not content:
                    raise LLMError("Ollama 返回空内容")
                return content.strip()
            except LLMError:
                raise
            except Exception as e:
                last_err = e
                if attempt < self.retries:
                    time.sleep(0.5 * (2 ** attempt))
        raise LLMError(f"Ollama 调用失败: {last_err}")

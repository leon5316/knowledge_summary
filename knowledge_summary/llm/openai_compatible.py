"""OpenAI 兼容 API 客户端（DeepSeek / OpenAI / vLLM / 任意兼容服务）。"""
from __future__ import annotations

import time
from typing import Dict, List

import requests

from .base import BaseLLM, LLMError


class OpenAICompatibleLLM(BaseLLM):
    name = "openai_compatible"

    def __init__(self, cfg):
        super().__init__(cfg)
        self.base_url = (cfg.get("llm", "base_url", "") or "").rstrip("/")
        self.api_key = cfg.get("llm", "api_key", "") or ""
        self.model = cfg.get("llm", "model", "deepseek-chat") or "deepseek-chat"
        if not self.base_url:
            raise LLMError(
                "llm.provider=openai_compatible 但未配置 llm.base_url "
                "（如 https://api.deepseek.com/v1 或本地 vLLM 地址）。"
                "若使用需要鉴权的服务，请同时设置环境变量 "
                f"{cfg.get('llm', 'api_key_env', 'LLM_API_KEY')}。"
            )

    def chat(self, messages, temperature=None, max_tokens=None) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                if resp.status_code != 200:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if not content:
                    raise LLMError("LLM 返回空内容")
                return content.strip()
            except LLMError:
                raise
            except Exception as e:  # 网络/解析错误，可重试
                last_err = e
                if attempt < self.retries:
                    time.sleep(0.5 * (2 ** attempt))
        raise LLMError(f"LLM 调用失败（已重试 {self.retries} 次）: {last_err}")

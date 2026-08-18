"""LLM 工厂：根据配置创建对应提供方的客户端。"""
from __future__ import annotations

from ..config import Config
from .base import BaseLLM, LLMError  # noqa: F401
from .local_fallback import LocalFallbackLLM
from .openai_compatible import OpenAICompatibleLLM
from .ollama import OllamaLLM
from .anthropic import AnthropicLLM

_PROVIDERS = {
    "openai_compatible": OpenAICompatibleLLM,
    "ollama": OllamaLLM,
    "anthropic": AnthropicLLM,
}


def create_llm(cfg: Config) -> BaseLLM:
    """创建 LLM 客户端；配置错误时抛 LLMError（调用方可决定是否降级）。"""
    provider = cfg.get("llm", "provider", "openai_compatible")
    if provider in ("none", "local"):
        return LocalFallbackLLM(cfg)
    cls = _PROVIDERS.get(provider)
    if cls is None:
        raise LLMError(f"未知的 llm.provider: {provider!r}")
    return cls(cfg)


__all__ = ["BaseLLM", "LLMError", "LocalFallbackLLM", "create_llm"]

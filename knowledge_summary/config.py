"""配置加载与合并。

优先级（低 -> 高）:
    1. 内置默认值（代码内 DEFAULTS）
    2. 仓库根目录的 default_config.yaml（若存在）
    3. 用户通过 --config 指定的配置文件
    4. CLI 直接覆盖项（如 --provider/--model/--output-dir-name）

API Key 只从环境变量读取（llm.api_key_env 指定变量名）。
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# ---- 内置默认值（default_config.yaml 缺失时的兜底，两者应保持一致） ----
DEFAULTS: Dict[str, Any] = {
    "general": {
        "output_dir_name": "knowledge",
        "ignore_dirs": [".git", ".svn", ".hg", "node_modules", "__pycache__",
                        ".venv", "venv", "dist", "build", ".idea", ".vscode", "knowledge"],
        "ignore_patterns": [],
        "max_file_size_mb": 20,
        "treat_unknown_as_text": False,
    },
    "llm": {
        "provider": "openai_compatible",
        "model": "deepseek-chat",
        "base_url": "",
        "api_key_env": "LLM_API_KEY",
        "temperature": 0.2,
        "max_tokens": 4096,
        "timeout_s": 120,
        "retries": 3,
        "concurrency": 4,
        "system_prompt_extra": "",
        "fallback_to_local": True,
    },
    "chunking": {
        "max_chunk_chars": 4000,
        "overlap_chars": 300,
        "prefer_semantic_boundary": True,
    },
    "summarization": {
        "enabled": True,
        "languages": ["en"],
        "hierarchy": ["chunk", "file", "global"],
    },
    "extractors": {
        "pdf": {"method": "auto"},
        "doc": {"method": "auto"},
        "sql": {"keep_comments": True},
        "python": {"include_docstrings": True},
        "html": {"include_tables": True},
    },
    "topology": {
        "enabled": True,
        "enable_static_analysis": True,
        "enable_llm_relations": True,
        "include_keywords_as_concepts": True,
        "max_relations_per_chunk": 100,
    },
    "locate_index": {
        "enabled": True,
        "max_snippet_chars": 200,
        "keyword_top_n": 30,
        "include_keywords": True,
        "include_entities": True,
    },
    "storage": {
        "overwrite": True,
        "write_chunks": True,
        "max_chunk_files": 500,
    },
}

SECRET_KEYS = ("api_key", "apikey", "token", "secret", "password")


class Config:
    def __init__(self, data: Dict[str, Any]):
        self.data = data

    def section(self, name: str) -> Dict[str, Any]:
        return self.data.get(name, {}) or {}

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.section(section).get(key, default)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并；override 中的 dict 与 base 深合并，其余类型直接替换。"""
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read_yaml(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件 {path} 顶层必须是映射（键值对）")
    return data


def load_config(
    user_config_path: Optional[str] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> Config:
    """加载并合并配置，解析 API Key。"""
    data = copy.deepcopy(DEFAULTS)

    # 仓库根目录的 default_config.yaml 作为第二优先级
    default_yaml = Path(__file__).resolve().parent.parent / "default_config.yaml"
    if default_yaml.exists():
        data = deep_merge(data, _read_yaml(default_yaml))

    # 用户配置文件
    if user_config_path:
        user_path = Path(user_config_path)
        if not user_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {user_path}")
        data = deep_merge(data, _read_yaml(user_path))

    # CLI 覆盖
    if cli_overrides:
        data = deep_merge(data, cli_overrides)

    # API Key 从环境变量解析
    key_env = data.get("llm", {}).get("api_key_env") or "LLM_API_KEY"
    data["llm"]["api_key"] = os.environ.get(key_env, "") or ""

    cfg = Config(data)
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    provider = cfg.get("llm", "provider", "")
    if provider not in ("openai_compatible", "ollama", "anthropic", "none", "local"):
        raise ValueError(f"未知的 llm.provider: {provider!r}（可选: openai_compatible | ollama | anthropic | none）")
    for key in ("max_chunk_chars", "overlap_chars", "max_file_size_mb", "concurrency", "retries", "max_tokens"):
        v = cfg.get("chunking", key) if key in ("max_chunk_chars", "overlap_chars") else cfg.get("llm", key) if key in ("concurrency", "retries", "max_tokens", "timeout_s") else cfg.get("general", key)
        if v is not None and not isinstance(v, (int, float)):
            raise ValueError(f"配置项 {key} 应为数字，实际为 {type(v).__name__}")
    if cfg.get("llm", "max_tokens", 0) <= 0:
        raise ValueError("llm.max_tokens 必须为正数")


def fingerprint(cfg: Config) -> str:
    """配置指纹：去除敏感字段后对规范化 JSON 取哈希。"""
    data = copy.deepcopy(cfg.data)

    def _scrub(d: Any) -> Any:
        if isinstance(d, dict):
            return {k: _scrub(v) for k, v in d.items() if not any(s in k.lower() for s in SECRET_KEYS)}
        if isinstance(d, list):
            return [_scrub(x) for x in d]
        return d

    canonical = json.dumps(_scrub(data), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def masked_summary(cfg: Config) -> str:
    """用于 --show-config 的脱敏展示。"""
    data = copy.deepcopy(cfg.data)
    for sec in data.values():
        if isinstance(sec, dict):
            for k in list(sec.keys()):
                if any(s in k.lower() for s in SECRET_KEYS):
                    sec[k] = "***"
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)

import os

import pytest

from knowledge_summary.config import Config, deep_merge, fingerprint, load_config


def test_defaults_load():
    cfg = load_config()
    assert cfg.get("general", "output_dir_name") == "knowledge"
    assert cfg.get("llm", "provider") == "openai_compatible"
    assert cfg.get("chunking", "max_chunk_chars") == 4000


def test_user_config_override(tmp_path):
    cfg_path = tmp_path / "user.yaml"
    cfg_path.write_text(
        "llm:\n  provider: ollama\n  model: qwen2.5:7b\nchunking:\n  max_chunk_chars: 2000\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_path))
    assert cfg.get("llm", "provider") == "ollama"
    assert cfg.get("llm", "model") == "qwen2.5:7b"
    assert cfg.get("chunking", "max_chunk_chars") == 2000
    # 未覆盖项保持默认
    assert cfg.get("general", "output_dir_name") == "knowledge"


def test_cli_override_wins():
    cfg = load_config(cli_overrides={"llm": {"provider": "none"}})
    assert cfg.get("llm", "provider") == "none"


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("MY_TEST_KEY", "secret-value")
    cfg = load_config(cli_overrides={"llm": {"api_key_env": "MY_TEST_KEY"}})
    assert cfg.get("llm", "api_key") == "secret-value"


def test_api_key_scrubbed_from_fingerprint():
    cfg = load_config(cli_overrides={"llm": {"api_key": "super-secret"}})
    fp1 = fingerprint(cfg)
    cfg2 = load_config(cli_overrides={"llm": {"api_key": "another-secret"}})
    fp2 = fingerprint(cfg2)
    assert fp1 == fp2  # key 变化不影响指纹
    assert "super-secret" not in fp1


def test_invalid_provider_rejected():
    with pytest.raises(ValueError):
        load_config(cli_overrides={"llm": {"provider": "nonsense"}})


def test_deep_merge_nested():
    base = {"a": {"b": 1, "c": 2}, "d": [1, 2]}
    merged = deep_merge(base, {"a": {"c": 9}, "e": 5})
    assert merged == {"a": {"b": 1, "c": 9}, "d": [1, 2], "e": 5}

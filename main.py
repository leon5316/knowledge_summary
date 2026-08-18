#!/usr/bin/env python3
"""知识总结与拓扑内核 — CLI 入口。

用法:
    python main.py <目标文件或文件夹> [选项]

示例:
    python main.py .                       # 总结当前目录
    python main.py ./report.pdf            # 总结单个 PDF
    python main.py ./src --config my.yaml  # 使用自定义配置
    python main.py ./src --provider none   # 强制离线静态模式
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from knowledge_summary import __version__
from knowledge_summary.config import load_config, masked_summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python main.py",
        description="知识总结与拓扑内核：解析多种文件格式并生成可供 LLM 阅读的知识库与定位索引。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("target", nargs="?", default=".", help="目标文件或文件夹（默认当前目录）")
    p.add_argument("--config", "-c", help="用户配置文件路径（覆盖 default_config.yaml）")
    p.add_argument("--output-dir-name", help="输出目录名（覆盖 general.output_dir_name）")
    p.add_argument("--provider", choices=["openai_compatible", "ollama", "anthropic", "none"],
                   help="LLM 提供方（覆盖 llm.provider）")
    p.add_argument("--model", help="模型名（覆盖 llm.model）")
    p.add_argument("--base-url", help="API base_url（覆盖 llm.base_url）")
    p.add_argument("--api-key-env", help="API Key 环境变量名（覆盖 llm.api_key_env）")
    p.add_argument("--show-config", action="store_true", help="显示解析后的配置（脱敏）并退出")
    p.add_argument("--quiet", "-q", action="store_true", help="关闭进度输出")
    p.add_argument("--version", action="version", version=f"knowledge-summary {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    overrides = {}
    if args.output_dir_name:
        overrides.setdefault("general", {})["output_dir_name"] = args.output_dir_name
    if args.provider:
        overrides.setdefault("llm", {})["provider"] = args.provider
    if args.model:
        overrides.setdefault("llm", {})["model"] = args.model
    if args.base_url:
        overrides.setdefault("llm", {})["base_url"] = args.base_url
    if args.api_key_env:
        overrides.setdefault("llm", {})["api_key_env"] = args.api_key_env

    if args.show_config:
        cfg = load_config(args.config, overrides)
        print(masked_summary(cfg))
        return 0

    try:
        from knowledge_summary.pipeline import run
        result = run(args.target, config_path=args.config,
                     cli_overrides=overrides, verbose=not args.quiet)
        return 0
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130
    except Exception as e:  # noqa: BLE001
        from knowledge_summary.pipeline import PipelineError
        if isinstance(e, PipelineError):
            print(f"错误: {e}", file=sys.stderr)
        else:
            print(f"错误: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

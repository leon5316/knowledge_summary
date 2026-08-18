"""解析器注册表：按扩展名分发到具体解析器。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import Extractor, ExtractorError  # noqa: F401
from . import text, python, sql, csvjson, html, ipynb, pdf, docx, doc  # noqa: F401  (注册副作用)
from ..models import Document


def get_extractor(path: Path) -> Optional[Extractor]:
    ext = path.suffix.lower().lstrip(".")
    return Extractor._registry.get(ext)


def supported_extensions() -> set:
    return set(Extractor._registry.keys())


def extract_file(path: Path, rel_path: str, cfg) -> Document:
    """按扩展名解析单个文件；无解析器时按配置决定是否当纯文本处理。"""
    ext = path.suffix.lower().lstrip(".")
    extractor = get_extractor(path)
    if extractor is None:
        if cfg.get("general", "treat_unknown_as_text", False):
            from .text import TextExtractor
            return TextExtractor().extract(path, rel_path, cfg)
        raise ExtractorError(f"不支持的文件类型 .{ext}（可在 general.treat_unknown_as_text 开启按纯文本处理）")
    return extractor.extract(path, rel_path, cfg)

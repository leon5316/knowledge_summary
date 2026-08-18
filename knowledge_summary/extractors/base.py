"""解析器基类与公共工具。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..models import Document


class ExtractorError(Exception):
    """解析失败（缺依赖、格式损坏、工具缺失等）。"""


class Extractor:
    """文件解析器基类。子类通过 __init_subclass__ 自动注册。"""

    extensions: set = set()
    display_name: str = "base"

    # 全局注册表: 扩展名 -> Extractor 实例
    _registry: dict = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for ext in getattr(cls, "extensions", set()):
            Extractor._registry[ext] = cls()

    def extract(self, path: Path, rel_path: str, cfg) -> Document:
        """解析文件，返回 Document。"""
        raise NotImplementedError

    # ---- 便捷工具 ----

    @staticmethod
    def read_text(path: Path) -> str:
        """宽容地读取文本文件（多种编码尝试）。"""
        data = path.read_bytes()
        for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def make_doc(path: Path, rel_path: str, fmt: str, text: str,
                 sections=None, meta=None) -> Document:
        return Document(
            path=str(path),
            rel_path=rel_path,
            format=fmt,
            text=text,
            sections=sections or [],
            meta=meta or {},
        )

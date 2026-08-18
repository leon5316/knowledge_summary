"""纯文本类解析器：txt / md / markdown / rst / log。"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Extractor
from ..models import Document, Section, Span


class TextExtractor(Extractor):
    extensions = {"txt", "md", "markdown", "rst", "log"}
    display_name = "text"

    def extract(self, path: Path, rel_path: str, cfg) -> Document:
        text = self.read_text(path)
        sections = self._detect_headings(text, path, rel_path)
        return self.make_doc(path, rel_path, path.suffix.lower().lstrip("."), text,
                             sections=sections, meta={"lines": text.count("\n") + 1})

    @staticmethod
    def _detect_headings(text: str, path: Path, rel_path: str):
        sections = []
        lines = text.split("\n")
        n = len(lines)
        prev_underline = False  # rst 下划线标题处理
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):  # md 标题
                m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
                if m:
                    sections.append(Section(
                        title=m.group(2).strip(),
                        kind="heading",
                        span=Span(str(path), rel_path, i, i),
                        meta={"level": len(m.group(1))},
                    ))
            elif re.match(r"^=+\s*$", stripped) and i > 1 and lines[i - 2].strip():
                sections.append(Section(
                    title=lines[i - 2].strip(), kind="heading",
                    span=Span(str(path), rel_path, i - 1, i),
                    meta={"level": 1, "style": "rst"},
                ))
            elif re.match(r"^-+\s*$", stripped) and i > 1 and lines[i - 2].strip():
                sections.append(Section(
                    title=lines[i - 2].strip(), kind="heading",
                    span=Span(str(path), rel_path, i - 1, i),
                    meta={"level": 2, "style": "rst"},
                ))
        return sections[:1000]

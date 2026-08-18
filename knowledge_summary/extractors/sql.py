"""SQL 源码解析器：全文 + 语句级结构切分。"""
from __future__ import annotations

from pathlib import Path

import sqlparse

from .base import Extractor
from ..models import Document, Section, Span


class SqlExtractor(Extractor):
    extensions = {"sql"}
    display_name = "sql"

    def extract(self, path: Path, rel_path: str, cfg) -> Document:
        text = self.read_text(path)
        keep_comments = cfg.get("extractors", "sql", {}).get("keep_comments", True)
        sections = []
        try:
            statements = sqlparse.split(text)
            search_from = 0
            for stmt in statements:
                stmt = (stmt or "").strip()
                if not stmt:
                    continue
                if not keep_comments and stmt.lstrip().startswith("--"):
                    continue
                start = text.find(stmt, search_from)
                if start == -1:
                    start = search_from
                else:
                    search_from = start + len(stmt)
                line_start = text.count("\n", 0, start) + 1
                line_end = text.count("\n", 0, start + len(stmt)) + 1
                first = " ".join(stmt.split())[:120]
                sections.append(Section(
                    title=first, kind="statement",
                    span=Span(str(path), rel_path, line_start, line_end),
                    meta={"length": len(stmt)},
                ))
        except Exception:
            pass
        return self.make_doc(path, rel_path, "sql", text,
                             sections=sections[:2000],
                             meta={"lines": text.count("\n") + 1, "statements": len(sections)})

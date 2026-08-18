"""Jupyter Notebook (.ipynb) 解析器。"""
from __future__ import annotations

import json
from pathlib import Path

from .base import Extractor
from ..models import Document, Section, Span


class IpynbExtractor(Extractor):
    extensions = {"ipynb"}
    display_name = "notebook"

    def extract(self, path: Path, rel_path: str, cfg) -> Document:
        raw = self.read_text(path)
        try:
            nb = json.loads(raw)
        except Exception:
            return self.make_doc(path, rel_path, "ipynb", raw)

        parts = []
        sections = []
        for idx, cell in enumerate(nb.get("cells", []), start=1):
            ctype = cell.get("cell_type", "code")
            src = "".join(cell.get("source", []))
            if ctype == "markdown":
                parts.append(src)
                sections.append(Section(
                    title=src.strip().splitlines()[0][:80] if src.strip() else "(empty)",
                    kind="cell", span=Span(str(path), rel_path, idx, idx),
                    meta={"type": "markdown"},
                ))
            else:
                parts.append(f"```python\n{src}\n```")
                sections.append(Section(
                    title=f"Code cell {idx}", kind="cell",
                    span=Span(str(path), rel_path, idx, idx),
                    meta={"type": "code"},
                ))
        text = "\n\n".join(parts)
        return self.make_doc(path, rel_path, "ipynb", text,
                             sections=sections[:2000],
                             meta={"cells": len(nb.get("cells", [])),
                                   "note": "Line numbers correspond to cell indexes"})

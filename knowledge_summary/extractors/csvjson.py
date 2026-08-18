"""CSV / TSV / JSON / JSONL 数据文件解析器。"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from .base import Extractor
from ..models import Document, Section, Span


class CsvJsonExtractor(Extractor):
    extensions = {"csv", "tsv", "json", "jsonl"}
    display_name = "csv/json"

    def extract(self, path: Path, rel_path: str, cfg) -> Document:
        raw = path.read_bytes()
        ext = path.suffix.lower().lstrip(".")
        text = raw.decode("utf-8", errors="replace")
        sections = []
        meta = {}

        if ext in ("csv", "tsv"):
            text = self._render_csv(text, ext == "tsv")
            meta["kind"] = "tabular"
        elif ext == "jsonl":
            text = self._render_jsonl(text, rel_path, str(path))
            meta["kind"] = "jsonl"
        else:
            text = self._render_json(text, rel_path, str(path), sections)
            meta["kind"] = "json"

        return self.make_doc(path, rel_path, ext, text, sections=sections, meta=meta)

    @staticmethod
    def _render_csv(text: str, is_tsv: bool) -> str:
        delim = "\t" if is_tsv else ","
        try:
            reader = csv.reader(io.StringIO(text), delimiter=delim)
            rows = list(reader)
        except Exception:
            return text
        if not rows:
            return ""
        lines = [", ".join(rows[0])]  # 表头
        for row in rows[1:]:
            lines.append(", ".join(row))
        return "\n".join(lines)

    @staticmethod
    def _render_json(text: str, rel_path: str, abspath: str, sections) -> str:
        try:
            data = json.loads(text)
        except Exception:
            return text
        if isinstance(data, list) and data and all(isinstance(x, dict) for x in data[:10]):
            # 表格式渲染
            keys = list(data[0].keys())
            lines = [", ".join(str(k) for k in keys)]
            for row in data:
                lines.append(", ".join(str(row.get(k, "")) for k in keys))
            return "\n".join(lines)
        rendered = json.dumps(data, ensure_ascii=False, indent=2)
        return rendered

    @staticmethod
    def _render_jsonl(text: str, rel_path: str, abspath: str) -> str:
        out = []
        for i, line in enumerate(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                out.append(json.dumps(obj, ensure_ascii=False))
            except Exception:
                out.append(line)
        return "\n".join(out)

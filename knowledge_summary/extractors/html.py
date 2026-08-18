"""HTML 解析器：标题结构 + 正文/代码/表格文本。"""
from __future__ import annotations

from pathlib import Path

from ..models import Document, Section, Span
from .base import Extractor, ExtractorError


class HtmlExtractor(Extractor):
    extensions = {"html", "htm"}
    display_name = "html"

    def extract(self, path: Path, rel_path: str, cfg) -> Document:
        try:
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise ExtractorError("解析 HTML 需要 beautifulsoup4，请先 pip install beautifulsoup4") from e

        raw = self.read_text(path)
        soup = BeautifulSoup(raw, "html.parser")

        lines = []
        sections = []
        include_tables = cfg.get("extractors", "html", {}).get("include_tables", True)

        title = soup.title.get_text(strip=True) if soup.title else path.stem
        if title:
            lines.append(f"# {title}")

        def emit(text: str, kind: str, level: int = 0, span_line: int = 0):
            if not text.strip():
                return
            lines.append(text)
            if kind == "heading":
                sections.append(Section(
                    title=text.strip().lstrip("#").strip(), kind="heading",
                    span=Span(str(path), rel_path, span_line, span_line),
                    meta={"level": level},
                ))

        # 按文档顺序遍历顶层块级元素
        body = soup.body or soup
        line_no = 1
        for el in body.descendants:
            if getattr(el, "name", None) in ("h1", "h2", "h3", "h4", "h5", "h6"):
                emit(el.get_text(" ", strip=True), "heading", int(el.name[1]), line_no)
            elif getattr(el, "name", None) in ("p", "li", "blockquote", "pre", "code"):
                emit(el.get_text("\n", strip=True), "text", span_line=line_no)
            elif getattr(el, "name", None) == "table" and include_tables:
                rows = []
                for tr in el.find_all("tr"):
                    cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                    rows.append(" | ".join(cells))
                emit("\n".join(rows), "table", span_line=line_no)
            line_no += 1

        text = "\n\n".join(l for l in lines if l.strip())
        return self.make_doc(path, rel_path, "html", text,
                             sections=sections[:1000],
                             meta={"title": title, "lines": line_no})

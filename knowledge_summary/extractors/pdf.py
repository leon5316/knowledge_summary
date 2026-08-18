"""PDF 解析器：按页提取文本，页号作为定位信息。"""
from __future__ import annotations

from pathlib import Path

from ..models import Document, Section, Span
from .base import Extractor, ExtractorError


class PdfExtractor(Extractor):
    extensions = {"pdf"}
    display_name = "pdf"

    def extract(self, path: Path, rel_path: str, cfg) -> Document:
        method = cfg.get("extractors", "pdf", {}).get("method", "auto")
        text, page_spans = self._extract(path, method)
        if not text.strip():
            raise ExtractorError(f"未能从 PDF 中提取到文本（可能是扫描件/图片型 PDF）: {rel_path}")

        sections = []
        line_offset = 0
        for page_no, page_text in page_spans:
            n = page_text.count("\n")
            sections.append(Section(
                title=f"Page {page_no}", kind="page",
                span=Span(str(path), rel_path,
                          line_offset + 1, line_offset + n + 1,
                          page_start=page_no, page_end=page_no),
                meta={"chars": len(page_text)},
            ))
            line_offset += n + 1

        return self.make_doc(path, rel_path, "pdf", text,
                             sections=sections[:5000],
                             meta={"pages": len(page_spans), "method": method})

    @staticmethod
    def _extract(path: Path, method: str):
        """返回 (全文, [(页号, 页文本), ...])。"""
        errors = []

        def try_pypdf():
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            out = []
            for i, page in enumerate(reader.pages, start=1):
                t = (page.extract_text() or "").strip()
                out.append((i, t))
            return out

        def try_pdfminer():
            from pdfminer.high_level import extract_pages
            from pdfminer.layout import LTTextContainer
            out = []
            for i, page_layout in enumerate(extract_pages(str(path)), start=1):
                parts = []
                for element in page_layout:
                    if isinstance(element, LTTextContainer):
                        parts.append(element.get_text())
                out.append((i, "".join(parts).strip()))
            return out

        def attempt(fn, need, name):
            if method not in ("auto", need):
                return None
            try:
                return PdfExtractor._join(fn())
            except ImportError:
                errors.append(f"需要 {name}，请 pip install {name}")
                return None
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name} 解析失败: {e}")
                return None

        result = attempt(try_pypdf, "pypdf", "pypdf")
        if result is None:
            result = attempt(try_pdfminer, "pdfminer", "pdfminer.six")
        if result is None:
            raise ExtractorError("PDF 解析失败：" + ("；".join(errors) or "无可用解析器"))
        return result

    @staticmethod
    def _join(page_list):
        parts = []
        spans = []
        for page_no, page_text in page_list:
            parts.append(page_text)
            spans.append((page_no, page_text))
        return "\n\n".join(parts), spans

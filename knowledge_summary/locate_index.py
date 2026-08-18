"""定位索引：实体名 / 关键词 / 文件 / 块 -> 源文件中的精确位置。"""
from __future__ import annotations

from typing import Dict, List

from .config import Config
from .llm.local_fallback import extract_keywords
from .models import Chunk, Document, Entity


def _snippet(text: str, center: int, max_chars: int) -> str:
    half = max_chars // 2
    start = max(0, center - half)
    end = min(len(text), center + half)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].replace("\n", " ").strip() + suffix


def build_locate_index(docs: List[Document], chunks_by_doc: Dict[str, List[Chunk]],
                       entities: List[Entity], cfg: Config) -> Dict:
    max_snippet = int(cfg.get("locate_index", "max_snippet_chars", 200))
    keyword_top_n = int(cfg.get("locate_index", "keyword_top_n", 30))
    include_keywords = cfg.get("locate_index", "include_keywords", True)
    include_entities = cfg.get("locate_index", "include_entities", True)

    # 按文档分组的块，用于将实体 span 关联到块
    chunks_by_doc = {k: sorted(v, key=lambda c: c.span.line_start) for k, v in chunks_by_doc.items()}

    def chunk_for_span(doc_rel: str, line: int):
        for c in chunks_by_doc.get(doc_rel, []):
            if c.span.line_start <= line <= c.span.line_end:
                return c
            if c.span.line_start > line:
                break
        return None

    index: Dict = {
        "entities": {},
        "keywords": {},
        "files": {},
        "chunks": {},
        "_meta": {"counts": {}},
    }

    # 1) 实体 -> 位置
    if include_entities:
        for e in entities:
            if not e.span:
                continue
            chunk = chunk_for_span(e.span.rel_path, e.span.line_start)
            hit = {
                "file": e.span.rel_path,
                "line_start": e.span.line_start,
                "line_end": e.span.line_end,
            }
            if e.span.page_start is not None:
                hit["page_start"] = e.span.page_start
                hit["page_end"] = e.span.page_end
            if chunk:
                hit["chunk_id"] = chunk.id
                pos = chunk.text.lower().find(e.name.lower())
                if pos != -1:
                    hit["snippet"] = _snippet(chunk.text, pos, max_snippet)
            index["entities"].setdefault(e.name, []).append(hit)

    # 2) 关键词 -> 位置（按块匹配）
    if include_keywords:
        for doc in docs:
            for chunk in chunks_by_doc.get(doc.rel_path, []):
                kws = extract_keywords(chunk.text, keyword_top_n)
                for kw in kws:
                    pos = chunk.text.lower().find(kw.lower())
                    if pos == -1:
                        pos = 0
                    hit = {
                        "file": chunk.span.rel_path,
                        "line_start": chunk.span.line_start,
                        "line_end": chunk.span.line_end,
                        "chunk_id": chunk.id,
                        "snippet": _snippet(chunk.text, pos, max_snippet),
                    }
                    if chunk.span.page_start is not None:
                        hit["page_start"] = chunk.span.page_start
                        hit["page_end"] = chunk.span.page_end
                    index["keywords"].setdefault(kw, []).append(hit)

    # 3) 文件 -> 概览
    for doc in docs:
        first_line = doc.text.strip().splitlines()[0][:120] if doc.text.strip() else ""
        index["files"][doc.rel_path] = {
            "format": doc.format,
            "chars": len(doc.text),
            "chunks": len(chunks_by_doc.get(doc.rel_path, [])),
            "summary_head": doc.meta.get("summary", "").splitlines()[0] if doc.meta.get("summary") else first_line,
        }

    # 4) 块 -> 位置 + 摘要
    for doc_rel, chunks in chunks_by_doc.items():
        for c in chunks:
            entry = {
                "file": c.span.rel_path,
                "span": c.span.to_dict(),
                "summary": c.summary or "",
            }
            index["chunks"][c.id] = entry

    index["_meta"]["counts"] = {
        "entities": len(index["entities"]),
        "keywords": len(index["keywords"]),
        "files": len(index["files"]),
        "chunks": len(index["chunks"]),
    }
    return index

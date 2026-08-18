"""文本分块：按语义边界切分，并保留到源文件的精确位置映射。"""
from __future__ import annotations

from typing import List

from .config import Config
from .models import Chunk, Document


def build_line_starts(text: str) -> List[int]:
    """每个逻辑行的起始字符偏移（第 i 行从 offsets[i] 开始）。"""
    offsets = [0]
    for m in __import__("re").finditer("\n", text):
        offsets.append(m.end())
    return offsets


def char_to_line(offsets: List[int], pos: int) -> int:
    """字符偏移 -> 行号（1 起）。"""
    lo, hi = 0, len(offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if offsets[mid] <= pos:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def _segments_by_paragraphs(text: str):
    """按空行切分段落，返回 [(start, end), ...] 字符区间。"""
    segs = []
    lines = text.split("\n")
    start = 0
    for i, line in enumerate(lines):
        if line.strip() == "":
            if i > 0 and lines[i - 1].strip() != "":
                segs.append((start, _pos_of_line(text, i)))
            start = _pos_of_line(text, i + 1)
    if lines and lines[-1].strip() != "":
        segs.append((start, len(text)))
    return segs


def _pos_of_line(text: str, line_idx: int) -> int:
    """第 line_idx 行（0 起）的起始偏移。"""
    if line_idx <= 0:
        return 0
    idx = 0
    for _ in range(line_idx):
        n = text.find("\n", idx)
        if n == -1:
            return len(text)
        idx = n + 1
    return idx


def _hard_split(text: str, start: int, end: int, max_chars: int) -> List:
    """超大段落按字符硬切。"""
    out = []
    s = start
    while s < end:
        e = min(s + max_chars, end)
        out.append((s, e))
        s = e
    return out


def _derive_pages(doc: Document, line_start: int, line_end: int):
    """根据文档的页面结构单元推导块对应的页码。"""
    pages = []
    for sec in doc.sections:
        if sec.kind == "page" and sec.span.page_start is not None:
            if sec.span.line_end >= line_start and sec.span.line_start <= line_end:
                pages.append(sec.span.page_start)
    if not pages:
        return None, None
    return min(pages), max(pages)


def chunk_document(doc: Document, cfg: Config, chunk_index: int = 0) -> List[Chunk]:
    """将文档切块。chunk_index 为文档序号，用于生成全局唯一的块 ID。"""
    text = doc.text
    if not text.strip():
        return []

    max_chars = int(cfg.get("chunking", "max_chunk_chars", 4000))
    overlap = int(cfg.get("chunking", "overlap_chars", 300))
    prefer_boundary = cfg.get("chunking", "prefer_semantic_boundary", True)

    offsets = build_line_starts(text)

    raw_spans = _segments_by_paragraphs(text) if prefer_boundary else [(0, len(text))]

    pieces: List = []  # 待组块的 (start, end) 区间
    for s, e in raw_spans:
        if e - s <= max_chars:
            pieces.append((s, e))
        else:
            pieces.extend(_hard_split(text, s, e, max_chars))

    # 组装块（带重叠）
    chunk_ranges: List = []
    cur_start = None
    cur_end = 0
    for s, e in pieces:
        if cur_start is None:
            cur_start = s
            cur_end = e
            continue
        if cur_end - cur_start + (e - s) > max_chars:
            chunk_ranges.append((cur_start, cur_end))
            # 重叠：取上一块尾部 overlap 字符作为新块开头
            cut = max(cur_start, cur_end - overlap)
            cur_start = cut
            cur_end = e
        else:
            cur_end = e
    if cur_start is not None:
        chunk_ranges.append((cur_start, cur_end))

    chunks = []
    for i, (s, e) in enumerate(chunk_ranges, start=1):
        cid = f"c{chunk_index:03d}_{i:04d}"
        line_start = char_to_line(offsets, s)
        line_end = char_to_line(offsets, max(e - 1, s)) if e > s else line_start
        page_start, page_end = _derive_pages(doc, line_start, line_end)
        from .models import Span
        span = Span(doc.path, doc.rel_path, line_start, line_end,
                    page_start=page_start, page_end=page_end)
        chunks.append(Chunk(id=cid, doc_rel_path=doc.rel_path,
                            text=text[s:e].strip("\n"), span=span))
    return chunks

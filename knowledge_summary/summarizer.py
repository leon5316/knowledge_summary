"""分层摘要：块级 -> 文件级 -> 全局总览。"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple

from .config import Config
from .llm.base import BaseLLM, LLMError
from .llm.local_fallback import extractive_summary
from .models import Chunk, Document


class Summarizer:
    def __init__(self, llm: BaseLLM, cfg: Config, warnings: List[str]):
        self.llm = llm
        self.cfg = cfg
        self.warnings = warnings
        self.enabled = cfg.get("summarization", "enabled", True)
        self.concurrency = max(1, int(cfg.get("llm", "concurrency", 4)))

    def _safe_chunk_summary(self, chunk: Chunk) -> str:
        try:
            return self.llm.summarize_chunk(chunk)
        except LLMError as e:
            self.warnings.append(f"块 {chunk.id} 摘要失败，使用离线静态摘要: {e}")
            return extractive_summary(chunk.text)

    def summarize_document(self, doc: Document, chunks: List[Chunk]) -> Tuple[List[Chunk], str]:
        """为文档的所有块生成摘要，并产出文件级摘要。返回 (带摘要的块列表, 文件级摘要)。"""
        if not self.enabled or not chunks:
            return chunks, ""
        with ThreadPoolExecutor(max_workers=min(self.concurrency, max(1, len(chunks)))) as ex:
            summaries = list(ex.map(self._safe_chunk_summary, chunks))
        for chunk, s in zip(chunks, summaries):
            chunk.summary = s

        try:
            file_summary = self.llm.summarize_file(doc, [(c.id, c.summary) for c in chunks])
        except LLMError as e:
            self.warnings.append(f"文件 {doc.rel_path} 摘要失败，使用离线静态摘要: {e}")
            file_summary = extractive_summary(doc.text)
        doc.meta["summary"] = file_summary
        return chunks, file_summary

    def summarize_global(self, file_summaries: List[Tuple[str, str]]) -> str:
        if not self.enabled or not file_summaries:
            return ""
        try:
            return self.llm.summarize_global(file_summaries)
        except LLMError as e:
            self.warnings.append(f"全局摘要失败，使用离线静态摘要: {e}")
            lines = [f"- {rel}: {s.splitlines()[0] if s else ''}" for rel, s in file_summaries]
            return "[Offline static summary] Global overview (file-level points):\n" + "\n".join(lines)

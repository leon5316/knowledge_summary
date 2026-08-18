"""主流水线：collect -> extract -> chunk -> summarize -> topology -> locate_index -> write。"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .chunking import chunk_document
from .config import Config, fingerprint, load_config
from .extractors import extract_file
from .extractors.base import ExtractorError
from .extractors.project import CollectError, collect_files
from .llm import LLMError, create_llm
from .llm.local_fallback import LocalFallbackLLM
from .locate_index import build_locate_index
from .models import Chunk, Document
from .storage import now_iso, write_knowledge
from .summarizer import Summarizer
from .topology import TopologyBuilder

_VERBOSE = True


def log(msg: str = "") -> None:
    if _VERBOSE:
        print(msg, flush=True)


@dataclass
class PipelineResult:
    out_dir: Path
    stats: Dict[str, Any]
    warnings: List[str] = field(default_factory=list)
    llm_name: str = ""


class PipelineError(Exception):
    """流水线致命错误（目标不存在、无可用文件等）。"""


def run(target: str,
        config_path: Optional[str] = None,
        cli_overrides: Optional[Dict[str, Any]] = None,
        verbose: bool = True) -> PipelineResult:
    global _VERBOSE
    _VERBOSE = verbose

    warnings: List[str] = []

    # ---- 配置与 LLM ----
    log("==> 加载配置")
    cfg = load_config(config_path, cli_overrides)
    llm = None
    try:
        llm = create_llm(cfg)
    except LLMError as e:
        if cfg.get("llm", "fallback_to_local", True):
            warnings.append(f"LLM 创建失败，已降级为离线静态模式: {e}")
            log(f"  [警告] {e}")
            log("  [警告] 已降级为离线静态模式（不调用 LLM）")
            llm = LocalFallbackLLM(cfg)
        else:
            raise
    if isinstance(llm, LocalFallbackLLM):
        log(f"  LLM 提供方: {llm.name}（离线静态模式）")
    else:
        log(f"  LLM 提供方: {llm.name} | 模型: {cfg.get('llm', 'model')}")

    # ---- 收集 ----
    log("==> 收集目标文件")
    try:
        root, files = collect_files(target, cfg)
    except CollectError as e:
        raise PipelineError(str(e)) from e
    log(f"  源根目录: {root}")
    log(f"  待解析文件: {len(files)}")
    if not files:
        raise PipelineError("没有找到可解析的文件（检查扩展名支持与忽略规则）")

    # ---- 解析 ----
    log("==> 解析文件")
    docs: List[Document] = []
    failed = 0
    for i, f in enumerate(files, start=1):
        try:
            rel = f.relative_to(root).as_posix() if f.is_relative_to(root) else f.name
            doc = extract_file(f, rel, cfg)
            if doc.text.strip():
                docs.append(doc)
                log(f"  [{i}/{len(files)}] {rel} ({len(doc.text)} 字符)")
            else:
                warnings.append(f"跳过空文件: {rel}")
                log(f"  [{i}/{len(files)}] {rel} (空内容，跳过)")
        except ExtractorError as e:
            failed += 1
            warnings.append(f"{f.name}: {e}")
            log(f"  [{i}/{len(files)}] {rel} 解析失败: {e}")
    if not docs:
        raise PipelineError("没有成功解析出任何内容")

    # ---- 分块 ----
    log("==> 分块")
    chunks_by_doc: Dict[str, List[Chunk]] = {}
    all_chunks: List[Chunk] = []
    for idx, doc in enumerate(docs):
        chunks = chunk_document(doc, cfg, chunk_index=idx)
        if chunks:
            chunks_by_doc[doc.rel_path] = chunks
            all_chunks.extend(chunks)
        else:
            warnings.append(f"{doc.rel_path} 未产生分块")
    log(f"  共 {len(all_chunks)} 个块")

    # ---- 摘要 ----
    log("==> 分层摘要（块 -> 文件 -> 全局）")
    summarizer = Summarizer(llm, cfg, warnings)
    file_summaries: List[tuple] = []
    for doc in docs:
        chunks = chunks_by_doc.get(doc.rel_path, [])
        chunks, file_summary = summarizer.summarize_document(doc, chunks)
        chunks_by_doc[doc.rel_path] = chunks
        if file_summary:
            file_summaries.append((doc.rel_path, file_summary))
        log(f"  {doc.rel_path}: {len(chunks)} 块摘要完成")
    global_summary = summarizer.summarize_global(file_summaries)
    log("  全局总览完成")

    # ---- 拓扑 ----
    log("==> 构建知识拓扑")
    builder = TopologyBuilder(cfg, llm, warnings)
    entities, relations = builder.build(docs, chunks_by_doc)
    log(f"  实体: {len(entities)}，关系: {len(relations)}")

    # ---- 定位索引 ----
    log("==> 构建定位索引")
    locate_index = build_locate_index(docs, chunks_by_doc, entities, cfg)

    # ---- 组装并写入 ----
    log("==> 写入 knowledge 目录")
    out_dir = root / cfg.get("general", "output_dir_name", "knowledge")
    graph_text = _render_graph(entities, relations)
    overview = _render_overview(global_summary, docs, entities, relations, file_summaries, graph_text)
    summary_md = _render_summary_md(global_summary, file_summaries, chunks_by_doc)

    stats = {
        "files": len(docs),
        "skipped": failed,
        "chunks": len(all_chunks),
        "entities": len(entities),
        "relations": len(relations),
        "index_entities": locate_index.get("_meta", {}).get("counts", {}).get("entities", 0),
        "index_keywords": locate_index.get("_meta", {}).get("counts", {}).get("keywords", 0),
    }
    manifest = {
        "schema_version": 1,
        "tool": "knowledge-summary",
        "tool_version": __version__,
        "generated_at": now_iso(),
        "source_root": str(root),
        "sources": [d.rel_path for d in docs],
        "llm": {"provider": llm.name, "model": cfg.get("llm", "model")},
        "config_fingerprint": fingerprint(cfg),
        "stats": stats,
    }
    write_knowledge(out_dir, {
        "source_root": str(root),
        "overview": overview,
        "summary": summary_md,
        "topology": {"entities": [e.to_dict() for e in entities],
                     "relations": [r.to_dict() for r in relations]},
        "locate_index": locate_index,
        "chunks": all_chunks,
        "manifest": manifest,
    }, cfg)

    # ---- 报告 ----
    log("")
    log("========== 完成 ==========")
    log(f"知识库目录: {out_dir}")
    log(f"文件: {stats['files']}（跳过 {stats['skipped']}）| 块: {stats['chunks']} | "
        f"实体: {stats['entities']} | 关系: {stats['relations']} | "
        f"索引条目: {stats['index_entities']} 实体 / {stats['index_keywords']} 关键词")
    if warnings:
        log(f"警告 {len(warnings)} 条：")
        for w in warnings[:20]:
            log(f"  - {w}")
        if len(warnings) > 20:
            log(f"  ... 其余 {len(warnings) - 20} 条略")

    return PipelineResult(out_dir=out_dir, stats=stats, warnings=warnings, llm_name=llm.name)


# ================= 渲染 =================

def _render_graph(entities, relations) -> str:
    lines = ["# Entity / Relation graph (text version)\n"]
    lines.append("## Entities")
    for e in sorted(entities, key=lambda x: (x.kind, x.name.lower()))[:500]:
        loc = e.span.display() if e.span else "(unlocated)"
        lines.append(f"- [{e.kind}] {e.name} — {e.description or '(no description)'} @ {loc}")
    lines.append("\n## Relations")
    for r in sorted(relations, key=lambda x: (x.source.lower(), x.target.lower()))[:500]:
        loc = r.span.display() if r.span else ""
        lines.append(f"- {r.source} --[{r.kind}]--> {r.target} {loc}")
    return "\n".join(lines)


def _render_overview(global_summary, docs, entities, relations, file_summaries, graph_text) -> str:
    lines = ["# Global Overview", ""]
    lines.append(global_summary or "(global summary not generated)")
    lines.append("")
    lines.append("## File list")
    for rel, s in file_summaries:
        head = s.splitlines()[0] if s else ""
        lines.append(f"- `{rel}`: {head}")
    lines.append("")
    lines.append("## Statistics")
    lines.append(f"- Files: {len(docs)}")
    lines.append(f"- Entities: {len(entities)} (functions/classes/tables/views/concepts, etc.)")
    lines.append(f"- Relations: {len(relations)}")
    lines.append("")
    lines.append("## Detailed graph")
    lines.append("> Structured version in `03_topology.json`; locate index in `04_locate_index.json`.")
    lines.append("")
    lines.append(graph_text)
    return "\n".join(lines)


def _render_summary_md(global_summary, file_summaries, chunks_by_doc) -> str:
    lines = ["# Hierarchical Summary", "", "## Global Overview", "",
             global_summary or "(not generated)", ""]
    for rel, s in file_summaries:
        lines.append(f"## File: {rel}")
        lines.append("")
        lines.append(s)
        lines.append("")
        chunks = chunks_by_doc.get(rel, [])
        if chunks:
            lines.append(f"### Chunk-level summaries ({len(chunks)} chunks)")
            for c in chunks:
                if c.summary:
                    lines.append(f"**{c.id}** ({c.span.display()}): {c.summary.splitlines()[0]}")
                    for extra in c.summary.splitlines()[1:]:
                        lines.append(f"  {extra}")
            lines.append("")
    return "\n".join(lines)

"""离线静态降级 LLM：不调用任何网络服务，输出提取式摘要。"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .base import BaseLLM

_STOPWORDS = set("""a an and are as at be by for from has have in is it its of on or that the
this to was were will with about above after again against all am any our out over own
can could did do does doing down each few further had he her here hers herself him
himself his how i if into me more most my myself no nor not off once only other ought
same say says she should so some such than theirs them themselves then there these they
theyre this those through under until up very was we what when where which while who
whom why would you your yours yourself""".split())

_CJK_STOP = set("的一个是了我在有和就不人都这中大为上个也时以到说要看会没他对出小得么那你下着过起见很把好还那可这那啥咱们呢吧吗啊哦嗯呀".strip())


def extract_keywords(text: str, top_n: int = 30) -> List[str]:
    """提取关键词：英文词 + 中文连续片段（2-4 字）与二元组。"""
    from collections import Counter

    counter: Counter = Counter()

    for w in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", text):
        low = w.lower()
        if low not in _STOPWORDS and not low.isdigit():
            counter[low] += 1

    for seq in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(seq) <= 4:
            if seq not in _CJK_STOP:
                counter[seq] += 1
        for i in range(len(seq) - 1):
            bg = seq[i:i + 2]
            if bg not in _CJK_STOP:
                counter[bg] += 1

    return [w for w, _ in counter.most_common(top_n)]


def extractive_summary(text: str, max_chars: int = 500) -> str:
    """Extractive summary: opening paragraph + keywords."""
    text = text.strip()
    if not text:
        return "(empty content)"
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    body = ""
    for p in paras:
        body = p
        if len(body) >= 120:
            break
    if len(body) > max_chars:
        body = body[:max_chars] + "…"
    kws = extract_keywords(text, 12)
    kw_line = ", ".join(kws) if kws else ""
    return f"Key points: {body}\nKeywords: {kw_line}"


class LocalFallbackLLM(BaseLLM):
    name = "local"
    json_capable = False

    def chat(self, messages, temperature=None, max_tokens=None) -> str:
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return extractive_summary(user)

    def chat_json(self, system: str, user: str) -> Dict[str, Any]:
        return {}

    def summarize_chunk(self, chunk) -> str:
        return f"[Offline static summary] Source: {chunk.span.display()}\n" + extractive_summary(chunk.text)

    def summarize_file(self, doc, chunk_summaries) -> str:
        body = "\n".join(f"- [{cid}] {s.splitlines()[0] if s else ''}" for cid, s in chunk_summaries)
        kws = extract_keywords(doc.text, 20)
        n = len(chunk_summaries)
        frag = f"{n} fragment" + ("s" if n != 1 else "")
        return (f"[Offline static summary] File: {doc.rel_path} ({frag})\n"
                f"Keywords: {', '.join(kws)}\nFragment points:\n{body}")

    def summarize_global(self, file_summaries) -> str:
        lines = []
        for rel, s in file_summaries:
            first = s.splitlines()[0] if s else ""
            lines.append(f"- {rel}: {first}")
        return "[Offline static summary] Global overview (file-level points):\n" + "\n".join(lines)

    def extract_topology_llm(self, text) -> Dict[str, Any]:
        return {"entities": [], "relations": []}

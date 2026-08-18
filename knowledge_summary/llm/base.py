"""LLM 抽象基类与提示词模板（默认生成英文总结）。"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from ..config import Config
from ..models import Chunk, Document


class LLMError(Exception):
    pass


def extract_json(text: str) -> Dict[str, Any]:
    """Robustly extract the first JSON object from LLM output."""
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:
                        return {}
    return {}


class BaseLLM:
    name = "base"
    json_capable = True

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.max_tokens = int(cfg.get("llm", "max_tokens", 4096))
        self.temperature = float(cfg.get("llm", "temperature", 0.2))
        self.timeout = int(cfg.get("llm", "timeout_s", 120))
        self.retries = int(cfg.get("llm", "retries", 3))
        self.system_extra = cfg.get("llm", "system_prompt_extra", "") or ""

    # ---------- low-level interface ----------

    def chat(self, messages: List[Dict[str, str]],
             temperature: float | None = None,
             max_tokens: int | None = None) -> str:
        """messages: [{"role": "system"|"user"|"assistant", "content": str}]"""
        raise NotImplementedError

    def chat_json(self, system: str, user: str) -> Dict[str, Any]:
        try:
            text = self.chat([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
        except LLMError:
            raise
        return extract_json(text)

    # ---------- prompts ----------

    def _lang_phrase(self) -> str:
        langs = self.cfg.get("summarization", "languages", ["en"])
        zh = "zh" in langs
        en = "en" in langs
        if zh and en:
            return "Respond in Simplified Chinese, keeping technical terms and code identifiers in English."
        if zh:
            return "Respond in Simplified Chinese."
        return "Respond in English."

    def _system_base(self, role_desc: str) -> str:
        extra = f"\nAdditional requirements: {self.system_extra}" if self.system_extra else ""
        return (
            f"You are a senior technical document and code analyst. {role_desc}\n"
            f"{self._lang_phrase()}{extra}"
        )

    # ---------- summarization ----------

    def summarize_chunk(self, chunk: Chunk) -> str:
        system = self._system_base(
            "Your task is to produce a concise and accurate summary of the given content fragment. "
            "The summary should: 1) capture the core topic and purpose; 2) list key technical points / "
            "business logic / data structures; 3) keep proper nouns and identifiers (function names, "
            "table names, APIs, etc.). Do not invent content that is not present in the source text."
        )
        user = (
            f"Source file: {chunk.doc_rel_path}\n"
            f"Location: {chunk.span.display()}\n"
            f"Here is the fragment:\n---BEGIN---\n{chunk.text}\n---END---\n\n"
            f"Generate a summary of this fragment (150-300 words)."
        )
        return self.chat([{"role": "system", "content": system},
                          {"role": "user", "content": user}])

    def summarize_file(self, doc: Document, chunk_summaries: List) -> str:
        system = self._system_base(
            "Your task is to produce an overall summary of a file based on the summaries of all its "
            "fragments. Cover: the file's purpose, its core structure, its external interfaces or "
            "key conclusions."
        )
        lines = [f"Source file: {doc.rel_path}"]
        if doc.meta.get("note"):
            lines.append(f"Note: {doc.meta['note']}")
        lines.append(f"The file is split into {len(chunk_summaries)} fragments. Their summaries:")
        for cid, summary in chunk_summaries:
            lines.append(f"\n[{cid}]: {summary}")
        lines.append("\nProduce the overall file summary (300-500 words). Do not simply repeat each "
                     "fragment summary verbatim.")
        return self.chat([{"role": "system", "content": system},
                          {"role": "user", "content": "\n".join(lines)}])

    def summarize_global(self, file_summaries: List) -> str:
        system = self._system_base(
            "Your task is to produce a global overview of a content repository based on the summaries "
            "of its files. Cover: 1) the overall topic and goal of the repository; 2) the main "
            "files/modules and their responsibilities; 3) possible dependencies or relations between "
            "files; 4) the most important points to keep in mind when reading this content."
        )
        lines = ["Below are the summaries of the files in the repository:"]
        for rel_path, summary in file_summaries:
            lines.append(f"\n### {rel_path}\n{summary}")
        lines.append("\nProduce the global overview (500-800 words).")
        return self.chat([{"role": "system", "content": system},
                          {"role": "user", "content": "\n".join(lines)}])

    # ---------- topology ----------

    def extract_topology_llm(self, text: str) -> Dict[str, Any]:
        """Return {"entities": [...], "relations": [...]}; empty structure on failure."""
        system = (
            "You extract 'entities' and 'relations' from the given content fragment to build a "
            "knowledge graph.\n"
            "Entity kinds: concept | module | function | class | table | column | view | api | "
            "data_field | business_object\n"
            "Relation kinds: related | depends_on | calls | inherits | implements | uses | part_of | "
            "references | contains | triggers\n"
            "Output strict JSON only, with no other text, in this format: "
            '{"entities":[{"name":"...","kind":"...","description":"..."}],'
            '"relations":[{"source":"...","target":"...","kind":"...","description":"..."}]}\n'
            "Entity names must match the identifiers/nouns in the source text; do not invent "
            "entities that are not present."
            f"\n{self._lang_phrase()}"
        )
        return self.chat_json(system, f"Here is the content fragment:\n---BEGIN---\n{text}\n---END---")

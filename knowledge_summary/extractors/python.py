"""Python 源码解析器：全文 + AST 结构（函数/类/模块 docstring）。"""
from __future__ import annotations

import ast
from pathlib import Path

from .base import Extractor
from ..models import Document, Section, Span


class PythonExtractor(Extractor):
    extensions = {"py", "pyw"}
    display_name = "python"

    def extract(self, path: Path, rel_path: str, cfg) -> Document:
        text = self.read_text(path)
        sections = []
        try:
            tree = ast.parse(text)
            mod_doc = ast.get_docstring(tree)
            if mod_doc:
                sections.append(Section(
                    title="Module docstring", kind="docstring",
                    span=Span(str(path), rel_path, 1, min(3, text.count("\n") + 1)),
                    meta={"text": mod_doc.splitlines()[0] if mod_doc else ""},
                ))
            # 收集任意深度的函数/类（含类内方法），按行号排序
            collected = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    title = node.name
                    kind = "function" if not isinstance(node, ast.ClassDef) else "class"
                    doc = ast.get_docstring(node)
                    meta = {"docstring_first": (doc or "").splitlines()[0] if doc else ""}
                    if isinstance(node, ast.ClassDef):
                        meta["bases"] = [self._base_name(b) for b in node.bases]
                    collected.append(Section(
                        title=title, kind=kind,
                        span=Span(str(path), rel_path, node.lineno, node.end_lineno or node.lineno),
                        meta=meta,
                    ))
            collected.sort(key=lambda s: s.span.line_start)
            sections.extend(collected)
        except SyntaxError:
            pass  # 语法不完整时仍保留全文
        return self.make_doc(path, rel_path, "py", text,
                             sections=sections[:2000],
                             meta={"lines": text.count("\n") + 1, "ast_ok": True})

    @staticmethod
    def _base_name(node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return PythonExtractor._base_name(node.value) + "." + node.attr
        return ""

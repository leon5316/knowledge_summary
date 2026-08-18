"""知识拓扑构建：静态分析（Python AST / SQL 语句解析）+ LLM 语义抽取双通道。"""
from __future__ import annotations

import ast
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

from .config import Config
from .llm.base import BaseLLM, LLMError
from .llm.local_fallback import extract_keywords
from .models import Chunk, Document, Entity, Relation, Span


class TopologyBuilder:
    def __init__(self, cfg: Config, llm: BaseLLM, warnings: List[str]):
        self.cfg = cfg
        self.llm = llm
        self.warnings = warnings
        self.enabled = cfg.get("topology", "enabled", True)
        self.static_enabled = cfg.get("topology", "enable_static_analysis", True)
        self.llm_enabled = cfg.get("topology", "enable_llm_relations", True)
        self.keywords_as_concepts = cfg.get("topology", "include_keywords_as_concepts", True)
        self.max_relations_per_chunk = int(cfg.get("topology", "max_relations_per_chunk", 100))
        self.concurrency = max(1, int(cfg.get("llm", "concurrency", 4)))

    # ================= 对外入口 =================

    def build(self, docs: List[Document], chunks_by_doc: Dict[str, List[Chunk]]) -> Tuple[List[Entity], List[Relation]]:
        if not self.enabled:
            return [], []

        entities: Dict[str, Entity] = {}
        relations: Dict[Tuple[str, str, str], Relation] = {}

        for doc in docs:
            if self.static_enabled:
                self._add(doc, *self._static_analysis(doc), entities, relations)

        # LLM 通道：按块抽取
        if self.llm_enabled and self.llm.json_capable:
            tasks = [(doc, chunk) for doc in docs for chunk in chunks_by_doc.get(doc.rel_path, [])]
            if tasks:
                with ThreadPoolExecutor(max_workers=min(self.concurrency, max(1, len(tasks)))) as ex:
                    results = list(ex.map(self._safe_llm_chunk, tasks))
                for (doc, chunk), (es, rs) in zip(tasks, results):
                    for e in es:
                        e.span = chunk.span
                        e.source = "llm"
                        self._add_entity(entities, e)
                    for r in rs:
                        r.span = chunk.span
                        r.source_flag = "llm"
                        self._add_relation(relations, r)

        # 关键词 -> concept 实体
        if self.keywords_as_concepts:
            for doc in docs:
                kws = extract_keywords(doc.text, int(self.cfg.get("locate_index", "keyword_top_n", 30)))
                for kw in kws:
                    key = kw.lower()
                    if key not in entities:
                        entities[key] = Entity(name=kw, kind="concept",
                                               description=f"High-frequency keyword (from {doc.rel_path})",
                                               source="keyword")

        return list(entities.values()), list(relations.values())

    def _add(self, doc, es, rs, entities, relations):
        for e in es:
            self._add_entity(entities, e)
        for r in rs:
            self._add_relation(relations, r)

    def _add_entity(self, entities: Dict[str, Entity], e: Entity):
        key = e.name.lower()
        if key not in entities:
            entities[key] = e
        elif entities[key].span is None and e.span is not None:
            entities[key].span = e.span
            entities[key].source = e.source

    def _add_relation(self, relations, r: Relation):
        key = (r.source.lower(), r.target.lower(), r.kind)
        if key not in relations:
            relations[key] = r

    def _safe_llm_chunk(self, task):
        doc, chunk = task
        try:
            data = self.llm.extract_topology_llm(chunk.text) or {}
        except LLMError as e:
            self.warnings.append(f"块 {chunk.id} 拓扑抽取失败: {e}")
            return [], []
        es = []
        for item in data.get("entities", [])[:200]:
            if isinstance(item, dict) and item.get("name"):
                es.append(Entity(name=str(item["name"])[:200], kind=str(item.get("kind", "concept")),
                                 description=str(item.get("description", ""))[:500]))
        rs = []
        for item in data.get("relations", [])[: self.max_relations_per_chunk]:
            if isinstance(item, dict) and item.get("source") and item.get("target"):
                rs.append(Relation(source=str(item["source"])[:200], target=str(item["target"])[:200],
                                   kind=str(item.get("kind", "related")),
                                   description=str(item.get("description", ""))[:500]))
        return es, rs

    # ================= 静态分析 =================

    def _static_analysis(self, doc: Document) -> Tuple[List[Entity], List[Relation]]:
        fmt = doc.format
        try:
            if fmt in ("py", "pyw"):
                return self._analyze_python(doc)
            if fmt == "sql":
                return self._analyze_sql(doc)
        except Exception as e:  # noqa: BLE001
            self.warnings.append(f"{doc.rel_path} 静态分析失败: {e}")
        return [], []

    # ----- Python AST -----

    def _analyze_python(self, doc: Document) -> Tuple[List[Entity], List[Relation]]:
        try:
            tree = ast.parse(doc.text)
        except SyntaxError:
            return [], []

        entities: List[Entity] = []
        relations: List[Relation] = []
        known: Dict[str, str] = {}  # 名称 -> kind
        node_spans: Dict[str, Tuple[int, int]] = {}

        mod_doc = ast.get_docstring(tree)
        if mod_doc:
            entities.append(Entity(name=doc.rel_path, kind="module",
                                   description=mod_doc.splitlines()[0] if mod_doc else "",
                                   span=Span(doc.path, doc.rel_path, 1, min(3, doc.text.count("\n") + 1)),
                                   source="static"))

        def mk_span(node) -> Span:
            return Span(doc.path, doc.rel_path, node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "function"
                d = ast.get_docstring(node) or ""
                known[node.name] = kind
                node_spans[node.name] = (node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno)
                entities.append(Entity(name=node.name, kind=kind,
                                       description=d.splitlines()[0] if d else "",
                                       span=mk_span(node), source="static",
                                       meta={"params": [a.arg for a in node.args.args]}))
            elif isinstance(node, ast.ClassDef):
                d = ast.get_docstring(node) or ""
                known[node.name] = "class"
                node_spans[node.name] = (node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno)
                entities.append(Entity(name=node.name, kind="class",
                                       description=d.splitlines()[0] if d else "",
                                       span=mk_span(node), source="static",
                                       meta={"bases": [self._base_name(b) for b in node.bases]}))

        # imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = (alias.asname or alias.name).split(".")[0]
                    relations.append(Relation(doc.rel_path, name, "imports",
                                              description=f"import {alias.name}", span=mk_span(node)))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    name = alias.asname or alias.name
                    target = f"{mod}.{alias.name}" if mod else alias.name
                    relations.append(Relation(doc.rel_path, target, "imports",
                                              description=f"from {mod} import {alias.name}", span=mk_span(node)))

        # 继承
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for b in node.bases:
                    bname = self._base_name(b)
                    if bname and bname in known:
                        relations.append(Relation(node.name, bname, "inherits", span=mk_span(node)))

        # 调用 + 引用（仅同文档内已定义实体）
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                src = node.name
                called = set()
                refs = set()
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        f = sub.func
                        if isinstance(f, ast.Name):
                            called.add(f.id)
                        elif isinstance(f, ast.Attribute):
                            called.add(f.attr)
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                        refs.add(sub.id)
                    if isinstance(sub, ast.Attribute):
                        refs.add(sub.attr)
                for c in called:
                    if c in known and c != src:
                        relations.append(Relation(src, c, "calls", span=mk_span(node)))
                for r in refs:
                    if r in known and r != src and r not in called:
                        relations.append(Relation(src, r, "references", span=mk_span(node)))

        # 去重
        seen = set()
        dedup_rel = []
        for r in relations:
            key = (r.source, r.target, r.kind)
            if key not in seen:
                seen.add(key)
                dedup_rel.append(r)
        return entities, dedup_rel[:2000]

    @staticmethod
    def _base_name(node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = TopologyBuilder._base_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return ""

    # ----- SQL -----

    def _analyze_sql(self, doc: Document) -> Tuple[List[Entity], List[Relation]]:
        try:
            import sqlparse
        except ImportError:
            return [], []

        text = doc.text
        entities: List[Entity] = []
        relations: List[Relation] = []
        tables: Dict[str, str] = {}  # 表名(小写) -> 原始名
        table_lines: Dict[str, int] = {}
        views: Dict[str, str] = {}  # 视图名(小写) -> 原始名
        view_lines: Dict[str, int] = {}
        known_names = set()

        def span_for(line_start: int, line_end: int) -> Span:
            return Span(doc.path, doc.rel_path, max(1, line_start), max(line_start, line_end))

        def line_of(offset: int) -> int:
            return text.count("\n", 0, offset) + 1

        def grab(stmt: str, m, group: int = 1) -> str:
            """从原始语句中按正则匹配位置取值，保留原始大小写。"""
            return stmt[m.start(group):m.end(group)].strip("`\"[]").split(".")[-1]

        statements = sqlparse.split(text)
        search_from = 0
        for stmt in statements:
            stmt = (stmt or "").strip()
            if not stmt:
                continue
            start = text.find(stmt, search_from)
            if start == -1:
                start = search_from
            else:
                search_from = start + len(stmt)
            s_line = line_of(start)
            e_line = line_of(start + len(stmt))
            span = span_for(s_line, e_line)
            upper = stmt.upper()

            m = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"\[]?[\w.]+[`\"\]]?)", upper)
            if m:
                tname = grab(stmt, m)
                tables[tname.lower()] = tname
                table_lines[tname.lower()] = s_line
                known_names.add(tname.lower())
                for col_name, col_type in self._extract_columns(stmt):
                    entities.append(Entity(name=col_name, kind="column",
                                           description=f"{tname}.{col_name} ({col_type})",
                                           span=span, source="static",
                                           meta={"parent_table": tname, "type": col_type}))
                # 外键
                for fk_col, ref_table, ref_col in self._extract_fks(stmt):
                    relations.append(Relation(f"{tname}.{fk_col}", f"{ref_table}.{ref_col}",
                                              "foreign_key", description=f"FOREIGN KEY ({fk_col}) REFERENCES {ref_table}({ref_col})",
                                              span=span))
                continue

            m = re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([`\"\[]?[\w.]+[`\"\]]?)", upper)
            if m:
                vname = grab(stmt, m)
                views[vname.lower()] = vname
                view_lines[vname.lower()] = s_line
                known_names.add(vname.lower())
                continue

            m = re.search(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"\[]?[\w.]+[`\"\]]?)", upper)
            if m:
                iname = grab(stmt, m)
                entities.append(Entity(name=iname, kind="index", span=span, source="static"))
                continue

        for tname_low, tname in tables.items():
            entities.append(Entity(name=tname, kind="table",
                                   span=span_for(table_lines[tname_low], table_lines[tname_low]),
                                   source="static"))
        for vname_low, vname in views.items():
            entities.append(Entity(name=vname, kind="view",
                                   span=span_for(view_lines[vname_low], view_lines[vname_low]),
                                   source="static"))

        # 仅对真正的 SELECT（含 CREATE VIEW ... AS SELECT）建立"读取"关系
        for stmt in statements:
            stmt = (stmt or "").strip()
            if not stmt:
                continue
            upper = stmt.upper()
            if "SELECT" not in upper:
                continue
            m = re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([`\"\[]?[\w.]+[`\"\]]?)\s+AS", upper)
            reader = grab(stmt, m) if m else "(select)"
            reader_low = reader.lower()
            for tname_low in known_names:
                if tname_low == reader_low:
                    continue
                if re.search(rf"\b{re.escape(tname_low)}\b", stmt, re.IGNORECASE):
                    relations.append(Relation(reader, tables.get(tname_low, tname_low), "reads",
                                              description=f"SELECT references table {tname_low}"))

        # 去重
        seen = set()
        dedup_rel = []
        for r in relations:
            key = (r.source.lower(), r.target.lower(), r.kind)
            if key not in seen:
                seen.add(key)
                dedup_rel.append(r)
        return entities, dedup_rel[:2000]

    @staticmethod
    def _extract_columns(stmt: str) -> List[Tuple[str, str]]:
        """从 CREATE TABLE 语句中提取 (列名, 类型)。"""
        open_paren = stmt.find("(")
        if open_paren == -1:
            return []
        depth = 0
        close_paren = -1
        for i in range(open_paren, len(stmt)):
            if stmt[i] == "(":
                depth += 1
            elif stmt[i] == ")":
                depth -= 1
                if depth == 0:
                    close_paren = i
                    break
        if close_paren == -1:
            return []
        body = stmt[open_paren + 1:close_paren]
        cols = []
        for chunk in body.split(","):
            chunk = chunk.strip()
            if not chunk or chunk.upper().split()[0] in (
                    "PRIMARY", "KEY", "CONSTRAINT", "FOREIGN", "UNIQUE", "CHECK", "INDEX", "REFERENCES"):
                continue
            m = re.match(r"^([`\"\[]?[\w]+[`\"\]]?)\s+([\w().\[\]]+)", chunk)
            if m:
                cols.append((m.group(1).strip("`\"[]"), m.group(2)))
        return cols

    @staticmethod
    def _extract_fks(stmt: str) -> List[Tuple[str, str, str]]:
        out = []
        for m in re.finditer(
                r"FOREIGN\s+KEY\s*\(([^)]+)\)\s*REFERENCES\s+([`\"\[]?[\w.]+[`\"\]]?)\s*\(([^)]+)\)",
                stmt, re.IGNORECASE):
            col = m.group(1).strip().strip("`\"[]")
            ref_table = m.group(2).strip("`\"[]").split(".")[-1]
            ref_col = m.group(3).strip().strip("`\"[]")
            out.append((col, ref_table, ref_col))
        return out

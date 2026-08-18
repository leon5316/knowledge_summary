"""数据模型：解析结果、来源指针、分块、实体、关系。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Span:
    """来源指针：精确定位到源文件中的位置（行号区间或页码）。"""

    source_path: str
    rel_path: str
    line_start: int = 1
    line_end: int = 1
    page_start: Optional[int] = None
    page_end: Optional[int] = None

    def display(self) -> str:
        if self.page_start is not None:
            if self.page_end and self.page_end != self.page_start:
                return f"{self.rel_path} pages {self.page_start}-{self.page_end}"
            return f"{self.rel_path} page {self.page_start}"
        if self.line_start == self.line_end:
            return f"{self.rel_path} line {self.line_start}"
        return f"{self.rel_path} lines {self.line_start}-{self.line_end}"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "file": self.rel_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
        }
        if self.page_start is not None:
            d["page_start"] = self.page_start
            d["page_end"] = self.page_end or self.page_start
        return d


@dataclass
class Section:
    """文档内部结构单元（标题 / 函数 / 类 / SQL 语句 / 页面 / 单元格等）。"""

    title: str
    kind: str  # heading | function | class | statement | page | cell | paragraph | table
    span: Span
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Document:
    """一个源文件解析后的完整内容。"""

    path: str  # 绝对路径
    rel_path: str  # 相对源根目录
    format: str  # 扩展名，如 py / pdf / sql
    text: str
    sections: List[Section] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """带来源指针的文本块。"""

    id: str
    doc_rel_path: str
    text: str
    span: Span
    summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "file": self.doc_rel_path,
            "span": self.span.to_dict(),
            "summary": self.summary,
        }


@dataclass
class Entity:
    """知识拓扑中的实体。"""

    name: str
    kind: str  # function | class | table | column | view | concept | module | index | api ...
    description: str = ""
    span: Optional[Span] = None
    source: str = "static"  # static | llm | keyword
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "span": self.span.to_dict() if self.span else None,
            "extracted_by": self.source,
            "meta": self.meta,
        }


@dataclass
class Relation:
    """知识拓扑中的关系。"""

    source: str
    target: str
    kind: str  # calls | inherits | imports | references | foreign_key | reads | related | depends_on ...
    description: str = ""
    span: Optional[Span] = None
    source_flag: str = "static"  # static | llm

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "description": self.description,
            "span": self.span.to_dict() if self.span else None,
            "extracted_by": self.source_flag,
        }

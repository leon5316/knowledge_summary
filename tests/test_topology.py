from knowledge_summary.config import load_config
from knowledge_summary.models import Document
from knowledge_summary.topology import TopologyBuilder

CFG = load_config()


def _builder():
    return TopologyBuilder(CFG, None, [])


def _py_doc():
    src = '''"""Module docstring"""
import json
from decimal import Decimal


class Base:
    pass


class Order(Base):
    def confirm(self):
        pass


def create_order():
    order = Order()
    order.confirm()
    return order
'''
    return Document(path="C:/x/m.py", rel_path="m.py", format="py", text=src)


def test_python_static_entities_and_relations():
    doc = _py_doc()
    es, rs = _builder()._static_analysis(doc)
    names = {e.name for e in es}
    assert {"Order", "Base", "confirm", "create_order"} <= names
    assert any(e.kind == "class" and e.name == "Order" for e in es)

    rel_keys = {(r.source, r.target, r.kind) for r in rs}
    assert ("m.py", "json", "imports") in rel_keys
    assert ("Order", "Base", "inherits") in rel_keys
    assert ("create_order", "confirm", "calls") in rel_keys
    # 实体带精确行号
    order = next(e for e in es if e.name == "Order")
    assert order.span.line_start > 0


def test_python_entities_have_accurate_lines():
    src = "\n".join([f"# comment {i}" for i in range(20)])
    src += "\n\nclass AfterComments:\n    pass\n"
    doc = Document(path="C:/x/m.py", rel_path="m.py", format="py", text=src)
    es, _ = _builder()._static_analysis(doc)
    cls = next(e for e in es if e.name == "AfterComments")
    assert cls.span.line_start == 22


def test_sql_static_analysis():
    sql = """CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE VIEW order_summary AS
SELECT o.id, c.name FROM orders o JOIN customers c ON c.id = o.customer_id;
"""
    doc = Document(path="C:/x/s.sql", rel_path="s.sql", format="sql", text=sql)
    es, rs = _builder()._static_analysis(doc)
    kinds = {e.kind for e in es}
    assert "table" in kinds and "view" in kinds and "column" in kinds
    names = {e.name for e in es}
    assert {"customers", "orders", "order_summary"} <= names

    rel_keys = {(r.source, r.target, r.kind) for r in rs}
    assert ("orders.customer_id", "customers.id", "foreign_key") in rel_keys
    assert ("order_summary", "orders", "reads") in rel_keys
    assert ("order_summary", "customers", "reads") in rel_keys


def test_llm_off_channel_skipped():
    # json_capable=False 的 LLM 不触发 LLM 通道
    from knowledge_summary.llm.local_fallback import LocalFallbackLLM

    b = TopologyBuilder(CFG, LocalFallbackLLM(CFG), [])
    doc = _py_doc()
    es, rs = b.build([doc], {"m.py": []})
    assert any(e.name == "Order" for e in es)  # 静态分析仍然生效

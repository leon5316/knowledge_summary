from knowledge_summary.chunking import build_line_starts, char_to_line, chunk_document
from knowledge_summary.config import load_config
from knowledge_summary.models import Document


def test_line_mapping():
    text = "abc\ndef\n\nghi"
    offsets = build_line_starts(text)
    assert char_to_line(offsets, 0) == 1
    assert char_to_line(offsets, 4) == 2
    assert char_to_line(offsets, 8) == 3
    assert char_to_line(offsets, 9) == 4


def _doc(text, rel="test.md"):
    return Document(path="C:/x/" + rel, rel_path=rel, format="md", text=text)


def test_single_chunk_small_file():
    cfg = load_config(cli_overrides={"llm": {"provider": "none"}})
    doc = _doc("hello world\nsecond line\n")
    chunks = chunk_document(doc, cfg)
    assert len(chunks) == 1
    assert chunks[0].span.line_start == 1
    assert chunks[0].span.line_end == 2


def test_multi_chunk_with_position_mapping():
    cfg = load_config(cli_overrides={
        "llm": {"provider": "none"},
        "chunking": {"max_chunk_chars": 100, "overlap_chars": 20},
    })
    lines = [f"line number {i} with some padding text" for i in range(1, 60)]
    text = "\n\n".join(lines)
    doc = _doc(text)
    chunks = chunk_document(doc, cfg)
    assert len(chunks) >= 2

    # 每个块的跨度必须与原文对应（行号不越界）
    n_lines = text.count("\n") + 1
    for c in chunks:
        assert 1 <= c.span.line_start <= c.span.line_end <= n_lines
        assert len(c.text) <= 100 + 20  # 允许重叠导致略超上限


def test_chunk_ids_unique():
    cfg = load_config(cli_overrides={"llm": {"provider": "none"}})
    lines = [f"line {i}" for i in range(200)]
    doc = _doc("\n".join(lines), "big.md")
    chunks = chunk_document(doc, cfg, chunk_index=0)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))

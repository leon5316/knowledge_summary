import json

from knowledge_summary.pipeline import run


def test_pipeline_e2e_offline(tmp_path):
    (tmp_path / "app.py").write_text(
        '"""Sample app"""\n\nclass Greeter:\n    def greet(self, name):\n        return f"hi {name}"\n\n'
        "def main():\n    g = Greeter()\n    return g.greet(\"world\")\n",
        encoding="utf-8",
    )
    (tmp_path / "data.sql").write_text(
        "CREATE TABLE users (id BIGINT PRIMARY KEY, name VARCHAR(100));\n",
        encoding="utf-8",
    )
    (tmp_path / "notes.md").write_text("# Notes\n\nsome documentation\n", encoding="utf-8")
    (tmp_path / "secret.bin").write_bytes(b"\x00\x01")

    result = run(str(tmp_path), cli_overrides={
        "llm": {"provider": "none"},
        "storage": {"max_chunk_files": 500},
    }, verbose=False)

    out = result.out_dir
    assert out.exists()
    assert out.name == "knowledge"

    # 文件齐全
    for name in ["00_README.md", "01_overview.md", "02_summary.md",
                 "03_topology.json", "04_locate_index.json", "manifest.json"]:
        assert (out / name).exists(), name

    # 拓扑包含 Python 类与 SQL 表
    topo = json.loads((out / "03_topology.json").read_text(encoding="utf-8"))
    entity_names = {e["name"] for e in topo["entities"]}
    assert "Greeter" in entity_names
    assert "users" in entity_names
    rel_keys = {(r["source"], r["target"], r["kind"]) for r in topo["relations"]}
    assert ("main", "Greeter", "calls") in rel_keys

    # 定位索引指向精确位置
    idx = json.loads((out / "04_locate_index.json").read_text(encoding="utf-8"))
    hits = idx["entities"].get("Greeter")
    assert hits and hits[0]["file"] == "app.py"
    assert hits[0]["line_start"] >= 3
    assert hits[0].get("chunk_id")

    # manifest 统计
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["stats"]["files"] == 3
    assert manifest["stats"]["entities"] > 0
    assert manifest["llm"]["provider"] == "local"

    # chunks 已写入
    chunk_files = list((out / "chunks").glob("*.md"))
    assert chunk_files


def test_pipeline_output_in_source_dir(tmp_path):
    (tmp_path / "doc.md").write_text("# T\n\nbody\n", encoding="utf-8")
    run(str(tmp_path), cli_overrides={"llm": {"provider": "none"}}, verbose=False)
    assert (tmp_path / "knowledge").exists()
    # 知识库自身不会被二次扫描
    (tmp_path / "knowledge" / "extra.md").write_text("x", encoding="utf-8")
    result = run(str(tmp_path), cli_overrides={"llm": {"provider": "none"}}, verbose=False)
    assert result.stats["files"] == 1


def test_pipeline_single_file(tmp_path):
    f = tmp_path / "single.py"
    f.write_text("def hello():\n    return 1\n", encoding="utf-8")
    run(str(f), cli_overrides={"llm": {"provider": "none"}}, verbose=False)
    assert (tmp_path / "knowledge").exists()


def test_pipeline_falls_back_without_base_url(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\nbody\n", encoding="utf-8")
    result = run(str(tmp_path), cli_overrides={"llm": {"provider": "openai_compatible", "base_url": ""}},
                 verbose=False)
    assert result.llm_name == "local"  # 降级为离线模式
    assert any("降级" in w or "LLM" in w for w in result.warnings)

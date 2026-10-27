import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run, run_json

m = load("生成物の直し方", "regen_check.py")


def build(tmp_path):
    g, db = graph(tmp_path)
    g.add("decision_point", "方式")
    g.add("option", "案 A", parent="D1")
    return db


def export(db, out):
    reopen(db).export_markdown()
    Path(out).write_text(reopen(db).export_markdown(), encoding="utf-8", newline="\n")


def test_fresh_export_matches(tmp_path, capsys):
    db = build(tmp_path)
    md = tmp_path / "design.md"
    export(db, md)
    rc, data = run_json(m, capsys, "--db", db, "--md", md)
    assert rc == 0 and data["same"] is True and data["problems"] == []


def test_crlf_does_not_count_as_a_difference(tmp_path, capsys):
    db = build(tmp_path)
    md = tmp_path / "design.md"
    md.write_bytes(reopen(db).export_markdown().replace("\n", "\r\n").encode("utf-8"))
    rc, _, _ = run(m, capsys, "--db", db, "--md", md)
    assert rc == 0


def test_hand_edit_is_detected_with_diff(tmp_path, capsys):
    db = build(tmp_path)
    md = tmp_path / "design.md"
    export(db, md)
    md.write_text(md.read_text(encoding="utf-8") + "\n手で足した一行\n", encoding="utf-8")
    rc, data = run_json(m, capsys, "--db", db, "--md", md)
    assert rc == 1 and data["same"] is False
    assert data["problems"][0]["id"] == "stale_generated"
    assert any("手で足した一行" in line for line in data["diff"])


def test_stale_after_db_change(tmp_path, capsys):
    db = build(tmp_path)
    md = tmp_path / "design.md"
    export(db, md)
    reopen(db).add("option", "案 B", parent="D1")
    rc, _, _ = run(m, capsys, "--db", db, "--md", md)
    assert rc == 1


def test_without_md_prints_procedure_and_missing_file_is_error(tmp_path, capsys):
    db = build(tmp_path)
    rc, out, _ = run(m, capsys, "--db", db)
    assert rc == 0 and "export --out" in out
    rc2, _, err = run(m, capsys, "--db", db, "--md", tmp_path / "none.md")
    assert rc2 == 2 and "ファイルが無い" in err


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path)
    md = tmp_path / "design.md"
    export(db, md)
    common_checks(m, db, capsys, monkeypatch, tmp_path, "--md", md)

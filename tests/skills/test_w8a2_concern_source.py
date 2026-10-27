import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, run, run_json

m = load("関心事の出所", "concern_source.py")


def build(tmp_path, sourced=(True, True), two_sh=True):
    g, db = graph(tmp_path)
    g.add("stakeholder", "顧客")
    if two_sh:
        g.add("stakeholder", "保守担当")
    g.add("stakeholder", "規格 IEC")
    for i, s in enumerate(sourced, 1):
        g.add("concern", f"関心事 {i}", attrs={"weight": 3})
        if s:
            g.link("source", f"CN{i}", "SH1" if i == 1 or not two_sh else "SH2")
    return db


def test_concern_without_source_flagged(tmp_path, capsys):
    db = build(tmp_path, sourced=(True, False))
    rc, out, _ = run(m, capsys, "--db", db)
    assert rc == 1
    assert "no_source:CN2" in out and "出所: （無い）" in out


def test_by_stakeholder_and_silent(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0
    assert data["by_stakeholder"] == {"SH1": ["CN1"], "SH2": ["CN2"]}
    assert data["silent_stakeholders"] == ["SH3"]


def test_single_source_is_noted(tmp_path, capsys):
    db = build(tmp_path, two_sh=False)
    _, data = run_json(m, capsys, "--db", db)
    assert any("1 者だけ" in n for n in data["notes"])


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path, sourced=(True, False))
    common_checks(m, db, capsys, monkeypatch, tmp_path)

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run_json

m = load("上位二割の検討", "top_two_tenths.py")


def build(tmp_path, weights=(5, 4, 3, 2, 1)):
    g, db = graph(tmp_path)
    for w in weights:
        g.add("concern", f"関心事 {w}", attrs={"weight": w} if w else {})
    return db


def test_top_fifth_of_five_is_the_heaviest(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0
    assert [r["id"] for r in data["top"]] == ["CN1"]
    assert data["uncovered"] == ["CN1"]  # 課題が立っていない


def test_ties_at_the_boundary_are_all_included(tmp_path, capsys):
    db = build(tmp_path, (5, 5, 3, 2, 1))
    _, data = run_json(m, capsys, "--db", db)
    assert [r["id"] for r in data["top"]] == ["CN1", "CN2"]


def test_issue_closed_covers_and_unweighted_listed(tmp_path, capsys):
    db = build(tmp_path, (5, 3, 0))
    g = reopen(db)
    g.add("issue", "待ちが長い")
    g.link("affects", "IS1", "CN1")
    reopen(db, "human").close("IS1", "resolved")
    _, data = run_json(m, capsys, "--db", db)
    assert data["top"][0]["covered"] is True and data["uncovered"] == []
    assert data["unweighted"] == ["CN3"]


def test_unresolved_issue_does_not_cover(tmp_path, capsys):
    db = build(tmp_path, (5, 3))
    g = reopen(db)
    g.add("issue", "待ちが長い")
    g.link("affects", "IS1", "CN1")
    _, data = run_json(m, capsys, "--db", db)
    assert data["uncovered"] == ["CN1"] and data["top"][0]["issues"][0]["label"] == "未解決"


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path)
    common_checks(m, db, capsys, monkeypatch, tmp_path)

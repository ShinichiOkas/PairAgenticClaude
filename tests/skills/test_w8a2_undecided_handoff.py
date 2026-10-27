import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run, run_json

m = load("未決の渡し方", "undecided_handoff.py")


def build(tmp_path):
    g, db = graph(tmp_path)
    g.add("decision_point", "方式")
    g.add("option", "案 A", parent="D1")
    g.add("option", "案 B", parent="D1")
    g.add("issue", "遅い")
    g.add("issue", "壊れる")
    h = reopen(db, "human")
    h.close("IS2", "deferred", resume_if="部品が入荷したら")
    g2 = reopen(db)
    g2.update("D1", attrs={"memo": "変えた"})  # 子の案に要再確認の印が付く
    return db


def test_lists_undecided_open_deferred_and_recheck(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0  # 未決は情報であり、検出ではない
    assert data["undecided"][0]["id"] == "D1" and len(data["undecided"][0]["options"]) == 2
    assert [o["id"] for o in data["open"]] == ["IS1"]
    assert data["deferred"] == [{"id": "IS2", "title": "壊れる", "resume_if": "部品が入荷したら"}]
    assert {r["downstream"] for r in data["recheck"]} == {"D1-A", "D1-B"}
    assert [f["rule"] for f in data["findings"]] == ["undecided"]


def test_text_has_headings_and_conditions(tmp_path, capsys):
    db = build(tmp_path)
    _, out, _ = run(m, capsys, "--db", db)
    assert "未決（推測で埋めない）" in out and "再開の条件: 部品が入荷したら" in out


def test_all_decided_says_none(tmp_path, capsys):
    g, db = graph(tmp_path)
    g.add("decision_point", "方式")
    g.add("option", "案 A", parent="D1")
    reopen(db, "human").decide("D1", "D1-A", conditions=["c"])
    _, data = run_json(m, capsys, "--db", db)
    assert data["undecided"] == []


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path)
    common_checks(m, db, capsys, monkeypatch, tmp_path)

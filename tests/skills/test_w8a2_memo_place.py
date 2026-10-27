import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, run, run_json

m = load("思いつきの置き場", "memo_place.py")


def build(tmp_path):
    g, db = graph(tmp_path)
    g.add("component", "制御器")
    g.add("note", "ここは分けた方がよいかも")
    g.add("note", "宙に浮いたメモ")
    g.link("about", "DN1", "LC1")
    return db


def test_note_about_target_and_floating_note(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0
    n1, n2 = data["notes"]
    assert n1["about"] == [{"target": "LC1", "seen": 1, "current": 1, "stale": False}]
    assert n2["about"] == []
    _, out, _ = run(m, capsys, "--db", db)
    assert "何についてのメモか分からない" in out


def test_target_change_makes_note_stale(tmp_path, capsys):
    db = build(tmp_path)
    g, _ = graph(tmp_path)
    g.update("LC1", title="制御器（改）")
    _, data = run_json(m, capsys, "--db", db)
    a = data["notes"][0]["about"][0]
    assert a["stale"] is True and (a["seen"], a["current"]) == (1, 2)
    _, out, _ = run(m, capsys, "--db", db)
    assert "古い" in out


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path)
    common_checks(m, db, capsys, monkeypatch, tmp_path)

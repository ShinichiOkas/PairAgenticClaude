import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run, run_json

m = load("決断の禁止事項", "decision_must.py")


def build(tmp_path, attrs):
    g, db = graph(tmp_path)
    g.add("decision_point", "方式")
    g.add("option", "案 A", parent="D1", attrs=attrs)
    g.add("option", "案 B", parent="D1")
    reopen(db, "human").decide("D1", "D1-A", conditions=["一台運用"])
    return db


def test_decision_without_must_flagged(tmp_path, capsys):
    db = build(tmp_path, {})
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1
    assert data["findings"][0]["id"] == "no_must:D1-A"
    assert data["decisions"][0]["must"] is None


def test_must_and_must_not_shown(tmp_path, capsys):
    db = build(tmp_path, {"must": ["温度を毎秒読む"], "must_not": ["蓋を開けて測らない"]})
    rc, out, _ = run(m, capsys, "--db", db)
    assert rc == 0
    assert "must:     温度を毎秒読む" in out and "must_not: 蓋を開けて測らない" in out
    assert "背景事情: 一台運用" in out


def test_only_must_not_is_enough(tmp_path, capsys):
    db = build(tmp_path, {"must_not": ["x"]})
    rc, _, _ = run(m, capsys, "--db", db)
    assert rc == 0


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path, {})
    common_checks(m, db, capsys, monkeypatch, tmp_path)

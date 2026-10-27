import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, run, run_json

m = load("関連の述語", "relation_predicate.py")


def build(tmp_path, predicate=None):
    g, db = graph(tmp_path)
    g.add("component", "炊飯制御")
    g.add("component", "温度計測")
    g.link("relation", "LC1", "LC2", predicate=predicate)
    return db


def test_relation_without_predicate_flagged(tmp_path, capsys):
    db = build(tmp_path)
    rc, out, _ = run(m, capsys, "--db", db)
    assert rc == 1
    assert "LC1 —（述語なし）→ LC2" in out and "no_predicate:L1" in out


def test_triples_and_tally(tmp_path, capsys):
    db = build(tmp_path, "を読む")
    g, _ = graph(tmp_path)  # 同じ DB を開き直す
    g.link("relation", "LC2", "LC1", predicate="に通知する")
    g.link("relation", "LC1", "LC2", predicate="を読む")  # 同じ線は増えない
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0
    assert [(t["subject"], t["predicate"], t["object"]) for t in data["relations"]] == \
        [("LC1", "を読む", "LC2"), ("LC2", "に通知する", "LC1")]
    assert data["predicates"] == {"を読む": 1, "に通知する": 1}


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path)
    common_checks(m, db, capsys, monkeypatch, tmp_path)

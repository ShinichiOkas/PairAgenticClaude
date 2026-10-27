import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, run, run_json

m = load("横断的関心事の見方", "crosscut_view.py")


def build(tmp_path):
    g, db = graph(tmp_path)
    g.add("concern", "安全")
    g.add("concern", "保守性")
    g.add("issue", "過熱")
    g.add("decision_point", "冷却方式")
    g.add("component", "ヒータ制御")
    g.add("component", "温度計測")
    g.link("affects", "IS1", "CN1")
    g.link("affects", "IS1", "CN2")
    g.link("anchors", "D1", "IS1")
    g.add("requirement", "過熱時に止める")
    g.link("derives", "D1", "RQ1")
    g.link("allocates", "RQ1", "LC1")
    g.link("allocates", "RQ1", "LC2")
    g.link("relation", "LC1", "LC2", predicate="を読む")
    return db


def test_groups_downstream_by_kind_and_collects_relations(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db, "CN1")
    assert rc == 0
    assert data["concerns"]["CN1"]["component"] == ["LC1", "LC2"]
    assert data["concerns"]["CN1"]["issue"] == ["IS1"]
    assert [(r["src"], r["predicate"], r["dst"]) for r in data["relations"]] == [("LC1", "を読む", "LC2")]


def test_common_elements_of_two_concerns(tmp_path, capsys):
    db = build(tmp_path)
    _, data = run_json(m, capsys, "--db", db, "CN1", "CN2")
    assert "LC1" in data["common"] and "D1" in data["common"]


def test_unknown_id_is_error_and_id_is_required(tmp_path, capsys):
    db = build(tmp_path)
    rc, _, err = run(m, capsys, "--db", db, "CN99")
    assert rc == 2 and "無い ID" in err
    with pytest.raises(SystemExit) as e:
        m.main(["--db", str(db)])
    assert e.value.code == 2


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path)
    common_checks(m, db, capsys, monkeypatch, tmp_path, "CN1")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run, run_json

m = load("仕様への制約の説明", "spec_constraint_impact.py")


def build(tmp_path):
    g, db = graph(tmp_path)
    g.add("constraint", "メモリ 64KB")
    g.add("decision_point", "制御方式")
    g.add("option", "PID", parent="D1", attrs={"must": ["周期 100ms"], "must_not": ["動的確保"]})
    g.add("option", "ファジィ", parent="D1")
    g.add("requirement", "温度を保つ")
    g.add("requirement", "無関係な要求")
    g.add("component", "制御器")
    g.link("derives", "D1-A", "RQ1")
    g.link("allocates", "RQ1", "LC1")
    reopen(db, "human").decide("D1", "D1-A", conditions=["c"])
    return db


def test_without_ids_lists_constraints_and_adopted_must(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0
    assert data["constraints"][0]["id"] == "CT1"
    assert data["adopted"][0]["must"] == ["周期 100ms"] and data["adopted"][0]["must_not"] == ["動的確保"]


def test_requirement_shows_imposing_decision_and_downstream(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db, "RQ1")
    assert rc == 0
    t = data["targets"][0]
    assert [c["option"] for c in t["imposed_by"]] == ["D1-A"]
    assert t["downstream"] == {"component": ["LC1"]}


def test_unrelated_requirement_has_no_constraint(tmp_path, capsys):
    db = build(tmp_path)
    _, out, _ = run(m, capsys, "--db", db, "RQ2")
    assert "この要素に制約を課している採用済みの案:\n    - なし" in out


def test_unknown_id(tmp_path, capsys):
    db = build(tmp_path)
    rc, _, err = run(m, capsys, "--db", db, "RQ9")
    assert rc == 2 and "無い ID" in err


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path)
    common_checks(m, db, capsys, monkeypatch, tmp_path, "RQ1")

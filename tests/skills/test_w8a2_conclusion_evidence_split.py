import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run_json

m = load("結論と根拠の分離", "conclusion_evidence_split.py")


def build(tmp_path, with_evidence):
    g, db = graph(tmp_path)
    g.add("decision_point", "方式")
    g.add("option", "案 A", parent="D1")
    g.add("record", "実測: 方式 A は 20 分")
    g.add("record", "誰も参照しないノート")
    h = reopen(db, "human")
    h.decide("D1", "D1-A", evidence=["NT1"] if with_evidence else [], conditions=["c"])
    return db


def test_conclusion_without_evidence_flagged(tmp_path, capsys):
    db = build(tmp_path, with_evidence=False)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1
    assert [f["id"] for f in data["findings"]] == ["no_evidence:D1"]
    assert data["conclusions"][0]["evidence"] == []


def test_links_conclusion_and_record_both_ways(tmp_path, capsys):
    db = build(tmp_path, with_evidence=True)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0
    assert data["conclusions"][0]["evidence"] == ["NT1"]
    refs = {r["id"]: r["referenced_by"] for r in data["records"]}
    assert refs == {"NT1": ["D1"], "NT2": []}
    assert data["unreferenced_records"] == ["NT2"]


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path, with_evidence=False)
    common_checks(m, db, capsys, monkeypatch, tmp_path)

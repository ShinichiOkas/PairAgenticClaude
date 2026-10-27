import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run_json

m = load("検証計画", "verification_plan.py")


def build(tmp_path, verification=None, recommended=False):
    g, db = graph(tmp_path)
    g.add("decision_point", "方式")
    a = {}
    if verification:
        a["verification"] = verification
    if recommended:
        a["recommended"] = True
    g.add("option", "案 A", parent="D1", attrs=a)
    g.add("option", "案 B", parent="D1")
    return db


def test_adopted_without_verification_flagged(tmp_path, capsys):
    db = build(tmp_path)
    reopen(db, "human").decide("D1", "D1-A", conditions=["c"])
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1
    assert data["options"] == [{"id": "D1-A", "title": "案 A", "why": "採用", "verification": None}]
    assert data["findings"][0]["id"] == "no_verification:D1-A"


def test_adopted_with_verification_clean(tmp_path, capsys):
    db = build(tmp_path, verification="実機で 3 回炊く")
    reopen(db, "human").decide("D1", "D1-A", conditions=["c"])
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0 and data["options"][0]["verification"] == "実機で 3 回炊く"


def test_recommended_counts_and_undecided_candidates_listed(tmp_path, capsys):
    db = build(tmp_path, recommended=True)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1 and data["options"][0]["why"] == "推奨"
    assert [c["id"] for c in data["unverified_candidates"]] == ["D1-B"]


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path, recommended=True)
    common_checks(m, db, capsys, monkeypatch, tmp_path)

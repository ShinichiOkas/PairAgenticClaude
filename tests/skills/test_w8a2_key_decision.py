import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run, run_json

m = load("要の決定点", "key_decision.py")


def build(tmp_path, both=False):
    g, db = graph(tmp_path)
    for t in ("方式", "通信"):
        g.add("decision_point", t)
        for v in ("a", "b", "c"):
            g.add("option", f"{t}案{v}", parent="D1" if t == "方式" else "D2", attrs={"viewpoint": v})
    g.add("requirement", "待ち時間を短くする")
    g.add("requirement", "電力を抑える")
    g.link("derives", "D1-A", "RQ1")
    g.link("derives", "D1-A", "RQ2")
    g.link("excludes", "D1-A", "D2-A")
    if both:
        h = reopen(db, "human")
        h.decide("D1", "D1-A", conditions=["c"])
        h.decide("D2", "D2-A", conditions=["c"])
    return db


def test_ranked_by_downstream_impact(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0
    assert [r["id"] for r in data["decision_points"]] == ["D1", "D2"]
    assert data["decision_points"][0]["impact"] == 2 and data["decision_points"][1]["impact"] == 0
    assert [(l["kind"], l["src"], l["dst"]) for l in data["option_links"]] == [("excludes", "D1-A", "D2-A")]


def test_excluded_both_adopted_flagged(tmp_path, capsys):
    db = build(tmp_path, both=True)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1
    assert [f["rule"] for f in data["findings"]] == ["excluded_both"]


def test_id_filter_and_bad_id(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db, "D2")
    assert rc == 0 and [r["id"] for r in data["decision_points"]] == ["D2"]
    rc2, _, err = run(m, capsys, "--db", db, "RQ1")
    assert rc2 == 2 and "決定点" in err


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path, both=True)
    common_checks(m, db, capsys, monkeypatch, tmp_path)

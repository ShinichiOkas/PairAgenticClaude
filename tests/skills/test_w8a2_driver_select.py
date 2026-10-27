import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, run, run_json

m = load("アーキテクチャドライバーの選別", "driver_select.py")


def build(tmp_path, weights=(5, 3, 5)):
    g, db = graph(tmp_path)
    for w in weights:
        g.add("concern", f"関心事 重み{w}", attrs={"weight": w} if w else {})
    g.add("issue", "待ちが長い")
    g.link("affects", "IS1", f"CN{len(weights)}" if len(weights) > 2 else "CN1")
    g.add("decision_point", "方式")
    g.link("anchors", "D1", "IS1")
    return db


def test_drivers_ranked_by_weight_then_downstream(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0
    assert [r["id"] for r in data["drivers"]] == ["CN3", "CN1"]  # CN3 は下流（課題・決定点）がある
    assert data["drivers"][0]["downstream"] == 2 and data["drivers"][0]["issues"] == ["IS1"]
    assert [r["id"] for r in data["others"]] == ["CN2"]


def test_threshold_widens_candidates(tmp_path, capsys):
    db = build(tmp_path)
    _, data = run_json(m, capsys, "--db", db, "--threshold", "3")
    assert [r["id"] for r in data["drivers"]] == ["CN3", "CN1", "CN2"]
    rc, _, err = run(m, capsys, "--db", db, "--threshold", "9")
    assert rc == 2 and "1〜5" in err


def test_unweighted_concern_is_flagged(tmp_path, capsys):
    db = build(tmp_path, weights=(5, 0))
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1 and data["findings"][0]["id"] == "no_weight:CN2"


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path)
    common_checks(m, db, capsys, monkeypatch, tmp_path)

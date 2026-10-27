import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run, run_json

m = load("視点の異なる三案", "option_viewpoints.py")


def build(tmp_path, views):
    g, db = graph(tmp_path)
    g.add("decision_point", "炊飯の制御方式")
    for v in views:
        g.add("option", f"案 {v}", parent="D1", attrs={"viewpoint": v} if v else {})
    return db


def test_two_options_flagged_with_viewpoints_listed(tmp_path, capsys):
    db = build(tmp_path, ["速さ", "安さ"])
    rc, out, _ = run(m, capsys, "--db", db)
    assert rc == 1
    assert "few_options:D1" in out and "視点: 速さ" in out


def test_same_viewpoint_and_missing_viewpoint_are_shown(tmp_path, capsys):
    db = build(tmp_path, ["速さ", "速さ", None])
    rc, data = run_json(m, capsys, "--db", db)
    dp = data["decision_points"][0]
    assert dp["same_viewpoint"] == {"速さ": ["D1-A", "D1-B"]}
    assert dp["no_viewpoint"] == ["D1-C"]
    assert rc == 1


def test_three_distinct_viewpoints_is_clean(tmp_path, capsys):
    db = build(tmp_path, ["速さ", "安さ", "保守性"])
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0 and data["findings"] == [] and data["decision_points"][0]["viewpoints"] == 3


def test_decided_point_is_not_flagged(tmp_path, capsys):
    db = build(tmp_path, ["速さ", "安さ"])
    reopen(db, "human").decide("D1", "D1-A", conditions=["当面は一台"])
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0 and data["decision_points"][0]["decided"] is True


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path, ["速さ", "安さ"])
    common_checks(m, db, capsys, monkeypatch, tmp_path)

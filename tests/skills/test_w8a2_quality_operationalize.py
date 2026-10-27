import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, run, run_json

m = load("品質特性の操作化", "quality_operationalize.py")


def build(tmp_path, measure="30 分以内", **override):
    g, db = graph(tmp_path)
    a = {"source": "利用者", "stimulus": "炊飯開始", "environment": "室温 20 度", "artifact": "制御部",
         "response": "炊き上がる", "response_measure": measure}
    a.update(override)
    g.add("qas", "炊飯時間", attrs={k: v for k, v in a.items() if v is not None})
    return db


def test_three_points_are_shown(tmp_path, capsys):
    db = build(tmp_path)
    rc, out, _ = run(m, capsys, "--db", db)
    assert rc == 0
    assert "測れる量・閾値: 30 分以内" in out and "測定条件:       室温 20 度" in out


def test_measure_without_number_is_listed_but_not_a_finding(tmp_path, capsys):
    db = build(tmp_path, measure="速い")
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0 and data["no_number"] == ["QS1"] and data["findings"] == []


def test_missing_environment_is_qas_incomplete(tmp_path, capsys):
    db = build(tmp_path, environment=None)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1 and data["findings"][0]["rule"] == "qas_incomplete"


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path, environment=None)
    common_checks(m, db, capsys, monkeypatch, tmp_path)

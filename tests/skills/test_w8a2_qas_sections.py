import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, run, run_json

m = load("区間の品質特性シナリオ", "qas_sections.py")

FULL = {"source": "利用者", "stimulus": "炊飯開始", "environment": "通常運転", "artifact": "制御部",
        "response": "炊き上がる", "response_measure": "30 分以内", "interval": "開始〜完了"}


def build(tmp_path, **override):
    g, db = graph(tmp_path)
    a = {**FULL, **override}
    g.add("qas", "炊飯時間", attrs={k: v for k, v in a.items() if v is not None})
    return db


def test_missing_source_flagged(tmp_path, capsys):
    db = build(tmp_path, source=None)
    rc, out, _ = run(m, capsys, "--db", db)
    assert rc == 1
    assert "source×" in out and "欠け: source" in out and "qas_incomplete:QS1" in out


def test_complete_scenario_clean(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0
    assert data["scenarios"][0]["missing"] == [] and data["scenarios"][0]["interval"] == "開始〜完了"


def test_measure_alias_is_accepted(tmp_path, capsys):
    db = build(tmp_path, response_measure=None, measure="30 分以内")
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0 and data["scenarios"][0]["fields"]["response_measure"] is True


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path, source=None)
    common_checks(m, db, capsys, monkeypatch, tmp_path)

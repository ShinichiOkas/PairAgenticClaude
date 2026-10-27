import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w4_load import load

m = load("実データでの棚卸し", "recheck_observations.py")


def make(tmp_path, rows):
    (tmp_path / "metrics.csv").write_text("timestamp,metric,value\n" + "\n".join(rows) + "\n", encoding="utf-8")


def week(vals, metric="error_rate"):
    return [f"2026-10-{20 + i}T12:00:00,{metric},{v}" for i, v in enumerate(vals)]


def item(**kw):
    base = {"id": "O1", "metric": "error_rate", "agg": "all", "op": "<", "threshold": 0.001,
            "window_days": 7, "source": "metrics.csv"}
    base.update(kw)
    return base


def test_all_satisfied_and_unsatisfied(tmp_path):
    make(tmp_path, week([0.0005] * 8))
    r = m.judge_item(item(), tmp_path, None, 0.01)
    assert r["verdict"] == "満たした" and r["points"] == 7
    make(tmp_path, week([0.0005] * 7 + [0.002]))
    r = m.judge_item(item(), tmp_path, None, 0.01)
    assert r["verdict"] == "満たしていない" and r["actual"] == 0.002


def test_window_not_covered_is_hold(tmp_path):
    make(tmp_path, week([0.0001] * 3))
    r = m.judge_item(item(), tmp_path, None, 0.01)
    assert r["verdict"] == "保留" and "届かない" in r["reason"]


def test_window_excludes_old_points(tmp_path):
    make(tmp_path, ["2026-10-01T12:00:00,error_rate,0.5"] + week([0.0005] * 8))
    assert m.judge_item(item(), tmp_path, None, 0.01)["verdict"] == "満たした"


def test_recorded_mismatch_reported(tmp_path):
    make(tmp_path, week([0.0005] * 8))
    r = m.judge_item(item(agg="max", recorded={"value": 0.0001, "at": "2026-09-01"}), tmp_path, None, 0.01)
    assert r["mismatch"] is True and "2026-09-01" in r["mismatch_note"]
    r = m.judge_item(item(agg="max", recorded={"value": 0.0005, "at": "2026-09-01"}), tmp_path, None, 0.01)
    assert r["mismatch"] is False


def test_log_pattern_and_missing_source(tmp_path):
    (tmp_path / "run.log").write_text("ok\nERROR a\nok\nERROR b\n", encoding="utf-8")
    r = m.judge_item({"id": "L", "source": "run.log", "pattern": "ERROR", "op": "<=", "threshold": 1}, tmp_path, None, 0.01)
    assert r["actual"] == 2 and r["verdict"] == "満たしていない"
    r = m.judge_item({"id": "X", "source": "nope.csv", "metric": "a", "op": "<", "threshold": 1}, tmp_path, None, 0.01)
    assert r["verdict"] == "保留"
    r = m.judge_item({"id": "Y", "source": "run.log"}, tmp_path, None, 0.01)
    assert r["verdict"] == "保留"


def test_cli_exit_on_mismatch(tmp_path, capsys):
    make(tmp_path, week([0.0005] * 8))
    ip = tmp_path / "items.json"
    ip.write_text(json.dumps([item(agg="max", recorded={"value": 0.01, "at": "2026-09-01"})]), encoding="utf-8")
    assert m.main(["--items", str(ip)]) == 1
    assert "食い違い" in capsys.readouterr().out

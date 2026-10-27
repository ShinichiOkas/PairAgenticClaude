import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def load(skill, name):
    p = ROOT / "skills" / "scripts" / skill / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"w5_{name}", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


rm = load("再実測", "remeasure")
PY = sys.executable


def go(capsys, *args):
    code = rm.main(list(args))
    return code, json.loads(capsys.readouterr().out)


def test_always_failing_is_reproduced(capsys):
    code, r = go(capsys, "--runs", "3", "--", PY, "-c", "import sys; sys.exit(3)")
    assert (code, r["verdict"], r["red_count"]) == (0, "再現する", 3)


def test_always_passing_is_not_reproduced_but_still_reported(capsys):
    code, r = go(capsys, "--runs", "2", "--", PY, "-c", "print('ok')")
    assert (code, r["verdict"], r["red_count"]) == (0, "再現しない", 0)


def test_intermittent_failure_is_unstable(capsys, tmp_path):
    counter = tmp_path / "c"
    script = ("import sys,pathlib;p=pathlib.Path(sys.argv[1]);n=int(p.read_text()) if p.exists() else 0;"
              "p.write_text(str(n+1));sys.exit(1 if n%2==0 else 0)")
    code, r = go(capsys, "--runs", "4", "--", PY, "-c", script, str(counter))
    assert (r["verdict"], r["red_count"]) == ("不安定", 2)


def test_red_pattern_makes_exit_zero_red(capsys):
    code, r = go(capsys, "--red-pattern", "Traceback", "--", PY, "-c", "print('Traceback boo')")
    assert r["verdict"] == "再現する"


def test_symptom_drift_is_flagged(capsys, tmp_path):
    counter = tmp_path / "c"
    script = ("import sys,pathlib;p=pathlib.Path(sys.argv[1]);n=int(p.read_text()) if p.exists() else 0;"
              "p.write_text(str(n+1));sys.stderr.write('e%d'%n);sys.exit(1)")
    code, r = go(capsys, "--runs", "2", "--", PY, "-c", script, str(counter))
    assert r["verdict"] == "再現する(症状が揺れる)"


def test_conditions_are_identical_across_runs_and_recorded(capsys):
    code, r = go(capsys, "--runs", "2", "--env", "W5X=1", "--", PY, "-c",
                 "import os,sys; sys.exit(0 if os.environ.get('W5X')=='1' else 9)")
    assert r["verdict"] == "再現しない" and r["conditions"]["env_added"] == {"W5X": "1"}


def test_timeout_is_red(capsys):
    code, r = go(capsys, "--timeout", "0.5", "--", PY, "-c", "import time; time.sleep(5)")
    assert r["runs"][0]["timeout"] is True and r["verdict"] == "再現する"


def test_missing_command_is_reported_as_red_not_crash(capsys):
    code, r = go(capsys, "--", "definitely-not-a-command-w5")
    assert code == 0 and r["runs"][0]["red"] is True


def test_no_command_is_input_error(capsys):
    assert rm.main(["--runs", "2"]) == 2


def test_out_file_not_overwritten(capsys, tmp_path):
    out = tmp_path / "r.json"
    assert rm.main(["--out", str(out), "--", PY, "-c", "pass"]) == 0
    first = out.read_text(encoding="utf-8")
    assert rm.main(["--out", str(out), "--", PY, "-c", "import sys; sys.exit(1)"]) == 2
    assert out.read_text(encoding="utf-8") == first

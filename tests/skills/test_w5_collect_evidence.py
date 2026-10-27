import hashlib
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def load(skill, name):
    p = ROOT / "skills" / "scripts" / skill / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"w5_{name}", p)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


ce = load("証拠の採取", "collect_evidence")


def make(tmp_path):
    (tmp_path / "in.json").write_bytes(b'{"a": 1}\r\n')
    (tmp_path / "app.log").write_bytes("行1\n行2\n行3\n".encode("utf-8"))
    return tmp_path


def run(tmp_path, *extra):
    return ce.main(["--input", str(tmp_path / "in.json"), "--log", str(tmp_path / "app.log"),
                    "--out", str(tmp_path / "ev"), "--now", "2026-10-27T09:10:00Z", *extra])


def test_dry_run_writes_nothing(tmp_path, capsys):
    make(tmp_path)
    assert run(tmp_path) == 0
    assert not (tmp_path / "ev").exists()
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


def test_apply_copies_bytes_unchanged_with_hashes(tmp_path):
    make(tmp_path)
    assert run(tmp_path, "--apply", "--event-time", "2026-10-27T09:00:00Z") == 0
    m = json.loads((tmp_path / "ev" / "manifest.json").read_text(encoding="utf-8"))
    f = {x["kind"]: x for x in m["files"]}
    stored = (tmp_path / "ev" / f["input"]["stored"]).read_bytes()
    assert stored == b'{"a": 1}\r\n'
    assert f["input"]["sha256"] == hashlib.sha256(stored).hexdigest()


def test_event_time_and_capture_time_are_kept_separate(tmp_path):
    make(tmp_path)
    run(tmp_path, "--apply", "--event-time", "2026-10-27T09:00:00Z")
    m = json.loads((tmp_path / "ev" / "manifest.json").read_text(encoding="utf-8"))
    assert (m["event_time"], m["captured_at"]) == ("2026-10-27T09:00:00Z", "2026-10-27T09:10:00Z")


def test_existing_output_is_never_overwritten(tmp_path, capsys):
    make(tmp_path)
    (tmp_path / "ev").mkdir()
    assert run(tmp_path, "--apply") == 2
    assert list((tmp_path / "ev").iterdir()) == []


def test_missing_input_is_rejected(tmp_path):
    assert ce.main(["--input", str(tmp_path / "x"), "--out", str(tmp_path / "ev"), "--apply"]) == 2
    assert not (tmp_path / "ev").exists()


def test_excerpt_is_separate_from_raw(tmp_path):
    make(tmp_path)
    run(tmp_path, "--apply", "--excerpt", "2")
    ex = next((tmp_path / "ev" / "excerpt").iterdir()).read_text(encoding="utf-8")
    assert ex == "行2\n行3\n"
    raw = next((tmp_path / "ev" / "raw" / "log").iterdir()).read_text(encoding="utf-8")
    assert "行1" in raw


def test_same_basename_logs_do_not_collide(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "x.log").write_text("A", encoding="utf-8")
    (tmp_path / "b" / "x.log").write_text("B", encoding="utf-8")
    assert ce.main(["--log", str(tmp_path / "a" / "x.log"), "--log", str(tmp_path / "b" / "x.log"),
                    "--out", str(tmp_path / "ev"), "--apply"]) == 0
    assert len(list((tmp_path / "ev" / "raw" / "log").iterdir())) == 2


def test_env_vars_recorded(tmp_path, monkeypatch):
    make(tmp_path)
    monkeypatch.setenv("W5_PROBE", "yes")
    run(tmp_path, "--apply", "--env", "W5_PROBE", "--env", "W5_ABSENT")
    m = json.loads((tmp_path / "ev" / "manifest.json").read_text(encoding="utf-8"))
    assert m["environment"]["vars"] == {"W5_ABSENT": None, "W5_PROBE": "yes"}

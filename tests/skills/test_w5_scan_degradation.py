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


sd = load("縮退経路のログ設計", "scan_degradation")


def status(src):
    return [s["status"] for s in sd.scan_source(src)]


def test_pass_swallow_is_silent():
    assert status("try:\n    f()\nexcept Exception:\n    pass\n") == ["silent"]


def test_warning_log_is_logged():
    assert status("try:\n    f()\nexcept OSError:\n    logging.warning('縮退: x')\n") == ["logged"]


def test_logger_object_warning_is_logged():
    assert status("try:\n    f()\nexcept OSError as e:\n    logger.exception('x')\n") == ["logged"]


def test_info_only_is_low_level():
    assert status("try:\n    f()\nexcept OSError:\n    logger.info('x')\n") == ["low-level"]


def test_bare_print_is_low_level_but_stderr_print_is_logged():
    assert status("try:\n    f()\nexcept OSError:\n    print('x')\n") == ["low-level"]
    assert status("try:\n    f()\nexcept OSError:\n    print('x', file=sys.stderr)\n") == ["logged"]


def test_reraise_is_not_degradation():
    assert status("try:\n    f()\nexcept OSError:\n    raise\n") == []
    assert status("try:\n    f()\nexcept OSError as e:\n    raise RuntimeError('x') from e\n") == []


def test_suppress_is_silent_degradation():
    s = sd.scan_source("import contextlib\nwith contextlib.suppress(KeyError):\n    f()\n")
    assert [(x["kind"], x["status"], x["exception"]) for x in s] == [("suppress", "silent", "KeyError")]


def test_bare_except_named_and_line_reported():
    s = sd.scan_source("x = 1\ntry:\n    f()\nexcept:\n    return_default()\n")
    assert (s[0]["exception"], s[0]["line"]) == ("(bare)", 4)


def test_nested_handlers_are_each_counted():
    src = ("try:\n    a()\nexcept A:\n    try:\n        b()\n    except B:\n        pass\n    logging.error('x')\n")
    assert sorted(status(src)) == ["logged", "silent"]


def test_cli_summary_and_exit(tmp_path, capsys):
    (tmp_path / "m.py").write_text(
        "try:\n    f()\nexcept A:\n    pass\ntry:\n    g()\nexcept B:\n    logging.warning('x')\n", encoding="utf-8")
    assert sd.main([str(tmp_path)]) == 1
    assert "縮退経路 2 件のうちログ(警告以上)を出すのは 1 件" in capsys.readouterr().out
    assert sd.main([str(tmp_path), "--fail-on", "never"]) == 0


def test_clean_code_passes_and_syntax_error_is_reported(tmp_path, capsys):
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    assert sd.main([str(tmp_path)]) == 0
    capsys.readouterr()
    (tmp_path / "bad.py").write_text("def (:\n", encoding="utf-8")
    assert sd.main([str(tmp_path), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["summary"]["unparsable"] == 1


def test_no_python_files_is_input_error(tmp_path):
    assert sd.main([str(tmp_path)]) == 2

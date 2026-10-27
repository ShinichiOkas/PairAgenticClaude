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


mc = load("ホワイトボックステストの書き方", "mutate_check")

MOD = '''"""doc 1"""
def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def both(a, b):
    return a and b
'''

STRONG = '''from mod import clamp, both
assert clamp(-1, 0, 10) == 0
assert clamp(11, 0, 10) == 10
assert clamp(5, 0, 10) == 5
assert clamp(0, 0, 10) == 0
assert clamp(10, 0, 10) == 10
assert both(True, False) is False
assert both(True, True) is True
assert both(False, True) is False
'''

WEAK = '''from mod import clamp
assert clamp(5, 0, 10) == 5
'''


def project(tmp_path, tests):
    (tmp_path / "mod.py").write_text(MOD, encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(tests, encoding="utf-8")
    return tmp_path


def run(tmp_path, *extra):
    return mc.main(["--src", "mod.py", "--root", str(tmp_path), "--test-cmd", "python test_mod.py",
                    "--json", *extra])


def test_enumerate_skips_docstrings_and_finds_operators():
    sites = mc.enumerate_mutants(MOD)
    descs = [d for _, _, d in sites]
    assert "Lt -> GtE" in descs and "Gt -> LtE" in descs and "And -> Or" in descs
    assert not any("1 -> 2" in d for d in descs)  # docstring の "doc 1" は変異対象でない


def test_apply_mutant_changes_exactly_the_chosen_site():
    k = next(k for k, _, d in mc.enumerate_mutants(MOD) if d == "And -> Or")
    out, desc = mc.apply_mutant(MOD, k)
    assert "a or b" in out and "x < lo" in out and desc[1] == "And -> Or"


def test_dry_run_lists_without_running(tmp_path, capsys):
    project(tmp_path, STRONG)
    assert run(tmp_path) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["dry_run"] is True and len(r["mutants"]) >= 5


def test_strong_tests_kill_everything(tmp_path, capsys):
    project(tmp_path, STRONG)
    assert run(tmp_path, "--run", "--timeout", "60") == 0
    r = json.loads(capsys.readouterr().out)
    assert r["survived"] == 0 and r["killed"] == r["total"] > 0


def test_weak_tests_leave_survivors_and_fail(tmp_path, capsys):
    project(tmp_path, WEAK)
    assert run(tmp_path, "--run") == 1
    r = json.loads(capsys.readouterr().out)
    assert r["survived"] > 0 and any("return" in s["mutation"] or "Lt" in s["mutation"] for s in r["survivors"])


def test_original_source_is_untouched(tmp_path, capsys):
    project(tmp_path, WEAK)
    run(tmp_path, "--run")
    assert (tmp_path / "mod.py").read_text(encoding="utf-8") == MOD


def test_failing_baseline_aborts_with_2(tmp_path, capsys):
    project(tmp_path, "assert 1 == 2\n")
    assert run(tmp_path, "--run") == 2


def test_max_survivors_threshold(tmp_path, capsys):
    project(tmp_path, WEAK)
    assert run(tmp_path, "--run", "--max-survivors", "999") == 0


def test_line_filter_narrows_mutants(tmp_path, capsys):
    project(tmp_path, STRONG)
    run(tmp_path, "--lines", "10-11")
    r = json.loads(capsys.readouterr().out)
    assert r["mutants"] and all(10 <= m["line"] <= 11 for m in r["mutants"])


def test_missing_src_is_input_error(tmp_path):
    assert mc.main(["--src", "nope.py", "--root", str(tmp_path), "--test-cmd", "pytest"]) == 2

import importlib.util
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


lt = load("ホワイトボックステストの書き方", "lint_tests")


def codes(src, **kw):
    issues, _ = lt.lint_source(src, "t.py", **kw)
    return [(i["code"], i["severity"]) for i in issues]


def test_test_without_assert_is_error():
    assert ("no-assert", "error") in codes("def test_a():\n    f()\n")


def test_trivial_asserts_are_errors():
    assert ("trivial-assert", "error") in codes("def test_a():\n    assert True\n")
    assert ("trivial-assert", "error") in codes("def test_a():\n    assert x == x\n")


def test_real_assert_with_raises_is_clean():
    src = ("import pytest\n\ndef test_a():\n    assert f() == 1\n\ndef test_b():\n    with pytest.raises(ValueError):\n        f(-1)\n")
    assert codes(src) == []


def test_many_assertions_warns_at_threshold_plus_one():
    body = "".join(f"    assert f({i}) == {i}\n" for i in range(4))
    src = "import pytest\n\ndef test_a():\n" + body + "\ndef test_r():\n    with pytest.raises(E):\n        f()\n"
    assert ("many-assertions", "warn") in codes(src)
    assert ("many-assertions", "warn") not in codes(src, max_asserts=4)


def test_unittest_style_assert_calls_count():
    src = "class T:\n    def test_a(self):\n        self.assertEqual(1, f())\n    def test_b(self):\n        self.assertRaises(E, f)\n"
    assert codes(src) == []


def test_missing_failure_path_is_warned_only_when_tests_exist():
    assert ("no-failure-path", "warn") in codes("def test_a():\n    assert f() == 1\n")
    assert codes("x = 1\n") == []


def test_cli_exit_code_and_input_errors(tmp_path):
    (tmp_path / "test_x.py").write_text("def test_a():\n    f()\n", encoding="utf-8")
    assert lt.main([str(tmp_path)]) == 1
    (tmp_path / "test_x.py").write_text("import pytest\ndef test_a():\n    assert f()\ndef test_b():\n    pytest.fail('x')\n", encoding="utf-8")
    assert lt.main([str(tmp_path)]) == 0
    assert lt.main([str(tmp_path / "empty")]) == 2


def test_syntax_error_file_is_an_error(tmp_path):
    (tmp_path / "test_bad.py").write_text("def (:\n", encoding="utf-8")
    assert lt.main([str(tmp_path)]) == 1

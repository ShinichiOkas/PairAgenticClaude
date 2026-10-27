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


ic = load("分担境界の切り方", "import_coupling")


def tree(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def test_edges_between_groups_and_none_within(tmp_path):
    tree(tmp_path, {"ui/__init__.py": "", "ui/view.py": "from core import model\nfrom . import helper\n",
                    "ui/helper.py": "", "core/__init__.py": "", "core/model.py": "import ui.helper\n"})
    r = ic.analyze(tmp_path)
    assert r["groups"] == ["core", "ui"] and r["n"] == 2 and r["max_possible_links"] == 1
    assert {(e["from"], e["to"]) for e in r["edges"]} == {("ui", "core"), ("core", "ui")}


def test_cycle_detected(tmp_path):
    tree(tmp_path, {"a/m.py": "import b.m\n", "b/m.py": "import a.m\n"})
    assert ic.analyze(tmp_path)["cycles"] == [["a", "b"]]


def test_no_cycle_for_dag(tmp_path):
    tree(tmp_path, {"a/m.py": "import b.m\n", "b/m.py": "import c.m\n", "c/m.py": ""})
    r = ic.analyze(tmp_path)
    assert r["cycles"] == [] and r["cross_edges"] == 2


def test_external_imports_are_ignored(tmp_path):
    tree(tmp_path, {"a/m.py": "import os, json\nimport requests\n", "b/m.py": ""})
    assert ic.analyze(tmp_path)["cross_edges"] == 0


def test_depth_two_splits_subpackages(tmp_path):
    tree(tmp_path, {"p/x/m.py": "import p.y.m\n", "p/y/m.py": ""})
    assert ic.analyze(tmp_path, depth=1)["cross_edges"] == 0
    assert ic.analyze(tmp_path, depth=2)["cross_edges"] == 1


def test_cli_exit_codes(tmp_path, capsys):
    tree(tmp_path, {"a/m.py": "import b.m\n", "b/m.py": "import c.m\n", "c/m.py": ""})
    assert ic.main([str(tmp_path)]) == 0
    assert ic.main([str(tmp_path), "--max-cross", "1"]) == 1
    (tmp_path / "c" / "m.py").write_text("import a.m\n", encoding="utf-8")
    assert ic.main([str(tmp_path)]) == 1
    assert ic.main([str(tmp_path / "nodir")]) == 2


def test_syntax_error_is_input_error(tmp_path):
    tree(tmp_path, {"a/m.py": "def (:\n"})
    assert ic.main([str(tmp_path)]) == 2

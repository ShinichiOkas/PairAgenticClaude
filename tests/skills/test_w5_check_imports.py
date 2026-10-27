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


ci = load("保証範囲の切り出し", "check_imports")


def tree(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def test_stdlib_only_passes(tmp_path):
    tree(tmp_path, {"a.py": "import os, json\nfrom pathlib import Path\nimport a_helper\n", "a_helper.py": "import re\n"})
    r = ci.check_stdlib([tmp_path])
    assert r["violations"] == [] and r["imports_checked"] == 5


def test_third_party_import_is_a_violation_with_location(tmp_path):
    tree(tmp_path, {"a.py": "import os\nimport requests\n\ndef f():\n    from yaml import safe_load\n"})
    r = ci.check_stdlib([tmp_path])
    assert [(v["import"], v["line"]) for v in r["violations"]] == [("requests", 2), ("yaml", 5)]


def test_relative_imports_and_declared_local_packages_are_not_violations(tmp_path):
    tree(tmp_path, {"p/__init__.py": "from . import x\n", "p/x.py": "import mypkg.sub\n"})
    assert ci.check_stdlib([tmp_path]) ["violations"][0]["import"] == "mypkg.sub"
    assert ci.check_stdlib([tmp_path], ["mypkg"])["violations"] == []


RULES = {"layers": {"ui": ["ui/*"], "core": ["core/*"], "db": ["db/*"]}, "allow": {"ui": ["core"], "core": ["db"]}}


def test_allowed_layer_dependency_is_clean(tmp_path):
    tree(tmp_path, {"ui/v.py": "from core import m\n", "core/m.py": "import db.store\n", "db/store.py": ""})
    r = ci.check_layers(tmp_path, RULES)
    assert r["violations"] == [] and r["layer_crossing_imports"] == 2


def test_upward_dependency_is_a_violation(tmp_path):
    tree(tmp_path, {"ui/v.py": "", "core/m.py": "import ui.v\n", "db/store.py": ""})
    v = ci.check_layers(tmp_path, RULES)["violations"]
    assert [(x["from_layer"], x["to_layer"], x["file"]) for x in v] == [("core", "ui", "core/m.py")]


def test_skipping_a_layer_is_a_violation(tmp_path):
    tree(tmp_path, {"ui/v.py": "import db.store\n", "db/store.py": ""})
    assert len(ci.check_layers(tmp_path, RULES)["violations"]) == 1


def test_unassigned_files_are_reported_not_hidden(tmp_path):
    tree(tmp_path, {"misc/z.py": "import ui.v\n", "ui/v.py": ""})
    assert ci.check_layers(tmp_path, RULES)["unassigned_files"] == ["misc/z.py"]


def test_cli_exit_codes(tmp_path, capsys):
    tree(tmp_path, {"a.py": "import requests\n"})
    assert ci.main(["stdlib", str(tmp_path)]) == 1
    tree(tmp_path, {"a.py": "import os\n"})
    assert ci.main(["stdlib", str(tmp_path)]) == 0
    rules = tmp_path / "r.json"
    rules.write_text(json.dumps(RULES), encoding="utf-8")
    assert ci.main(["layers", str(tmp_path), "--rules", str(rules)]) == 0
    assert ci.main(["layers", str(tmp_path / "x"), "--rules", str(rules)]) == 2

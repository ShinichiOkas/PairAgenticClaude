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


ei = load("インタフェース設計", "extract_interface")

V1 = '''
def load(path, strict=False):
    """読む。

    Raises: ValueError 空のとき
    """
    if not path:
        raise ValueError("empty")
    return path


def _helper(x):
    return x


class Store:
    """入れ物"""

    def put(self, key, value):
        """置く"""
        return None

    def _internal(self):
        pass
'''


def by_name(items):
    return {i["name"]: i for i in items}


def test_extracts_public_surface_only_with_self_dropped():
    items = by_name(ei.extract(V1))
    assert set(items) == {"load", "Store", "Store.put"}
    assert [p["name"] for p in items["Store.put"]["params"]] == ["key", "value"]
    assert items["load"]["raises"] == ["ValueError"]
    assert items["load"]["params"][1]["required"] is False


def test_all_overrides_underscore_convention():
    src = "__all__ = ['_x']\ndef _x():\n    pass\ndef y():\n    pass\n"
    assert [i["name"] for i in ei.extract(src)] == ["_x"]


def codes(src):
    return {(i["code"], i["severity"]) for i in ei.check_items(ei.extract(src))}


def test_private_param_leak_and_mutable_default_are_errors():
    assert ("leak-private-param", "error") in codes('def f(_ctx):\n    """d"""\n')
    assert ("mutable-default", "error") in codes('def f(x=[]):\n    """d"""\n')


def test_undocumented_raise_is_error_and_documented_is_clean():
    assert ("undocumented-raise", "error") in codes('def f():\n    """d"""\n    raise KeyError("k")\n')
    assert codes('def f():\n    """d. KeyError を送出する"""\n    raise KeyError("k")\n') == set()


def test_private_type_in_annotation_is_warned():
    assert ("leak-private-type", "warn") in codes('def f(x: "_Impl"):\n    """d"""\n')
    assert ("leak-private-type", "warn") in codes('def f() -> _Impl:\n    """d"""\n')


def snap(src):
    return {"m.py": ei.extract(src)}


def kinds(old, new):
    return sorted((s, m) for s, _, m in ei.diff(snap(old), snap(new)))


def test_diff_identical_is_empty():
    assert ei.diff(snap(V1), snap(V1)) == []


def test_removed_function_and_new_required_param_are_breaking():
    new = V1.replace("def load(path, strict=False):", "def load(path, mode, strict=False):")
    ks = kinds(V1, new)
    assert any(s == "breaking" and "mode" in m and "必須" in m for s, m in ks)
    ks2 = kinds(V1, "def other():\n    pass\n")
    assert ("breaking", "削除された") in ks2 and ("compatible", "追加された") in ks2


def test_new_optional_param_is_compatible():
    new = V1.replace("def load(path, strict=False):", "def load(path, strict=False, verbose=False):")
    assert [s for s, _ in kinds(V1, new)] == ["compatible"]


def test_new_exception_is_breaking_and_param_reorder_is_breaking():
    new = V1.replace('raise ValueError("empty")', 'raise ValueError("empty")\n    raise OSError("x")')
    assert ("breaking", "送出する例外が増えた: OSError") in kinds(V1, new)
    reorder = V1.replace("def load(path, strict=False):", "def load(strict=False, path=None):")
    assert any(s == "breaking" for s, _ in kinds(V1, reorder))


def test_return_type_change_is_breaking():
    a = "def f() -> int:\n    return 1\n"
    b = "def f() -> str:\n    return 'a'\n"
    assert kinds(a, b)[0][0] == "breaking"


def test_cli_snapshot_and_diff_exit_codes(tmp_path, capsys):
    (tmp_path / "m.py").write_text(V1, encoding="utf-8")
    out = tmp_path / "s1.json"
    assert ei.main(["snapshot", str(tmp_path / "m.py"), "--out", str(out)]) == 0
    assert ei.main(["snapshot", str(tmp_path / "m.py"), "--out", str(out)]) == 2  # 上書きしない
    (tmp_path / "m.py").write_text("def load():\n    pass\n", encoding="utf-8")
    out2 = tmp_path / "s2.json"
    ei.main(["snapshot", str(tmp_path / "m.py"), "--out", str(out2)])
    assert ei.main(["diff", str(out), str(out2)]) == 1
    assert ei.main(["diff", str(out), str(out)]) == 0
    assert ei.main(["diff", str(out), str(tmp_path / "none.json")]) == 2


def test_check_cli_exit(tmp_path):
    (tmp_path / "m.py").write_text('def f(_x):\n    """d"""\n', encoding="utf-8")
    assert ei.main(["check", str(tmp_path / "m.py")]) == 1
    (tmp_path / "m.py").write_text('def f(x):\n    """d"""\n', encoding="utf-8")
    assert ei.main(["check", str(tmp_path / "m.py")]) == 0

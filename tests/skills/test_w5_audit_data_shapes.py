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


ds = load("データ構造設計", "audit_data_shapes")


def codes(src):
    return {(i["code"], i["severity"]) for i in ds.audit_source(src)}


def test_shared_mutable_default_is_error():
    assert ("shared-mutable-default", "error") in codes("class A:\n    xs: list = []\n")


def test_default_factory_is_fine():
    src = "from dataclasses import dataclass, field\n@dataclass\nclass A:\n    xs: list[int] = field(default_factory=list)\n"
    assert codes(src) == set()


def test_multi_optional_and_multi_bool_warn_on_records_only():
    rec = "@dataclass\nclass J:\n    a: Optional[int]\n    b: str | None\n    p: bool\n    q: bool\n"
    assert {("multi-optional", "warn"), ("multi-bool", "warn")} <= codes(rec)
    plain = "class J:\n    a: Optional[int]\n    b: Optional[int]\n"
    assert ("multi-optional", "warn") not in codes(plain)


def test_one_optional_is_not_flagged():
    assert codes("@dataclass\nclass J:\n    a: Optional[int]\n    b: int\n") == set()


def test_stringly_state_and_untyped_fields():
    c = codes("@dataclass\nclass J:\n    status: str\n    blob: Any\n    meta: dict\n")
    assert ("stringly-state", "warn") in c and ("untyped-field", "warn") in c


def test_enum_typed_state_is_clean():
    assert codes("@dataclass\nclass J:\n    status: Status\n") == set()


def test_class_without_annotated_fields_is_skipped():
    assert codes("class A:\n    def f(self):\n        pass\n") == set()


def test_infer_shape_optional_nullable_enum_and_mixed():
    recs = [{"id": 1, "kind": "a", "note": None}, {"id": 2, "kind": "b", "note": "x", "extra": 1},
            {"id": "3", "kind": "a"}, {"id": 4, "kind": "b"}]
    shape = ds.infer_shape(recs)
    f = {x["path"]: x for x in shape["fields"]}
    assert shape["records"] == 4
    assert f["id"]["mixed_types"] is True and f["id"]["optional"] is False
    assert f["kind"]["enum_like"] == ["a", "b"]
    assert f["note"]["optional"] is True and f["note"]["nullable"] is True
    assert f["extra"]["optional"] is True
    assert "mixed_types" not in f["note"]


def test_infer_shape_nested_paths():
    shape = ds.infer_shape([{"a": {"b": 1}, "l": [1, 2]}])
    assert {"a", "a.b", "l", "l[]"} == {x["path"] for x in shape["fields"]}


def test_shape_cli_reads_json_and_jsonl(tmp_path, capsys):
    (tmp_path / "a.jsonl").write_text('{"x": 1}\n{"x": 2}\n', encoding="utf-8")
    (tmp_path / "b.json").write_text('[{"y": true}]', encoding="utf-8")
    assert ds.main(["shape", str(tmp_path / "a.jsonl"), str(tmp_path / "b.json")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["records"] == 3
    assert {f["path"] for f in out["fields"]} == {"x", "y"}


def test_shape_cli_bad_input(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert ds.main(["shape", str(tmp_path / "bad.json")]) == 2


def test_classes_cli_exit_codes(tmp_path):
    (tmp_path / "m.py").write_text("class A:\n    xs: list = []\n", encoding="utf-8")
    assert ds.main(["classes", str(tmp_path)]) == 1
    (tmp_path / "m.py").write_text("class A:\n    n: int = 0\n", encoding="utf-8")
    assert ds.main(["classes", str(tmp_path)]) == 0

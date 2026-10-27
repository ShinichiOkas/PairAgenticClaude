#!/usr/bin/env python3
"""データ構造を 2 面から監査する: classes=Python のレコード型が不正な状態を表現できないか / shape=JSON・JSONL の実データの形（欄・型・任意・列挙らしさ）。

使い方:
  python audit_data_shapes.py classes src/                    # dataclass/NamedTuple/TypedDict/注釈付きクラスの監査
  python audit_data_shapes.py shape data/*.jsonl [--enum-max 6]   # 永続化されている形を実データから起こす
指摘（classes）: shared-mutable-default(error) / multi-optional(warn) / multi-bool(warn) / stringly-state(warn) / untyped-field(warn)
終了コード: 0 / 1=error あり / 2=入力不備
"""
import argparse
import ast
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

STATE_NAMES = {"status", "state", "kind", "type", "mode", "phase", "level"}


def _is_optional(ann):
    s = ast.unparse(ann)
    return s.startswith("Optional[") or "| None" in s or "None |" in s


def _is_record(cls):
    for d in cls.decorator_list:
        if "dataclass" in ast.unparse(d):
            return True
    return any(ast.unparse(b) in ("NamedTuple", "TypedDict") or ast.unparse(b).endswith("BaseModel") for b in cls.bases)


def audit_source(src, path="<src>"):
    out = []
    tree = ast.parse(src)

    def add(sev, code, line, cls, msg):
        out.append({"file": str(path), "line": line, "severity": sev, "code": code, "class": cls, "message": msg})

    for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        fields = [n for n in cls.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
        if not fields:
            continue
        record = _is_record(cls)
        for f in fields:
            name = f.target.id
            if f.value is not None and isinstance(f.value, (ast.List, ast.Dict, ast.Set)):
                add("error", "shared-mutable-default", f.lineno, cls.name,
                    f"{name} の既定値がリテラルの可変値（インスタンス間で共有される。default_factory を使う）")
            ann = ast.unparse(f.annotation)
            if ann in ("Any", "dict", "Dict", "list", "List", "object") or ann.startswith("Dict[str, Any]"):
                add("warn", "untyped-field", f.lineno, cls.name, f"{name}: {ann} は形を語らない（構造を型で書く）")
            if name in STATE_NAMES and ann == "str":
                add("warn", "stringly-state", f.lineno, cls.name, f"{name}: str は表現できない値を許す（Enum/Literal にする）")
        if record:
            opt = [f.target.id for f in fields if _is_optional(f.annotation)]
            if len(opt) >= 2:
                add("warn", "multi-optional", cls.lineno, cls.name,
                    f"Optional が {len(opt)} 個（{', '.join(opt)}）。None の組合せ 2^{len(opt)} のうち意味のある状態は？ 和型/別クラスに分けられないか")
            bools = [f.target.id for f in fields if ast.unparse(f.annotation) == "bool"]
            if len(bools) >= 2:
                add("warn", "multi-bool", cls.lineno, cls.name,
                    f"bool が {len(bools)} 個（{', '.join(bools)}）。組合せの一部は不正な状態ではないか")
    return sorted(out, key=lambda i: (i["file"], i["line"]))


def _tname(v):
    if v is None:
        return "null"
    return {bool: "bool", int: "int", float: "float", str: "str", list: "list", dict: "object"}.get(type(v), type(v).__name__)


def _walk(v, path, acc):
    if isinstance(v, dict):
        for k, x in v.items():
            p = f"{path}.{k}" if path else k
            acc[p]["types"][_tname(x)] += 1
            acc[p]["n"] += 1
            if isinstance(x, str):
                acc[p]["values"][x] += 1
            _walk(x, p, acc)
    elif isinstance(v, list):
        for x in v:
            acc[path + "[]"]["types"][_tname(x)] += 1
            acc[path + "[]"]["n"] += 1
            _walk(x, path + "[]", acc)


def infer_shape(records, enum_max=6):
    """records: dict のリスト。欄ごとに型・出現率・列挙らしさを返す（決定的な順序）。"""
    acc = defaultdict(lambda: {"types": Counter(), "n": 0, "values": Counter()})
    for r in records:
        _walk(r, "", acc)
    total = len(records)
    fields = []
    for p in sorted(acc):
        a = acc[p]
        top = "[]" not in p and "." not in p
        f = {"path": p, "types": dict(sorted(a["types"].items())), "count": a["n"],
             "optional": top and a["n"] < total, "nullable": "null" in a["types"]}
        if len(set(a["types"]) - {"null"}) > 1:
            f["mixed_types"] = True
        if a["values"] and len(a["values"]) <= enum_max and sum(a["values"].values()) >= len(a["values"]) * 2:
            f["enum_like"] = sorted(a["values"])
        fields.append(f)
    return {"records": total, "fields": fields}


def load_records(path):
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except ValueError:
        return [json.loads(l) for l in text.splitlines() if l.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("classes")
    c.add_argument("paths", nargs="+")
    s = sub.add_parser("shape")
    s.add_argument("paths", nargs="+")
    s.add_argument("--enum-max", type=int, default=6)
    a = ap.parse_args(argv)
    if a.cmd == "classes":
        files = []
        for p in map(Path, a.paths):
            files += sorted(x for x in p.rglob("*.py") if "__pycache__" not in x.parts) if p.is_dir() else ([p] if p.is_file() else [])
        if not files:
            print("対象の .py が無い", file=sys.stderr)
            return 2
        errs = 0
        for f in files:
            try:
                items = audit_source(f.read_text(encoding="utf-8"), f.as_posix())
            except SyntaxError as e:
                print(f"error syntax {f}: {e}")
                errs += 1
                continue
            for i in items:
                errs += i["severity"] == "error"
                print(f"{i['severity']:5} {i['code']:22} {i['file']}:{i['line']} {i['class']}: {i['message']}")
        print(f"error {errs} 件")
        return 1 if errs else 0
    recs = []
    for p in a.paths:
        try:
            recs += [r for r in load_records(p) if isinstance(r, dict)]
        except (OSError, ValueError) as e:
            print(f"読めない: {p}: {e}", file=sys.stderr)
            return 2
    if not recs:
        print("オブジェクトのレコードが無い", file=sys.stderr)
        return 2
    print(json.dumps(infer_shape(recs, a.enum_max), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main())

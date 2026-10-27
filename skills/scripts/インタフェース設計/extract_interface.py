#!/usr/bin/env python3
"""Python モジュールの公開インタフェース（名前・引数・戻り・送出する例外）を抜き出し、隠せていないものを指摘し、版どうしの契約差分を出す。

使い方:
  python extract_interface.py snapshot pkg/ --out iface.json    # 公開面を JSON に固定（--out 先が既存なら書かない）
  python extract_interface.py check pkg/mod.py                  # 漏れの指摘（_引数・可変既定値・文書化されない raise ほか）
  python extract_interface.py diff old.json new.json            # 契約の差分。破壊的変更があれば終了コード 1
公開 = 先頭が _ でない最上位の関数/クラス（__all__ があればそれ）。クラスは公開メソッドまで。
終了コード: 0 / 1=check の error または diff の破壊的変更 / 2=入力不備
"""
import argparse
import ast
import json
import re
import sys
from pathlib import Path


def _iter_py(paths):
    for p in map(Path, paths):
        if p.is_dir():
            yield from sorted(x for x in p.rglob("*.py") if "__pycache__" not in x.parts)
        elif p.is_file():
            yield p


def _args(fn):
    a = fn.args
    out = []
    pos = a.posonlyargs + a.args
    defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    for arg, d in zip(pos, defaults):
        out.append({"name": arg.arg, "kind": "pos", "required": d is None,
                    "annotation": ast.unparse(arg.annotation) if arg.annotation else None,
                    "default": ast.unparse(d) if d is not None else None})
    if a.vararg:
        out.append({"name": a.vararg.arg, "kind": "var", "required": False, "annotation": None, "default": None})
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        out.append({"name": arg.arg, "kind": "kwonly", "required": d is None,
                    "annotation": ast.unparse(arg.annotation) if arg.annotation else None,
                    "default": ast.unparse(d) if d is not None else None})
    if a.kwarg:
        out.append({"name": a.kwarg.arg, "kind": "kwvar", "required": False, "annotation": None, "default": None})
    return out


def _raises(fn):
    names = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Raise) and n.exc is not None:
            e = n.exc.func if isinstance(n.exc, ast.Call) else n.exc
            if isinstance(e, (ast.Name, ast.Attribute)):
                names.add(ast.unparse(e))
    return sorted(names)


def _func(fn, qual, owner_public=True):
    params = [p for p in _args(fn) if not (qual.count(".") >= 1 and p["name"] in ("self", "cls"))]
    return {"name": qual, "kind": "function", "params": params,
            "returns": ast.unparse(fn.returns) if fn.returns else None,
            "raises": _raises(fn), "doc": ast.get_docstring(fn) or ""}


def extract(src):
    tree = ast.parse(src)
    exported = None
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets):
            try:
                exported = set(ast.literal_eval(n.value))
            except ValueError:
                pass
    items = []
    for n in tree.body:
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        public = (n.name in exported) if exported is not None else not n.name.startswith("_")
        if not public:
            continue
        if isinstance(n, ast.ClassDef):
            items.append({"name": n.name, "kind": "class", "params": [], "returns": None, "raises": [],
                          "doc": ast.get_docstring(n) or ""})
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                        not m.name.startswith("_") or m.name == "__init__"):
                    items.append(_func(m, f"{n.name}.{m.name}"))
        else:
            items.append(_func(n, n.name))
    return items


def snapshot(paths):
    snap = {}
    for f in _iter_py(paths):
        items = extract(f.read_text(encoding="utf-8"))
        if items:
            snap[f.as_posix()] = items
    return snap


def _private_name(annotation):
    """注釈の文字列（引用符つきでも）に、先頭が _ の名前が含まれるか。"""
    return any(t.startswith("_") for t in re.findall(r"[A-Za-z_]\w*", annotation))


def check_items(items, file="<src>"):
    out = []

    def add(sev, code, name, msg):
        out.append({"file": file, "severity": sev, "code": code, "name": name, "message": msg})

    for it in items:
        if it["kind"] == "class" or it["kind"] == "function":
            if not it["doc"] and not it["name"].endswith("__init__"):
                add("warn", "no-docstring", it["name"], "呼ぶ側が知るべき契約の書き場所が無い")
        for p in it["params"]:
            if p["name"].startswith("_"):
                add("error", "leak-private-param", it["name"], f"引数 {p['name']} は内部の都合が漏れている")
            if p["default"] and p["default"].startswith(("[", "{", "set(", "list(", "dict(")):
                add("error", "mutable-default", it["name"], f"引数 {p['name']} の既定値 {p['default']} は共有される")
            if p["annotation"] and _private_name(p["annotation"]):
                add("warn", "leak-private-type", it["name"], f"引数 {p['name']} の型 {p['annotation']} に非公開の名前")
        if it["returns"] and _private_name(it["returns"]):
            add("warn", "leak-private-type", it["name"], f"戻りの型 {it['returns']} に非公開の名前")
        for r in it["raises"]:
            if r.split(".")[-1] not in it["doc"]:
                add("error", "undocumented-raise", it["name"], f"{r} を送出するが docstring に無い（エラーの契約）")
    return out


def diff(old, new):
    """公開面 old -> new。breaking / compatible の列を返す。"""
    res = []

    def flat(s):
        return {(f, i["name"]): i for f, items in s.items() for i in items}

    o, n = flat(old), flat(new)
    for k in sorted(o.keys() - n.keys()):
        res.append(("breaking", k, "削除された"))
    for k in sorted(n.keys() - o.keys()):
        res.append(("compatible", k, "追加された"))
    for k in sorted(o.keys() & n.keys()):
        a, b = o[k], n[k]
        op = {p["name"]: p for p in a["params"]}
        np_ = {p["name"]: p for p in b["params"]}
        for name in op.keys() - np_.keys():
            res.append(("breaking", k, f"引数 {name} が消えた/改名された"))
        for name in np_.keys() - op.keys():
            res.append(("breaking" if np_[name]["required"] else "compatible", k,
                        f"引数 {name} が増えた（{'必須' if np_[name]['required'] else '任意'}）"))
        for name in op.keys() & np_.keys():
            if op[name]["kind"] != np_[name]["kind"]:
                res.append(("breaking", k, f"引数 {name} の渡し方が変わった"))
            elif not op[name]["required"] and np_[name]["required"]:
                res.append(("breaking", k, f"引数 {name} が任意から必須になった"))
            elif op[name]["default"] != np_[name]["default"]:
                res.append(("compatible", k, f"引数 {name} の既定値が変わった（{op[name]['default']} -> {np_[name]['default']}）"))
        if [p["name"] for p in a["params"] if p["name"] in np_] != [p["name"] for p in b["params"] if p["name"] in op]:
            res.append(("breaking", k, "引数の順序が変わった"))
        if a["returns"] != b["returns"]:
            res.append(("breaking", k, f"戻りの型が変わった（{a['returns']} -> {b['returns']}）"))
        for r in sorted(set(b["raises"]) - set(a["raises"])):
            res.append(("breaking", k, f"送出する例外が増えた: {r}"))
        for r in sorted(set(a["raises"]) - set(b["raises"])):
            res.append(("compatible", k, f"送出する例外が減った: {r}"))
    return res


def _write_new(path, text):
    p = Path(path)
    if p.exists():
        print(f"出力先が既に在る（上書きしない）: {p}", file=sys.stderr)
        return False
    p.write_text(text, encoding="utf-8")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("paths", nargs="+")
    s.add_argument("--out")
    c = sub.add_parser("check")
    c.add_argument("paths", nargs="+")
    d = sub.add_parser("diff")
    d.add_argument("old")
    d.add_argument("new")
    a = ap.parse_args(argv)
    if a.cmd == "snapshot":
        snap = snapshot(a.paths)
        if not snap:
            print("公開インタフェースが見つからない", file=sys.stderr)
            return 2
        text = json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if a.out:
            return 0 if _write_new(a.out, text) else 2
        sys.stdout.write(text)
        return 0
    if a.cmd == "check":
        files = list(_iter_py(a.paths))
        if not files:
            print("対象の .py が無い", file=sys.stderr)
            return 2
        errs = 0
        for f in files:
            for i in check_items(extract(f.read_text(encoding="utf-8")), f.as_posix()):
                errs += i["severity"] == "error"
                print(f"{i['severity']:5} {i['code']:20} {i['file']} {i['name']}: {i['message']}")
        print(f"error {errs} 件")
        return 1 if errs else 0
    try:
        old = json.loads(Path(a.old).read_text(encoding="utf-8"))
        new = json.loads(Path(a.new).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"スナップショットを読めない: {e}", file=sys.stderr)
        return 2
    res = diff(old, new)
    for sev, (f, name), msg in res:
        print(f"{sev:10} {f} {name}: {msg}")
    br = sum(r[0] == "breaking" for r in res)
    print(f"破壊的 {br} 件 / 互換 {len(res) - br} 件")
    return 1 if br else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main())

#!/usr/bin/env python3
"""import を数えて「標準ライブラリのみ」と「層構造に違反していない」を機械で判定し、設計保証に貼れる件数つきの結果を出す。

使い方:
  python check_imports.py stdlib src/ --local mypkg           # 標準ライブラリ以外の import を列挙
  python check_imports.py layers src/ --rules layers.json    # 層の依存方向の違反を列挙
rules.json: {"layers": {"ui": ["ui/*"], "core": ["core/*"]}, "allow": {"ui": ["core"], "core": []}}
  パターンは対象ルートからの相対パス（fnmatch）。同じ層への依存は常に許す。allow に無い層への依存が違反。
判定できるものは機械に置く方が保証より強い。保証には残り（機械にも外形にも落ちないもの）だけを書く。
終了コード: 0=違反なし / 1=違反あり / 2=入力不備
"""
import argparse
import ast
import fnmatch
import json
import sys
from pathlib import Path


def iter_py(root):
    return sorted(x for x in root.rglob("*.py") if "__pycache__" not in x.parts)


def top_imports(path):
    """(行, モジュール名, 相対か, 'from m import x' の m.x 候補) のリスト。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [(n.lineno, a.name, False, []) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                out.append((n.lineno, "." * n.level + (n.module or ""), True, []))
            elif n.module:
                out.append((n.lineno, n.module, False, [f"{n.module}.{a.name}" for a in n.names]))
    return out


def local_names(roots, extra):
    names = set(extra)
    for r in roots:
        for f in r.iterdir() if r.is_dir() else []:
            if f.suffix == ".py":
                names.add(f.stem)
            elif f.is_dir() and (f / "__init__.py").exists():
                names.add(f.name)
    return names


def check_stdlib(roots, extra_local=()):
    std = set(sys.stdlib_module_names)
    local = local_names(roots, extra_local)
    viol, total = [], 0
    for r in roots:
        for f in ([r] if r.is_file() else iter_py(r)):
            for ln, name, rel, _subs in top_imports(f):
                if rel:
                    continue
                total += 1
                top = name.split(".")[0]
                if top not in std and top not in local:
                    viol.append({"file": f.as_posix(), "line": ln, "import": name})
    return {"imports_checked": total, "violations": viol}


def layer_of(rel, layers):
    for name, pats in layers.items():
        if any(fnmatch.fnmatch(rel, p) for p in pats):
            return name
    return None


def resolve_target(name, root):
    parts = name.split(".")
    while parts:
        base = root.joinpath(*parts)
        for cand in (base.with_suffix(".py"), base / "__init__.py"):
            if cand.is_file():
                return cand.relative_to(root).as_posix()
        parts.pop()
    return None


def check_layers(root, rules):
    layers, allow = rules["layers"], rules.get("allow", {})
    viol, total, unassigned = [], 0, []
    for f in iter_py(root):
        rel = f.relative_to(root).as_posix()
        src_layer = layer_of(rel, layers)
        if src_layer is None:
            unassigned.append(rel)
            continue
        for ln, name, is_rel, subs in top_imports(f):
            if is_rel:
                continue
            # `from m import x` は m.x（サブモジュール）が実在すればそちらを、無ければ m を対象にする
            tgts = [t for t in (resolve_target(s, root) for s in subs) if t] or [resolve_target(name, root)]
            for tgt in sorted({t for t in tgts if t}):
                tl = layer_of(tgt, layers)
                if tl is None or tl == src_layer:
                    continue
                total += 1
                if tl not in allow.get(src_layer, []):
                    viol.append({"file": rel, "line": ln, "import": name, "from_layer": src_layer, "to_layer": tl})
    return {"layer_crossing_imports": total, "violations": viol, "unassigned_files": unassigned}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stdlib")
    s.add_argument("paths", nargs="+")
    s.add_argument("--local", action="append", default=[], help="自前のパッケージ名（複数可）")
    l = sub.add_parser("layers")
    l.add_argument("root")
    l.add_argument("--rules", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "stdlib":
            roots = [Path(p) for p in a.paths]
            if not all(r.exists() for r in roots):
                print("パスが無い", file=sys.stderr)
                return 2
            res = check_stdlib(roots, a.local)
            print(json.dumps(res, ensure_ascii=False, indent=2))
            print(f"import {res['imports_checked']} 件のうち標準ライブラリ外 {len(res['violations'])} 件", file=sys.stderr)
        else:
            root = Path(a.root)
            rules = json.loads(Path(a.rules).read_text(encoding="utf-8"))
            if not root.is_dir() or "layers" not in rules:
                print("root か rules が不正", file=sys.stderr)
                return 2
            res = check_layers(root, rules)
            print(json.dumps(res, ensure_ascii=False, indent=2))
            print(f"層を跨ぐ import {res['layer_crossing_imports']} 件のうち違反 {len(res['violations'])} 件", file=sys.stderr)
    except (SyntaxError, OSError, ValueError) as e:
        print(f"入力不備: {e}", file=sys.stderr)
        return 2
    return 1 if res["violations"] else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

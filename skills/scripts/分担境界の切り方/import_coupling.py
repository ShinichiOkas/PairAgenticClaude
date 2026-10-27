#!/usr/bin/env python3
"""Python パッケージを括り（トップのディレクトリ）に分けて括り間の import 結合を数え、結合の上限 n(n-1)/2 や √n の目安・循環と並べて出す。

使い方:
  python import_coupling.py src/ [--depth 1] [--max-cross 12] [--json]
括り = --root からの先頭 --depth 階層のパス。括り間の依存（A が B を import）を辺として数える。
終了コード: 0 / 1=循環がある、または --max-cross を超える / 2=入力不備
"""
import argparse
import ast
import json
import math
import sys
from pathlib import Path


def module_index(root):
    idx = {}
    for f in sorted(root.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        rel = f.relative_to(root).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            idx[".".join(parts)] = f.relative_to(root).as_posix()
    return idx


def imports_of(path, modname, is_pkg):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    pkg = modname.split(".") if is_pkg else modname.split(".")[:-1]
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = pkg[:len(pkg) - (n.level - 1)] if n.level > 1 else pkg
                head = ".".join(base + ([n.module] if n.module else []))
            else:
                head = n.module or ""
            out.append(head)
            out += [f"{head}.{a.name}" if head else a.name for a in n.names]
    return out


def resolve(name, idx):
    parts = name.split(".")
    while parts:
        cand = ".".join(parts)
        if cand in idx:
            return idx[cand]
        parts.pop()
    return None


def group_name(rel, depth):
    parts = rel.split("/")
    return "/".join(parts[:depth]) if len(parts) > depth else "(root)"


def cycles(edges):
    """括り間の辺から強連結成分（サイズ>1）を返す。"""
    nodes = sorted({x for e in edges for x in e})
    adj = {n: sorted(b for a, b in edges if a == n) for n in nodes}
    index, low, st, on, res, c = {}, {}, [], set(), [], [0]

    def sc(v):
        index[v] = low[v] = c[0]
        c[0] += 1
        st.append(v)
        on.add(v)
        for w in adj[v]:
            if w not in index:
                sc(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = st.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                res.append(sorted(comp))

    for n in nodes:
        if n not in index:
            sc(n)
    return sorted(res)


def analyze(root, depth=1):
    idx = module_index(root)
    by_file = {v: k for k, v in idx.items()}
    edges = {}
    for rel, mod in sorted(by_file.items()):
        g1 = group_name(rel, depth)
        for name in imports_of(root / rel, mod, rel.endswith("__init__.py")):
            tgt = resolve(name, idx)
            if tgt:
                g2 = group_name(tgt, depth)
                if g1 != g2:
                    edges.setdefault((g1, g2), set()).add((rel, tgt))
    groups = sorted({group_name(r, depth) for r in by_file})
    n = len(groups)
    pairs = sorted(edges)
    return {"groups": groups, "n": n, "max_possible_links": n * (n - 1) // 2, "sqrt_n_hint": round(math.sqrt(n), 2),
            "cross_edges": len(pairs), "file_level_imports": sum(len(v) for v in edges.values()),
            "edges": [{"from": a, "to": b, "imports": len(edges[(a, b)])} for a, b in pairs],
            "cycles": cycles(pairs)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root")
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--max-cross", type=int, default=None, help="括り間の辺の上限")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if not root.is_dir():
        print("root がディレクトリでない", file=sys.stderr)
        return 2
    try:
        res = analyze(root, a.depth)
    except SyntaxError as e:
        print(f"構文エラー: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"括り {res['n']} 個（結合の最大 {res['max_possible_links']}、括りの数の目安 √n≒{res['sqrt_n_hint']}）")
        for e in res["edges"]:
            print(f"  {e['from']} -> {e['to']}  ({e['imports']} import)")
        print(f"括り間の依存 {res['cross_edges']} 本 / 循環 {len(res['cycles'])} 組 {res['cycles'] or ''}")
    bad = bool(res["cycles"]) or (a.max_cross is not None and res["cross_edges"] > a.max_cross)
    return 1 if bad else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

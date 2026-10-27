#!/usr/bin/env python3
"""Python ソースに 1 箇所ずつ小さな変異（比較・演算・真偽・定数・戻り値）を入れ、テストが落ちるか（殺せるか）を測る。

使い方:
  python mutate_check.py --src pkg/mod.py --root . --test-cmd "pytest -q tests/test_mod.py"          # 下見: 変異の一覧だけ
  python mutate_check.py --src pkg/mod.py --root . --test-cmd "pytest -q tests/test_mod.py" --run    # 実行: 生き残りを報告
元のファイルは触らない（--root を一時ディレクトリへ複写して、そこで変異させる）。先に無変異でテストが通ることを確かめる。
終了コード: 0=生き残りが --max-survivors 以下 / 1=超過 / 2=入力不備・無変異でテストが落ちる
"""
import argparse
import ast
import copy
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CMP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
       ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn, ast.NotIn: ast.In}
BIN = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add, ast.FloorDiv: ast.Mult, ast.Mod: ast.Mult}


def _docstring_ids(tree):
    ids = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            f = n.body[0]
            if isinstance(f, ast.Expr) and isinstance(f.value, ast.Constant) and isinstance(f.value.value, str):
                ids.add(id(f.value))
    return ids


class Mutator(ast.NodeTransformer):
    """target=None なら変異点を数えるだけ。target=k なら k 番目の変異点だけを変える。"""

    def __init__(self, target=None, skip=()):
        self.target, self.count, self.skip, self.desc = target, 0, set(skip), None

    def _hit(self, node, desc):
        k = self.count
        self.count += 1
        if self.target == k:
            self.desc = (getattr(node, "lineno", 0), desc)
            return True
        if self.target is None:
            self.sites.append((k, getattr(node, "lineno", 0), desc))
        return False

    sites = None

    def visit_Compare(self, node):
        self.generic_visit(node)
        for i, op in enumerate(node.ops):
            new = CMP.get(type(op))
            if new and self._hit(node, f"{type(op).__name__} -> {new.__name__}"):
                node.ops[i] = new()
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        new = BIN.get(type(node.op))
        if new and self._hit(node, f"{type(node.op).__name__} -> {new.__name__}"):
            node.op = new()
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        new = ast.Or if isinstance(node.op, ast.And) else ast.And
        if self._hit(node, f"{type(node.op).__name__} -> {new.__name__}"):
            node.op = new()
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._hit(node, "not 除去"):
            return node.operand
        return node

    def visit_Constant(self, node):
        if id(node) in self.skip:
            return node
        v = node.value
        if isinstance(v, bool):
            if self._hit(node, f"{v} -> {not v}"):
                return ast.copy_location(ast.Constant(value=not v), node)
        elif isinstance(v, int):
            if self._hit(node, f"{v} -> {v + 1}"):
                return ast.copy_location(ast.Constant(value=v + 1), node)
        return node

    def visit_Return(self, node):
        self.generic_visit(node)
        if node.value is not None and not (isinstance(node.value, ast.Constant) and node.value.value is None):
            if self._hit(node, "return 値 -> None"):
                node.value = ast.Constant(value=None)
        return node


def enumerate_mutants(src):
    tree = ast.parse(src)
    m = Mutator(None, _docstring_ids(tree))
    m.sites = []
    m.visit(tree)
    return m.sites


def apply_mutant(src, k):
    tree = ast.parse(src)
    m = Mutator(k, _docstring_ids(tree))
    m.sites = []
    out = m.visit(tree)
    ast.fix_missing_locations(out)
    return ast.unparse(out), m.desc


def build_cmd(test_cmd):
    parts = shlex.split(test_cmd, posix=(sys.platform != "win32"))
    if parts and parts[0] == "pytest":
        return [sys.executable, "-m", "pytest"] + parts[1:]
    if parts and parts[0] in ("python", "python3"):
        return [sys.executable] + parts[1:]
    return parts


def run_tests(cmd, cwd, timeout):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False  # 無限ループに化けた変異も「検出された」と数える


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True, help="変異させるファイル（--root からの相対）")
    ap.add_argument("--root", default=".", help="複写して試すプロジェクト根")
    ap.add_argument("--test-cmd", required=True)
    ap.add_argument("--run", action="store_true", help="実際に変異を入れてテストを走らせる（既定は一覧のみ）")
    ap.add_argument("--lines", default=None, help="対象行範囲 例 10-40")
    ap.add_argument("--limit", type=int, default=0, help="試す変異の上限（0=全部）")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--max-survivors", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    srcp = root / a.src
    if not srcp.is_file():
        print(f"対象が無い: {srcp}", file=sys.stderr)
        return 2
    src = srcp.read_text(encoding="utf-8")
    sites = enumerate_mutants(src)
    if a.lines:
        lo, _, hi = a.lines.partition("-")
        sites = [s for s in sites if int(lo) <= s[1] <= int(hi or lo)]
    if a.limit:
        sites = sites[:a.limit]
    src_lines = src.splitlines()
    rows = [{"id": k, "line": ln, "mutation": d, "text": src_lines[ln - 1].strip() if 0 < ln <= len(src_lines) else ""}
            for k, ln, d in sites]
    if not a.run:
        if a.json:
            print(json.dumps({"dry_run": True, "mutants": rows}, ensure_ascii=False, indent=2))
        else:
            for r in rows:
                print(f"#{r['id']:<4} L{r['line']:<5} {r['mutation']:<22} | {r['text']}")
            print(f"変異 {len(rows)} 件（下見。--run で実行）")
        return 0
    cmd = build_cmd(a.test_cmd)
    survivors, killed = [], 0
    with tempfile.TemporaryDirectory() as td:
        work = Path(td) / "w"
        shutil.copytree(root, work, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "node_modules"))
        target = work / a.src
        if not run_tests(cmd, work, a.timeout):
            print("無変異でテストが通らない。変異試験の前提が崩れている（計器の較正）", file=sys.stderr)
            return 2
        for r in rows:
            new_src, _ = apply_mutant(src, r["id"])
            target.write_text(new_src, encoding="utf-8")
            if run_tests(cmd, work, a.timeout):
                survivors.append(r)
            else:
                killed += 1
        target.write_text(src, encoding="utf-8")
    total = len(rows)
    res = {"total": total, "killed": killed, "survived": len(survivors),
           "score": round(killed / total, 3) if total else None, "survivors": survivors}
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for s in survivors:
            print(f"生存 #{s['id']} L{s['line']} {s['mutation']} | {s['text']}")
        print(f"変異 {total} 件 / 検出 {killed} / 生存 {len(survivors)}")
    return 1 if len(survivors) > a.max_survivors else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

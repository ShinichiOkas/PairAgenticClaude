#!/usr/bin/env python3
"""計器のソースが測定対象の内部実装（モジュール・ファイル・パッチ）に依存していないかを静的に洗い出す。

内部名は --internal-dir（対象の実装ディレクトリ）の .py 名と、--internal-name の明示から集める。
検出: (1) 内部モジュールの import  (2) 内部ディレクトリ配下のパス参照  (3) 実装を書き換える操作
      (monkeypatch / mock.patch / setattr(...) / sed -i 等)  (4) 対象側へ sys.path を足す操作
使い方: scan_internal_deps.py INSTRUMENT_DIR_OR_FILE --internal-dir src --internal-name mylib
終了コード: 検出があれば 1。読むだけ。
"""
import argparse
import ast
import re
import sys
from pathlib import Path

PATCH_PAT = re.compile(r"monkeypatch|mock\.patch|\bpatch\(|setattr\(|sed\s+-i|importlib\.reload")


def internal_names(internal_dir, extra):
    names = set(extra)
    if internal_dir:
        for p in Path(internal_dir).rglob("*.py"):
            names.add(p.stem if p.name != "__init__.py" else p.parent.name)
    names.discard("__init__")
    names.discard("")
    return names


def scan_file(path, names, internal_dir):
    findings = []
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError as e:
            return [(path, e.lineno or 0, "解析不能", str(e))]
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                if m.split(".")[0] in names or any(part in names for part in m.split(".")):
                    findings.append((path, node.lineno, "内部モジュールの import", m))
    idir = Path(internal_dir).name if internal_dir else None
    for n, line in enumerate(text.splitlines(), start=1):
        if PATCH_PAT.search(line):
            findings.append((path, n, "実装の書き換え・差し替え", line.strip()))
        if idir and re.search(r"(^|[\\/'\" ])" + re.escape(idir) + r"[\\/]", line) and not line.lstrip().startswith("#"):
            findings.append((path, n, "内部ディレクトリのパス参照", line.strip()))
        if re.search(r"sys\.path\.(insert|append)", line) and idir and idir in line:
            findings.append((path, n, "対象側への sys.path 追加", line.strip()))
    return findings


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("instrument")
    ap.add_argument("--internal-dir")
    ap.add_argument("--internal-name", action="append", default=[])
    a = ap.parse_args(argv)
    names = internal_names(a.internal_dir, a.internal_name)
    root = Path(a.instrument)
    files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in (".py", ".sh", ".bat", ".ps1", ".js"))
    all_f = []
    for f in files:
        all_f += scan_file(f, names, a.internal_dir)
    for p, n, kind, detail in all_f:
        print(f"[内部依存] {p}:{n} {kind}: {detail}")
    print(f"走査 {len(files)} ファイル / 内部名 {len(names)} 個 / 検出 {len(all_f)} 件")
    return 1 if all_f else 0


if __name__ == "__main__":
    sys.exit(main())

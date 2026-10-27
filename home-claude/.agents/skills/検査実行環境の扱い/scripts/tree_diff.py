#!/usr/bin/env python
"""ディレクトリの内容（相対パス＋SHA-256）を撮って、実行の前後で何が増え・変わり・消えたかを差分で示す。

    python tree_diff.py snapshot DIR [-o before.json]        # 撮る（-o を省くと標準出力。既存ファイルは上書きしない）
    python tree_diff.py diff before.json DIR                 # 撮った時点と今の DIR の差分
    python tree_diff.py diff before.json after.json          # 撮った 2 つの比較

「何も書いていない」と報告する前に実際に差分を見るための道具。__pycache__ / .pytest_cache / *.pyc / *.log / 一時ファイルは
見落とされやすいので [実行の副産物] の印を付けて示す。除外はしない（復元もしない）。
終了コード: diff は 差分なし = 0 ／ 差分あり = 1 ／ 入力不正 = 2
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ARTIFACT = re.compile(r"(^|/)(__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|\.hypothesis|\.coverage)(/|$)|\.pyc$|\.log$|\.tmp$|~$")


def snapshot(root: str) -> dict[str, str]:
    if not os.path.isdir(root):
        raise NotADirectoryError(root)
    out: dict[str, str] = {}
    for dp, dns, fns in os.walk(root):
        dns.sort()
        if not dns and not fns and dp != root:
            out[os.path.relpath(dp, root).replace(os.sep, "/") + "/"] = "<dir>"
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            if os.path.islink(p):
                out[rel] = "<symlink:" + os.readlink(p) + ">"
                continue
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            out[rel] = h.hexdigest()
    return out


def compare(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    added = sorted(k for k in after if k not in before)
    removed = sorted(k for k in before if k not in after)
    changed = sorted(k for k in after if k in before and before[k] != after[k])
    return {"added": added, "changed": changed, "removed": removed}


def render(d: dict[str, list[str]]) -> str:
    lines = []
    for key, title in (("added", "追加"), ("changed", "変更"), ("removed", "削除")):
        lines.append(f"{title}: {len(d[key])} 件")
        for p in d[key]:
            lines.append(f"  {p}" + ("  [実行の副産物]" if ARTIFACT.search(p) else ""))
    return "\n".join(lines)


def load_side(arg: str) -> dict[str, str]:
    if os.path.isdir(arg):
        return snapshot(arg)
    with open(arg, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="実行前後のディレクトリ差分（読むだけ。-o を指定したときだけ書く）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("dir")
    s.add_argument("-o", "--out")
    d = sub.add_parser("diff")
    d.add_argument("before")
    d.add_argument("after")
    d.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "snapshot":
            snap = snapshot(a.dir)
            text = json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True)
            if a.out:
                if os.path.exists(a.out):
                    print(f"エラー: {a.out} は既にある（上書きしない）", file=sys.stderr)
                    return 2
                with open(a.out, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text + "\n")
                print(f"撮った: {len(snap)} 件 -> {a.out}")
            else:
                print(text)
            return 0
        diff = compare(load_side(a.before), load_side(a.after))
    except (OSError, ValueError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    print(json.dumps(diff, ensure_ascii=False, indent=2) if a.json else render(diff))
    return 1 if any(diff.values()) else 0


if __name__ == "__main__":
    sys.exit(main())

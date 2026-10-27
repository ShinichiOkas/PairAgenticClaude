#!/usr/bin/env python3
"""スライスサイズ（XS/S/M/L）の編成表を引き、昇格の判断点から推奨サイズを出し、合意ドキュメントの「スライス」行へ変更を追記する。

使い方:
  python slice_ops.py roster --size M                     # そのサイズで走らせる役の編成
  python slice_ops.py suggest --current S --git-range main..HEAD --rejections 1
  python slice_ops.py suggest --current S --premise-collapse --files 5     # 判断点 -> 推奨サイズ
  python slice_ops.py record agreements/x.md --to M --reason "前提崩壊" --apply   # 「S → M（日付・理由）」を追記

判断点（スキル本文 §2）: 前提崩壊／探針の制約／差し戻し／範囲外の指摘／3 ファイル超 or 新モジュール。外部依存・基盤が動くなら L。
サイズは上げるだけ（走り終えた役は破棄しない）。「スライス:」行は上書きせず追記する。
"""
from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

SIZES = ["XS", "S", "M", "L"]
ROSTER = {
    "XS": ["受入検査実施者", "（非回帰）"],
    "S": ["構築者", "非回帰", "受入検査実施者", "同期担当"],
    "M": ["意図取得", "仕様", "受入検査設計", "構築", "非回帰", "受入検査", "報告", "同期"],
    "L": ["意図取得", "探針（複数）", "アーキテクチャ", "仕様", "受入検査設計", "構築", "詳細設計",
          "非回帰", "受入検査", "配布追従検査", "報告", "同期"],
}
NOTES = {
    "XS": "親が実装し、検証だけ別コンテキスト",
    "S": "バグ票が仕様。単一機能修正",
    "M": "合意ドキュメントを書く標準的な機能スプリント",
    "L": "アーキテクチャ・外部依存・基盤が動く大規模スプリント",
}


def git_changes(rng: str, cwd: str) -> tuple[int, int, int]:
    """(変更ファイル数, 追加ファイル数, 新しいディレクトリ配下の追加数)。"""
    r = subprocess.run(["git", "-C", cwd, "diff", "--name-status", rng],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    changed = added = 0
    for ln in r.stdout.splitlines():
        parts = ln.split("\t")
        if len(parts) < 2:
            continue
        changed += 1
        if parts[0].startswith("A"):
            added += 1
    return changed, added, added


def suggest(current: str, *, files: int, new_module: bool, premise: bool, probe: bool,
            rejections: int, out_of_scope: bool, external: bool, foundation: bool) -> tuple[str, list[str]]:
    reasons = []
    if premise:
        reasons.append("前提崩壊が発覚した")
    if probe:
        reasons.append("探針で技術的制約が見つかった")
    if rejections > 0:
        reasons.append(f"差し戻しが {rejections} 回発生した")
    if out_of_scope:
        reasons.append("いずれかの役から範囲外が上がった")
    if files > 3:
        reasons.append(f"変更対象が {files} ファイル（3 を超える）")
    if new_module:
        reasons.append("新モジュールの作成を伴う")
    idx = SIZES.index(current)
    target = idx
    if reasons:
        target = min(idx + 1, len(SIZES) - 1)
    if external or foundation:
        reasons.append("外部依存／基盤・保存先が動く -> L")
        target = len(SIZES) - 1
    return SIZES[target], reasons


def cmd_roster(a) -> int:
    print(f"{a.size}: {NOTES[a.size]}")
    print("編成: " + " -> ".join(ROSTER[a.size]))
    return 0


def cmd_suggest(a) -> int:
    files, new_module = a.files, a.new_module
    if a.git_range:
        ch, added, _ = git_changes(a.git_range, a.project)
        files = max(files, ch)
        new_module = new_module or added > 0 and a.new_module_if_added
    size, reasons = suggest(a.current, files=files, new_module=new_module, premise=a.premise_collapse,
                            probe=a.probe_constraint, rejections=a.rejections, out_of_scope=a.out_of_scope,
                            external=a.external_dependency, foundation=a.foundation)
    if size == a.current:
        print(f"推奨: {size}（据え置き。サイズを上げる判断点なし）")
    else:
        print(f"推奨: {a.current} -> {size}")
        for r in reasons:
            print(f"  - {r}")
        print("おまかせ指定なら自律的に引き上げて事後報告。通常は 1 行で師匠に知らせ、待たずに進める。")
    return 0


def cmd_record(a) -> int:
    path = Path(a.file)
    t = path.read_text(encoding="utf-8")
    date = a.date or datetime.date.today().isoformat()
    m = re.search(r"^(スライス[:：]\s*)(.*)$", t, re.M)
    if m:
        cur = re.match(r"\s*(XS|S|M|L)\b", m.group(2))
        # 現在の最終サイズ（「A → B」の末尾）より下げない
        sizes = re.findall(r"\b(XS|S|M|L)\b", m.group(2))
        last = sizes[-1] if sizes else None
        if last and SIZES.index(a.to) < SIZES.index(last):
            print(f"ERROR: サイズを下げる記録はしない（現在 {last} -> {a.to}）。走り終えた役は破棄しない", file=sys.stderr)
            return 2
        if last == a.to:
            print(f"変更なし: すでに {a.to}")
            return 0
        frm = last or (cur.group(1) if cur else "?")
        line = f"{m.group(0).rstrip()} / {frm} → {a.to}（{date}・{a.reason}）"
        new = t[:m.start()] + line + t[m.end():]
    else:
        line = f"スライス: {a.to}（{date}・{a.reason}）"
        # 先頭の見出し行の直後に 1 行足す。見出しが無ければ本文の先頭
        hm = re.search(r"^# .+$", t, re.M)
        pos = hm.end() if hm else 0
        new = t[:pos] + f"\n\n{line}" + t[pos:]
    if not a.apply:
        print(f"[下見] {line}")
        return 0
    path.write_text(new, encoding="utf-8", newline="\n")
    print(f"追記した: {path}: {line}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("roster")
    r.add_argument("--size", required=True, choices=SIZES)
    s = sub.add_parser("suggest")
    s.add_argument("--current", required=True, choices=SIZES)
    s.add_argument("--git-range", default="", help="例 main..HEAD（変更ファイル数を数える）")
    s.add_argument("--project", default=".")
    s.add_argument("--files", type=int, default=0)
    s.add_argument("--new-module", action="store_true")
    s.add_argument("--new-module-if-added", action="store_true", help="git-range に追加ファイルがあれば新モジュール扱い")
    s.add_argument("--premise-collapse", action="store_true")
    s.add_argument("--probe-constraint", action="store_true")
    s.add_argument("--rejections", type=int, default=0)
    s.add_argument("--out-of-scope", action="store_true")
    s.add_argument("--external-dependency", action="store_true")
    s.add_argument("--foundation", action="store_true")
    rc = sub.add_parser("record")
    rc.add_argument("file")
    rc.add_argument("--to", required=True, choices=SIZES)
    rc.add_argument("--reason", required=True)
    rc.add_argument("--date", default="")
    rc.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    return {"roster": cmd_roster, "suggest": cmd_suggest, "record": cmd_record}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""復唱に返ってきた訂正を、相手の原文のまま追記式の記録に残す（--out を指定したときだけ書く。無ければ下見）。

    python correction_log.py --restated "つまりXですか" --correction "いや、Yだ" --date 2026-10-27 --out corrections.md

訂正こそが入力に無かった情報なので、原文を一字も変えずに残す。番号は既存の記録の件数から決まる（決定的）。
既存の記録は書き換えない（末尾に足すだけ）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def next_number(existing: str) -> int:
    nums = [int(m) for m in re.findall(r"^## 訂正 (\d+)", existing, flags=re.M)]
    return (max(nums) if nums else 0) + 1


def render(num: int, restated: str, correction: str, date: str, original: str) -> str:
    lines = [f"## 訂正 {num}", ""]
    if date:
        lines.append(f"- 日付: {date}")
    if original:
        lines.append("- 相手の原文（復唱の元）:")
        lines += [f"  > {l}" for l in original.splitlines()]
    lines.append("- こちらの復唱:")
    lines += [f"  > {l}" for l in restated.splitlines()]
    lines.append("- 返ってきた訂正（原文のまま）:")
    lines += [f"  > {l}" for l in correction.splitlines()]
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--restated", required=True, help="こちらの復唱")
    ap.add_argument("--correction", required=True, help="返ってきた訂正（原文のまま）")
    ap.add_argument("--original", default="", help="復唱の元になった相手の原文（任意）")
    ap.add_argument("--date", default="", help="日付（任意。指定しなければ書かない＝決定的）")
    ap.add_argument("--out", type=Path, help="追記先。指定しなければ下見（標準出力のみ）")
    a = ap.parse_args(argv)
    if not a.correction.strip():
        print("エラー: 訂正が空", file=sys.stderr)
        return 2
    existing = ""
    if a.out and a.out.exists():
        existing = a.out.read_text(encoding="utf-8")
    entry = render(next_number(existing), a.restated, a.correction, a.date, a.original)
    if not a.out:
        print(entry, end="")
        print("（下見。書くには --out を指定）")
        return 0
    head = "" if existing else "# 復唱への訂正の記録\n\n"
    sep = "" if (not existing or existing.endswith("\n\n")) else ("\n" if existing.endswith("\n") else "\n\n")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open("a", encoding="utf-8", newline="\n") as f:
        f.write(head + sep + entry)
    print(f"追記した: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

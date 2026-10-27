#!/usr/bin/env python3
"""測定台帳（CSV）を測定値・推定値・仮置き値に分けて検査し、推定が測定欄に紛れていないかを洗い出す。

入力 CSV の列: item,kind,value,instrument,error,note
  kind は measured / estimated / assumed のいずれか。
検査: kind 不正／measured なのに値が空・計器なし・誤差なし／「だいたい・約・~・程度」等の語が measured にある／
      measured でない行が値を持つのは正常、measured の空欄は埋めずに残す（空を埋めない）。
使い方: ledger_check.py LEDGER.csv [--split]   （--split で種別ごとの表を出力）
終了コード: 指摘があれば 1。読むだけ。
"""
import argparse
import csv
import re
import sys

KINDS = ("measured", "estimated", "assumed")
HEDGE = re.compile(r"だいたい|大体|約|おおよそ|程度|くらい|ぐらい|~|〜|推定|想定|概算|about|approx|roughly", re.I)


def check(rows):
    issues = []
    for i, r in enumerate(rows, start=2):
        item = (r.get("item") or "").strip() or "(名前なし)"
        kind = (r.get("kind") or "").strip()
        value = (r.get("value") or "").strip()
        if kind not in KINDS:
            issues.append((i, "kind不正", f"{item}: kind={kind!r}（{'/'.join(KINDS)}）"))
            continue
        if kind != "measured":
            continue
        if not value:
            continue  # 空欄は正しい。埋めない
        if HEDGE.search(value) or HEDGE.search(r.get("note") or ""):
            issues.append((i, "測定欄に推定の語", f"{item}: 「だいたい」系の語がある。推定なら kind=estimated へ"))
        if not (r.get("instrument") or "").strip():
            issues.append((i, "計器なし", f"{item}: measured なのに instrument が空"))
        if not (r.get("error") or "").strip():
            issues.append((i, "誤差なし", f"{item}: measured なのに error（計器の誤差）が空"))
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("file")
    ap.add_argument("--split", action="store_true")
    a = ap.parse_args(argv)
    with open(a.file, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if a.split:
        for k in KINDS:
            sub = [r for r in rows if (r.get("kind") or "").strip() == k]
            print(f"## {k} ({len(sub)})")
            for r in sub:
                print(f"- {r.get('item')}: {r.get('value') or '(空)'}")
    issues = check(rows)
    for row, kind, detail in issues:
        print(f"[指摘] 行{row} {kind}: {detail}")
    print(f"指摘 {len(issues)} 件")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())

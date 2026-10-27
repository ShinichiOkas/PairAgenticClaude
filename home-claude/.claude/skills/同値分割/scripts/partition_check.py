#!/usr/bin/env python
"""同値分割の表（類・区間・有効/無効・根拠）を検め、類が入力空間を覆っているか（隙間・重なり）と各類の代表値を出す。

    python partition_check.py partitions.txt --domain "[0,200]"

partitions.txt は 1 行 1 類、'|' 区切り（'#' 始まりは注釈）:
    名前 | 区間 | 有効 または 無効 | 根拠（なぜ同じ結果になるはずか。仕様の側の言葉で）
区間は [a,b] (a,b) [a,b) (a,b] a..b >=a <b など（開閉を明示。片側を空にして無限）。
検査: [隙間] 類の和が --domain を覆っていない ／ [重なり] 2 つの類が同じ値を持つ ／
      [根拠なし] 根拠が空（書けない分割は分割ではない） ／ [実装参照の疑い] 根拠が実装を見た語を含む ／
      [有効類なし]/[無効類なし]。代表値は各類の中央付近の 1 点。--step で刻みを変える。
終了コード: 0 = 問題なし ／ 1 = 問題あり ／ 2 = 入力が読めない
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

IMPL_WORDS = ("実装", "ソース", "コード", "if 文", "if文", "関数", "メソッド", "クラス", "分岐", "ロジック")
NEG = Decimal("-Infinity")
POS = Decimal("Infinity")


class SpecError(ValueError):
    pass


def num(text: str) -> Decimal:
    try:
        return Decimal(text.strip())
    except InvalidOperation:
        raise SpecError(f"数値として読めない: {text!r}")


def parse_interval(text: str):
    t = text.strip().replace("　", "").replace("，", ",").replace("、", ",")
    m = re.fullmatch(r"([\[\(])\s*([^,]*?)\s*,\s*([^,\]\)]*?)\s*([\]\)])", t)
    if m:
        lo = num(m.group(2)) if m.group(2) else None
        hi = num(m.group(3)) if m.group(3) else None
        return lo, m.group(1) == "[", hi, m.group(4) == "]"
    m = re.fullmatch(r"(-?[\d.]+)\s*(?:\.\.|〜|~|-)\s*(-?[\d.]+)", t)
    if m:
        return num(m.group(1)), True, num(m.group(2)), True
    m = re.fullmatch(r"(>=|≧|>|<=|≦|<)\s*(-?[\d.]+)", t)
    if m:
        op, v = m.group(1), num(m.group(2))
        return {">=": (v, True, None, False), "≧": (v, True, None, False), ">": (v, False, None, False),
                "<=": (None, False, v, True), "≦": (None, False, v, True), "<": (None, False, v, False)}[op]
    raise SpecError(f"区間の書き方を読めない: {text!r}")


def to_closed(iv, step: Decimal):
    """刻み上の閉区間 (lo, hi) に直す。None は無限。空区間なら None を返す。"""
    lo, lc, hi, hc = iv
    lo = NEG if lo is None else (lo if lc else lo + step)
    hi = POS if hi is None else (hi if hc else hi - step)
    if lo > hi:
        return "empty"
    return lo, hi


def fmt(x) -> str:
    if x == POS:
        return "∞"
    if x == NEG:
        return "-∞"
    s = format(x, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def representative(lo, hi, step: Decimal) -> Decimal:
    if lo == NEG and hi == POS:
        return Decimal(0)
    if lo == NEG:
        return hi
    if hi == POS:
        return lo
    n = int((hi - lo) / step) // 2
    return lo + step * n


def load(path: str):
    classes = []
    with open(path, encoding="utf-8") as f:
        for ln, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            cells = [c.strip() for c in line.split("|")]
            if len(cells) < 3:
                raise SpecError(f"{ln} 行目: 名前 | 区間 | 有効/無効 [| 根拠] の形で書くこと")
            name, iv, kind = cells[0], cells[1], cells[2]
            if kind not in ("有効", "無効"):
                raise SpecError(f"{ln} 行目: 3 列目は 有効 か 無効: {kind!r}")
            classes.append({"name": name, "text": iv, "iv": parse_interval(iv), "kind": kind,
                            "reason": cells[3] if len(cells) > 3 else "", "line": ln})
    if not classes:
        raise SpecError("類が 1 つも無い")
    return classes


def check(classes, domain, step: Decimal):
    problems: list[str] = []
    closed = []
    for c in classes:
        cl = to_closed(c["iv"], step)
        if cl == "empty":
            problems.append(f"[空の類] {c['name']}: 区間 {c['text']} に値が無い（刻み {fmt(step)}）")
            continue
        closed.append((c, cl[0], cl[1]))
        if not c["reason"]:
            problems.append(f"[根拠なし] {c['name']}: 「同じ結果になるはず」の根拠が空")
        elif any(w in c["reason"] for w in IMPL_WORDS):
            problems.append(f"[実装参照の疑い] {c['name']}: 根拠に実装側の語がある（{c['reason']}）。分割は仕様だけから導く")
    if not any(c["kind"] == "有効" for c in classes):
        problems.append("[有効類なし] 有効な類が 1 つも無い")
    if not any(c["kind"] == "無効" for c in classes):
        problems.append("[無効類なし] 無効な類が 1 つも無い")

    ordered = sorted(closed, key=lambda t: t[1])
    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            (a, alo, ahi), (b, blo, bhi) = ordered[i], ordered[j]
            lo, hi = max(alo, blo), min(ahi, bhi)
            if lo <= hi:
                problems.append(f"[重なり] {a['name']} と {b['name']}: {fmt(lo)}..{fmt(hi)} が両方に入る")
    dlo, dhi = domain
    cursor = dlo
    for c, lo, hi in ordered:
        if hi < cursor:
            continue
        if lo > cursor:
            end = min(lo - step, dhi)
            if cursor <= end:
                problems.append(f"[隙間] {fmt(cursor)}..{fmt(end)} がどの類にも入らない")
        cursor = max(cursor, hi + step)
    if cursor <= dhi:
        problems.append(f"[隙間] {fmt(cursor)}..{fmt(dhi)} がどの類にも入らない")
    # 定義域の外にはみ出す類は注意として出す
    for c, lo, hi in closed:
        if hi < dlo or lo > dhi:
            problems.append(f"[域外] {c['name']}: 区間 {c['text']} が --domain と交わらない（域外）")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="同値分割の類の網羅（隙間・重なり）と代表値（読むだけ）")
    ap.add_argument("file")
    ap.add_argument("--domain", required=True, help="入力空間の区間。例 [0,200] / 1..64 / '(,)' は不可（無限なら >=0 など）")
    ap.add_argument("--step", default="1")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        step = num(a.step)
        if step <= 0:
            raise SpecError("--step は正の数")
        classes = load(a.file)
        d = parse_interval(a.domain)
        dc = to_closed(d, step)
        if dc == "empty":
            raise SpecError("--domain が空")
    except (SpecError, OSError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    problems = check(classes, dc, step)
    reps = []
    for c in classes:
        cl = to_closed(c["iv"], step)
        if cl != "empty":
            lo, hi = max(cl[0], dc[0]), min(cl[1], dc[1])
            if lo > hi:
                continue
            reps.append({"name": c["name"], "kind": c["kind"], "interval": c["text"],
                         "representative": fmt(representative(lo, hi, step))})
    if a.json:
        print(json.dumps({"representatives": reps, "problems": problems}, ensure_ascii=False, indent=2))
    else:
        print("代表値（各類から 1 つ）:")
        for r in reps:
            print(f"  {r['name']:<16} {r['kind']}  {r['interval']:<16} 代表 {r['representative']}")
        print(f"\n問題: {len(problems)} 件")
        for p in problems:
            print("  " + p)
        if not problems:
            print("  なし（類は定義域を隙間なく・重なりなく覆っている）")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""仕様に書かれた区間から、境界ごとの 3 点（境界-1 / 境界 / 境界+1）と有効・無効の期待を決定的に出す。

    python boundary_values.py --range "年齢=[0,120]" --range "個数=(0,10]" --range "名前長:length=1..64"

区間の書き方（仕様の文言をそのまま写す。開閉が曖昧なら書かずに止まる）:
  [a,b] (a,b) [a,b) (a,b]   開閉を明示（a か b を空にすると片側が無限: "[0,)"）
  a..b                      閉区間（[a,b] と同じ）
  >=a  >a  <=b  <b          片側
  名前=区間                  名前は省略できる。"名前:length" のように :length を付けると長さ（0 = 空を境界に足す）
  --step 0.01               刻み（既定 1）。小数の仕様はここで刻みを明示する
  --type int32              型の最小・最大とそれを 1 超えた値（オーバーフロー）を境界に足す
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

TYPES = {
    "int8": (-(2**7), 2**7 - 1), "int16": (-(2**15), 2**15 - 1),
    "int32": (-(2**31), 2**31 - 1), "int64": (-(2**63), 2**63 - 1),
    "uint8": (0, 2**8 - 1), "uint16": (0, 2**16 - 1),
    "uint32": (0, 2**32 - 1), "uint64": (0, 2**64 - 1),
}


class SpecError(ValueError):
    pass


def num(text: str) -> Decimal:
    try:
        return Decimal(text.strip())
    except InvalidOperation:
        raise SpecError(f"数値として読めない: {text!r}")


def parse_interval(text: str):
    """(lo, lo_closed, hi, hi_closed)。無限は None。"""
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
        if op in (">=", "≧"):
            return v, True, None, False
        if op == ">":
            return v, False, None, False
        if op in ("<=", "≦"):
            return None, False, v, True
        return None, False, v, False
    raise SpecError(f"区間の書き方を読めない: {text!r}（開閉が分かる形で書くこと。仕様に開閉が無いなら仕様の欠陥）")


def contains(iv, x: Decimal) -> bool:
    lo, lc, hi, hc = iv
    if lo is not None and (x < lo or (x == lo and not lc)):
        return False
    if hi is not None and (x > hi or (x == hi and not hc)):
        return False
    return True


def fmt(x: Decimal) -> str:
    s = format(x, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def points(iv, step: Decimal, kind: str, type_name: str | None):
    """境界ごとの点。各点は (理由, 値, 有効か)。値の重複は理由を併記する。"""
    lo, lc, hi, hc = iv
    raw: list[tuple[str, Decimal]] = []
    if lo is not None:
        tag = "下限" + ("(含む)" if lc else "(含まない)")
        raw += [(f"{tag}-1", lo - step), (tag, lo), (f"{tag}+1", lo + step)]
    if hi is not None:
        tag = "上限" + ("(含む)" if hc else "(含まない)")
        raw += [(f"{tag}-1", hi - step), (tag, hi), (f"{tag}+1", hi + step)]
    if kind == "length":
        raw.append(("空（長さ0）", Decimal(0)))
    if type_name:
        tmin, tmax = TYPES[type_name]
        raw += [(f"{type_name}最小", Decimal(tmin)), (f"{type_name}最小-1(溢れ)", Decimal(tmin - 1)),
                (f"{type_name}最大", Decimal(tmax)), (f"{type_name}最大+1(溢れ)", Decimal(tmax + 1))]
    merged: dict[Decimal, list[str]] = {}
    for why, v in raw:
        if kind == "length" and v < 0:
            merged.setdefault(v, []).append(why + "[負の長さ:到達不能]")
            continue
        merged.setdefault(v, []).append(why)
    out = []
    for v in sorted(merged):
        out.append({"value": fmt(v), "valid": contains(iv, v), "why": " / ".join(merged[v])})
    return out


def split_name(spec: str, idx: int):
    name, kind = f"範囲{idx}", "number"
    if "=" in spec and not re.match(r"^\s*[\[\(<>]", spec):
        name, _, spec = spec.partition("=")
        name = name.strip()
        if ":" in name:
            name, _, k = name.partition(":")
            if k.strip() not in ("length", "number"):
                raise SpecError(f"種類は length か number: {k!r}")
            kind = k.strip()
    return name.strip(), kind, spec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="区間から境界値 3 点と有効・無効の期待を出す（読むだけ）")
    ap.add_argument("--range", dest="ranges", action="append", required=True, metavar="[名前[:length]=]区間")
    ap.add_argument("--step", default="1", help="刻み（既定 1）")
    ap.add_argument("--type", choices=sorted(TYPES), help="型の最小・最大・溢れを足す")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        step = num(a.step)
        if step <= 0:
            raise SpecError("--step は正の数")
        result = []
        for i, spec in enumerate(a.ranges, 1):
            name, kind, body = split_name(spec, i)
            iv = parse_interval(body)
            if iv[0] is None and iv[2] is None:
                raise SpecError(f"{name}: 両端が無限で境界が無い")
            result.append({"name": name, "kind": kind, "interval": body.strip(),
                           "points": points(iv, step, kind, a.type)})
    except SpecError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    for r in result:
        print(f"## {r['name']}  {r['interval']}  ({r['kind']})")
        for p in r["points"]:
            print(f"  {p['value']:>22}  {'有効' if p['valid'] else '無効'}  {p['why']}")
    print("\n※ 開閉は仕様の文言どおり。仕様に境界が書かれていない項目は、ここで決めず仕様の欠陥として戻す。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

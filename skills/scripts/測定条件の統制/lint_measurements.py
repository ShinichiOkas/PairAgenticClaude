#!/usr/bin/env python3
"""測定値の CSV を検査し、条件の欠落・変えた条件が 2 つ以上の比較・試行回数と分散の欠落を洗い出す。

入力 CSV の列: name,value,unit,conditions,group
  conditions は "k=v;k=v" 形式（環境・データ・版など）。group は同じ条件で繰り返した試行の束ね名（省略可）。
使い方: lint_measurements.py FILE.csv [--min-trials 3] [--json]
終了コード: 指摘があれば 1、無ければ 0。既定は読むだけ。
"""
import argparse
import csv
import json
import statistics
import sys


def parse_cond(s):
    out = {}
    for part in (s or "").split(";"):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        out[k.strip()] = v.strip()
    return out


def lint(rows, min_trials):
    issues = []
    groups = {}
    for i, r in enumerate(rows, start=2):  # 1 行目はヘッダ
        name = (r.get("name") or "").strip()
        label = f"行{i} {name or '(名前なし)'}"
        try:
            val = float(r.get("value", ""))
        except ValueError:
            issues.append({"row": i, "kind": "値が数値でない", "detail": f"{label}: value={r.get('value')!r}"})
            continue
        cond = parse_cond(r.get("conditions"))
        if not cond:
            issues.append({"row": i, "kind": "条件なしの数値", "detail": f"{label}: 値 {val} に測定条件が付いていない"})
        if not (r.get("unit") or "").strip():
            issues.append({"row": i, "kind": "単位なし", "detail": f"{label}: unit が空"})
        key = (name, (r.get("group") or "").strip() or json.dumps(cond, sort_keys=True))
        groups.setdefault(key, []).append((val, cond))
    summary = []
    for (name, g), items in groups.items():
        vals = [v for v, _ in items]
        conds = [json.dumps(c, sort_keys=True) for _, c in items]
        if len(set(conds)) > 1:
            issues.append({"row": None, "kind": "同一群内で条件が不一致", "detail": f"{name}/{g}: 群の中で条件が揺れている"})
        n = len(vals)
        sd = statistics.stdev(vals) if n > 1 else None
        summary.append({"name": name, "group": g, "n": n, "mean": statistics.fmean(vals), "stdev": sd,
                        "min": min(vals), "max": max(vals)})
        if n < min_trials:
            issues.append({"row": None, "kind": "試行回数不足",
                           "detail": f"{name}/{g}: n={n} < {min_trials}（平均を出すなら分散と回数も要る）"})
    # 同名の群どうしで、条件の差が 2 キー以上なら「どちらが効いたか分からない」
    by_name = {}
    for (name, g), items in groups.items():
        by_name.setdefault(name, []).append((g, items[0][1]))
    for name, lst in by_name.items():
        for a in range(len(lst)):
            for b in range(a + 1, len(lst)):
                ca, cb = lst[a][1], lst[b][1]
                diff = sorted(k for k in set(ca) | set(cb) if ca.get(k) != cb.get(k))
                if len(diff) >= 2:
                    issues.append({"row": None, "kind": "変えた条件が 2 つ以上",
                                   "detail": f"{name}: {lst[a][0]} と {lst[b][0]} は {diff} が違う。どれが効いたか分からない"})
    return issues, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file")
    ap.add_argument("--min-trials", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    with open(a.file, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    issues, summary = lint(rows, a.min_trials)
    if a.json:
        print(json.dumps({"issues": issues, "summary": summary}, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for s in summary:
            sd = "-" if s["stdev"] is None else f"{s['stdev']:.6g}"
            print(f"[群] {s['name']}/{s['group']}: n={s['n']} mean={s['mean']:.6g} sd={sd} min={s['min']:.6g} max={s['max']:.6g}")
        for it in issues:
            print(f"[指摘] {it['kind']}: {it['detail']}")
        print(f"指摘 {len(issues)} 件")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())

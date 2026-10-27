#!/usr/bin/env python3
"""観測項目の解除条件を、記録された値ではなく実データ（CSV・ログ）を読み直して判定し、記録との食い違いを報告する（読むだけ）。

入力:
  --items items.json   観測項目の配列。1 項目の形:
     {"id": "OBS-1", "metric": "error_rate", "agg": "max", "op": "<", "threshold": 0.001,
      "window_days": 7, "source": "metrics.csv",
      "recorded": {"value": 0.0009, "at": "2026-09-01"}}
     ログの行数を数える項目: {"id": "OBS-2", "source": "run.log", "pattern": "ERROR", "op": "<=", "threshold": 0}
     agg: mean | max | min | last | sum | count | all（全点が条件を満たす。op/threshold を各点に当てる）
  CSV は列 timestamp,metric,value（timestamp は ISO 形式。tz は無視）。source は --base 基準の相対パス。
判定:
  満たした / 満たしていない / 保留（ウィンドウ内にデータが無い、またはデータの範囲がウィンドウ日数に届かない）。
  結果には必ず「引いた範囲」「基準時刻」を添える。recorded があれば食い違い（相対誤差 --tol 超）も出す。
--now を省くと、データ中の最大 timestamp を基準時刻にする（実行日に依存しない）。
LLM・ネットワークは呼ばない。何も書き込まない。食い違いがあれば終了コード 1。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import operator
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq, "!=": operator.ne}


def parse_ts(s: str) -> dt.datetime:
    s = s.strip()
    if len(s) == 10:
        s += "T00:00:00"
    t = dt.datetime.fromisoformat(s.replace(" ", "T", 1) if "T" not in s else s)
    return t.replace(tzinfo=None)


def load_csv(path: Path) -> list[tuple[dt.datetime, str, float]]:
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((parse_ts(r["timestamp"]), r["metric"].strip(), float(r["value"])))
            except (KeyError, ValueError):
                continue  # 壊れた行は数えない（件数は skipped で見せる）
    return rows


def aggregate(agg: str, vals: list[float]) -> float:
    if agg == "mean":
        return sum(vals) / len(vals)
    if agg == "max":
        return max(vals)
    if agg == "min":
        return min(vals)
    if agg == "last":
        return vals[-1]
    if agg == "sum":
        return sum(vals)
    if agg == "count":
        return float(len(vals))
    raise ValueError(f"未知の agg: {agg}")


def judge_item(item: dict, base: Path, now_arg: dt.datetime | None, tol: float) -> dict:
    out: dict = {"id": item.get("id")}
    op = item.get("op")
    if op not in OPS or "threshold" not in item:
        return {**out, "verdict": "保留", "reason": "op / threshold が無い（解除条件が述語になっていない）"}
    cmp, thr = OPS[op], float(item["threshold"])
    src = base / item["source"]
    if not src.is_file():
        return {**out, "verdict": "保留", "reason": f"データが読めない: {item['source']}"}

    if "pattern" in item:  # ログの行数
        rx = re.compile(item["pattern"])
        n = sum(1 for ln in src.read_text(encoding="utf-8", errors="replace").splitlines() if rx.search(ln))
        actual, verdict = float(n), None
        verdict = "満たした" if cmp(actual, thr) else "満たしていない"
        out.update(verdict=verdict, actual=actual, condition=f"count({item['pattern']}) {op} {thr:g}",
                   range="ログ全体", source=item["source"])
    else:
        data = [r for r in load_csv(src) if r[1] == item.get("metric")]
        if not data:
            return {**out, "verdict": "保留", "reason": f"metric {item.get('metric')!r} のデータが無い"}
        now = now_arg or max(r[0] for r in data)
        days = float(item.get("window_days", 0) or 0)
        start = now - dt.timedelta(days=days) if days else min(r[0] for r in data)
        win = sorted((r for r in data if start < r[0] <= now) if days else (r for r in data if r[0] <= now),
                     key=lambda r: r[0])
        rng = f"{start.isoformat()} 〜 {now.isoformat()}"
        out.update(range=rng, now=now.isoformat(), source=item["source"], points=len(win))
        if not win:
            return {**out, "verdict": "保留", "reason": "ウィンドウ内にデータが無い"}
        if days and (win[0][0] - start) > dt.timedelta(days=1):
            return {**out, "verdict": "保留",
                    "reason": f"データが {win[0][0].isoformat()} からしか無く、{days:g} 日間に届かない"}
        vals = [r[2] for r in win]
        agg = item.get("agg", "all")
        if agg == "all":
            ok = all(cmp(v, thr) for v in vals)
            actual = max(vals) if op in ("<", "<=") else min(vals) if op in (">", ">=") else vals[-1]
        else:
            actual = aggregate(agg, vals)
            ok = cmp(actual, thr)
        out.update(verdict="満たした" if ok else "満たしていない", actual=actual,
                   condition=f"{agg}({item.get('metric')}) {op} {thr:g}")

    rec = item.get("recorded")
    if rec is not None and "actual" in out:
        rv = float(rec["value"])
        diff = abs(out["actual"] - rv)
        rel = diff / max(abs(rv), 1e-12) if rv != 0 else (0.0 if diff == 0 else float("inf"))
        out["recorded"] = {"value": rv, "at": rec.get("at")}
        out["mismatch"] = rel > tol
        if out["mismatch"]:
            out["mismatch_note"] = f"記録 {rv:g}（{rec.get('at')}）と実データ {out['actual']:g} が食い違う"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--items", required=True)
    ap.add_argument("--base", help="source の基準ディレクトリ（省略時は items.json のあるディレクトリ）")
    ap.add_argument("--now", help="基準時刻 ISO（省略時はデータの最大 timestamp）")
    ap.add_argument("--tol", type=float, default=0.01, help="記録との相対誤差の許容（既定 0.01）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ip = Path(a.items)
    items = json.loads(ip.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        print("items は配列であること", file=sys.stderr)
        return 2
    base = Path(a.base) if a.base else ip.parent
    now = parse_ts(a.now) if a.now else None
    results = [judge_item(it, base, now, a.tol) for it in items]
    mism = [r for r in results if r.get("mismatch")]
    if a.json:
        print(json.dumps({"results": results, "mismatches": len(mism)}, ensure_ascii=False, indent=2))
    else:
        print(f"観測項目 {len(results)} 件 / 食い違い {len(mism)} 件")
        for r in results:
            line = f"- {r['id']}: {r['verdict']}"
            if "actual" in r:
                line += f"（{r['condition']} / 実データ {r['actual']:g} / 範囲 {r['range']}）"
            if "reason" in r:
                line += f" 理由: {r['reason']}"
            print(line)
            if r.get("mismatch"):
                print(f"    ! {r['mismatch_note']}")
    return 1 if mism else 0


if __name__ == "__main__":
    raise SystemExit(main())

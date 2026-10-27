#!/usr/bin/env python3
"""記録文書から、時刻の添えられていない測定値と、基準日より古い日付つきの測定値を拾い上げる（読むだけ）。

「引用した値には引いた時刻を添える」「時刻の無い数値は出どころを疑う」の機械で出来る部分。
測定値の判定: 数字 + 単位（% ms 秒 分 件 行 回 MB 倍 個 など）。段落（空行で区切られた塊）の中に
日付（2026-09-01 / 2026/9/1 / 2026年9月1日 / ISO 時刻）が 1 つも無ければ「時刻なし」。
日付があって、その最新が基準日より --max-age-days 日より古ければ「古い」。
コードフェンスの中は見ない。

使い方:
  python find_stale_values.py docs/observations.md --now 2026-10-27 --max-age-days 30
  python find_stale_values.py notes/*.md --json
--now を省くと今日の日付（実行日に依存。再現したいときは --now を渡す）。
LLM・ネットワークは呼ばない。何も書き込まない。指摘があれば終了コード 1。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

RE_DATE = re.compile(
    r"(?P<y>20\d{2})\s*(?:[-/.]|年)\s*(?P<m>\d{1,2})\s*(?:[-/.]|月)\s*(?P<d>\d{1,2})\s*日?")
RE_VALUE = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?\s*(?:%|％|ms|秒|分|時間|件|行|回|MB|KB|GB|倍|個|本|人|req/s|rps)")
RE_RELATIVE = re.compile(r"\d+\s*(?:分|時間|日)前|さっき|直前")


def parse_dates(text: str) -> list[dt.date]:
    out = []
    for m in RE_DATE.finditer(text):
        try:
            out.append(dt.date(int(m["y"]), int(m["m"]), int(m["d"])))
        except ValueError:
            pass
    return out


def blocks(text: str):
    """(開始行番号, [(行番号, 行)]) の段落を順に返す。コードフェンス内は飛ばす。"""
    cur: list[tuple[int, str]] = []
    fence = False
    for no, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if not line.strip():
            if cur:
                yield cur
                cur = []
            continue
        cur.append((no, line))
    if cur:
        yield cur


def scan_text(text: str, now: dt.date, max_age_days: int) -> list[dict]:
    findings = []
    for blk in blocks(text):
        joined = "\n".join(l for _, l in blk)
        dates = parse_dates(joined)
        newest = max(dates) if dates else None
        relative = bool(RE_RELATIVE.search(joined))
        for no, line in blk:
            stripped = RE_DATE.sub(" ", line)
            vals = [m.group(0).strip() for m in RE_VALUE.finditer(stripped)]
            if not vals:
                continue
            if newest is None and not relative:
                findings.append({"line": no, "kind": "時刻なし", "values": vals, "text": line.strip()})
            elif newest is not None:
                age = (now - newest).days
                if age > max_age_days:
                    findings.append({"line": no, "kind": "古い", "age_days": age, "newest_date": newest.isoformat(),
                                     "values": vals, "text": line.strip()})
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--now", help="基準日 YYYY-MM-DD（省略時は今日）")
    ap.add_argument("--max-age-days", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    now = dt.date.fromisoformat(a.now) if a.now else dt.date.today()
    report = []
    for f in a.files:
        p = Path(f)
        if not p.is_file():
            print(f"読めない: {f}", file=sys.stderr)
            return 2
        for fd in scan_text(p.read_text(encoding="utf-8", errors="replace"), now, a.max_age_days):
            fd["file"] = p.as_posix()
            report.append(fd)
    if a.json:
        print(json.dumps({"now": now.isoformat(), "max_age_days": a.max_age_days, "findings": report},
                         ensure_ascii=False, indent=2))
    else:
        print(f"基準日 {now} / 古さの上限 {a.max_age_days} 日 / 指摘 {len(report)} 件")
        for r in report:
            extra = f"（最新 {r['newest_date']} = {r['age_days']} 日前）" if r["kind"] == "古い" else ""
            print(f"- {r['file']}:{r['line']} [{r['kind']}]{extra} {', '.join(r['values'])} :: {r['text']}")
    return 1 if report else 0


if __name__ == "__main__":
    raise SystemExit(main())

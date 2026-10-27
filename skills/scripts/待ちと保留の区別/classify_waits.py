#!/usr/bin/env python3
"""止まっている項目の一覧を「待ち（他人の作業）」「保留（判定できない）」「混在」「判別不能」に仕分け、待ちには上げる期限を、保留には観測の問いを付ける（読むだけ）。

入力: JSON 配列または CSV（ヘッダ付き）。1 項目のキー:
  id, text, since（止まり始めた日 YYYY-MM-DD・任意）,
  waiting_for（誰の何が来れば動けるか・待ちの印）, release_condition（何が観測できれば判定できるか・保留の印）
仕分け:
  waiting_for だけ → 待ち ／ release_condition だけ → 保留 ／ 両方 → 混在（分けて書き直す）
  どちらも無い → 本文のキーワードで推定（推定と明示）。決まらなければ判別不能
    =「何があれば進むか」を書いてみる、という問いを返す
  待ちで since が --now から --escalate-days 日を超えたら「上げる」。保留は上げず観測する。

使い方:
  python classify_waits.py waits.json --now 2026-10-27 --escalate-days 3
LLM・ネットワークは呼ばない。何も書き込まない。判別不能・混在があれば終了コード 1。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

WAIT_WORDS = ("待ち", "返事", "レビュー", "承認", "依頼中", "依頼済", "完了後", "マージ待", "回答", "納品", "リリース待")
HOLD_WORDS = ("観測", "データ", "実運用", "判定できない", "測れ", "測定", "情報不足", "不明", "再現", "ログ")


def load(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("JSON は配列であること")
        return data
    return list(csv.DictReader(text.splitlines()))


def classify(item: dict, now: dt.date | None, escalate_days: int) -> dict:
    wf = (item.get("waiting_for") or "").strip()
    rc = (item.get("release_condition") or "").strip()
    text = (item.get("text") or "")
    out = {"id": item.get("id"), "text": text}
    if wf and rc:
        out.update(kind="混在", how="確定", advice="待ちと保留が 1 項目に混ざっている。2 項目に分けて書き直す")
    elif wf:
        out.update(kind="待ち", how="確定")
    elif rc:
        out.update(kind="保留", how="確定")
    else:
        w = [x for x in WAIT_WORDS if x in text]
        h = [x for x in HOLD_WORDS if x in text]
        if w and not h:
            out.update(kind="待ち", how="推定", hint=w, advice="waiting_for（誰の何が来れば動けるか）を書く")
        elif h and not w:
            out.update(kind="保留", how="推定", hint=h, advice="release_condition（何が観測できれば判定できるか）を書く")
        else:
            out.update(kind="判別不能", how="-", advice="まず「何があれば進むか」を 1 行書く。人の作業なら待ち、観測できる事実なら保留")
    if out["kind"] == "待ち":
        out["depends_on"] = wf or None
        since = (item.get("since") or "").strip()
        if since and now:
            age = (now - dt.date.fromisoformat(since)).days
            out["age_days"] = age
            out["action"] = "上げる" if age > escalate_days else "待つ"
        else:
            out["action"] = "since が無く、上げ時を判定できない"
    elif out["kind"] == "保留":
        out["action"] = "観測する（上げない）"
        out["question"] = rc or "何が観測できれば判定できるか"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file")
    ap.add_argument("--now", help="基準日 YYYY-MM-DD（省略時は今日）")
    ap.add_argument("--escalate-days", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    now = dt.date.fromisoformat(a.now) if a.now else dt.date.today()
    try:
        items = load(Path(a.file))
    except (ValueError, OSError) as e:
        print(f"読めない: {e}", file=sys.stderr)
        return 2
    res = [classify(i, now, a.escalate_days) for i in items]
    counts: dict[str, int] = {}
    for r in res:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    if a.json:
        print(json.dumps({"now": now.isoformat(), "counts": counts, "items": res}, ensure_ascii=False, indent=2))
    else:
        print(f"基準日 {now} / " + " / ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        for r in res:
            line = f"- [{r['kind']}{'(推定)' if r['how'] == '推定' else ''}] {r['id']}: {r['text']}"
            if "action" in r:
                line += f" -> {r['action']}"
            print(line)
            if "advice" in r:
                print(f"    ? {r['advice']}")
    return 1 if counts.get("判別不能") or counts.get("混在") else 0


if __name__ == "__main__":
    raise SystemExit(main())

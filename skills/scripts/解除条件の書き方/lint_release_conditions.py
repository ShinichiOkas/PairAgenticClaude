#!/usr/bin/env python3
"""待ち・保留・観測項目の一覧を検査し、解除条件が述語でない／判定者・期限・解除時の動作が無い項目を挙げる（読むだけ）。

入力は Markdown の表（ヘッダに 項目 / 解除条件 / 判定者 / 期限 / 解除時の動作 を含む）か、
同じキーの JSON 配列。表のヘッダは部分一致（「判定する人」は 判定者 ではないので注意: 判定者 / 担当 / 判定担当 を許す）。

検査:
  解除条件が空 / 「様子を見る」「適宜」「しばらく」等の曖昧語 / 数値も比較語も無い（述語に見えない）
  判定者が空 / 期限が空 / 解除時の動作（〜になったら何をするか）が空
  期限が --now より過去（期限切れ。期限までに解除できなかったこと自体が判定結果）

使い方:
  python lint_release_conditions.py observations.md --now 2026-10-27
  python lint_release_conditions.py template        # 表の雛形を出す
LLM・ネットワークは呼ばない。何も書き込まない。error があれば終了コード 1。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

COLS = {
    "item": ("項目", "観測項目", "名前"),
    "cond": ("解除条件", "条件"),
    "judge": ("判定者", "判定担当", "担当"),
    "due": ("期限", "期日"),
    "action": ("解除時の動作", "解除後", "何をするか", "動作"),
}
VAGUE = ("様子を見る", "様子見", "適宜", "しばらく", "落ち着いたら", "問題なければ", "そのうち", "いずれ",
         "状況による", "必要に応じて", "場合によって", "目処がついたら", "目途")
RE_PRED = re.compile(r"\d|未満|以上|以下|超える|ゼロ|全て|すべて|全[^\s]{1,6}が|一致|存在|成功|失敗|完了|[<>=≦≧≤≥]")
RE_DATE = re.compile(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})")

TEMPLATE = (
    "| 項目 | 解除条件（実データの述語） | 判定者 | 期限 | 解除時の動作 |\n"
    "|---|---|---|---|---|\n"
    "| <何を待つ/保留するか> | <例: エラー率が 7 日間連続で 0.1% 未満> | <誰が判定するか> | <YYYY-MM-DD> | <条件成立で何をするか> |\n"
)


def pick(row: dict, key: str) -> str:
    for h, v in row.items():
        if any(n in h for n in COLS[key]):
            return (v or "").strip()
    return ""


def has_col(headers: list[str], key: str) -> bool:
    return any(any(n in h for n in COLS[key]) for h in headers)


def parse_tables(text: str) -> list[dict]:
    rows: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and re.fullmatch(r"\s*\|?[\s:|-]*-[\s:|-]*", lines[i + 1]):
            headers = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            j = i + 2
            if has_col(headers, "cond"):
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                    cells += [""] * (len(headers) - len(cells))
                    rows.append(dict(zip(headers, cells)))
                    j += 1
            i = j
        else:
            i += 1
    return rows


def lint_row(row: dict, now: dt.date | None) -> list[tuple[str, str]]:
    probs: list[tuple[str, str]] = []
    cond = pick(row, "cond")
    if not cond or re.fullmatch(r"[-—–ー?？<>＜＞\s]*|<.*>", cond):
        probs.append(("error", "解除条件が空（または未記入のプレースホルダ）"))
    else:
        v = [w for w in VAGUE if w in cond]
        if v:
            probs.append(("error", f"曖昧語「{'」「'.join(v)}」は解除条件ではない"))
        elif not RE_PRED.search(cond):
            probs.append(("warn", "数値も比較語も無く、実データの述語に見えない"))
    for key, label in (("judge", "判定者"), ("due", "期限"), ("action", "解除時の動作")):
        val = pick(row, key)
        if not val or re.fullmatch(r"<.*>", val) or val in ("-", "—", "未定", "TBD"):
            probs.append(("error", f"{label}が無い"))
    due = pick(row, "due")
    m = RE_DATE.search(due)
    if m and now:
        try:
            d = dt.date(int(m[1]), int(m[2]), int(m[3]))
            if d < now:
                probs.append(("warn", f"期限 {d} は基準日 {now} を過ぎている（解除できていなければ、それ自体が判定結果）"))
        except ValueError:
            probs.append(("error", f"期限の日付が不正: {due}"))
    elif due and not m and not re.fullmatch(r"<.*>", due) and due not in ("-", "—", "未定", "TBD"):
        probs.append(("warn", f"期限が日付で読めない: {due}"))
    return probs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", help="Markdown / JSON のファイル、または template")
    ap.add_argument("--now", help="基準日 YYYY-MM-DD（省略時は期限切れを判定しない）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if a.file == "template":
        print(TEMPLATE, end="")
        return 0
    p = Path(a.file)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        rows = json.loads(text)
    else:
        rows = parse_tables(text)
    if not rows:
        print("検査できる表（解除条件の列を持つ）が見つからない", file=sys.stderr)
        return 2
    now = dt.date.fromisoformat(a.now) if a.now else None
    report = []
    for r in rows:
        probs = lint_row(r, now)
        report.append({"item": pick(r, "item") or "(無名)", "problems": [{"level": l, "message": m} for l, m in probs]})
    errors = sum(1 for r in report for p_ in r["problems"] if p_["level"] == "error")
    warns = sum(1 for r in report for p_ in r["problems"] if p_["level"] == "warn")
    if a.json:
        print(json.dumps({"items": report, "errors": errors, "warnings": warns}, ensure_ascii=False, indent=2))
    else:
        print(f"項目 {len(report)} 件 / error {errors} / warn {warns}")
        for r in report:
            print(f"- {r['item']}: {'OK' if not r['problems'] else ''}")
            for p_ in r["problems"]:
                print(f"    [{p_['level']}] {p_['message']}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

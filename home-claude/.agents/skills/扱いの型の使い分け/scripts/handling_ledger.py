#!/usr/bin/env python
"""満たせない項目の「扱い」台帳を検査し（5 型・暫定の解除条件・方針・不可能とできなかったの混同・黙って落ちた項目）、下流が進めるかを集計する。

    python handling_ledger.py 台帳.md [--items 項目.txt] [--provisional allow|deny|unknown] [--strict]

台帳は表（または縦棒区切りの行）:  項目ID | 型 | 内容 | 解除条件
    R5 | 暫定 | 目標値 3 秒 | A が目標値を答えたら差し替える
型は スコープ外／延期／代案／不可能／暫定。暫定には「誰の何の動作か」の解除条件が要る。
--provisional はプロセス方針が暫定を許すか（W-6）。deny なら暫定は使えず「不可能」として上げる。
--items に採番済みの項目（`R1: ...`）を渡すと、台帳に載っていない項目は「黙って落ちている」候補として挙げる。読むだけ。
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

TYPES = ["スコープ外", "延期", "代案", "不可能", "暫定"]
PROCEEDS = {"スコープ外": True, "延期": True, "代案": True, "不可能": False, "暫定": True}
ACTOR = re.compile(r"A\b|A が|Aが|師匠|人間|ユーザー|利用者|依頼者|発注者|仕様作成者|PjM|担当|責任者|オーナー|承認者")
ACTION = re.compile(r"答え|回答|承認|確定|直し|直す|決め|決定|提示|指定|差し替|読み替|与え|通知|レビュー|合意")
COULD_NOT = re.compile(r"時間が(?:足り|なく|ない)|難しい|できなかった|わからなかった|分からなかった|調べきれ|手が回ら|実装できな|面倒|工数")
ID_RE = r"[A-Za-z]+\d+"


def parse(text: str) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    errs: list[str] = []
    for no, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or "|" not in s:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) or not c for c in cells):
            continue
        if len(cells) > 1 and cells[1] in ("型", "扱い"):
            continue
        if len(cells) < 2:
            errs.append(f"[書式] {no} 行目: `項目ID | 型 | 内容 | 解除条件` の形ではない")
            continue
        cells += [""] * (4 - len(cells))
        rows.append({"id": cells[0], "type": cells[1], "body": cells[2], "release": cells[3], "line": no})
    return rows, errs


def lint(rows: list[dict], provisional: str = "unknown", items: dict[str, str] | None = None) -> list[str]:
    out: list[str] = []
    seen: dict[str, int] = {}
    for r in rows:
        i, t = r["id"], r["type"]
        if i in seen:
            out.append(f"[重複] {i}（{seen[i]} 行目と {r['line']} 行目）")
        seen[i] = r["line"]
        if t not in TYPES:
            out.append(f"[型が不明] {i}: 「{t}」は 5 型（{'・'.join(TYPES)}）のどれでもない。黙って落とすのはどの型でもない")
            continue
        if not r["body"]:
            out.append(f"[内容が空] {i}（{t}）: 何をどう扱うかが書かれていない")
        if t == "暫定":
            rel = r["release"]
            if not rel:
                out.append(f"[解除条件が無い] {i}: 解除条件の無い暫定は確定値と区別が付かない")
            elif not (ACTOR.search(rel) and ACTION.search(rel)):
                out.append(f"[解除条件が曖昧] {i}: 「誰が何をしたら差し替えるか」まで書く → {rel}")
            if provisional == "deny":
                out.append(f"[方針が暫定を許していない] {i}: 暫定は使えない。「不可能」として上げる")
            elif provisional == "unknown":
                out.append(f"[方針未確認] {i}: 暫定を許すかはプロセス方針が決める。--provisional allow|deny で確かめる")
        elif t == "不可能":
            if COULD_NOT.search(r["body"]):
                out.append(f"[できなかったの混同の疑い] {i}: 不可能は「deps を満たす OUT が存在しない」こと。自分の限界の話になっていないか → {r['body']}")
        elif r["release"] and t in ("スコープ外", "代案"):
            pass
    if items is not None:
        ledger = {r["id"] for r in rows}
        for i, t in items.items():
            if i not in ledger:
                out.append(f"[黙って落ちている候補] {i}: 台帳に扱いが無い（満たせた項目なら無視してよい）→ {t}")
        for r in rows:
            if r["id"] not in items:
                out.append(f"[項目に無いID] {r['id']} は項目一覧に無い")
    return out


def summarize(rows: list[dict]) -> dict:
    counts = {t: sum(1 for r in rows if r["type"] == t) for t in TYPES}
    return {"counts": counts,
            "blocking": [r["id"] for r in rows if r["type"] in PROCEEDS and not PROCEEDS[r["type"]]],
            "open_provisional": [(r["id"], r["release"]) for r in rows if r["type"] == "暫定"]}


def read_items(text: str) -> dict[str, str]:
    d = {}
    for line in text.splitlines():
        m = re.match(rf"^\s*(?:[-*+]\s*)?\[?({ID_RE})\]?\s*[:：]\s*(.*)$", line)
        if m:
            d[m.group(1)] = re.sub(r"\s*\[曖昧語:[^\]]*\]\s*$", "", m.group(2)).strip()
    return d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("ledger", type=Path)
    ap.add_argument("--items", type=Path, help="採番済みの項目一覧（R1: ...）")
    ap.add_argument("--provisional", choices=["allow", "deny", "unknown"], default="unknown",
                    help="プロセス方針が暫定を許すか（既定 unknown＝未確認として指摘）")
    ap.add_argument("--strict", action="store_true", help="指摘があれば終了コード 1")
    a = ap.parse_args(argv)
    for p in (a.ledger,) + ((a.items,) if a.items else ()):
        if not p.is_file():
            print(f"エラー: ファイルが無い: {p}", file=sys.stderr)
            return 2
    rows, errs = parse(a.ledger.read_text(encoding="utf-8"))
    items = read_items(a.items.read_text(encoding="utf-8")) if a.items else None
    found = errs + lint(rows, a.provisional, items)
    s = summarize(rows)
    print("型ごとの件数: " + " ／ ".join(f"{t} {n}" for t, n in s["counts"].items()))
    if s["blocking"]:
        print("下流が止まる（上げる）: " + "、".join(s["blocking"]))
    else:
        print("下流は進める（不可能の項目なし）")
    for i, rel in s["open_provisional"]:
        print(f"  暫定 {i} の解除条件: {rel or '（無い）'}")
    for f in found:
        print(f)
    if not found:
        print("指摘なし")
    return 1 if (a.strict and found) else 0


if __name__ == "__main__":
    sys.exit(main())

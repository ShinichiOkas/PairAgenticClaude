#!/usr/bin/env python
"""合否の三値（合格／不合格／保留）の報告を検め、保留に理由と解除条件が付いているか・「たぶん」で合格にしていないかを指摘する。

    python hold_lint.py REPORT.md [--policy ternary|binary]

読む形（どちらでもよい）:
  表     ヘッダに「判定」または「結果」の列があり、保留の行は「理由」「解除条件」の列を持つ
  箇条書き 「- T-03 保留 理由: … 解除条件: …」（続きの字下げ行も同じ項目として読む）
指摘:
  [理由なし]        保留に理由が無い（データが足りない／期間が要る／環境が無い など）
  [解除条件なし]    保留に解除条件が無い（付かない保留は作らない）
  [解除条件が曖昧]  「いつか／そのうち／様子を見て／必要に応じて」だけで、何が起きたら何をするかが無い
  [たぶんで合格]    合格の行に「たぶん／おそらく／はず／と思う」がある（それは保留である）
  [方針違反]        --policy binary（二値の方針）なのに保留が使われている
判定はしない。件数の集計（三値）と指摘を出す。終了コード: 0 = 指摘なし ／ 1 = 指摘あり ／ 2 = 入力不正
"""
from __future__ import annotations

import argparse
import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

VAGUE_ONLY = ("いつか", "そのうち", "様子を見", "必要に応じ", "適宜", "後で", "あとで", "状況次第")
GUESS = ("たぶん", "多分", "おそらく", "恐らく", "はず", "と思う", "と思われ", "だろう", "きっと")


def verdict_of(text: str) -> str | None:
    t = text
    if re.search(r"不合格|❌|\bNG\b|\bFAIL", t, re.I):
        return "不合格"
    if re.search(r"保留|⏸|\bHOLD\b|\bPENDING\b", t, re.I):
        return "保留"
    if re.search(r"合格|✅|\bOK\b|\bPASS", t, re.I):
        return "合格"
    return None


def split_row(line: str) -> list[str]:
    s = line.strip().strip("|")
    return [c.strip() for c in s.split("|")]


def col(header: list[str], names: tuple[str, ...]) -> int | None:
    for i, h in enumerate(header):
        if any(n in h for n in names):
            return i
    return None


def entries(text: str):
    """(ラベル, 判定, 理由, 解除条件, 全文) の列。"""
    out = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", lines[i + 1]) and "-" in lines[i + 1]:
            header = split_row(ln)
            cv = col(header, ("判定", "結果"))
            cr = col(header, ("理由", "なぜ"))
            cu = col(header, ("解除条件", "解除"))
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = split_row(lines[j])
                if cv is not None and cv < len(cells):
                    v = verdict_of(cells[cv])
                    if v:
                        reason = cells[cr] if cr is not None and cr < len(cells) else ""
                        rel = cells[cu] if cu is not None and cu < len(cells) else ""
                        out.append((cells[0][:40], v, reason, rel, lines[j]))
                j += 1
            i = j
            continue
        m = re.match(r"^(\s*)(?:[-*]|\d+[.)])\s+(.*)$", ln)
        if m and verdict_of(m.group(2)):
            block = [ln]
            ind = len(m.group(1))
            j = i + 1
            while j < len(lines) and lines[j].strip() and (len(lines[j]) - len(lines[j].lstrip())) > ind:
                block.append(lines[j])
                j += 1
            full = "\n".join(block)
            reason = _field(full, ("理由", "なぜ", "保留理由"))
            rel = _field(full, ("解除条件", "解除"))
            out.append((m.group(2)[:40], verdict_of(m.group(2)), reason, rel, full))
            i = j
            continue
        i += 1
    return out


def _field(block: str, names: tuple[str, ...]) -> str:
    for n in names:
        m = re.search(n + r"\s*[:：]\s*(.*?)(?=(?:解除条件|理由|なぜ|保留理由)\s*[:：]|$)", block, re.S)
        if m:
            return m.group(1).strip().strip("—-、。 \n")
    return ""


def lint(text: str, policy: str):
    problems = []
    tally = {"合格": 0, "不合格": 0, "保留": 0}
    ents = entries(text)
    for label, v, reason, rel, full in ents:
        tally[v] += 1

        def add(kind, msg):
            problems.append({"item": label, "kind": kind, "message": msg})

        if v == "保留":
            if policy == "binary":
                add("方針違反", "二値の方針なのに保留が使われている（保留を許すかは方針が決める）")
            if not reason:
                add("理由なし", "保留の理由が無い（データが足りない／期間が要る／環境が無い など）")
            if not rel:
                add("解除条件なし", "解除条件が無い。何が起きたら何をするかを書く")
            elif any(w in rel for w in VAGUE_ONLY) and not re.search(r"\d|なったら|したら|れば|とき|時|まで|以上|以下", rel):
                add("解除条件が曖昧", f"「{rel[:30]}」。観測できる条件と、満たしたときの行動を書く")
        elif v == "合格":
            hit = [w for w in GUESS if w in full]
            if hit:
                add("たぶんで合格", f"合格の行に「{hit[0]}」。根拠が推測なら保留である")
    return tally, problems, len(ents)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="保留（第 3 の値）の理由・解除条件を検める（読むだけ）")
    ap.add_argument("report")
    ap.add_argument("--policy", choices=("ternary", "binary"), default="ternary")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        with open(a.report, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    tally, problems, n = lint(text, a.policy)
    if n == 0:
        print("エラー: 判定の行（合格／不合格／保留）を 1 件も読めなかった", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"tally": tally, "problems": problems}, ensure_ascii=False, indent=2))
    else:
        print(f"集計: 合格 {tally['合格']} ／ 不合格 {tally['不合格']} ／ 保留 {tally['保留']}")
        print(f"指摘: {len(problems)} 件")
        for p in problems:
            print(f"  [{p['kind']}] {p['item']}: {p['message']}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

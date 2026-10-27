#!/usr/bin/env python
"""残留リスクの節を検め、各項目が「①何が起こりうるか」と「②何を確かめていないか」の 2 つで 1 組になっているかを指摘する。

    python lint_residual_risk.py REPORT.md [--upstream UPSTREAM.md]

対象は「残留リスク」を含む見出しの節（無ければファイル全体）。項目 = 最上位の箇条書き（- / * / 1.）か ### 見出し。
各項目の中で次を探す（行頭の印は ① ② でも「起こりうる」「確かめていない」でもよい）:
  ① 行: ①／起こりうる／何が起こりうるか／リスク:     ② 行: ②／確かめていない／未確認／未測定／検証していない
指摘:
  [②なし]            ② 行が無い（心配事の一覧になる）
  [①なし]            ① 行が無い
  [②が空]            ② が「なし」だけ（確かめたなら残留リスクではなく測定値）
  [①に②の中身]      ① に「未測定／確かめていない」等がある（確かめれば消えるものは ② へ）
  [たぶん大丈夫]     「たぶん／おそらく問題ない」等。根拠が外れる形を書く
  [無印の転記]       --upstream の項目と同文で、減らせた分（減った／解消／確認済み）の記述が無い
判定はしない。指摘のみ。終了コード: 0 = 指摘なし ／ 1 = 指摘あり ／ 2 = 入力不正
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

M1 = re.compile(r"^\s*(?:[-*]\s*)?(?:①|起こりうる|何が起こりうるか|リスク\s*[:：])")
M2 = re.compile(r"^\s*(?:[-*]\s*)?(?:②|確かめていない|何を確かめていないか|未確認|未測定|検証していない)")
UNVERIFIED_IN_1 = ("未測定", "確かめていない", "測っていない", "未確認", "検証していない", "試していない")
VAGUE = ("たぶん", "多分", "おそらく問題", "恐らく問題", "大丈夫と思", "大丈夫だと思", "問題ないと思", "きっと")
EMPTY2 = re.compile(r"^(?:なし|無し|特になし|ない|-|n/?a|none)[。.\s]*$", re.I)
REDUCED = ("減ら", "減った", "解消", "確認済", "確かめた", "測定した", "消えた")
ITEM = re.compile(r"^(\s*)(?:[-*]|\d+[.)])\s+(.*)$")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def risk_section(text: str) -> list[str]:
    lines = text.splitlines()
    start, level = None, 0
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m and "残留リスク" in m.group(2):
            start, level = i + 1, len(m.group(1))
            break
    if start is None:
        return lines
    end = len(lines)
    for j in range(start, len(lines)):
        m = re.match(r"^(#{1,6})\s", lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break
    return lines[start:end]


def split_items(lines: list[str]):
    cands = [(i, m.group(1)) for i, ln in enumerate(lines) if (m := ITEM.match(ln))]
    heads = [i for i, ln in enumerate(lines) if re.match(r"^#{3,6}\s", ln)]
    starts: list[int]
    if heads:
        starts = heads
    elif cands:
        base = min(len(ind) for _, ind in cands)
        starts = [i for i, ind in cands if len(ind) == base]
    else:
        return []
    items = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(lines)
        items.append(lines[s:e])
    return items


def norm(s: str) -> str:
    return re.sub(r"[\s\-*・①②:：。、.]+", "", s)


def label(item: list[str]) -> str:
    first = re.sub(r"^\s*(?:[-*]|\d+[.)]|#+)\s*", "", item[0]).strip()
    return first[:40] + ("…" if len(first) > 40 else "")


def text_after(line: str, rx: re.Pattern) -> str:
    return re.sub(r"^[\s\-*]*(?:①|②|起こりうる|何が起こりうるか|リスク|確かめていない|何を確かめていないか|未確認|未測定|検証していない)\s*[:：]?\s*", "", line).strip()


def lint(report: str, upstream: str | None):
    items = split_items(risk_section(report))
    problems = []
    up_items = {norm("".join(it)): it for it in split_items(risk_section(upstream))} if upstream else {}
    if not items:
        return [{"item": "-", "kind": "項目なし", "message": "残留リスクの項目が見つからない（書いていないなら「なし」と根拠を書く）"}]
    for it in items:
        lb = label(it)

        def add(kind, msg):
            problems.append({"item": lb, "kind": kind, "message": msg})

        l1 = [ln for ln in it if M1.match(ln)]
        l2 = [ln for ln in it if M2.match(ln)]
        if not l2:
            add("②なし", "「何を確かめていないか」の行が無い")
        else:
            t2 = " ".join(text_after(ln, M2) for ln in l2).strip()
            if not t2 or EMPTY2.match(t2):
                add("②が空", "②が「なし」か空。確かめたなら残留リスクではなく測定値として書く")
        if not l1:
            add("①なし", "「何が起こりうるか」の行が無い")
        elif any(w in text_after(ln, M1) for ln in l1 for w in UNVERIFIED_IN_1):
            add("①に②の中身", "①に「未測定／確かめていない」の趣旨がある。確かめれば消えるものは②へ")
        joined = " ".join(it)
        for w in VAGUE:
            if w in joined:
                add("たぶん大丈夫", f"「{w}」。根拠が外れる形を書くこと")
                break
        if up_items:
            k = norm(joined)
            if k in up_items and not any(w in joined for w in REDUCED):
                add("無印の転記", "上流の項目と同文で、自分が減らせた分の記述が無い")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="残留リスクが ①②の 2 つで 1 組かを検める（読むだけ）")
    ap.add_argument("report")
    ap.add_argument("--upstream")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        report = read(a.report)
        up = read(a.upstream) if a.upstream else None
    except OSError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    problems = lint(report, up)
    if a.json:
        print(json.dumps(problems, ensure_ascii=False, indent=2))
    else:
        print(f"指摘: {len(problems)} 件")
        for p in problems:
            print(f"  [{p['kind']}] {p['item']}: {p['message']}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

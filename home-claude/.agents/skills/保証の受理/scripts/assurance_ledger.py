#!/usr/bin/env python
"""設計保証の各項目（主張とエビデンス）に、受理／不受理の「候補」を機械的に付け、受理した項目の残留リスク雛形を出す。

    python assurance_ledger.py 設計保証.md [--spec-items 内部項目.txt]

読む形（どちらでもよい）:
  表       ヘッダに「項目」と「エビデンス（証拠）」の列。「主張」の列があれば使う
  節       「### 項目名」の下に「主張: …」「エビデンス: …」（続きの行・コードブロックもエビデンス）
候補の付け方（不受理の理由は 2 つだけ。「内容に納得できない」は理由にしない）:
  不受理① エビデンスが無い（空・「なし」・「レビュー済み」「確認済み」だけの主張の繰り返し）
  不受理② エビデンスが主張を支えていない（主張の件数とエビデンスの件数が食い違う／エビデンスに「未実装」等の否定）
  受理候補 機械出力・実行ログ・コマンド・コードブロック・path:line など、内部を見ずに検められる材料がある
  要判断   上のどれにも当てはまらない（機械では決めない。人／LLM が読んで決める）
受理候補は「検証した」ではない。残留リスクの雛形（①起こりうる ②自分では検証していない）を添えて出す。
--spec-items: 外形から見えない仕様項目を 1 行 1 項目で渡すと、保証に載っていないもの（誰も保証していない）を指摘する。
終了コード: 0 = 不受理・未掲載なし ／ 1 = あり ／ 2 = 入力不正
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

NEGATION = ("未実装", "実装していない", "実装しなかった", "できなかった", "できていない", "断念", "対象外",
            "未対応", "未検証", "満たしていない", "満たせなかった", "見送", "未着手", "対応していない")
CLAIM_ONLY = re.compile(r"^[\s✅⭕○◯]*(レビュー済み?|確認済み?|問題なし|問題ない|実施済み?|対応済み?|OK|大丈夫|守っている|満たしている)[\s。.]*$", re.I)
EMPTY = re.compile(r"^[\s\-–—]*(なし|無し|ない|n/?a|none|tbd|未記入)?[\s。.]*$", re.I)
MECHANICAL = [re.compile(p) for p in (r"```", r"`[^`]+`", r"\$\s*\w+", r"\b\w[\w./\\-]*\.\w+:\d+", r"exit\s*(code|status)?\s*[:=]?\s*\d",
                                       r"機械出力|実行ログ|実行結果|出力一覧|import\s+\w+|^\s*(from|import)\s+\w+", r"\bgrep\b|\bpytest\b|\bpython\b")]


def table_entries(lines: list[str]):
    out = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", lines[i + 1]) and "-" in lines[i + 1]:
            head = [c.strip() for c in lines[i].strip().strip("|").split("|")]

            def ix(*names):
                for k, h in enumerate(head):
                    if any(n in h for n in names):
                        return k
                return None

            ci, cc, ce = ix("項目"), ix("主張"), ix("エビデンス", "証拠", "根拠")
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if ce is not None:
                    name = cells[ci] if ci is not None and ci < len(cells) else (cells[0] if cells else "")
                    claim = cells[cc] if cc is not None and cc < len(cells) else name
                    ev = cells[ce] if ce < len(cells) else ""
                    out.append((name, claim, ev))
                j += 1
            i = j
        else:
            i += 1
    return out


def section_entries(lines: list[str]):
    out = []
    starts = [i for i, ln in enumerate(lines) if re.match(r"^#{2,6}\s+\S", ln)]
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(lines)
        body = lines[s + 1:e]
        ev_i = next((n for n, ln in enumerate(body) if re.match(r"^\s*(?:[-*]\s*)?\**(エビデンス|証拠)\**\s*[:：]", ln)), None)
        if ev_i is None:
            continue
        name = re.sub(r"^#+\s*", "", lines[s]).strip()
        claim = name
        for ln in body[:ev_i]:
            m = re.match(r"^\s*(?:[-*]\s*)?\**主張\**\s*[:：]\s*(.*)$", ln)
            if m:
                claim = m.group(1).strip()
        first = re.sub(r"^\s*(?:[-*]\s*)?\**(エビデンス|証拠)\**\s*[:：]\s*", "", body[ev_i])
        out.append((name, claim, "\n".join([first] + body[ev_i + 1:]).strip()))
    return out


def nums_with_ken(s: str) -> list[int]:
    return [int(x) for x in re.findall(r"(\d+)\s*(?:件|個|箇所|経路)", s)]


def classify(claim: str, ev: str):
    e = ev.strip()
    if not e or EMPTY.match(e):
        return "不受理①", "エビデンスが無い"
    if CLAIM_ONLY.match(e) and not any(r.search(e) for r in MECHANICAL):
        return "不受理①", "エビデンスが主張の言い換え（機械出力・ログ・コマンドが無い）"
    neg = [w for w in NEGATION if w in e and w not in claim]
    if neg:
        return "不受理②", f"エビデンスに「{neg[0]}」がある。主張と食い違う"
    cn, en = nums_with_ken(claim), nums_with_ken(e)
    if cn and en and max(cn) != max(en):
        return "不受理②", f"主張は {max(cn)} 件、エビデンスは {max(en)} 件"
    if any(r.search(e) for r in MECHANICAL):
        return "受理候補", "内部を見ずに検められる材料（コマンド・ログ・コード等）がある"
    return "要判断", "機械では決められない。エビデンスが主張を支えているかを読んで決める"


def analyze(text: str, spec_items: list[str]):
    lines = text.splitlines()
    ents = table_entries(lines) or section_entries(lines)
    rows = []
    for name, claim, ev in ents:
        verdict, why = classify(claim, ev)
        rows.append({"item": name, "claim": claim, "verdict": verdict, "why": why})
    missing = []
    names = " ".join(r["item"] + " " + r["claim"] for r in rows)
    for s in spec_items:
        if s not in names:
            missing.append(s)
    return rows, missing


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="設計保証の受理／不受理の候補と残留リスクの雛形（読むだけ）")
    ap.add_argument("assurance")
    ap.add_argument("--spec-items")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        with open(a.assurance, encoding="utf-8") as f:
            text = f.read()
        spec = []
        if a.spec_items:
            with open(a.spec_items, encoding="utf-8") as f:
                spec = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    except OSError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    rows, missing = analyze(text, spec)
    if not rows:
        print("エラー: 保証の項目を読めなかった（表に「項目」「エビデンス」列、または「### 項目」＋「エビデンス:」）", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"rows": rows, "not_in_assurance": missing}, ensure_ascii=False, indent=2))
    else:
        print("| 項目 | 候補 | 理由 |\n|---|---|---|")
        for r in rows:
            print(f"| {r['item']} | {r['verdict']} | {r['why']} |")
        acc = [r for r in rows if r["verdict"] == "受理候補"]
        if acc:
            print("\n## 残留リスク（受理したが自分では検証していない項目・雛形）")
            for r in acc:
                print(f"- {r['item']}\n  - ① 保証が外れる形: （要記入）\n  - ② 確かめていない: 「{r['claim']}」は送り手の保証を受理しただけで、自分では検めていない")
        if missing:
            print("\n## 保証に載っていない項目（誰も保証していない。保証扱いしない）")
            for m in missing:
                print(f"- {m}")
        print("\n※ 候補は機械の仮置き。受理は「この材料でこの主張を受け取る」という人の判断である。")
    bad = [r for r in rows if r["verdict"].startswith("不受理")]
    return 1 if bad or missing else 0


if __name__ == "__main__":
    sys.exit(main())

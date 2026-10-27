#!/usr/bin/env python
"""復唱が原文の写しになっていないかを、文字列の重なりで測る（逐語率・最長の逐語連続・含まないものの言い直しの有無）。

    python restate_check.py 原文.txt 復唱.txt [--n 6] [--run 20] [--max-ratio 0.5] [--strict]

「一致したように見えたら疑う」を数字にする。判断（言い直しが十分か）は人間が行う。この道具は疑いを指摘するだけ。
読むだけ。ファイルは書かない。同じ入力なら同じ出力。
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

NEG_PAT = re.compile(r"含まない|ではない|ではなく|は除く|を除く|対象外|範囲外|扱わない|しない(?:という|理解)|ではありません")
STRIP = re.compile(r"[\s、。，．,.!！?？「」『』（）()\[\]・:：;；\-–—*_`#>]")


def normalize(s: str) -> str:
    return STRIP.sub("", s)


def runs(orig: str, rest: str, n: int) -> tuple[float, list[str]]:
    """復唱の n 文字窓のうち原文にも現れる割合と、連続して一致した区間（文字列）の一覧。"""
    if len(rest) < n:
        return 0.0, []
    shingles = {orig[i : i + n] for i in range(len(orig) - n + 1)}
    hit = [rest[i : i + n] in shingles for i in range(len(rest) - n + 1)]
    ratio = sum(hit) / len(hit)
    out: list[str] = []
    i = 0
    while i < len(hit):
        if hit[i]:
            j = i
            while j + 1 < len(hit) and hit[j + 1]:
                j += 1
            out.append(rest[i : j + n])
            i = j + 1
        else:
            i += 1
    return ratio, out


def analyze(orig_text: str, rest_text: str, n: int = 6, run: int = 20, max_ratio: float = 0.5) -> dict:
    o, r = normalize(orig_text), normalize(rest_text)
    ratio, rs = runs(o, r, n)
    longest = max(rs, key=len) if rs else ""
    long_runs = sorted((x for x in rs if len(x) >= run), key=lambda x: (-len(x), x))
    quotes = [q for q in re.findall(r"[「『]([^」』]+)[」』]", rest_text) if len(normalize(q)) >= n]
    quoted_verbatim = [q for q in quotes if normalize(q) in o]
    findings: list[str] = []
    if not r:
        findings.append("[復唱が空] 復唱の本文が無い")
    if ratio > max_ratio:
        findings.append(f"[逐語率が高い] {ratio:.0%} が原文と同じ並び（{n} 文字窓）。自分の語で言い直せているか疑う")
    if long_runs:
        findings.append(f"[長い逐語連続] {len(long_runs)} か所（{run} 文字以上）。最長 {len(longest)} 文字")
    if quoted_verbatim:
        findings.append(f"[原文の引用] 「」内が原文そのままの箇所が {len(quoted_verbatim)} か所（引用だけの確認は確認したふりになる）")
    if not NEG_PAT.search(rest_text):
        findings.append("[含まないものの言い直しが無い] 「Y は含まないという理解でよいですか」の形が見当たらない")
    return {
        "ratio": ratio,
        "longest": longest,
        "long_runs": long_runs,
        "quoted_verbatim": quoted_verbatim,
        "has_negative": bool(NEG_PAT.search(rest_text)),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("original", type=Path, help="相手の原文（テキスト）")
    ap.add_argument("restatement", type=Path, help="自分の復唱（テキスト）")
    ap.add_argument("--n", type=int, default=6, help="重なりを数える窓の文字数（既定 6）")
    ap.add_argument("--run", type=int, default=20, help="長い逐語連続とみなす文字数（既定 20）")
    ap.add_argument("--max-ratio", type=float, default=0.5, help="逐語率の許容上限（既定 0.5）")
    ap.add_argument("--strict", action="store_true", help="疑いがあれば終了コード 1")
    a = ap.parse_args(argv)
    for p in (a.original, a.restatement):
        if not p.is_file():
            print(f"エラー: ファイルが無い: {p}", file=sys.stderr)
            return 2
    res = analyze(a.original.read_text(encoding="utf-8"), a.restatement.read_text(encoding="utf-8"), a.n, a.run, a.max_ratio)
    print(f"逐語率: {res['ratio']:.0%}（{a.n} 文字窓）")
    print(f"最長の逐語連続: {len(res['longest'])} 文字")
    for x in res["long_runs"]:
        print(f"  逐語: {x}")
    print(f"含まないものの言い直し: {'あり' if res['has_negative'] else 'なし'}")
    if res["findings"]:
        print("疑い:")
        for f in res["findings"]:
            print(f"  {f}")
        print("※ 疑いの指摘であって断定ではない。判定は人間が行う。")
    else:
        print("疑いなし（ただし一致したように見えるときは、同じ語のまま返していないかを目で確かめる）")
    return 1 if (a.strict and res["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())

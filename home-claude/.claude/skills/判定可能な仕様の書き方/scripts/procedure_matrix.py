#!/usr/bin/env python
"""仕様項目ごとの「満たしている」の定義と判定手続きの対応表を、両向き（偽陽性・偽陰性）の記入漏れ・実施可能性の代用・根拠の無い「等価」について検査し、雛形も作る。

    python procedure_matrix.py new 仕様項目.txt [--out 対応表.md]
    python procedure_matrix.py lint 対応表.md [--spec 仕様項目.txt] [--strict]

仕様項目.txt は `S1: 外部パッケージに依存しない` の形の行。対応表は項目ごとに `## S1: ...` の節と箇条書き:
    - 満たしている:  （手続きより先に書く定義）   - 手続き:
    - 偽陽性:  （no が出たが実は満たしている形）  - 偽陰性:  （満たしていないのに no が出ない形）
    - 検出できない範囲:  （後ろ向きが成り立たない範囲。消さずに書く）
    - 等価置換: なし／はい   - 反例: （はい のときだけ。2 個以上、；区切り）
`new` は --out を指定し、無いファイルのときだけ書く。`lint` は読むだけ。
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

KEYS = ["満たしている", "手続き", "偽陽性", "偽陰性", "検出できない範囲", "等価置換", "反例"]
KEYLINE = re.compile(r"^\s*[-*]\s*(" + "|".join(KEYS) + r")\s*[:：]\s*(.*)$")
EMPTY = re.compile(r"^(?:tbd|todo|未記入|未定|\?|？|-|ー|―)?$", re.I)
NEGATIVE = re.compile(r"^(?:なし|無し|ない|ありません|該当なし|無い)")
SUBSTITUTE = re.compile(r"落ちなければ|失敗しなければ|エラー(?:が)?(?:出|起き)なければ|例外(?:が)?(?:出|起き)なければ|実行(?:でき|して)(?:れば|たら|た)|動けば|動作すれば|起動すれば|通れば")
SPEC_RE = re.compile(r"^\s*(?:[-*+]\s*)?\[?([A-Za-z]+\d+)\]?\s*[:：]\s*(.*)$")


def parse(text: str) -> list[dict]:
    secs: list[dict] = []
    cur = None
    last = None
    for line in text.splitlines():
        h = re.match(r"^##\s+\[?([A-Za-z]+\d+)\]?\s*[:：]?\s*(.*)$", line)
        if h:
            cur = {"id": h.group(1), "title": h.group(2).strip(), "f": {}}
            secs.append(cur)
            last = None
            continue
        if cur is None:
            continue
        m = KEYLINE.match(line)
        if m:
            last = m.group(1)
            cur["f"][last] = m.group(2).strip()
        elif last and line.startswith((" ", "\t")) and line.strip():
            cur["f"][last] += (" " if cur["f"][last] else "") + line.strip().lstrip("-*・ ").strip()
        elif line.strip() and not line.startswith("#"):
            last = None
    return secs


def lint(text: str, spec_ids: list[str] | None = None) -> list[str]:
    out: list[str] = []
    secs = parse(text)
    if not secs:
        return ["[項目が無い] `## S1: ...` の節が 1 つも無い"]
    ids = [s["id"] for s in secs]
    for i in sorted({x for x in ids if ids.count(x) > 1}):
        out.append(f"[重複] {i} が 2 回ある")
    for s in secs:
        i, f = s["id"], s["f"]
        for k in ("満たしている", "手続き", "偽陽性", "偽陰性"):
            if k not in f:
                out.append(f"[{k}が無い] {i}: `- {k}:` の行が無い")
            elif EMPTY.match(f[k]):
                out.append(f"[{k}が空] {i}")
        d = f.get("満たしている", "")
        if d and SUBSTITUTE.search(d):
            out.append(f"[実施可能性の代用の疑い] {i}: 「満たしている」の定義が「実行できた」の形 → 実行できたは満たしているではない: {d}")
        fn = f.get("偽陰性", "")
        rng = f.get("検出できない範囲", "")
        if fn and not EMPTY.match(fn):
            if NEGATIVE.match(fn):
                if len(NEGATIVE.sub("", fn).strip(" 。、．:：（）()")) < 6:
                    out.append(f"[偽陰性「なし」に根拠が無い] {i}: 「なし」と書くなら、なぜ無いかを書く")
            elif not rng or EMPTY.match(rng) or NEGATIVE.match(rng):
                out.append(f"[検出できない範囲が無い] {i}: 偽陰性の形を挙げているのに、検出できない範囲として書かれていない（消さずに書く）")
        eq = f.get("等価置換", "")
        if re.match(r"^(?:はい|あり|yes|y)", eq, re.I):
            cex = [c for c in re.split(r"[;；\n]", f.get("反例", "")) if c.strip() and not EMPTY.match(c.strip())]
            if len(cex) < 2:
                out.append(f"[等価の根拠が足りない] {i}: 「等価な手続きに置き換えた」には反例探しが 2〜3 個要る（いま {len(cex)} 個）")
    if spec_ids is not None:
        for i in spec_ids:
            if i not in ids:
                out.append(f"[仕様項目に手続きが無い] {i}")
        for i in ids:
            if i not in spec_ids:
                out.append(f"[仕様に無い項目] {i} は仕様項目の一覧に無い")
    return out


def skeleton(items: list[tuple[str, str]]) -> str:
    parts = ["# 仕様項目と判定手続きの対応表", ""]
    for i, t in items:
        parts += [
            f"## {i}: {t}", "",
            "- 満たしている: ", "- 手続き: ", "- 偽陽性: ", "- 偽陰性: ", "- 検出できない範囲: ",
            "- 等価置換: なし", "- 反例: ", "",
        ]
    return "\n".join(parts)


def read_spec(text: str) -> list[tuple[str, str]]:
    r = []
    for line in text.splitlines():
        m = SPEC_RE.match(line)
        if m:
            r.append((m.group(1), m.group(2).strip()))
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new", help="仕様項目から対応表の雛形を作る")
    n.add_argument("spec", type=Path)
    n.add_argument("--out", type=Path)
    l = sub.add_parser("lint", help="対応表を検査する（読むだけ）")
    l.add_argument("matrix", type=Path)
    l.add_argument("--spec", type=Path, help="仕様項目の一覧。全項目に節があるかも見る")
    l.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "new":
        if not a.spec.is_file():
            print(f"エラー: ファイルが無い: {a.spec}", file=sys.stderr)
            return 2
        items = read_spec(a.spec.read_text(encoding="utf-8"))
        if not items:
            print("エラー: `S1: ...` の形の仕様項目が読めない", file=sys.stderr)
            return 2
        text = skeleton(items)
        if not a.out:
            print(text)
            print("（下見。書くには --out を指定）")
            return 0
        if a.out.exists():
            print(f"エラー: 既にある。上書きしない: {a.out}", file=sys.stderr)
            return 2
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text + "\n", encoding="utf-8", newline="\n")
        print(f"書いた: {a.out}（{len(items)} 項目）")
        return 0
    if not a.matrix.is_file():
        print(f"エラー: ファイルが無い: {a.matrix}", file=sys.stderr)
        return 2
    spec_ids = None
    if a.spec:
        if not a.spec.is_file():
            print(f"エラー: ファイルが無い: {a.spec}", file=sys.stderr)
            return 2
        spec_ids = [i for i, _ in read_spec(a.spec.read_text(encoding="utf-8"))]
    text = a.matrix.read_text(encoding="utf-8")
    found = lint(text, spec_ids)
    print(f"項目数: {len(parse(text))}")
    for f in found:
        print(f)
    if not found:
        print("指摘なし（記入の形式が揃っているだけ。偽陰性の形が本当に尽くされているかは人間が見る）")
    return 1 if (a.strict and found) else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""入力文書（要望など）を項目に採番し、「こんな感じ」「など」のような曖昧語を持つ項目に印を付ける。

    python number_items.py 要望.txt [--prefix R] [--out 項目.txt]

出力は `R1: 項目の文` の行。採番は逆向き走査（trace_coverage.py）の前提になる。
見出し行（# で始まる行）は採番しない。1 行に複数の文があれば句点で割る。--out を指定し、無いファイルのときだけ書く。
例示に見える語（「こんな感じ」「〜など」「といった形で」）は、それ自体が曖昧語なので落とさず印を付ける。
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

# 長い語を先に。例示に見える語・程度語・指示のぼかし。
AMBIGUOUS = [
    "こんな感じ", "そんな感じ", "いい感じ", "良い感じ", "みたいな", "のような", "といった形", "といった", "とか",
    "など", "等", "適宜", "適切に", "適切な", "なるべく", "できるだけ", "基本的に", "原則として", "必要に応じて",
    "よしなに", "うまく", "ちゃんと", "きちんと", "しっかり", "柔軟に", "十分", "いろいろ", "色々", "何か", "ある程度",
    "見やすく", "わかりやすく", "分かりやすく", "使いやすく", "速く", "高速", "軽く", "簡単に", "すぐ", "できれば",
    "結果が出る", "出力される", "表示される", "保存される",
]
_AMB_RE = re.compile("|".join(re.escape(w) for w in sorted(AMBIGUOUS, key=lambda w: (-len(w), w))))
_BULLET = re.compile(r"^\s*(?:[-*+・]|\d+[.)．])\s+")


def split_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = _BULLET.sub("", s).strip()
        # 句点・感嘆・疑問で割る（記号は文末に残す）
        for part in re.split(r"(?<=[。！？!?])\s*", s):
            part = part.strip()
            if part:
                items.append(part)
    return items


def ambiguous_words(item: str) -> list[str]:
    seen: list[str] = []
    for m in _AMB_RE.finditer(item):
        if m.group(0) not in seen:
            seen.append(m.group(0))
    return seen


def number(text: str, prefix: str = "R") -> list[tuple[str, str, list[str]]]:
    return [(f"{prefix}{i}", it, ambiguous_words(it)) for i, it in enumerate(split_items(text), 1)]


def render(rows) -> str:
    return "\n".join(f"{i}: {t}" + (f"  [曖昧語: {'・'.join(w)}]" if w else "") for i, t, w in rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("input", type=Path)
    ap.add_argument("--prefix", default="R", help="項目番号の接頭辞（既定 R）")
    ap.add_argument("--out", type=Path, help="書き出し先（無いファイルのときだけ書く）")
    a = ap.parse_args(argv)
    if not a.input.is_file():
        print(f"エラー: ファイルが無い: {a.input}", file=sys.stderr)
        return 2
    rows = number(a.input.read_text(encoding="utf-8"), a.prefix)
    body = render(rows)
    n_amb = sum(1 for _, _, w in rows if w)
    if a.out:
        if a.out.exists():
            print(f"エラー: 既にある。上書きしない: {a.out}", file=sys.stderr)
            return 2
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(body, encoding="utf-8", newline="\n")
        print(f"書いた: {a.out}")
    else:
        print(body, end="")
    print(f"項目数: {len(rows)} ／ 曖昧語を含む項目: {n_amb}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

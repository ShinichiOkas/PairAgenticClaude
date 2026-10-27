#!/usr/bin/env python
"""用語定義ファイルを検査し（含む／含まない／境界例／上位語との差／人間の確定の有無）、雛形も作る。

    python lint_glossary.py lint 用語定義.md [--strict]
    python lint_glossary.py new 語1 語2 [--out 用語定義.md]

書式: 語ごとに `## 語` の節。中に `- 含む:` `- 含まない:` `- 境界例:` `- 上位語との差:` `- 確定:` の箇条書き。
片側だけの定義・空欄・「特になし」・AI が自分で選んだ確定を指摘する。`new` は --out を指定し、かつ無いファイルのときだけ書く。
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

KEYS = ["含む", "含まない", "境界例", "上位語との差", "確定"]
REQUIRED = ["含む", "含まない"]
PLACEHOLDER = re.compile(r"^(?:なし|無し|特になし|-|ー|―|tbd|todo|未記入|未定|？|\?|n/?a)?$", re.I)
UNCONFIRMED = re.compile(r"未回答|未確定|未定|保留|^$")
AI_SELF = re.compile(r"AI(?:が|の判断)|自分で(?:選|決)|私が(?:選|決)|推測|おそらく|仮に")
KEYLINE = re.compile(r"^\s*[-*]\s*(含まない|含む|境界例|上位語との差|確定)\s*[:：]\s*(.*)$")


def parse(text: str) -> list[dict]:
    terms: list[dict] = []
    cur: dict | None = None
    last: str | None = None
    for line in text.splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", line)
        if h:
            cur = {"term": h.group(1), "fields": {}}
            terms.append(cur)
            last = None
            continue
        if cur is None:
            continue
        m = KEYLINE.match(line)
        if m:
            last = m.group(1)
            cur["fields"][last] = m.group(2).strip()
        elif last and line.startswith((" ", "\t")) and line.strip():
            cur["fields"][last] += (" " if cur["fields"][last] else "") + line.strip().lstrip("-*・ ").strip()
        elif line.strip():
            last = None
    return terms


def lint(text: str) -> list[str]:
    out: list[str] = []
    terms = parse(text)
    if not terms:
        return ["[定義が無い] `## 語` の節が 1 つも無い"]
    seen: set[str] = set()
    for t in terms:
        name, f = t["term"], t["fields"]
        if name in seen:
            out.append(f"[重複] 「{name}」が 2 回定義されている")
        seen.add(name)
        for k in REQUIRED:
            if k not in f:
                out.append(f"[{k}が無い] 「{name}」: `- {k}:` の行が無い（片側だけの定義は境界が確定しない）")
            elif PLACEHOLDER.match(f[k].strip()):
                out.append(f"[{k}が空] 「{name}」: 例が書かれていない")
        if "含む" in f and "含まない" in f and f["含む"].strip() and f["含む"].strip() == f["含まない"].strip():
            out.append(f"[含む・含まないが同一] 「{name}」: 同じ内容が両側にある")
        if "境界例" not in f or PLACEHOLDER.match(f.get("境界例", "").strip()):
            out.append(f"[境界例が無い] 「{name}」: 中心例は誰も間違えない。境界例を 1 つ以上")
        if "上位語との差" not in f or PLACEHOLDER.match(f.get("上位語との差", "").strip()):
            out.append(f"[上位語との差が無い] 「{name}」: 「これは X の一種だが Y の点で違う」の形で")
        c = f.get("確定", None)
        if c is None or UNCONFIRMED.search(c.strip()):
            out.append(f"[未確定] 「{name}」: 人間の回答による確定が無い（確定は人間の回答による）")
        elif AI_SELF.search(c):
            out.append(f"[自分で選んだ疑い] 「{name}」: 確定欄に AI が選んだ旨の語がある → {c}")
    return out


def skeleton(names: list[str]) -> str:
    parts = ["# 用語定義", ""]
    for n in names:
        parts += [
            f"## {n}", "",
            "- 含む: ", "- 含まない: ", "- 境界例: ", "- 上位語との差: ", "- 確定: 未回答", "",
        ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("lint", help="用語定義ファイルを検査する（読むだけ）")
    l.add_argument("file", type=Path)
    l.add_argument("--strict", action="store_true", help="指摘があれば終了コード 1")
    n = sub.add_parser("new", help="雛形を作る（--out を指定し、無いファイルのときだけ書く）")
    n.add_argument("terms", nargs="+")
    n.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "lint":
        if not a.file.is_file():
            print(f"エラー: ファイルが無い: {a.file}", file=sys.stderr)
            return 2
        text = a.file.read_text(encoding="utf-8")
        found = lint(text)
        print(f"語の数: {len(parse(text))}")
        for f in found:
            print(f)
        if not found:
            print("指摘なし")
        return 1 if (a.strict and found) else 0
    text = skeleton(a.terms)
    if not a.out:
        print(text)
        print("（下見。書くには --out を指定）")
        return 0
    if a.out.exists():
        print(f"エラー: 既にある。上書きしない: {a.out}", file=sys.stderr)
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(f"書いた: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

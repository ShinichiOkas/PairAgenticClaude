#!/usr/bin/env python3
"""文書ごとに「正の向き」の宣言が冒頭にあるかを検査し、宣言の雛形も出す（読むだけ）。

宣言の書式（文書の冒頭 30 行以内。行頭の `>` `#` `-` `*` や <!-- --> は許す）:
  正の向き: 実装が正          （または 文書が正 / 生成物）
  生成コマンド: <コマンド>     （生成物のとき必須。「手で編集しない」も書く）
  実装の担い手: <誰が直すか>   （文書が正のとき必須）

使い方:
  python check_direction.py check docs README.md          # 検査（宣言なし・両方が正・必須行の欠け）
  python check_direction.py scaffold --kind 生成物         # 冒頭に貼る雛形を標準出力へ
LLM・ネットワークは呼ばない。何も書き込まない。違反があれば終了コード 1。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

HEAD_LINES = 30
DOC_SUFFIXES = {".md", ".txt", ".rst", ".adoc"}
RE_DIR = re.compile(r"正の向き\s*[:：]\s*(.+)")
RE_CMD = re.compile(r"生成コマンド\s*[:：]\s*(\S.*)")
RE_OWNER = re.compile(r"実装の担い手\s*[:：]\s*(\S.*)")
NO_EDIT = re.compile(r"手で編集しない|手で直さない|DO NOT EDIT|do not edit", re.I)

SCAFFOLDS = {
    "実装が正": "> 正の向き: 実装が正\n> （食い違ったら文書を直す）\n",
    "文書が正": "> 正の向き: 文書が正\n> 実装の担い手: <誰が実装を直すか>\n",
    "生成物": "> 正の向き: 生成物（正は常に元）\n> 生成コマンド: <元から生成するコマンド>\n> 手で編集しない。直すときは元を直して再生成する。\n",
}


def classify(value: str) -> str:
    v = value.strip()
    has_impl = "実装が正" in v or "実装" in v and "正" in v and "文書" not in v
    has_doc = "文書が正" in v
    if ("両方" in v) or (has_impl and has_doc):
        return "両方"
    if "生成物" in v:
        return "生成物"
    if has_doc:
        return "文書が正"
    if "実装が正" in v or has_impl:
        return "実装が正"
    return "不明"


def check_text(text: str) -> dict:
    head = text.splitlines()[:HEAD_LINES]
    joined = "\n".join(head)
    m = RE_DIR.search(joined)
    problems: list[str] = []
    if not m:
        return {"declared": None, "problems": ["正の向きの宣言が冒頭 30 行に無い"]}
    kind = classify(m.group(1))
    if kind == "両方":
        problems.append("「両方が正」は宣言ではない（どちらかに決める）")
    elif kind == "不明":
        problems.append(f"宣言の値を読めない: {m.group(1).strip()!r}（実装が正 / 文書が正 / 生成物）")
    elif kind == "生成物":
        if not RE_CMD.search(joined):
            problems.append("生成物なのに「生成コマンド:」が無い")
        if not NO_EDIT.search(joined):
            problems.append("生成物なのに「手で編集しない」の明記が無い")
    elif kind == "文書が正":
        if not RE_OWNER.search(joined):
            problems.append("文書が正なのに「実装の担い手:」が無い")
    return {"declared": kind, "problems": problems}


def collect(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            out.extend(f for f in sorted(p.rglob("*")) if f.is_file() and f.suffix.lower() in DOC_SUFFIXES)
        elif p.is_file():
            out.append(p)
    return out


def cmd_check(a) -> int:
    results = []
    for f in collect(a.paths):
        r = check_text(f.read_text(encoding="utf-8", errors="replace"))
        r["file"] = f.as_posix()
        results.append(r)
    bad = [r for r in results if r["problems"]]
    if a.json:
        print(json.dumps({"results": results, "violations": len(bad)}, ensure_ascii=False, indent=2))
    else:
        print(f"文書 {len(results)} 件 / 違反 {len(bad)} 件")
        for r in results:
            tag = r["declared"] or "宣言なし"
            print(f"- {r['file']}: {tag}")
            for p in r["problems"]:
                print(f"    ! {p}")
    return 1 if bad else 0


def cmd_scaffold(a) -> int:
    print(SCAFFOLDS[a.kind], end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="宣言の有無と整合を検査する")
    c.add_argument("paths", nargs="+")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)
    s = sub.add_parser("scaffold", help="宣言の雛形を出す")
    s.add_argument("--kind", required=True, choices=sorted(SCAFFOLDS))
    s.set_defaults(fn=cmd_scaffold)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())

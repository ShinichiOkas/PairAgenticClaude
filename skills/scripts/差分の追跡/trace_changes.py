#!/usr/bin/env python3
"""変更されたファイルの一覧から、それを参照している文書を引き、引けなかった変更と文書側が古い対応を一覧にする（読むだけ）。

使い方:
  git diff --name-only v1..v2 | python trace_changes.py --docs docs README.md
  python trace_changes.py --changes changes.txt --docs docs --repo-root . --json

変更一覧は 1 行 1 パス（`git diff --name-only` / `git log --name-only --pretty=format:` の出力）。
文書がその変更を参照しているとは、文書の本文に「リポジトリ相対パス」または「ファイル名」が現れること。
LLM・ネットワークは呼ばない。何も書き込まない。引けなかった変更は「該当なし」として必ず出す。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

DOC_SUFFIXES = {".md", ".txt", ".rst", ".adoc"}


def read_changes(text: str) -> list[str]:
    seen: list[str] = []
    for line in text.splitlines():
        p = line.strip().replace("\\", "/")
        if not p or p.startswith("#"):
            continue
        if p not in seen:
            seen.append(p)
    return seen


def collect_docs(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in DOC_SUFFIXES:
                    out.append(f)
        elif p.is_file():
            out.append(p)
    uniq: list[Path] = []
    for f in out:
        if f not in uniq:
            uniq.append(f)
    return uniq


def mentions(text: str, change: str) -> str | None:
    """text が change を参照していれば、一致の種類（'path' / 'name'）を返す。"""
    if change in text:
        return "path"
    name = change.rsplit("/", 1)[-1]
    if len(name) >= 4 and re.search(r"(?<![\w.-])" + re.escape(name) + r"(?![\w-])", text):
        return "name"
    return None


def trace(changes: list[str], docs: list[Path], repo_root: Path | None = None,
          with_mtime: bool = False) -> dict:
    texts = {}
    for d in docs:
        try:
            texts[d] = d.read_text(encoding="utf-8", errors="replace").replace("\\", "/")
        except OSError:
            texts[d] = ""
    rows = []
    for ch in changes:
        # 文書自身の変更は「文書側の更新」であって追跡対象ではない
        hits = []
        for d in docs:
            if d.as_posix().endswith(ch) or ch.endswith(d.as_posix()):
                continue
            kind = mentions(texts[d], ch)
            if kind:
                hits.append({"doc": d.as_posix(), "match": kind})
        row = {"change": ch, "docs": hits}
        if with_mtime and repo_root is not None:
            src = repo_root / ch
            if src.exists():
                sm = src.stat().st_mtime
                row["source_mtime"] = sm
                for h in row["docs"]:
                    dm = Path(h["doc"]).stat().st_mtime
                    h["doc_older_than_source"] = dm < sm
        rows.append(row)
    unmatched = [r["change"] for r in rows if not r["docs"]]
    stale = sorted({h["doc"] for r in rows for h in r["docs"] if h.get("doc_older_than_source")})
    return {"changes": rows, "unmatched": unmatched, "stale_docs": stale,
            "counts": {"changes": len(rows), "matched": len(rows) - len(unmatched),
                       "unmatched": len(unmatched), "docs_scanned": len(docs)}}


def render(res: dict) -> str:
    c = res["counts"]
    lines = [f"変更 {c['changes']} 件 / 文書 {c['docs_scanned']} 件を走査 / 引けた {c['matched']} 件 / 該当なし {c['unmatched']} 件", ""]
    for r in res["changes"]:
        if r["docs"]:
            lines.append(f"- {r['change']}")
            for h in r["docs"]:
                flag = " [文書の方が古い]" if h.get("doc_older_than_source") else ""
                lines.append(f"    -> {h['doc']} ({h['match']}一致){flag}")
    lines.append("")
    lines.append("## 該当なし（文書から引けなかった変更）")
    lines.extend([f"- {u}" for u in res["unmatched"]] or ["- （なし）"])
    if res["stale_docs"]:
        lines.append("")
        lines.append("## 更新日が実装より古い文書")
        lines.extend(f"- {d}" for d in res["stale_docs"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--changes", help="変更一覧ファイル（省略時は標準入力）")
    ap.add_argument("--docs", nargs="+", required=True, help="文書のファイルまたはディレクトリ")
    ap.add_argument("--repo-root", help="変更パスの基準ディレクトリ（--with-mtime で使う）")
    ap.add_argument("--with-mtime", action="store_true", help="文書とソースの更新日を比べる（実ファイルの mtime に依存）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    text = Path(a.changes).read_text(encoding="utf-8") if a.changes else sys.stdin.read()
    changes = read_changes(text)
    docs = collect_docs(a.docs)
    root = Path(a.repo_root) if a.repo_root else None
    res = trace(changes, docs, root, a.with_mtime)
    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else render(res))
    return 0 if not res["unmatched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

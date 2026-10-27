#!/usr/bin/env python3
"""師匠の用語定義を vocab-<term>.md の定形で登録し、既知の用語を引く／テキスト中の既知用語を洗い出す。既定は下見、--apply で書く。

使い方:
  python vocab_ops.py add --term シンプル --include 外部依存なし --exclude 機能が少ない --example "..." --tags design --apply
  python vocab_ops.py find シンプル             # 既に学んだ用語か（部分一致）
  python vocab_ops.py scan --file notes.txt     # テキスト中に出る既知用語を列挙（再確認を避ける）
  python vocab_ops.py list

定義は「含むもの」と「含まないもの」の両方が必須（用語定義の書き方）。同名は上書きせず、定義変更は --update で改訂履歴つきで置換する。
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

DEFAULT_HOME = Path.home() / ".claude" / "pair-agent"


def term_filename(term: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|\s]+', "-", term.strip()).strip("-")
    return f"vocab-{safe}.md"


def stamp(now: str) -> str:
    return now or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def render(term: str, tags: list[str], inc: list[str], exc: list[str], example: str, ts: str, created: str) -> str:
    inc_s = "\n".join(f"- {x}" for x in inc)
    exc_s = "\n".join(f"- {x}" for x in exc)
    return (
        "---\n"
        f"name: vocab-{term}\n"
        "category: vocabulary\n"
        "maturity: confirmed\n"
        f"domain_tags: [{', '.join(tags)}]\n"
        "proposed_by: human\n"
        "confirmed_by: human\n"
        f"created_at: {created}\n"
        f"updated_at: {ts}\n"
        "---\n\n"
        f"# 「{term}」の定義\n\n"
        f"この師匠が「{term}」と言うとき:\n\n"
        f"含むもの:\n{inc_s}\n\n含まないもの:\n{exc_s}\n"
        + (f"\n例: {example}\n" if example else "")
    )


def load_terms(home: Path) -> list[dict]:
    out = []
    d = home / "skills"
    for f in sorted(d.glob("vocab-*.md")) if d.is_dir() else []:
        t = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^#\s*「(.+?)」の定義", t, re.M)
        term = m.group(1) if m else f.stem[len("vocab-"):]
        out.append({"term": term, "file": f, "text": t})
    return out


def cmd_add(a) -> int:
    if not a.include or not a.exclude:
        print("ERROR: 定義には --include と --exclude の両方が要る（含むものと含まないもの）", file=sys.stderr)
        return 2
    ts = stamp(a.now)
    target = Path(a.home) / "skills" / term_filename(a.term)
    tags = [t.strip() for t in a.tags.split(",") if t.strip()]
    created = ts
    if target.exists():
        if not a.update:
            print(f"既知の用語（上書きしない。定義が変わったときだけ --update）: {target}")
            return 3
        old = target.read_text(encoding="utf-8")
        m = re.search(r"^created_at:\s*(.*)$", old, re.M)
        created = m.group(1).strip() if m else ts
    body = render(a.term, tags, a.include, a.exclude, a.example, ts, created)
    if target.exists():
        body += f"\n## 改訂履歴\n\n- [{ts}] 定義を更新\n"
    if not a.apply:
        print(f"[下見] {target}\n\n{body}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")
    print(f"登録した: {target}")
    return 0


def cmd_find(a) -> int:
    q = a.term.lower()
    hits = [t for t in load_terms(Path(a.home)) if q in t["term"].lower() or t["term"].lower() in q]
    if not hits:
        print(f"未知の用語: {a.term}（確認して登録する）")
        return 1
    for t in hits:
        print(f"- 「{t['term']}」 {t['file'].name}")
    return 0


def cmd_scan(a) -> int:
    text = Path(a.file).read_text(encoding="utf-8", errors="replace") if a.file else sys.stdin.read()
    found = [t for t in load_terms(Path(a.home)) if t["term"] and t["term"] in text]
    for t in found:
        print(f"既知: 「{t['term']}」 -> {t['file'].name}（再確認しない）")
    print(f"\n既知の用語 {len(found)} 件")
    return 0


def cmd_list(a) -> int:
    ts = load_terms(Path(a.home))
    for t in ts:
        ok = "含まない" in t["text"] and "含む" in t["text"]
        print(f"- 「{t['term']}」 {t['file'].name}" + ("" if ok else "  [注意: 含む/含まないの片方が無い]"))
    print(f"\n{len(ts)} 件")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--home", default=str(DEFAULT_HOME))
    p.add_argument("--now", default="")
    sub = p.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add")
    ad.add_argument("--term", required=True)
    ad.add_argument("--include", action="append", default=[])
    ad.add_argument("--exclude", action="append", default=[])
    ad.add_argument("--example", default="")
    ad.add_argument("--tags", default="")
    ad.add_argument("--update", action="store_true")
    ad.add_argument("--apply", action="store_true")
    f = sub.add_parser("find")
    f.add_argument("term")
    s = sub.add_parser("scan")
    s.add_argument("--file", default="", help="省略時は標準入力")
    sub.add_parser("list")
    a = p.parse_args(argv)
    return {"add": cmd_add, "find": cmd_find, "scan": cmd_scan, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

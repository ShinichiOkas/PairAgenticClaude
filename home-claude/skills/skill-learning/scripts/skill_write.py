#!/usr/bin/env python3
"""Skill の新規作成（定型の雛形）と maturity の昇格（フロントマター更新＋改訂履歴の追記）をする。既定は下見、--apply で書く。

使い方:
  python skill_write.py new --name my-rule --category process --maturity confirmed \
      --tags git --body "実装前に仕様書を作る" --quote "師匠の原文" --apply
  python skill_write.py promote ~/.claude/pair-agent/skills/my-rule.md --to confirmed --by 師匠 --quote "原文" --apply

昇格は draft -> forming -> confirmed の順。draft -> confirmed は師匠の原文（--quote）があるときだけ。
降格（取り消し）は --demote を付ける。既存ファイルへの new は上書きしない。
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
ORDER = ["draft", "forming", "confirmed"]
CATEGORIES = ("process", "domain", "vocabulary", "user_model")


def now_stamp(now: str) -> str:
    return now or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def set_fm_field(text: str, key: str, value: str) -> str:
    """フロントマターの key を置換（無ければ末尾に追加）。他の行は触らない。"""
    m = re.match(r"^(---[ \t]*\r?\n)(.*?)(\r?\n---)", text, re.S)
    if not m:
        raise ValueError("フロントマターが無い")
    lines = m.group(2).split("\n")
    out, done = [], False
    for ln in lines:
        if re.match(rf"^{re.escape(key)}\s*:", ln):
            out.append(f"{key}: {value}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"{key}: {value}")
    return m.group(1) + "\n".join(out) + m.group(3) + text[m.end():]


def get_fm_field(text: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}\s*:\s*(.*?)\s*$", text.split("\n---", 2)[0], re.M)
    return m.group(1).strip("'\"") if m else ""


def append_history(text: str, line: str) -> str:
    if "## 改訂履歴" in text:
        return text.rstrip("\n") + f"\n{line}\n"
    return text.rstrip("\n") + f"\n\n## 改訂履歴\n\n{line}\n"


MIN_QUOTE = 15


def extract_quotes(text: str) -> list[str]:
    """師匠の原文引用を取り出す: 「…」で囲まれた 15 文字以上（同一行内）と、`> ` で始まる引用行の 15 文字以上。
    空白は連続を 1 つにして比べる。"""
    found: list[str] = []
    for ln in text.splitlines():
        cands = re.findall(r"「([^「」]+)」", ln)
        m = re.match(r"^\s*>\s?(.*)$", ln)
        if m:
            cands.append(m.group(1))
        for c in cands:
            n = " ".join(c.split())
            if len(n) >= MIN_QUOTE and n not in found:
                found.append(n)
    return found


def find_same_quote(base: Path, new_text: str) -> tuple[str, str] | None:
    """書き込み先ディレクトリの既存 .md に、新しい本文と同じ引用が有れば (ファイル名, 引用) を返す。"""
    quotes = extract_quotes(new_text)
    if not quotes or not base.is_dir():
        return None
    for f in sorted(base.glob("*.md")):
        try:
            have = extract_quotes(f.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        for q in quotes:
            if q in have:
                return f.name, q
    return None


def cmd_new(a) -> int:
    ts = now_stamp(a.now)
    name = a.name
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        print("ERROR: --name は英数字・ハイフン・アンダースコア（ファイル名になる）", file=sys.stderr)
        return 2
    if a.maturity == "confirmed" and not a.quote:
        print("ERROR: confirmed で新規登録するには師匠の原文 --quote が要る（AI の観測だけなら forming）", file=sys.stderr)
        return 2
    base = Path(a.dir) if a.dir else Path(a.home) / "skills"
    target = base / f"{name}.md"
    if target.exists():
        print(f"ERROR: 既に有る（上書きしない）: {target}", file=sys.stderr)
        return 3
    proposed_by = "human" if a.maturity == "confirmed" else "ai"
    confirmed_by = "human" if a.maturity == "confirmed" else "null"
    body = (
        "---\n"
        f"name: {name}\n"
        f"category: {a.category}\n"
        f"maturity: {a.maturity}\n"
        f"domain_tags: [{', '.join(t.strip() for t in a.tags.split(',') if t.strip())}]\n"
        f"source_sprint_ids: [{a.sprint_id}]\n"
        f"proposed_by: {proposed_by}\n"
        f"confirmed_by: {confirmed_by}\n"
        f"created_at: {ts}\n"
        f"updated_at: {ts}\n"
        "---\n\n"
        f"# {a.title or name}\n\n"
        f"{a.body}\n"
    )
    if a.quote:
        body += f"\n## 師匠の原文\n\n> {a.quote}\n"
    body += f"\n## 改訂履歴\n\n- [{ts}] 初版作成 (by: {proposed_by})\n"
    if not a.allow_same_quote:
        hit = find_same_quote(base, body)
        if hit:
            print(f"ERROR: 同じ宣言の既存 Skill: {hit[0]}（引用: {hit[1]}）。"
                  "新しく作らず、その Skill へ追記する（意図して別 Skill にするなら --allow-same-quote）", file=sys.stderr)
            return 4
    if not a.apply:
        print(f"[下見] {target}\n\n{body}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")
    print(f"登録した: {target} ({a.maturity})")
    return 0


def cmd_promote(a) -> int:
    path = Path(a.file)
    if not path.is_file():
        print(f"ERROR: 無い: {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    cur = get_fm_field(text, "maturity")
    if cur not in ORDER:
        print(f"ERROR: 現在の maturity が不正: {cur!r}", file=sys.stderr)
        return 2
    to = a.to
    ci, ti = ORDER.index(cur), ORDER.index(to)
    if ti == ci:
        print(f"変更なし: すでに {cur}")
        return 0
    if ti < ci and not a.demote:
        print("ERROR: 降格には --demote（師匠の取り消し。CorrectionRecord にも残すこと）", file=sys.stderr)
        return 2
    if ti > ci + 1 and not a.quote:
        print("ERROR: draft -> confirmed は師匠の原文 --quote があるときだけ", file=sys.stderr)
        return 2
    if to == "confirmed" and not (a.quote or a.by):
        print("ERROR: confirmed への昇格には --by か --quote（根拠）が要る", file=sys.stderr)
        return 2
    ts = now_stamp(a.now)
    new = set_fm_field(text, "maturity", to)
    new = set_fm_field(new, "updated_at", ts)
    if to == "confirmed":
        new = set_fm_field(new, "confirmed_by", a.by or "human")
        new = set_fm_field(new, "confirmed_at", ts[:10])
    elif ti < ci:
        new = set_fm_field(new, "confirmed_by", "null")
    why = f"（根拠: {a.quote}）" if a.quote else ""
    verb = "降格" if ti < ci else "昇格"
    new = append_history(new, f"- [{ts}] maturity {cur} -> {to} {verb}{why} (by: {a.by or 'ai'})")
    if not a.apply:
        print(f"[下見] {path}: {cur} -> {to}")
        return 0
    path.write_text(new, encoding="utf-8", newline="\n")
    print(f"{verb}した: {path}: {cur} -> {to}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--home", default=str(DEFAULT_HOME))
    p.add_argument("--now", default="", help="タイムスタンプの固定（テスト用。既定は現在時刻）")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--name", required=True)
    n.add_argument("--category", required=True, choices=CATEGORIES)
    n.add_argument("--maturity", default="forming", choices=ORDER)
    n.add_argument("--tags", default="")
    n.add_argument("--title", default="")
    n.add_argument("--body", required=True)
    n.add_argument("--quote", default="", help="師匠の原文（confirmed には必須）")
    n.add_argument("--sprint-id", default="")
    n.add_argument("--dir", default="", help="保存先（既定 <home>/skills。プロジェクト固有なら .pair-agent/skills）")
    n.add_argument("--allow-same-quote", action="store_true",
                   help="同じ師匠の原文を持つ既存 Skill が有っても別 Skill として書く（二重登録検査を外す）")
    n.add_argument("--apply", action="store_true")
    pr =sub.add_parser("promote")
    pr.add_argument("file")
    pr.add_argument("--to", required=True, choices=ORDER)
    pr.add_argument("--by", default="")
    pr.add_argument("--quote", default="")
    pr.add_argument("--demote", action="store_true")
    pr.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    return cmd_new(a) if a.cmd == "new" else cmd_promote(a)


if __name__ == "__main__":
    sys.exit(main())

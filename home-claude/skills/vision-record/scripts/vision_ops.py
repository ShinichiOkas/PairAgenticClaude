#!/usr/bin/env python3
"""師匠が自分から述べたビジョンを vision/<sprint_id>.md の定形で記録し、過去のビジョンを検索し、繰り返し現れる関心を数える。既定は下見、--apply で書く。

使い方:
  python vision_ops.py add --sprint-id S1 --goal "認証の刷新" --project myproj --said "原文" \
      --match "login.py: 想定どおり" --differ "audit: 想定外" --learn "auth: 外部依存を嫌う" --apply
  python vision_ops.py search --keyword 認証            # 協議で「前回はこういうイメージでしたが」と出す材料
  python vision_ops.py patterns --min 2                 # 「ドメイン別の学び」に 2 回以上出た領域 = user_model 候補

ビジョンは師匠が自分から述べたときだけ記録する（振り返りで問いかけない）。--said が空なら記録しない。
"""
from __future__ import annotations

import argparse
import collections
import datetime
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_HOME = Path.home() / ".claude" / "pair-agent"


def stamp(now: str) -> str:
    return now or datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def render(a, ts: str) -> str:
    def bullets(xs: list[str]) -> str:
        return "\n".join(f"- {x}" for x in xs) if xs else "- （なし）"
    return (
        "---\n"
        f"sprint_id: {a.sprint_id}\n"
        f"recorded_at: {ts}\n"
        f'sprint_goal: "{a.goal}"\n'
        f'project: "{a.project}"\n'
        "---\n\n"
        f"# ビジョン記録: {a.goal}\n\n"
        f"## 頭の中にあったもの\n\n{a.said}\n\n"
        f"## イメージと合致した箇所\n\n{bullets(a.match)}\n\n"
        f"## イメージと異なった箇所\n\n{bullets(a.differ)}\n\n"
        f"## ドメイン別の学び\n\n{bullets(a.learn)}\n"
    )


def cmd_add(a) -> int:
    if not a.said.strip():
        print("ERROR: 師匠の言葉（--said）が空。ビジョンは師匠が述べたときだけ記録する（問いかけて作らない）", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", a.sprint_id):
        print("ERROR: --sprint-id は英数字・ハイフン等（ファイル名になる）", file=sys.stderr)
        return 2
    target = Path(a.home) / "vision" / f"{a.sprint_id}.md"
    if target.exists():
        print(f"ERROR: 既に有る（上書きしない）: {target}", file=sys.stderr)
        return 3
    body = render(a, stamp(a.now))
    if not a.apply:
        print(f"[下見] {target}\n\n{body}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")
    print(f"記録した: {target}")
    return 0


def files(home: Path) -> list[Path]:
    d = home / "vision"
    return sorted(d.glob("*.md")) if d.is_dir() else []


def title_of(text: str, fallback: str) -> str:
    m = re.search(r"^#\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


def cmd_search(a) -> int:
    kws = [k.lower() for k in a.keyword]
    n = 0
    for f in files(Path(a.home)):
        t = f.read_text(encoding="utf-8", errors="replace")
        low = t.lower()
        if not all(k in low for k in kws):
            continue
        n += 1
        print(f"- {f.name}: {title_of(t, f.stem)}")
        shown = 0
        for line in t.splitlines():
            if any(k in line.lower() for k in kws) and shown < a.context:
                print(f"    {line.strip()[:140]}")
                shown += 1
    print(f"\n{n} 件")
    return 0


def cmd_patterns(a) -> int:
    c: collections.Counter[str] = collections.Counter()
    where: dict[str, list[str]] = collections.defaultdict(list)
    for f in files(Path(a.home)):
        t = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^##\s*ドメイン別の学び\s*$(.*?)(?=^##\s|\Z)", t, re.S | re.M)
        if not m:
            continue
        seen = set()
        for line in m.group(1).splitlines():
            lm = re.match(r"^\s*-\s*([^:：]+)[:：]", line)
            if lm:
                seen.add(lm.group(1).strip().lower())
        for d in seen:
            c[d] += 1
            where[d].append(f.name)
    shown = 0
    for d, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])):
        if n >= a.min:
            shown += 1
            print(f"- {d}: {n} 回 ({', '.join(where[d][:4])}) -> user_model Skill 候補")
    if not shown:
        print(f"{a.min} 回以上出た領域はありません")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--home", default=str(DEFAULT_HOME))
    p.add_argument("--now", default="")
    sub = p.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add")
    ad.add_argument("--sprint-id", required=True)
    ad.add_argument("--goal", required=True)
    ad.add_argument("--project", default="")
    ad.add_argument("--said", required=True, help="師匠の回答（原文）")
    ad.add_argument("--match", action="append", default=[], help="'対象: 何が合っていたか'")
    ad.add_argument("--differ", action="append", default=[], help="'対象: 何が違ったか'")
    ad.add_argument("--learn", action="append", default=[], help="'ドメイン: 学んだこと'")
    ad.add_argument("--apply", action="store_true")
    s = sub.add_parser("search")
    s.add_argument("--keyword", action="append", required=True, help="全てを含むものを出す")
    s.add_argument("--context", type=int, default=2)
    pt = sub.add_parser("patterns")
    pt.add_argument("--min", type=int, default=2)
    a = p.parse_args(argv)
    return {"add": cmd_add, "search": cmd_search, "patterns": cmd_patterns}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

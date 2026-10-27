#!/usr/bin/env python3
"""Skill ファイル群のフロントマターを検査し、棚卸しと「協議深度」の判定をする（読むだけ）。

使い方:
  python skill_lint.py lint                       # ペア固有 skills/ を検査（必須項目・maturity・重複名）
  python skill_lint.py lint --dir .pair-agent/skills --dir ~/.claude/pair-agent/skills
  python skill_lint.py inventory                  # maturity x category の件数表
  python skill_lint.py depth --tags git,tests     # confirmed の数から skip / light / thorough を決める

協議深度の規則（Pair Agent 規約）: confirmed process が有る -> follow、confirmed domain 2 件以上 -> skip、
1 件 -> light、draft/forming のみ・無し -> thorough。
"""
from __future__ import annotations

import argparse
import collections
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
MATURITIES = ("draft", "forming", "confirmed")
CATEGORIES = ("process", "domain", "vocabulary", "user_model")


def parse_frontmatter(text: str) -> dict[str, object]:
    text = text.lstrip("﻿")
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return {}
    fm: dict[str, object] = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*?)\s*$", line)
        if not km:
            continue
        k, v = km.group(1), km.group(2)
        if v.startswith("[") and v.endswith("]"):
            fm[k] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        else:
            fm[k] = v.strip("'\"")
    return fm


def load_dir(d: Path) -> list[dict]:
    items = []
    if not d.is_dir():
        return items
    files = sorted(list(d.glob("*.md")) + list(d.glob("*/SKILL.md")))
    for f in files:
        fm = parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        tags = fm.get("domain_tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        items.append({
            "path": f, "fm": fm, "name": str(fm.get("name") or ""),
            "maturity": str(fm.get("maturity") or ""),
            # 既存資産は category の代わりに type を使うことがある
            "category": str(fm.get("category") or fm.get("type") or ""),
            "tags": list(tags),
        })
    return items


def lint(items: list[dict]) -> tuple[list[str], list[str]]:
    errors, warns = [], []
    seen: dict[str, Path] = {}
    for it in items:
        p, fm = it["path"], it["fm"]
        label = f"{p.parent.name}/{p.name}"
        if not fm:
            errors.append(f"{label}: フロントマターが無い")
            continue
        if not it["name"]:
            errors.append(f"{label}: name が無い")
        elif it["name"] in seen:
            errors.append(f"{label}: name '{it['name']}' が {seen[it['name']].name} と重複")
        else:
            seen[it["name"]] = p
        if it["maturity"] not in MATURITIES:
            errors.append(f"{label}: maturity が不正/欠落 ({it['maturity'] or '無し'})")
        if not it["category"]:
            warns.append(f"{label}: category(type) が無い")
        elif it["category"] not in CATEGORIES:
            warns.append(f"{label}: category '{it['category']}' は規定外 {CATEGORIES}")
        if it["maturity"] == "confirmed" and str(fm.get("confirmed_by") or "").lower() in ("", "null", "none"):
            warns.append(f"{label}: confirmed なのに confirmed_by が空")
        if not fm.get("description") and not it["tags"] and "created_at" not in fm:
            warns.append(f"{label}: description / domain_tags / created_at のどれも無い")
    return errors, warns


def decide_depth(items: list[dict], tags: list[str]) -> tuple[str, str]:
    rel = [i for i in items if not tags or set(tags) & set(i["tags"])]
    conf = [i for i in rel if i["maturity"] == "confirmed"]
    cp = [i for i in conf if i["category"] == "process"]
    cd = [i for i in conf if i["category"] == "domain"]
    if cp:
        return "follow", f"confirmed process Skill が有る: {cp[0]['name']}（そのルールに従う）"
    if len(cd) >= 2:
        return "skip", f"confirmed domain Skill が {len(cd)} 件（信頼して進む）"
    if len(cd) == 1:
        return "light", f"confirmed domain Skill が 1 件: {cd[0]['name']}（軽く確認）"
    return "thorough", "confirmed の process/domain Skill が無い（しっかり詰める）"


def collect(dirs: list[str], home: str) -> list[dict]:
    paths = [Path(d) for d in dirs] or [Path(home) / "skills"]
    items: list[dict] = []
    for d in paths:
        items.extend(load_dir(d))
    return items


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--home", default=str(DEFAULT_HOME))
    p.add_argument("--dir", action="append", default=[], help="検査するディレクトリ（複数可。既定は <home>/skills）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lint")
    sub.add_parser("inventory")
    d = sub.add_parser("depth")
    d.add_argument("--tags", default="", help="タスクのドメインタグ（カンマ区切り。空なら全 Skill が対象）")
    a = p.parse_args(argv)
    items = collect(a.dir, a.home)
    if a.cmd == "lint":
        errors, warns = lint(items)
        for e in errors:
            print("ERROR", e)
        for w in warns:
            print("WARN ", w)
        print(f"\n{len(items)} 件 / ERROR {len(errors)} / WARN {len(warns)}")
        return 1 if errors else 0
    if a.cmd == "inventory":
        c = collections.Counter((i["maturity"] or "(無し)", i["category"] or "(無し)") for i in items)
        print(f"{len(items)} 件")
        for (m, cat), n in sorted(c.items()):
            print(f"  {m:10s} {cat:12s} {n}")
        return 0
    tags = [t.strip() for t in a.tags.split(",") if t.strip()]
    depth, why = decide_depth(items, tags)
    print(f"{depth}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

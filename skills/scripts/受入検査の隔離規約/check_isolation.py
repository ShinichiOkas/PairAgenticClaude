#!/usr/bin/env python
"""成果物定義（.mk）を読み、受入検査が「姿勢」ではなく「遮断」でブラックボックスになっているか（deps と blocks）を検める。

    python check_isolation.py models/waterfall-small.mk [他の.mk ...] [--impl 実装物 --impl 設計書]

検査（受入検査仕様・受入検査報告書・設計保証・実行可能物の各 target に対して）:
  [実装物が dep]      受入検査の target が実装物（--impl で増やせる）を直接 deps に持っている
  [遮断の欠落]        受入検査の target の blocks に実装物が無い（実行可能物があるなら受入検査仕様はそれも）
  [迂回路]            受入検査の dep をたどると、機械でも設計保証でもない中継（blocks 済みを除く）が実装物を持っている（遮断の抜け道）
  [設計保証が素通し]  設計保証が deps にあるのに、設計保証 target が blocks に 受入検査仕様 を持たない
  [設計保証が無い]    受入検査が 設計保証 を dep に持つのに、設計保証 を作る target が無い
  [切り出しが機械でない] 実行可能物 が by: machine でない、または実装物以外を deps に持つ（内容を足さない）
  [姿勢の疑い]        blocks に実装物が無いまま、out / post に「見ない」「参照しない」等の姿勢の書き方がある
判定はしない。構造から読める指摘だけを出す。`.mk` の書式は tools/derive_roles.py と同じ（`target : deps` と `# blocks :` ほか）。
終了コード: 0 = 指摘なし ／ 1 = 指摘あり ／ 2 = 入力不正
"""
from __future__ import annotations

import argparse
import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

SUFFIX = re.compile(r"(_v\([a-z](?:[+-]\d+)?\))?\??$")
POSTURE = ("見ない", "見ないように", "参照しない", "読まない", "覗かない", "目を通さない")
ACCEPT_TARGETS = ("受入検査仕様", "受入検査報告書")


def base(name: str) -> str:
    return SUFFIX.sub("", name.strip()).strip()


def split_list(v: str) -> list[str]:
    return [base(p) for p in re.split(r"[,、]", v) if p.strip() and p.strip() not in {"-", "none", "なし"}]


def parse_mk(path: str):
    rules: dict[str, dict] = {}
    cur = None
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip()
            if not line.strip():
                continue
            if line.lstrip().startswith("#"):
                body = line.lstrip()[1:].strip()
                if cur is None or ":" not in body:
                    continue
                key, _, value = body.partition(":")
                key = key.strip().lower()
                if key == "blocks":
                    cur["blocks"] = split_list(value)
                elif key == "by":
                    cur["by"] = value.strip()
                elif key in ("post", "out"):
                    cur["text"] += " " + value
                continue
            if ":" in line and not line.startswith((" ", "\t")):
                t, _, d = line.partition(":")
                cur = {"target": base(t), "deps": split_list(d), "blocks": [], "by": "agent", "text": ""}
                rules[cur["target"]] = cur
    return rules


def check(rules: dict[str, dict], impl: set[str]):
    problems = []

    def add(target, kind, msg):
        problems.append({"target": target, "kind": kind, "message": msg})

    has_exec = "実行可能物" in rules
    for name, r in rules.items():
        if name in ACCEPT_TARGETS:
            if not r["deps"] and not r["blocks"]:
                continue  # 起点（外から与えられる）
            direct = sorted(impl & set(r["deps"]))
            if direct:
                add(name, "実装物が dep", f"deps に {', '.join(direct)} がある。動かせる形（実行可能物）に割って渡す")
            if not (impl & set(r["blocks"])):
                add(name, "遮断の欠落", "blocks に実装物が無い（遮断が構造として書かれていない）")
            elif name == "受入検査仕様" and has_exec and "実行可能物" not in r["blocks"]:
                add(name, "遮断の欠落", "実行可能物があるのに、受入検査仕様の blocks に実行可能物が無い（動くものを見ると『あるものに合わせた』検査になる）")
            if not (impl & set(r["blocks"])) and any(w in r["text"] for w in POSTURE):
                add(name, "姿勢の疑い", "遮断で書けておらず、out/post に「見ない」等の姿勢の書き方がある。成果物の割り方を疑う")
            if name == "受入検査報告書":
                # 迂回路: 機械でも設計保証でもない中継が実装物を持っていないか
                seen, stack = set(), list(r["deps"])
                while stack:
                    n = stack.pop()
                    if n in seen or n not in rules or n in r["blocks"] or n in impl or (impl & set(rules[n]["blocks"])):
                        continue  # 遮断済み・実装物そのもの・自分で実装物を遮断している成果物は中継として数えない
                    seen.add(n)
                    m = rules[n]
                    if n != "設計保証" and not m["by"].startswith("machine") and (impl & set(m["deps"])):
                        add(name, "迂回路", f"{n} が実装物を持つ（by: {m['by']}）。{name} から {n} 経由で実装物に届く")
                    if n != "設計保証" and not m["by"].startswith("machine"):
                        stack.extend(m["deps"])
                if "設計保証" in r["deps"]:
                    if "設計保証" not in rules:
                        add(name, "設計保証が無い", "設計保証を dep に持つが、設計保証を作る target が無い")
                    elif "受入検査仕様" not in rules["設計保証"]["blocks"]:
                        add("設計保証", "設計保証が素通し", "blocks に 受入検査仕様 が無い（保証が検査項目を左右できてしまう）")
        elif name == "実行可能物":
            if not r["by"].startswith("machine"):
                add(name, "切り出しが機械でない", f"by: {r['by']}。内容を足さない切り出しは機械にやらせる")
            extra = [d for d in r["deps"] if d not in impl]
            if extra:
                add(name, "切り出しが機械でない", f"実装物以外の dep がある（{', '.join(extra)}）。内容を足すことになる")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=".mk の受入検査の遮断（deps / blocks）を検める（読むだけ）")
    ap.add_argument("mk", nargs="+")
    ap.add_argument("--impl", action="append", help="遮断すべき成果物名（既定 実装物。複数指定可）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    impl = set(a.impl or ["実装物"])
    result = {}
    try:
        for p in a.mk:
            rules = parse_mk(p)
            if not rules:
                print(f"エラー: {p} に target が 1 つも無い", file=sys.stderr)
                return 2
            result[p] = check(rules, impl)
    except OSError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    total = sum(len(v) for v in result.values())
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for p, probs in result.items():
            print(f"{p}: 指摘 {len(probs)} 件")
            for x in probs:
                print(f"  [{x['kind']}] {x['target']}: {x['message']}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())

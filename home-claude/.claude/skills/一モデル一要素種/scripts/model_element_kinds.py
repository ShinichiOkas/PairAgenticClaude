#!/usr/bin/env python
"""関連（relation）でつながる要素の集まりを一枚の図とみなし、一枚に複数の要素種が混ざっているものを指摘する。

    python model_element_kinds.py [--db PATH] [--backend json|sqlite] [--json] [ID …]

読む規則: no_predicate（関連に述語が無い）、mixed_kinds（中核の検出。図 MO と shows で明示した図の要素種の混在）。
DB に図 MO が 1 枚でもあれば混在は中核の mixed_kinds の検出をそのまま出す。MO が 1 枚も無い DB では連結成分から推定し、
  ID を inferred_mixed_kinds:<要素ID> にして「図が DB に無いので関連のつながりから推定した」と書く。
出すもの: 関連でつながる要素の連結成分（＝一枚の図）ごとの要素種と要素、種類が 2 つ以上の図（混在）、割り付けの図（allocates。ここだけは混在してよい例外）。
ID を渡すと、その要素を含む図だけを出す。混在は problems として出し、終了コード 1 にする。
読むだけ（DB に書かない）。--db --backend --json は中核 design_graph.py と同じ名前。
design_graph.py の探し方: 環境変数 PAIR_AGENT_DESIGN_GRAPH → このスクリプトから上へ辿った tools/design_graph.py
  → ~/.claude/pair-agent/tools/ → ~/.gemini/config/pair-agent/tools/。見つからなければ探した場所を出して終了コード 2。
終了コード: 0 = 指摘なし ／ 1 = 指摘あり ／ 2 = 入力不正・DB が無い・中核が見つからない
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ENV_CORE = "PAIR_AGENT_DESIGN_GRAPH"
ALIVE = ("hypothesis", "confirmed")


class CoreNotFound(Exception):
    """design_graph.py がどこにも無い。tried に探した場所を持つ。"""

    def __init__(self, tried: list[Path]) -> None:
        super().__init__("design_graph.py が見つからない")
        self.tried = tried


def core_candidates() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get(ENV_CORE)
    if env:
        out.append(Path(env))
    here = Path(__file__).resolve().parent
    for d in (here, *here.parents):
        out.append(d / "tools" / "design_graph.py")
    home = Path.home()
    out.append(home / ".claude" / "pair-agent" / "tools" / "design_graph.py")
    out.append(home / ".gemini" / "config" / "pair-agent" / "tools" / "design_graph.py")
    return out


def load_core() -> Any:
    tried = core_candidates()
    for p in tried:
        if p.is_file():
            spec = importlib.util.spec_from_file_location("design_graph", p)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules["design_graph"] = mod
            spec.loader.exec_module(mod)
            return mod
    raise CoreNotFound(tried)


def is_core_error(e: BaseException) -> bool:
    return any(c.__name__ == "DesignGraphError" for c in type(e).__mro__)


def empty(v: Any) -> bool:
    return v is None or (isinstance(v, (str, list, dict, tuple)) and len(v) == 0) or (isinstance(v, str) and not v.strip())


def txt(v: Any) -> str:
    if empty(v):
        return "なし"
    if isinstance(v, str):
        return v
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return "／".join(v)
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def pick(g: Any, rules: tuple[str, ...]) -> list[dict[str, Any]]:
    """この Skill の観点の検出だけ（見送り済みは除く）。"""
    return [{"id": f["id"], "rule": f["rule"], "target": f["target"], "level": f["level"], "message": f["message"]}
            for f in g.check() if f["rule"] in rules]


def finding_lines(findings: list[dict[str, Any]]) -> list[str]:
    out = ["## 検出（design_graph.py check の該当規則）"]
    out += [f"- [{f['id']}] {f['message']}" + ("（情報）" if f["level"] == "info" else "") for f in findings]
    if not findings:
        out.append("- なし")
    return out



DESC = '関連でつながる図ごとに要素種の混在を指摘する。'
RULES: tuple[str, ...] = ('no_predicate', 'mixed_kinds')
INFERRED_NOTE = "図が DB に無いので関連のつながりから推定した"


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("ids", nargs="*", metavar="ID", help="この要素を含む図だけを出す（省くと全部）")


def collect(core: Any, g: Any, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    for i in args.ids:
        if i not in g.nodes:
            raise core.DesignGraphError(f"無い ID: {i}")
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for l in g.links.values():
        if l["kind"] == "relation" and l["state"] in ALIVE and l["src"] in g.nodes and l["dst"] in g.nodes:
            parent[find(l["src"])] = find(l["dst"])
    groups: dict[str, list[str]] = {}
    for x in list(parent):
        groups.setdefault(find(x), []).append(x)
    models: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    # 図（種類 MO）が DB に 1 枚でもあれば、混在は中核の mixed_kinds の検出をそのまま出す。無ければ連結成分で推定する
    has_mo = any(n["kind"] == "model" and n["state"] in ALIVE for n in g.nodes.values())
    lines = ["## 関連でつながる図（連結成分）"]
    if has_mo:
        lines.append("（図 MO が DB にあるので、混在は中核の mixed_kinds の検出で見る。下の連結成分は参考）")
    for members in sorted((sorted(m, key=core.natkey) for m in groups.values()), key=lambda m: core.natkey(m[0])):
        if args.ids and not set(args.ids) & set(members):
            continue
        kinds = sorted({g.nodes[m]["kind"] for m in members})
        mixed = len(kinds) > 1 and not has_mo
        models.append({"elements": members, "kinds": kinds, "mixed": mixed})
        lines.append(f"図 {members[0]}…  要素種: {', '.join(kinds)}  要素: {', '.join(members)}" + ("  ← 混在（推定）" if mixed else ""))
        if mixed:
            problems.append({"id": f"inferred_mixed_kinds:{members[0]}",
                             "message": f"一枚の図に要素種が混ざっている（{', '.join(kinds)}）。{INFERRED_NOTE}。"
                                        "図を分けるか、割り付けの図にする"})
    if not models:
        lines.append("- 関連でつながる図なし")
    alloc = [{"id": l["id"], "src": l["src"], "dst": l["dst"]} for l in sorted(g.links.values(), key=lambda l: core.natkey(l["id"]))
             if l["kind"] == "allocates" and l["state"] in ALIVE]
    lines.append("")
    lines.append("## 割り付けの図（混在してよい例外）")
    lines += [f"- {a['id']}: {a['src']} —allocates→ {a['dst']}" for a in alloc] or ["- なし"]
    if problems:
        lines.append("")
        lines.append("## 要確認")
        lines += [f"- {p['message']}" for p in problems]
    findings = pick(g, RULES)
    return ({"models": models, "allocations": alloc, "problems": problems, "findings": findings},
            lines + [""] + finding_lines(findings))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=DESC)
    ap.add_argument("--db", default=None, help="DB の置き場（既定は中核の既定 .pair-agent/design/graph.jsonl）")
    ap.add_argument("--backend", choices=["json", "sqlite"], default=None, help="省くと --db の拡張子で決める")
    ap.add_argument("--json", action="store_true", help="機械向けの JSON で出す")
    add_args(ap)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        core = load_core()
        _, path = core.resolve_backend(args.db, args.backend)
        if not Path(path).exists():
            raise core.DesignGraphError(f"DB が無い: {path}")
        g = core.DesignGraph(args.db, args.backend, "ai")
        data, lines = collect(core, g, args)
    except CoreNotFound as e:
        print("エラー: design_graph.py が見つからない。探した場所:", file=sys.stderr)
        for p in e.tried:
            print(f"  {p}", file=sys.stderr)
        return 2
    except Exception as e:
        if is_core_error(e):
            print(f"エラー: {e}", file=sys.stderr)
            return 2
        raise
    if args.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print("\n".join(lines))
    bad = any(f["level"] != "info" for f in data["findings"]) or bool(data.get("problems"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

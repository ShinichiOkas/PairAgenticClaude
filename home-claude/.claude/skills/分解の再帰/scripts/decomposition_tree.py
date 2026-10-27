#!/usr/bin/env python
"""要素の分解（親 → 子）を木で出し、親の外との関連と、親に割り付いた要求が、どれかの子に引き継がれているかを検める。

    python decomposition_tree.py [--db PATH] [--backend json|sqlite] [--id ID ...] [--json]

設計の因果 DB（tools/design_graph.py）を読むだけで、書かない。親子は `add --parent`（contains）と refines リンクで読む（案は決定点の子なので除く）。
分解の再帰では、親の外との関連は必ずどれかの子に割り付く。親ごとに次を数える:
  [関連が子に無い]   親と外の要素を結ぶ relation で、子（孫以下を含む）のどれも同じ相手（またはその内側）と結ばれていない
  [要求が子に無い]   親に割り付いた要求を、子のどれも受けていない
親の中どうしの関連（子と子）は外との関連ではないので数えない。--id は親の指定（その親と、その下の分解だけ）。
子を足す・関連を張るのは人と AI が `design_graph.py add／link` で行う。この入口は変えない。
design_graph.py は 環境変数 PAIR_AGENT_DESIGN_GRAPH → 上位の tools/ → ~/.claude/pair-agent/tools/ の順で探す。
終了コード: 0 = 引き継ぎ漏れなし ／ 1 = あり ／ 2 = 入力不正・中核や DB が見つからない
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

sys.dont_write_bytecode = True
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

ENV_CORE = "PAIR_AGENT_DESIGN_GRAPH"
ALIVE = ("hypothesis", "confirmed")
CORE: Any = None


class CoreError(Exception):
    """中核が見つからない・DB が無い・入力が誤り（終了コード 2）。"""


def find_core() -> Path:
    """design_graph.py を探す。環境変数 → 上位の tools/ → install 先の順。見つからなければ探した場所を添えて止まる。"""
    tried: list[str] = []
    env = os.environ.get(ENV_CORE)
    if env:
        tried.append(f"環境変数 {ENV_CORE}={env}")
        if Path(env).is_file():
            return Path(env)
    here = Path(__file__).resolve().parent
    tried.append(f"{here} から上へ辿った tools/design_graph.py")
    for d in (here, *here.parents):
        if (d / "tools" / "design_graph.py").is_file():
            return d / "tools" / "design_graph.py"
    for rel in (".claude/pair-agent/tools/design_graph.py", ".gemini/config/pair-agent/tools/design_graph.py"):
        p = Path.home() / rel
        tried.append(str(p))
        if p.is_file():
            return p
    raise CoreError("design_graph.py が見つからない。探した場所:\n  " + "\n  ".join(tried))


def open_graph(db: str | None, backend: str | None) -> Any:
    """中核を読み込み、DB を読み取り専用の使い方で開く（この入口は書き込みの API を呼ばない）。"""
    global CORE
    path = find_core()
    spec = importlib.util.spec_from_file_location("_design_graph_core", path)
    if spec is None or spec.loader is None:
        raise CoreError(f"design_graph.py を読み込めない: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    CORE = mod
    try:
        _, dbpath = mod.resolve_backend(db, backend)
        if not Path(dbpath).exists():
            raise CoreError(f"DB が無い: {dbpath}（--db で指す。既定は .pair-agent/design/graph.jsonl）")
        return mod.DesignGraph(db, backend, "ai")
    except mod.DesignGraphError as e:
        raise CoreError(str(e)) from e


def natkey(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def entity(g: Any, ident: str) -> dict:
    return g.nodes.get(ident) or g.links.get(ident) or {}


def alive_nodes(g: Any, *kinds: str) -> list[dict]:
    return sorted((n for n in g.nodes.values() if n["kind"] in kinds and n["state"] in ALIVE),
                  key=lambda n: natkey(n["id"]))


def alive_links(g: Any, *kinds: str) -> list[dict]:
    return sorted((l for l in g.links.values() if l["kind"] in kinds and l["state"] in ALIVE),
                  key=lambda l: natkey(l["id"]))


def check_ids(g: Any, ids: list[str] | None) -> set[str]:
    out = set(ids or [])
    for i in sorted(out, key=natkey):
        if i not in g.nodes and i not in g.links:
            raise CoreError(f"その ID は DB に無い: {i}")
    return out


def findings(g: Any, rules: tuple[str, ...], ids: set[str] | None = None) -> list[dict]:
    """中核の check のうち、指定した規則の検出だけ（見送り済みは出ない）。"""
    return [f for f in g.check() if f["rule"] in rules and (not ids or f["target"] in ids)]


def fline(f: dict) -> str:
    return f"[{f['id']}] {f['message']}"


def tree_lines(g: Any, rows: list[dict]) -> list[str]:
    """why の行を木で出す（各段の状態・指している根拠・要再確認）。"""
    out = []
    for r in rows:
        lid = f" {r['link']}" if r["link"] and r["via"] != "ends" else ""
        head = "" if r["depth"] == 0 else f"← {r['via']}{lid} ← "
        ev = ""
        if not r["kind"].startswith("link:"):
            ev = f"  根拠: {', '.join(r['evidence'])}" if r["evidence"] else "  根拠: なし"
        out.append(f"{'  ' * r['depth']}{head}{g.label(r['id'])}{ev}{'  ⚠要再確認' if r['stale'] else ''}")
    return out


def run(argv: list[str] | None, description: str, add_args: Callable[[argparse.ArgumentParser], None],
        analyze: Callable[[Any, argparse.Namespace], tuple[Any, list[str], bool]]) -> int:
    p = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", help="DB の置き場（既定 .pair-agent/design/graph.jsonl）")
    p.add_argument("--backend", choices=["json", "sqlite"], help="省くと --db の拡張子で決める")
    p.add_argument("--json", action="store_true", help="機械向けの JSON で出す")
    add_args(p)
    args = p.parse_args(argv)
    try:
        g = open_graph(args.db, args.backend)
    except CoreError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    try:
        data, lines, bad = analyze(g, args)
    except (CoreError, CORE.DesignGraphError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print("\n".join(lines))
    return 1 if bad else 0


def add_id_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--id", action="append", metavar="ID", help="この ID だけを対象にする（繰り返せる）")


def analyze(g: Any, args: argparse.Namespace) -> tuple[Any, list[str], bool]:
    ids = check_ids(g, args.id)
    kids: dict[str, set[str]] = {}
    for n in alive_nodes(g, *CORE.KINDS):
        par = g.nodes.get(n.get("parent") or "")
        if par and par["kind"] != "decision_point" and n["kind"] != "option":
            kids.setdefault(par["id"], set()).add(n["id"])
    for l in alive_links(g, "refines"):
        if l["src"] in g.nodes and l["dst"] in g.nodes:
            kids.setdefault(l["src"], set()).add(l["dst"])

    def below(p: str, seen: set[str] | None = None) -> set[str]:
        seen = seen if seen is not None else set()
        for c in kids.get(p, ()):
            if c not in seen:
                seen.add(c)
                below(c, seen)
        return seen

    rel = alive_links(g, "relation")
    alloc = alive_links(g, "allocates")
    parents = sorted(kids, key=natkey)
    if ids:
        scope = set(ids)
        for i in ids:
            scope |= below(i)
        parents = [p for p in parents if p in scope]
    items, bad = [], False
    for p in parents:
        inside = below(p) | {p}
        lost_rel, lost_rq = [], []
        for l in rel:
            if p not in (l["src"], l["dst"]):
                continue
            other = l["dst"] if l["src"] == p else l["src"]
            if other in inside:
                continue
            reach = {other} | below(other)
            carried = any((m["src"] in below(p) and m["dst"] in reach) or (m["dst"] in below(p) and m["src"] in reach)
                          for m in rel if m["id"] != l["id"])
            if not carried:
                lost_rel.append({"link": l["id"], "other": other, "predicate": l.get("predicate")})
        for a in alloc:
            if a["dst"] == p and not any(b["src"] == a["src"] and b["dst"] in below(p) for b in alloc):
                lost_rq.append({"link": a["id"], "requirement": a["src"]})
        items.append({"id": p, "title": g.nodes[p]["title"], "children": sorted(kids[p], key=natkey),
                      "lost_relations": lost_rel, "lost_requirements": lost_rq})
        bad = bad or bool(lost_rel or lost_rq)
    lines = []
    child_ids = {c for p in kids for c in kids[p]}

    def draw(p: str, depth: int) -> None:
        lines.append("  " * depth + g.label(p))
        for c in sorted(kids.get(p, ()), key=natkey):
            draw(c, depth + 1)

    shown = {i["id"] for i in items}
    for r in sorted((p for p in kids if p not in child_ids and (p in shown or any(c in shown for c in below(p)))), key=natkey):
        draw(r, 0)
    for it in items:
        for x in it["lost_relations"]:
            lines.append(f"[関連が子に無い] {it['id']} — {x['other']}（{x['link']}・述語 {x['predicate'] or 'なし'}）: 子のどれにも割り付いていない")
        for x in it["lost_requirements"]:
            lines.append(f"[要求が子に無い] {it['id']} に割り付いた {x['requirement']}（{x['link']}）を受ける子が無い")
    if not items:
        lines.append("分解している要素が無い")
    elif not bad:
        lines.append("引き継ぎ漏れなし")
    return {"parents": items}, lines, bad


def main(argv: list[str] | None = None) -> int:
    return run(argv, __doc__ or "", add_id_arg, analyze)


if __name__ == "__main__":
    sys.exit(main())

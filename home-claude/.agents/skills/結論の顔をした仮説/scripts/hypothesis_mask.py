#!/usr/bin/env python
"""結論の顔をした仮説（確定の上流にある仮説）を設計の因果 DB から洗い出し、どの仮説を確かめると何件の確定が顔を取り戻すかを出す。

    python hypothesis_mask.py [--db PATH] [--backend json|sqlite] [--id ID ...] [--json]

設計の因果 DB（tools/design_graph.py）を読むだけで、書かない。中核の検出規則 [hyp_dep]（確定が仮説の上に立つ）だけを出す。
  結論ごと  確定の要素と、その上流の鎖にある仮説（直接の上流か、さらに上流か）
  仮説ごと  その仮説に依存している確定の件数（多い順）。確かめる順番の材料にする（確定にするのは人）
鎖は中核の `why` をそのまま使う。文書へ書き出したとき（export）に仮説が結論の顔で並ばないよう、先にここで数える。
design_graph.py は 環境変数 PAIR_AGENT_DESIGN_GRAPH → 上位の tools/ → ~/.claude/pair-agent/tools/ の順で探す。
終了コード: 0 = 指摘なし ／ 1 = 指摘あり ／ 2 = 入力不正・中核や DB が見つからない
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
    fs = findings(g, ("hyp_dep",), ids)
    conclusions = []
    meta: dict[str, dict[str, str]] = {}
    ledger: dict[str, set[str]] = {}
    for f in fs:
        t = f["target"]
        direct = set(f.get("upstream", []))
        hyps = [r for r in g.why(t) if r["depth"] > 0 and r["state"] == "hypothesis" and not r["kind"].startswith("link:")]
        conclusions.append({"id": t, "title": g.nodes[t]["title"], "kind": g.nodes[t]["kind"],
                            "hypotheses": [{"id": r["id"], "kind": r["kind"], "title": r["title"], "depth": r["depth"],
                                            "direct": r["id"] in direct} for r in hyps]})
        for r in hyps:
            meta[r["id"]] = {"id": r["id"], "kind": r["kind"], "title": r["title"]}
            ledger.setdefault(r["id"], set()).add(t)
    to_confirm: list[dict[str, Any]] = []
    for i in sorted(ledger, key=lambda i: (-len(ledger[i]), natkey(i))):
        to_confirm.append({**meta[i], "conclusions": sorted(ledger[i], key=natkey), "count": len(ledger[i])})
    data = {"conclusions": conclusions, "to_confirm": to_confirm}
    lines: list[str] = []
    if not conclusions:
        lines.append("指摘なし（仮説の上に立つ確定は無い）")
    for c in conclusions:
        lines.append(f"{c['id']}（確定）{c['title']}")
        for h in c["hypotheses"]:
            how = "直接の上流" if h["direct"] else str(h["depth"]) + " 段上流"
            lines.append(f"  仮説 {h['id']} {h['title']}（{how}）")
    if to_confirm:
        lines.append("")
        lines.append("確かめる候補（その仮説に依存する確定の多い順）:")
        lines += [f"  {e['id']} {e['title']} → {e['count']} 件: {', '.join(e['conclusions'])}" for e in to_confirm]
    return data, lines, bool(conclusions)


def main(argv: list[str] | None = None) -> int:
    return run(argv, __doc__ or "", add_id_arg, analyze)


if __name__ == "__main__":
    sys.exit(main())

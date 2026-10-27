#!/usr/bin/env python
"""上流が変わって要再確認になった下流を、人が仕分ける順（上流から一段ずつ）に並べ、仕分けた先に印が進む一段先も出す。

    python triage_queue.py [--db PATH] [--backend json|sqlite] [--json]

設計の因果 DB（tools/design_graph.py）を読むだけで、書かない。中核の `recheck`（上流の版がリンクの見た版より進んだ一段先）と
検出規則 [on_dead]（却下・廃止の上に立つ）を、仕分けの作業表にする:
  先に仕分ける   上流そのものが仕分け待ちではない行（いま仕分けられる）
  後で仕分ける   上流がほかの行の下流で、仕分け待ち（その上流を先に仕分ける）
  一段先         その下流の、さらに下流（仕分けで下流を直すと印が進む先）と、過去の仕分けの回数
仕分けは人が `design_graph.py --actor human triage LINK --ok`（問題なし）か `--issue 課題名`（課題にする）で行う。一括で「問題なし」にしない。
design_graph.py は 環境変数 PAIR_AGENT_DESIGN_GRAPH → 上位の tools/ → ~/.claude/pair-agent/tools/ の順で探す。
終了コード: 0 = 仕分け待ちなし ／ 1 = 仕分け待ちまたは却下・廃止の上に立つ要素あり ／ 2 = 入力不正・中核や DB が見つからない
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
    rows = g.recheck()
    waiting = {m["downstream"] for m in rows}
    edges = g.edges()
    queue = []
    for m in rows:
        nxt = sorted({d for (u, d, _, _) in edges if u == m["downstream"]}, key=natkey)
        past = sum(1 for t in g.triages if t.get("link") == m["link"])
        queue.append({**m, "ready": m["upstream"] not in waiting, "next": nxt, "past_triages": past,
                      "upstream_title": entity(g, m["upstream"]).get("title"),
                      "downstream_title": entity(g, m["downstream"]).get("title")})
    queue.sort(key=lambda q: (not q["ready"], natkey(q["downstream"]), natkey(q["link"])))
    dead = findings(g, ("on_dead",))
    data = {"queue": queue, "on_dead": dead}
    lines = [f"仕分け待ち {len(queue)} 件（先に仕分ける {sum(1 for q in queue if q['ready'])}）"]
    for q in queue:
        tag = "先に" if q["ready"] else "後で（上流 " + q["upstream"] + " が仕分け待ち）"
        lines.append(f"  [{tag}] {q['link']}（{q['kind']}）: {q['downstream']} {q['downstream_title']}"
                     f" ← {q['upstream']} {q['upstream_title']}（見た版 v{q['seen']} → いま v{q['current']}）")
        lines.append(f"      一段先: {', '.join(q['next']) or 'なし'} ／ 過去の仕分け {q['past_triages']} 回")
    if dead:
        lines.append("却下・廃止の上に立つ:")
        lines += ["  " + fline(f) for f in dead]
    if not queue and not dead:
        lines.append("仕分け待ちなし")
    return data, lines, bool(queue or dead)


def main(argv: list[str] | None = None) -> int:
    return run(argv, __doc__ or "", lambda p: None, analyze)


if __name__ == "__main__":
    sys.exit(main())

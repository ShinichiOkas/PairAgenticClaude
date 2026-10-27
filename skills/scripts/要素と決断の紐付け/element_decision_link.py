#!/usr/bin/env python
"""要素（論理コンポーネント・インタフェース）ごとに、生んだ決断（課題 → 採用した案）が結ばれているかを分類し、理由の書けない孤児を指摘する。

    python element_decision_link.py [--db PATH] [--backend json|sqlite] [--id ID ...] [--json]

設計の因果 DB（tools/design_graph.py）を読むだけで、書かない。要素ごとに中核の `why` の鎖を見て分類する:
  決断あり          鎖に案・決定点がある（案が採用か、未決・不採用かも添える。決断が覆ったとき要否を判断する材料）
  自明              attrs.obvious が真（電源スイッチがあること等。決断を書かなくてよい）
  決断なし（上流のみ） 親・導出・割り付けなど上流はあるが、決断は結ばれていない（骨格の要素か、決断の書き忘れか確かめる）
  [orphan]          上流が何も無い。中核の検出規則（決定点が課題につながっていない場合も含む）
決断を結ぶのは `design_graph.py link …`／`add --parent`。この入口は変えない。
design_graph.py は 環境変数 PAIR_AGENT_DESIGN_GRAPH → 上位の tools/ → ~/.claude/pair-agent/tools/ の順で探す。
終了コード: 0 = 孤児なし ／ 1 = 孤児あり ／ 2 = 入力不正・中核や DB が見つからない
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
    orphan = {f["target"]: f for f in findings(g, ("orphan",))}
    items = []
    for n in alive_nodes(g, "component", "interface"):
        if ids and n["id"] not in ids:
            continue
        rows = [r for r in g.why(n["id"]) if r["depth"] > 0 and not r["kind"].startswith("link:")]
        decisions = []
        for r in rows:
            if r["kind"] == "option":
                dp = g.nodes[r["id"]].get("parent")
                d = (g.nodes.get(dp or "") or {}).get("decision")
                status = "採用" if d and d.get("option") == r["id"] else ("不採用" if d else "未決")
                decisions.append({"option": r["id"], "decision_point": dp, "status": status, "option_state": r["state"]})
        if decisions:
            cls = "決断あり"
        elif n["attrs"].get("obvious"):
            cls = "自明"
        elif n["id"] in orphan:
            cls = "孤児"
        else:
            cls = "決断なし（上流のみ）"
        items.append({"id": n["id"], "title": n["title"], "class": cls, "decisions": decisions,
                      "upstream": [r["id"] for r in rows if r["depth"] == 1]})
    dps = [f for f in orphan.values() if g.nodes[f["target"]]["kind"] == "decision_point" and (not ids or f["target"] in ids)]
    counts: dict[str, int] = {}
    for it in items:
        counts[it["class"]] = counts.get(it["class"], 0) + 1
    data = {"elements": items, "orphan_decision_points": dps, "counts": counts}
    lines = ["分類: " + "・".join(f"{k} {v}" for k, v in sorted(counts.items())) if items else "対象の要素が無い"]
    for it in items:
        lines.append(f"  [{it['class']}] {it['id']} {it['title']}")
        for d in it["decisions"]:
            lines.append(f"      決断 {d['decision_point']} → 案 {d['option']}（{d['status']}）")
    lines += [fline(f) for f in dps]
    bad = bool(counts.get("孤児") or dps)
    return data, lines, bad


def main(argv: list[str] | None = None) -> int:
    return run(argv, __doc__ or "", add_id_arg, analyze)


if __name__ == "__main__":
    sys.exit(main())

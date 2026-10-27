#!/usr/bin/env python
"""設計の因果 DB の要素を「AI が出した仮説のまま」と「人が確定・却下・廃止した」に分け、人の手を経ずに仮説を離れた要素・根拠リンクを例外として出す。

    python hypothesis_ledger.py [--db PATH] [--backend json|sqlite] [--json]

設計の因果 DB（tools/design_graph.py）を読むだけで、書かない。各要素の履歴（誰が何を行ったか）から次を数える:
  仮説のまま     仮説の状態で、人が一度も触れていない要素（AI が出した案・仮説。確定に変えられるのは人だけ）
  人が触れた     確定・却下・廃止に変わった要素と、その操作をした人・イベント番号
  例外           仮説でないのに人の操作が履歴に無い要素、人以外が張った根拠（evidence）リンク（権限の外で変わった疑い）
AI の出力を仮説の状態で記録に入れる規約を、DB の履歴で検める。この入口は状態を変えない。
design_graph.py は 環境変数 PAIR_AGENT_DESIGN_GRAPH → 上位の tools/ → ~/.claude/pair-agent/tools/ の順で探す。
終了コード: 0 = 例外なし ／ 1 = 例外あり ／ 2 = 入力不正・中核や DB が見つからない
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


def humans(g: Any, ident: str) -> list[dict]:
    return [h for h in g.history.get(ident, []) if h.get("actor") == "human"]


def analyze(g: Any, args: argparse.Namespace) -> tuple[Any, list[str], bool]:
    hyp, touched, exceptions = [], [], []
    for n in sorted(g.nodes.values(), key=lambda n: natkey(n["id"])):
        hist = g.history.get(n["id"], [])
        creator = next((h["actor"] for h in hist if h["op"] == "create"), None)
        row = {"id": n["id"], "kind": n["kind"], "title": n["title"], "state": n["state"], "created_by": creator}
        hs = humans(g, n["id"])
        if n["state"] == "hypothesis":
            hyp.append({**row, "human_ops": len(hs)})
        else:
            last = hs[-1] if hs else None
            touched.append({**row, "by": last["actor"] if last else None, "seq": last["seq"] if last else None})
            if not hs:
                exceptions.append({**row, "reason": "仮説でないが、人の操作が履歴に無い"})
    for l in alive_links(g, "evidence"):
        if not humans(g, l["id"]):
            exceptions.append({"id": l["id"], "kind": "evidence", "title": f"{l['src']} → {l['dst']}", "state": l["state"],
                               "created_by": None, "reason": "根拠リンクは人だけが張る。履歴に人の操作が無い"})
    data = {"hypothesis_only": hyp, "touched_by_human": touched, "exceptions": exceptions,
            "counts": {"hypothesis_only": len(hyp), "touched_by_human": len(touched), "exceptions": len(exceptions)}}
    lines = [f"仮説のまま {len(hyp)} 件 ／ 人が触れた {len(touched)} 件 ／ 例外 {len(exceptions)} 件"]
    lines += [f"  仮説 {h['id']} {h['title']}（作った者: {h['created_by']}・人の操作 {h['human_ops']} 回）" for h in hyp]
    lines += [f"  {t['state']} {t['id']} {t['title']}（人の操作: seq {t['seq']}）" for t in touched]
    lines += [f"  例外 {e['id']} {e['title']}: {e['reason']}" for e in exceptions]
    return data, lines, bool(exceptions)


def main(argv: list[str] | None = None) -> int:
    return run(argv, __doc__ or "", lambda p: None, analyze)


if __name__ == "__main__":
    sys.exit(main())

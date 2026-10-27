#!/usr/bin/env python
"""割り付けの連鎖（要求 → 論理コンポーネント → … → 実装先）を辿り、どこにも割り付かない要求・要素と、実装先に届いていない連鎖を課題の候補として出す。

    python allocation_gaps.py [--db PATH] [--backend json|sqlite] [--platform ID ...] [--json]

設計の因果 DB（tools/design_graph.py）を読むだけで、書かない。次を課題の候補として出す:
  [unallocated]      割り付けた要素・関連が無い要求
  要素に要求が無い   どの allocates の先にもならない論理コンポーネント・インタフェース（誰のための部品か。自明は attrs.obvious）
  [orphan]           上流の無い要素（中核の検出規則）
  実装先が未定       --platform で実装先の要素（プラットフォーム）を指したとき、連鎖の行き止まりがそこに届いていないもの
連鎖は allocates リンクだけを辿る。実装先へ割り付けると新しい課題が出る（一周目と同じ決定ループで解く）。起票は人が行う。
design_graph.py は 環境変数 PAIR_AGENT_DESIGN_GRAPH → 上位の tools/ → ~/.claude/pair-agent/tools/ の順で探す。
終了コード: 0 = 課題の候補なし ／ 1 = あり ／ 2 = 入力不正・中核や DB が見つからない
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


def add_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--platform", action="append", metavar="ID", help="実装先の要素（繰り返せる）。指すと「実装先が未定」も出す")


def ends_of(g: Any, ident: str) -> list[str]:
    """割り付けの先。関連（リンク）に割り付けたときは、その両端の要素。"""
    l = g.links.get(ident)
    return [l["src"], l["dst"]] if l and l["kind"] == "relation" else [ident]


def analyze(g: Any, args: argparse.Namespace) -> tuple[Any, list[str], bool]:
    platforms = check_ids(g, args.platform)
    out: dict[str, list[str]] = {}
    for l in alive_links(g, "allocates"):
        out.setdefault(l["src"], []).extend(ends_of(g, l["dst"]))
    received = {t for ts in out.values() for t in ts}
    chains: list[list[str]] = []

    def walk(path: list[str]) -> None:
        nxt = [t for t in out.get(path[-1], []) if t not in path]
        if not nxt:
            chains.append(path)
        for t in nxt:
            walk([*path, t])

    for rq in alive_nodes(g, "requirement"):
        if out.get(rq["id"]):
            walk([rq["id"]])
    unalloc = findings(g, ("unallocated",))
    orphans = [f for f in findings(g, ("orphan",)) if g.nodes[f["target"]]["kind"] in ("component", "interface")]
    no_req = [n["id"] for n in alive_nodes(g, "component", "interface")
              if n["id"] not in received and n["id"] not in platforms and not n["attrs"].get("obvious")]
    no_pf = sorted({c[-1] for c in chains if platforms and c[-1] not in platforms}, key=natkey)
    data = {"chains": chains, "unallocated": unalloc, "no_requirement": no_req, "orphans": orphans, "no_platform": no_pf}
    lines = [f"割り付けの連鎖 {len(chains)} 本"]
    lines += ["  " + " → ".join(c) for c in chains]
    lines += [fline(f) for f in unalloc]
    lines += [f"要素に要求が無い: {g.label(i)}" for i in no_req]
    lines += [fline(f) for f in orphans]
    lines += [f"実装先が未定: {g.label(i)}（連鎖の行き止まり）" for i in no_pf]
    bad = bool(unalloc or no_req or orphans or no_pf)
    if not bad:
        lines.append("課題の候補なし")
    return data, lines, bad


def main(argv: list[str] | None = None) -> int:
    return run(argv, __doc__ or "", add_args, analyze)


if __name__ == "__main__":
    sys.exit(main())

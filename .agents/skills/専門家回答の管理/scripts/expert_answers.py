#!/usr/bin/env python
"""専門家などの回答（設計ノート NT）ごとに、どの決定・確定がその回答に依拠しているかを出し、誰も依拠していない回答と、回答を指さない確定を見分ける。

    python expert_answers.py [--db PATH] [--backend json|sqlite] [--match TEXT] [--json]

設計の因果 DB（tools/design_graph.py）を読むだけで、書かない。種類 record（設計ノート）を回答として扱い、次を出す:
  回答ごと     回答の状態、それを根拠（evidence）として指す決定・確定（リンクの状態つき）、回答が検証する要求（verifies）
  誰も依拠しない回答   決定要因として残したのに、どこからも指されていない回答
  [no_evidence]       中核の検出規則。確定なのに回答（根拠）を指していない対象
--match TEXT は、題名・属性に TEXT を含む回答だけを対象にする（専門家名・領域名で絞る用）。
根拠リンクを張るのは人だけ（`design_graph.py --actor human state ID confirmed --evidence NT`）。この入口は変えない。
design_graph.py は 環境変数 PAIR_AGENT_DESIGN_GRAPH → 上位の tools/ → ~/.claude/pair-agent/tools/ の順で探す。
終了コード: 0 = 根拠の無い確定なし ／ 1 = あり ／ 2 = 入力不正・中核や DB が見つからない
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
    p.add_argument("--match", metavar="TEXT", help="題名・属性にこの文字列を含む回答だけ")


def analyze(g: Any, args: argparse.Namespace) -> tuple[Any, list[str], bool]:
    records = []
    for r in sorted((n for n in g.nodes.values() if n["kind"] == "record" and n["state"] in ALIVE), key=lambda n: natkey(n["id"])):
        if args.match and args.match not in r["title"] + json.dumps(r["attrs"], ensure_ascii=False):
            continue
        deps = []
        for l in alive_links(g, "evidence"):
            if l["dst"] == r["id"]:
                s = g.nodes.get(l["src"], {})
                deps.append({"id": l["src"], "title": s.get("title"), "state": s.get("state"), "link": l["id"], "link_state": l["state"]})
        verifies = [l["dst"] for l in alive_links(g, "verifies") if l["src"] == r["id"]]
        records.append({"id": r["id"], "title": r["title"], "state": r["state"], "attrs": r["attrs"],
                        "relied_on_by": deps, "verifies": verifies})
    fs = findings(g, ("no_evidence",))
    unused = [r["id"] for r in records if not r["relied_on_by"]]
    data = {"records": records, "unreferenced": unused, "findings": fs}
    lines = [f"回答（設計ノート） {len(records)} 件"]
    for r in records:
        lines.append(f"{r['id']} [{r['state']}] {r['title']}")
        for d in r["relied_on_by"]:
            lines.append(f"  依拠: {d['id']} {d['title']}（{d['state']}・根拠リンク {d['link']} は{d['link_state']}）")
        if r["verifies"]:
            lines.append("  検証する要求: " + ", ".join(r["verifies"]))
    lines.append("誰も依拠していない回答: " + (", ".join(unused) or "なし"))
    lines += [fline(f) for f in fs]
    return data, lines, bool(fs)


def main(argv: list[str] | None = None) -> int:
    return run(argv, __doc__ or "", add_args, analyze)


if __name__ == "__main__":
    sys.exit(main())

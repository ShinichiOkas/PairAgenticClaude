#!/usr/bin/env python
"""骨格（論理コンポーネントと、述語つきの関連線）を主語・述語・目的語の三つ組で出し、新しく足された要素・述語の無い線・線の引かれていない要素を指摘する。

    python skeleton_derive.py [--db PATH] [--backend json|sqlite] [--json]

設計の因果 DB（tools/design_graph.py）を読むだけで、書かない。生きた論理コンポーネントを由来で分ける:
  骨格         決断にも親にも結ばれていない（ミニマル定義の語から導いた要素。導出元 derives があればそれを添える）
  決断由来     鎖に案がある（骨格に足された要素）
  親から       親（parent／refines）の分解として生まれた要素
  自明         attrs.obvious が真
関連線は relation を「主語 —述語→ 目的語」で出す。指摘:
  [orphan]       上流が何も無い要素（中核の検出規則）
  [no_predicate] 述語の無い線（述語のない線は不完全な文。図に置かない）
  線なし         どの関連線にも載っていない要素（骨格は関連線だけで作る）
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
    comps = alive_nodes(g, "component")
    cid = {c["id"] for c in comps}
    triples = []
    on_line: set[str] = set()
    for l in alive_links(g, "relation"):
        if l["src"] in cid or l["dst"] in cid:
            triples.append({"link": l["id"], "subject": l["src"], "predicate": l.get("predicate"), "object": l["dst"]})
            on_line |= {l["src"], l["dst"]}
    orphan = {f["target"] for f in findings(g, ("orphan",))}
    elements = []
    for c in comps:
        rows = [r for r in g.why(c["id"]) if r["depth"] > 0 and not r["kind"].startswith("link:")]
        derived = [l["src"] for l in alive_links(g, "derives") if l["dst"] == c["id"]]
        if any(r["kind"] == "option" for r in rows):
            origin = "決断由来"
        elif c["attrs"].get("obvious"):
            origin = "自明"
        elif c.get("parent") or any(l["dst"] == c["id"] for l in alive_links(g, "refines")):
            origin = "親から"
        else:
            origin = "骨格"
        elements.append({"id": c["id"], "title": c["title"], "origin": origin, "derives_from": derived,
                         "orphan": c["id"] in orphan, "on_line": c["id"] in on_line})
    npred = findings(g, ("no_predicate",))
    isolated = [e["id"] for e in elements if not e["on_line"] and len(elements) > 1]
    data = {"elements": elements, "relations": triples, "no_predicate": npred, "isolated": isolated,
            "orphans": [e["id"] for e in elements if e["orphan"]]}
    lines = [f"論理コンポーネント {len(elements)} 件・関連線 {len(triples)} 本"]
    lines += [f"  [{e['origin']}] {e['id']} {e['title']}" + (f"（導出元: {', '.join(e['derives_from'])}）" if e["derives_from"] else "")
              for e in elements]
    lines += [f"  {t['subject']} —{t['predicate'] or '（述語なし）'}→ {t['object']}（{t['link']}）" for t in triples]
    lines += [fline(f) for f in npred]
    lines += [f"[orphan] {i} は上流が何も無い" for i in data["orphans"]]
    lines += [f"[線なし] {i} はどの関連線にも載っていない" for i in isolated]
    bad = bool(npred or isolated or data["orphans"])
    return data, lines, bad


def main(argv: list[str] | None = None) -> int:
    return run(argv, __doc__ or "", lambda p: None, analyze)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""案の欠点（attrs.cons）を由来（手段由来／本質的）ごとに分け、由来の無い欠点を指摘する。

    python cons_origin.py [--db PATH] [--backend json|sqlite] [--json]

読む規則: cons_no_origin（欠点に由来 origin が無い）。
出すもの: 生きた案ごとの欠点と由来、由来別の件数。
手段由来は別の案で避けられる欠点、本質的は課題に内在してどの案でも避けられない欠点（Skill 本文）。
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



DESC = '案の欠点を由来（手段由来／本質的）別に並べる。'
RULES: tuple[str, ...] = ('cons_no_origin',)


MEANS = ("means", "手段由来")
ESSENTIAL = ("essential", "本質的")


def add_args(ap: argparse.ArgumentParser) -> None:
    pass


def origin_of(c: Any) -> str | None:
    o = c.get("origin") if isinstance(c, dict) else None
    if o in MEANS:
        return "手段由来"
    if o in ESSENTIAL:
        return "本質的"
    return None


def collect(core: Any, g: Any, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    rows: list[dict[str, Any]] = []
    tally = {"手段由来": 0, "本質的": 0, "由来なし": 0}
    lines = ["## 案ごとの欠点と由来"]
    for o in g.find("option"):
        if o["state"] not in ALIVE or empty(o["attrs"].get("cons")):
            continue
        cons = o["attrs"]["cons"]
        entries = []
        for c in (cons if isinstance(cons, list) else [cons]):
            origin = origin_of(c)
            tally[origin or "由来なし"] += 1
            entries.append({"text": c.get("text") if isinstance(c, dict) else str(c), "origin": origin})
        rows.append({"id": o["id"], "title": o["title"], "cons": entries})
        lines.append(f"{o['id']} {o['title']}")
        for e in entries:
            lines.append(f"  - [{e['origin'] or '由来なし'}] {txt(e['text'])}")
    if not rows:
        lines.append("- 欠点を書いた案なし")
    lines.append("")
    lines.append(f"件数: 手段由来 {tally['手段由来']} ／ 本質的 {tally['本質的']} ／ 由来なし {tally['由来なし']}")
    lines.append("手段由来は別の案で避けられるか確かめる。本質的はどの案でも避けられない（課題として引き渡す）。")
    findings = pick(g, RULES)
    return {"options": rows, "tally": tally, "findings": findings}, lines + [""] + finding_lines(findings)


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

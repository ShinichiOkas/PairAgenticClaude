#!/usr/bin/env python
"""アーキテクチャが仕様に課す制約（制約・採用した案の must／must_not）と、要求を変えたときの下流への影響を示す。

    python spec_constraint_impact.py [--db PATH] [--backend json|sqlite] [--json] [RQ …]

読む規則: なし（検出ではなく説明の材料。終了コードは常に 0）。
出すもの: ID なし → 制約（CT）と、決断済みの案の must／must_not の一覧。要求などの ID を渡す → その上流にある採用済みの案の制約と、
下流（変更のインパクト）を要素種ごとに。アーキテクトは仕様を決めない。制約と変更のインパクトを説明する。
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



DESC = 'アーキテクチャが仕様に課す制約と、変更のインパクトを示す。'
RULES: tuple[str, ...] = ()


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("ids", nargs="*", metavar="ID", help="変更を考える要求など（省くと制約の一覧）")


def adopted_constraints(core: Any, g: Any, only: set[str] | None = None) -> list[dict[str, Any]]:
    out = []
    for d in g.find("decision_point"):
        dec = d.get("decision")
        if d["state"] not in ALIVE or not dec:
            continue
        o = g.nodes[dec["option"]]
        if only is not None and o["id"] not in only:
            continue
        out.append({"decision_point": d["id"], "option": o["id"], "title": o["title"],
                    "must": o["attrs"].get("must"), "must_not": o["attrs"].get("must_not")})
    return out


def collect(core: Any, g: Any, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    lines: list[str] = []
    data: dict[str, Any] = {"findings": []}
    if not args.ids:
        cts = [{"id": n["id"], "title": n["title"], "state": n["state"]} for n in g.find("constraint") if n["state"] in ALIVE]
        decs = adopted_constraints(core, g)
        lines.append("## 制約（CT）")
        lines += [f"- {c['id']} [{c['state']}] {c['title']}" for c in cts] or ["- なし"]
        lines += ["", "## 採用した案が課す制約"]
        for c in decs:
            lines.append(f"- {c['decision_point']} → {c['option']} {c['title']}")
            lines.append(f"    must: {txt(c['must'])} ／ must_not: {txt(c['must_not'])}")
        if not decs:
            lines.append("- なし")
        data.update({"constraints": cts, "adopted": decs})
        return data, lines
    per = []
    for i in args.ids:
        if i not in g.nodes:
            raise core.DesignGraphError(f"無い ID: {i}")
        up = {x["id"] for x in g.why(i)}
        down: dict[str, list[str]] = {}
        for x in g.impact(i):
            if x["id"] != i and not x["kind"].startswith("link:"):
                down.setdefault(x["kind"], []).append(x["id"])
        imposing = adopted_constraints(core, g, up)
        per.append({"id": i, "title": g.nodes[i]["title"], "imposed_by": imposing,
                    "downstream": {k: sorted(v, key=core.natkey) for k, v in sorted(down.items())}})
        lines.append(f"{i} {g.nodes[i]['title']}")
        lines.append("  この要素に制約を課している採用済みの案:")
        for c in imposing:
            lines.append(f"    - {c['option']} {c['title']}  must: {txt(c['must'])} ／ must_not: {txt(c['must_not'])}")
        if not imposing:
            lines.append("    - なし")
        lines.append("  変更のインパクト（下流）:")
        for k, v in per[-1]["downstream"].items():
            lines.append(f"    - {core.KINDS[k][1]}: {', '.join(v)}")
        if not per[-1]["downstream"]:
            lines.append("    - なし")
    data["targets"] = per
    return data, lines


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

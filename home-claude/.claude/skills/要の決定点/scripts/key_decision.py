#!/usr/bin/env python
"""決定点を下流への影響の広さで並べ、案どうしのリンク（requires／excludes／conflicts／synergy／linked）と排他の両方採用を示す。

    python key_decision.py [--db PATH] [--backend json|sqlite] [--json] [D …]

読む規則: excluded_both（排他の案が両方とも採用されている）、few_options（未決で案が 3 つ未満）。
出すもの: 生きた決定点を影響の広さ（自分の案を除いた下流の数）の順に並べた表、案どうしのリンクの一覧。ID を渡すとその決定点だけ。
「要」は下流に多くが掛かる決定点。順位は読む順の目安で、重要度の判定ではない。
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



DESC = '決定点を影響の広さの順に並べ、案どうしのリンクを示す。'
RULES: tuple[str, ...] = ('excluded_both', 'few_options')


OPTION_LINKS = ("requires", "excludes", "conflicts", "synergy", "linked")


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("ids", nargs="*", metavar="D", help="見る決定点（省くと全部）")


def collect(core: Any, g: Any, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    wanted = set(args.ids)
    for i in sorted(wanted):
        if i not in g.nodes or g.nodes[i]["kind"] != "decision_point":
            raise core.DesignGraphError(f"決定点（D…）ではない: {i}")
    opts = {o["id"]: o for o in g.find("option")}
    rows: list[dict[str, Any]] = []
    scope: set[str] = set()
    for d in g.find("decision_point"):
        if d["state"] not in ALIVE or (wanted and d["id"] not in wanted):
            continue
        mine = {i for i, o in opts.items() if o.get("parent") == d["id"]}
        scope |= mine
        impact = [x["id"] for x in g.impact(d["id"]) if x["id"] != d["id"] and x["id"] not in mine]
        rows.append({"id": d["id"], "title": d["title"], "decided": bool(d.get("decision")),
                     "options": len(mine), "impact": len(impact), "downstream": impact})
    rows.sort(key=lambda r: (-r["impact"], core.natkey(r["id"])))
    links = []
    for l in sorted(g.links.values(), key=lambda l: core.natkey(l["id"])):
        if l["kind"] in OPTION_LINKS and l["state"] in ALIVE and (l["src"] in scope or l["dst"] in scope):
            links.append({"id": l["id"], "kind": l["kind"], "src": l["src"], "dst": l["dst"]})
    lines = ["## 決定点（下流への影響の広い順）"]
    for r in rows:
        lines.append(f"{r['id']} {r['title']}  影響 {r['impact']}・案 {r['options']}  " + ("決断済み" if r["decided"] else "未決"))
    if not rows:
        lines.append("- 決定点なし")
    lines.append("")
    lines.append("## 案どうしのリンク")
    lines += [f"- {l['id']}: {l['src']} —{l['kind']}→ {l['dst']}" for l in links] or ["- なし"]
    findings = pick(g, RULES)
    return {"decision_points": rows, "option_links": links, "findings": findings}, lines + [""] + finding_lines(findings)


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

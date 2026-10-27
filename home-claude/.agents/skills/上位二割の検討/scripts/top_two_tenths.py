#!/usr/bin/env python
"""重みの高い関心事の上位二割を取り出し、それぞれに課題が立ち、閉じられているかを示す。

    python top_two_tenths.py [--db PATH] [--backend json|sqlite] [--json]

読む規則: closure_incomplete（閉じ方の記録の欠け）。
出すもの: 重み（attrs.weight 1〜5）の高い順に並べた関心事のうち上位二割（端数は切り上げ、境界で同じ重みのものは全部入れる）と、
それに影響する課題・リスク（affects リンク）の閉じ方。課題が立っていない・未解決の上位関心事は「担保されていない」として列挙する。
網羅性は求めない。重みの無い関心事は順位に入れない。
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



DESC = '重みの上位二割の関心事と、その課題の閉じ方を示す。'
RULES: tuple[str, ...] = ('closure_incomplete',)


import math


def add_args(ap: argparse.ArgumentParser) -> None:
    pass


def weight_of(n: dict[str, Any]) -> int | None:
    w = n["attrs"].get("weight")
    return w if isinstance(w, int) and not isinstance(w, bool) and 1 <= w <= 5 else None


def collect(core: Any, g: Any, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    cns = [n for n in g.find("concern") if n["state"] in ALIVE]
    weighted = sorted((n for n in cns if weight_of(n) is not None), key=lambda n: (-(weight_of(n) or 0), core.natkey(n["id"])))
    unweighted = [n["id"] for n in cns if weight_of(n) is None]
    top: list[dict[str, Any]] = []
    if weighted:
        k = max(1, math.ceil(len(weighted) * 0.2))
        threshold = weight_of(weighted[k - 1]) or 0
        top = [n for n in weighted if (weight_of(n) or 0) >= threshold]
    rows: list[dict[str, Any]] = []
    uncovered: list[str] = []
    lines = [f"## 上位二割の関心事（重みつき {len(weighted)} 件中 {len(top)} 件）"]
    for n in top:
        issues = []
        for l in sorted(g.links.values(), key=lambda l: core.natkey(l["id"])):
            if l["kind"] == "affects" and l["dst"] == n["id"] and l["state"] in ALIVE and g.nodes[l["src"]]["state"] in ALIVE:
                m = g.nodes[l["src"]]
                key = (m.get("closure") or {}).get("as", "open")
                issues.append({"id": m["id"], "title": m["title"], "closure": key, "label": core.CLOSURE_LABEL[key]})
        solid = [i for i in issues if i["closure"] in ("resolved", "accepted")]
        if not solid:
            uncovered.append(n["id"])
        rows.append({"id": n["id"], "title": n["title"], "weight": weight_of(n), "issues": issues, "covered": bool(solid)})
        lines.append(f"{n['id']} 重み {weight_of(n)} {n['title']}  " + ("担保あり" if solid else "担保されていない"))
        for i in issues:
            lines.append(f"  - {i['id']} [{i['label']}] {i['title']}")
        if not issues:
            lines.append("  - 影響する課題なし（affects を張る）")
    if not top:
        lines.append("- 重みの付いた関心事なし")
    if uncovered:
        lines.append("")
        lines.append("担保されていない上位の関心事（課題が無い・未解決・退けた／保留のみ）: " + ", ".join(uncovered))
    if unweighted:
        lines.append(f"重みが無く順位に入れなかった関心事: {', '.join(unweighted)}")
    findings = pick(g, RULES)
    return ({"top": rows, "uncovered": uncovered, "unweighted": unweighted, "findings": findings},
            lines + [""] + finding_lines(findings))


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

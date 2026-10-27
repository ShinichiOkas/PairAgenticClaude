#!/usr/bin/env python
"""結論（決断）と根拠（設計ノート）を別々に並べ、互いを ID の参照で結ぶ。根拠の無い結論と、どの結論にも参照されない根拠を指摘する。

    python conclusion_evidence_split.py [--db PATH] [--backend json|sqlite] [--json]

読む規則: no_evidence（根拠の無い確定）、undecided（未決。情報）。
出すもの: 決断済みの決定点（結論）ごとの根拠の ID、設計ノート（NT）ごとにそれを指している結論・要素、参照されていない設計ノート。
結論の文書と根拠の文書を分けても、ID でつながっていることを確かめるための表。
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



DESC = '結論と根拠を別々に並べ、ID の参照で結ぶ。'
RULES: tuple[str, ...] = ('no_evidence', 'undecided')


def add_args(ap: argparse.ArgumentParser) -> None:
    pass


def collect(core: Any, g: Any, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    conclusions: list[dict[str, Any]] = []
    lines = ["## 結論（決断）→ 根拠"]
    for d in g.find("decision_point"):
        dec = d.get("decision")
        if d["state"] not in ALIVE or not dec:
            continue
        ev = g.evidence_of(d["id"])
        conclusions.append({"id": d["id"], "title": d["title"], "option": dec["option"], "evidence": ev})
        lines.append(f"{d['id']} {d['title']} → {dec['option']}  根拠: " + (", ".join(ev) or "（指していない）"))
    if not conclusions:
        lines.append("- 決断済みの決定点なし")
    records: list[dict[str, Any]] = []
    lines += ["", "## 根拠（設計ノート）← 参照している結論・要素"]
    for r in g.find("record"):
        if r["state"] not in ALIVE:
            continue
        refs = sorted({l["src"] for l in g.links.values() if l["kind"] == "evidence" and l["dst"] == r["id"]
                       and l["state"] in ALIVE}, key=core.natkey)
        records.append({"id": r["id"], "title": r["title"], "referenced_by": refs})
        lines.append(f"{r['id']} {r['title']}  参照: " + (", ".join(refs) or "（誰も参照していない）"))
    if not records:
        lines.append("- 設計ノートなし")
    unreferenced = [r["id"] for r in records if not r["referenced_by"]]
    findings = pick(g, RULES)
    return ({"conclusions": conclusions, "records": records, "unreferenced_records": unreferenced, "findings": findings},
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

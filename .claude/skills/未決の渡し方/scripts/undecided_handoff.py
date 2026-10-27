#!/usr/bin/env python
"""未決の決定点・未解決の課題・保留・要再確認を「人に渡す一覧」として並べる。

    python undecided_handoff.py [--db PATH] [--backend json|sqlite] [--json]

読む規則: undecided（未決の決定点。情報なので終了コードには影響しない）。
出すもの: 未決の決定点と案、未解決の課題・リスク、保留（再開の条件つき）、仕分け待ちの要再確認。
未決は推測で埋めない。この一覧を人に渡し、決めてもらう。
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



DESC = '未決・未解決・保留・要再確認を人に渡す一覧にする。'
RULES: tuple[str, ...] = ('undecided',)


def add_args(ap: argparse.ArgumentParser) -> None:
    pass


def collect(core: Any, g: Any, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    st = g.status()
    opts = g.find("option")
    dps = []
    lines = ["## 人に渡す: 未決（推測で埋めない）", "", "### 未決の決定点"]
    for d in st["undecided"]:
        n = g.nodes[d]
        mine = [{"id": o["id"], "title": o["title"]} for o in opts if o.get("parent") == d and o["state"] in ALIVE]
        dps.append({"id": d, "title": n["title"], "options": mine})
        lines.append(f"- {d} {n['title']}（案: {', '.join(o['id'] for o in mine) or 'なし'}）")
    if not dps:
        lines.append("- なし")
    lines += ["", "### 未解決の課題・リスク"]
    opened = [{"id": i, "title": g.nodes[i]["title"]} for i in st["open_issues"]]
    lines += [f"- {o['id']} {o['title']}" for o in opened] or ["- なし"]
    lines += ["", "### 保留（再開の条件）"]
    held = [{"id": i, "title": g.nodes[i]["title"], "resume_if": g.nodes[i]["closure"].get("resume_if")} for i in st["deferred"]]
    lines += [f"- {h['id']} {h['title']}（再開の条件: {txt(h['resume_if'])}）" for h in held] or ["- なし"]
    lines += ["", "### 要再確認（仕分け待ち）"]
    rc = g.recheck()
    lines += [f"- {m['link']}: {m['downstream']} ← {m['upstream']}（v{m['seen']} → v{m['current']}）" for m in rc] or ["- なし"]
    findings = pick(g, RULES)
    return ({"undecided": dps, "open": opened, "deferred": held, "recheck": rc, "findings": findings},
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

#!/usr/bin/env python
"""課題・リスクを閉じ方（解決／受容／退ける／保留／未解決）別に並べ、閉じ方の記録が欠けるものを指摘する。

    python issue_closure.py [--db PATH] [--backend json|sqlite] [--json]

読む規則: closure_incomplete（受容に根拠が無い・退けるに reopen_if が無い・保留に resume_if が無い）。
出すもの: 生きた課題（IS）・リスク（RK）ごとの閉じ方・理由・開き直す／再開の条件・根拠、閉じ方ごとの件数。
受容と退けるを混ぜない（受容は誰が何をどの条件で受けたかの記録、退けるは開き直す条件）。
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



DESC = '課題・リスクを閉じ方別に並べる。'
RULES: tuple[str, ...] = ('closure_incomplete',)


def add_args(ap: argparse.ArgumentParser) -> None:
    pass


def collect(core: Any, g: Any, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    rows: list[dict[str, Any]] = []
    tally: dict[str, int] = {v: 0 for v in core.CLOSURE_LABEL.values()}
    lines = ["## 課題・リスクの閉じ方"]
    for kind in ("issue", "risk"):
        for n in g.find(kind):
            if n["state"] not in ALIVE:
                continue
            c = n.get("closure") or {}
            key = c.get("as", "open")
            label = core.CLOSURE_LABEL[key]
            tally[label] += 1
            rows.append({"id": n["id"], "kind": kind, "title": n["title"], "closure": key, "label": label,
                         "reason": c.get("reason"), "reopen_if": c.get("reopen_if"), "resume_if": c.get("resume_if"),
                         "evidence": g.evidence_of(n["id"])})
            lines.append(f"{n['id']} [{label}] {n['title']}")
            if c.get("reason"):
                lines.append(f"  理由: {c['reason']}")
            if key == "accepted":
                lines.append(f"  受けた記録: {txt(g.evidence_of(n['id']))}")
            if key == "dismissed":
                lines.append(f"  開き直す条件: {txt(c.get('reopen_if'))}")
            if key == "deferred":
                lines.append(f"  再開の条件: {txt(c.get('resume_if'))}")
    if not rows:
        lines.append("- 課題・リスクなし")
    lines.append("")
    lines.append("件数: " + " ／ ".join(f"{k} {v}" for k, v in tally.items()))
    findings = pick(g, RULES)
    return {"items": rows, "tally": tally, "findings": findings}, lines + [""] + finding_lines(findings)


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

#!/usr/bin/env python
"""却下・廃止された案を、決定点の決断の条件・欠点・却下の理由つきで一覧し、語で絞る。

    python precedent_lookup.py [--db PATH] [--backend json|sqlite] [--json] [語 …] [--state rejected|retired|confirmed|any]

読む規則: なし（検出ではなく判例の一覧。終了コードは常に 0）。
出すもの: 既定は却下・廃止の案。決定点の題、その決断（採用した案と背景事情）、案の欠点・視点、状態を変えた理由。
語を渡すと題・属性・親の決定点の題・背景事情に全部の語を含むものだけ（大文字小文字を区別しない）。結論ではなく条件の差で引くための材料。
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



DESC = '却下・廃止された案を、決断の条件と理由つきで一覧する。'
RULES: tuple[str, ...] = ()


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("terms", nargs="*", metavar="語", help="全部を含む案だけ（省くと全部）")
    ap.add_argument("--state", choices=["rejected", "retired", "confirmed", "any"], default=None,
                    help="案の状態（既定は rejected と retired）")


def collect(core: Any, g: Any, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    reasons: dict[str, str] = {}
    for ev in g.log.read():
        if ev.get("op") == "state" and ev.get("reason"):
            reasons[ev["id"]] = ev["reason"]
    if args.state is None:
        want = ("rejected", "retired")
    elif args.state == "any":
        want = ("hypothesis", "confirmed", "rejected", "retired")
    else:
        want = (args.state,)
    terms = [t.lower() for t in args.terms]
    rows: list[dict[str, Any]] = []
    lines = ["## 判例（案）"]
    for o in g.find("option"):
        if o["state"] not in want:
            continue
        dp = g.nodes.get(o.get("parent") or "", {})
        dec = dp.get("decision") or {}
        hay = json.dumps([o["title"], o["attrs"], dp.get("title"), dec.get("conditions")], ensure_ascii=False).lower()
        if not all(t in hay for t in terms):
            continue
        rows.append({"id": o["id"], "title": o["title"], "state": o["state"], "decision_point": dp.get("id"),
                     "decision_point_title": dp.get("title"), "adopted": dec.get("option"),
                     "conditions": dec.get("conditions") or [], "reason": reasons.get(o["id"]),
                     "viewpoint": o["attrs"].get("viewpoint"), "cons": o["attrs"].get("cons")})
        lines.append(f"{o['id']} [{core.STATE_LABEL[o['state']]}] {o['title']}")
        lines.append(f"  決定点: {dp.get('id')} {dp.get('title')}  採用: {dec.get('option') or '（未決）'}")
        lines.append(f"  決断の背景事情: {txt(dec.get('conditions'))}")
        lines.append(f"  状態を変えた理由: {txt(reasons.get(o['id']))}")
        lines.append(f"  視点: {txt(o['attrs'].get('viewpoint'))} ／ 欠点: {txt(o['attrs'].get('cons'))}")
    if not rows:
        lines.append("- 該当なし")
    return {"precedents": rows, "findings": []}, lines


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

#!/usr/bin/env python3
"""設計の因果 DB から区間目標の予算表（目標・配分・合計・超過）を作り、合計が目標を超えた区間と突き合わせられない予算を出す。

    python budget_table.py [--db PATH] [--backend json|sqlite] [--id QS1 ...] [--json]

読む形（設計の因果 DB）:
  目標   区間の品質要求（QS など）の attrs.target（数）と attrs.unit
  配分   そこから出る allocates（→ 工程・論理コンポーネント）の attrs.budget（数）・unit・basis（根拠の知見）
出す:
  予算表（関心事ごとに 1 表。配分先・予算・状態・根拠）と、合計・残り・超過
  [budget_over]        配分の合計が目標を超える（それ自体がアーキテクチャ課題。予算の取り合いを起票する）
  [budget_unreadable]  予算が数でない・単位が目標と違う（1 表に混ぜない）・目標が無いのに配分している
判定はしない。表と検出を出すだけ。知見の数値は仮説のまま置く（状態の列で見える）。
中核 design_graph.py の探し方: 環境変数 PAIR_AGENT_DESIGN_GRAPH → この場所から上の tools/design_graph.py
→ ~/.claude/pair-agent/tools/ → ~/.gemini/config/pair-agent/tools/。読むだけで DB には書かない。
終了コード: 0 = 検出なし ／ 1 = 検出あり ／ 2 = 中核が見つからない・入力の誤り
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

sys.dont_write_bytecode = True

ENV = "PAIR_AGENT_DESIGN_GRAPH"
NEEDS = "budgets"  # 中核に要る API（古い中核を見分ける）
RULES = ("budget_over", "budget_unreadable")
PROBLEM = {"no_budget": "予算なし（合計に入れない）", "not_number": "数でない（合計に入れない）",
           "unit": "単位が目標と違う（合計に入れない）"}
STATE = {"hypothesis": "仮説", "confirmed": "確定", "rejected": "却下", "retired": "廃止"}


def core_candidates() -> list[tuple[str, Path]]:
    """design_graph.py を探す場所（探す順）。"""
    out: list[tuple[str, Path]] = []
    env = os.environ.get(ENV)
    if env:
        out.append((f"環境変数 {ENV}", Path(env).expanduser()))
    here = Path(__file__).resolve().parent
    out += [("この場所から上", d / "tools" / "design_graph.py") for d in (here, *here.parents)]
    try:
        home = Path.home()
        out.append(("install 先", home / ".claude" / "pair-agent" / "tools" / "design_graph.py"))
        out.append(("install 先", home / ".gemini" / "config" / "pair-agent" / "tools" / "design_graph.py"))
    except RuntimeError:
        pass
    return out


def load_core() -> ModuleType | None:
    """中核を読み込む。見つからない・古いときは、どこを探したかを stderr に出して None。"""
    tried = []
    for how, p in core_candidates():
        tried.append(f"  {how}: {p}")
        if not p.is_file():
            if how.startswith("環境変数"):
                print(f"注意: {ENV} の指す先が無い。次の場所を探す: {p}", file=sys.stderr)
            continue
        spec = importlib.util.spec_from_file_location("design_graph", p)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(getattr(mod, "DesignGraph", None), NEEDS):
            print(f"エラー: 中核が古い（DesignGraph.{NEEDS} が無い）: {p}", file=sys.stderr)
            return None
        return mod
    print("エラー: 設計の因果 DB の中核 design_graph.py が見つからない。探した場所:\n" + "\n".join(tried), file=sys.stderr)
    return None


def collect(g: Any, ids: list[str] | None) -> dict:
    tables = [t for t in g.budgets() if not ids or t["id"] in ids]
    findings = [f for f in g.check() if f["rule"] in RULES]
    if ids:
        links = {i["link"] for t in tables for i in t["items"]}
        findings = [f for f in findings if f["target"] in ids or f["target"] in links]
    return {"db": str(g.path), "backend": g.backend, "last_seq": g.last_seq, "tables": tables, "findings": findings}


def _v(x: Any, unit: str | None) -> str:
    return f"{x}{' ' + unit if unit else ''}"


def render(data: dict) -> list[str]:
    L = [f"DB: {data['db']}（{data['backend']}・seq {data['last_seq']}）", ""]
    if not data["tables"]:
        L.append("予算表なし（目標値 attrs.target か、予算 attrs.budget つきの allocates が無い）")
    for t in data["tables"]:
        unit = t["unit"]
        if t["problem"] is None:
            goal = _v(t["target"], unit)
        elif t["problem"] == "target_not_number":
            goal = f"読めない（{t['target']!r}）"
        else:
            goal = "なし"
        L.append(f"## {t['id']} {t['title']} [{STATE[t['state']]}]  目標 {goal}")
        L.append("")
        L.append("| 配分先 | 予算 | 状態 | 根拠の知見 | 備考 |")
        L.append("|---|---|---|---|---|")
        for i in t["items"]:
            budget = "—" if i["problem"] == "no_budget" else _v(i["budget"], i["unit"] or unit)
            L.append(f"| {i['to']} {i['to_title']} | {budget} | {STATE[i['state']]} | {i['basis'] or ''} | "
                     f"{PROBLEM.get(i['problem'] or '', '')} |")
        if not t["items"]:
            L.append("| （配分なし） | | | | |")
        line = f"合計 {_v(t['total'], unit)}"
        if t["problem"] is None:
            line += f" ／ 目標 {_v(t['target'], unit)} → " + (
                f"超過 {_v(t['excess'], unit)}（予算の取り合い。課題にする）" if t["over"] else f"残り {_v(t['remaining'], unit)}")
        L += ["", line, ""]
    L.append("## 検出")
    L += [f"- [{f['id']}] {f['message']}" for f in data["findings"]] or ["- なし"]
    return L


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    p = argparse.ArgumentParser(prog="budget_table.py", description=(__doc__ or "").splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--db", help="DB の置き場（省くと中核の既定 .pair-agent/design/graph.jsonl）")
    p.add_argument("--backend", choices=["json", "sqlite"], help="省くと --db の拡張子で決める")
    p.add_argument("--id", action="append", metavar="ID", help="この要素（QS など）の表だけ。繰り返せる")
    p.add_argument("--json", action="store_true", help="機械向けの JSON で出す")
    args = p.parse_args(argv)
    dg = load_core()
    if dg is None:
        return 2
    try:
        data = collect(dg.DesignGraph(args.db, args.backend, actor="ai"), args.id)
    except dg.DesignGraphError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print("\n".join(render(data)))
    return 1 if any(f["level"] != "info" for f in data["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())

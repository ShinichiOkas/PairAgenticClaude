#!/usr/bin/env python3
"""設計の因果 DB から括りごとの数の表（要素の数・内部の結合・外部との結合）を作り、宣言した上限を超えた括りだけを出す。

    python coupling_table.py [--db PATH] [--backend json|sqlite] [--root ID ...] [--json]

読む形（設計の因果 DB）:
  括り   --parent で作った親子（構造の要素: 論理コンポーネント・実装部品・インタフェース）。案（D1-A）も括りになる
  結合   生きた relation の両端の組（同じ組に述語が 2 つあっても 1 つと数える）
  上限   括りの attrs.max_coupling（外部との結合の上限。0 以上の整数）
出す:
  全体の 3 つの数（要素の数／要素間の結合の数／外部との結合の数）と、最大 n(n-1)/2・√n（括りの数の目安）
  括りごとの表。--root で案（構造の候補）や括りを選ぶと、その行だけを並べて比べられる
  [coupling_over]  上限を宣言した括りの外部結合が上限を超える・上限が読めない
⚠ 数が大きいこと自体は課題にしない（指標を検出規則にすると数合わせの設計が生まれる）。数は案を比べる材料。
中核 design_graph.py の探し方: 環境変数 PAIR_AGENT_DESIGN_GRAPH → この場所から上の tools/design_graph.py
→ ~/.claude/pair-agent/tools/ → ~/.gemini/config/pair-agent/tools/。読むだけで DB には書かない。
終了コード: 0 = 検出なし ／ 1 = 宣言した上限の超過あり ／ 2 = 中核が見つからない・入力の誤り
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
NEEDS = "coupling"  # 中核に要る API（古い中核を見分ける）
RULES = ("coupling_over",)


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


def collect(g: Any, roots: list[str] | None) -> dict:
    table = g.coupling()
    missing: list[str] = []
    if roots:
        for r in roots:
            g.get(r)  # 無い ID は誤り（終了コード 2）
        have = {row["id"] for row in table["groups"]}
        missing = [r for r in roots if r not in have]
        table["groups"] = [row for row in table["groups"] if row["id"] in roots]
    findings = [f for f in g.check() if f["rule"] in RULES and (not roots or f["target"] in roots)]
    return {"db": str(g.path), "backend": g.backend, "last_seq": g.last_seq, **table, "not_groups": missing,
            "findings": findings}


def render(data: dict) -> list[str]:
    n = data["elements"]
    L = [f"DB: {data['db']}（{data['backend']}・seq {data['last_seq']}）", "",
         f"全体: 要素 {n} ／ 要素間の結合 {data['couplings']}（最大 n(n-1)/2 = {data['max_pairs']}）"
         f" ／ 外部との結合 {data['external']} ／ √n ≈ {data['sqrt_n']}（括りの数の目安）", "",
         "| 括り | 子 | 要素 | 内部の結合 | 外部との結合 | 上限 |", "|---|---|---|---|---|---|"]
    for r in data["groups"]:
        if r["limit_valid"] is None:
            lim = "—"
        elif not r["limit_valid"]:
            lim = f"読めない（{r['max_coupling']!r}）"
        else:
            lim = f"{r['max_coupling']}{' ⚠超過' if r['over'] else ''}"
        L.append(f"| {r['id']} {r['title']} | {r['children']} | {r['elements']} | {r['internal']} | {r['external']} | {lim} |")
    if not data["groups"]:
        L.append("| （括りなし: 子を持つ構造の要素・案が無い） | | | | | |")
    for r in data["not_groups"]:
        L.append(f"- {r} は括りではない（構造の要素の子が無く、上限も宣言していない）")
    L += ["", "数が大きいこと自体は課題にしない。案ごとに並べて比べる材料にする（「分解しない」案も同じ表に）。",
          "検出は上限（attrs.max_coupling）を宣言した括りだけ。", "", "## 検出"]
    L += [f"- [{f['id']}] {f['message']}" for f in data["findings"]] or ["- なし"]
    return L


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    p = argparse.ArgumentParser(prog="coupling_table.py", description=(__doc__ or "").splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--db", help="DB の置き場（省くと中核の既定 .pair-agent/design/graph.jsonl）")
    p.add_argument("--backend", choices=["json", "sqlite"], help="省くと --db の拡張子で決める")
    p.add_argument("--root", action="append", metavar="ID", help="この括り・案の行だけを並べる。繰り返せる")
    p.add_argument("--json", action="store_true", help="機械向けの JSON で出す")
    args = p.parse_args(argv)
    dg = load_core()
    if dg is None:
        return 2
    try:
        data = collect(dg.DesignGraph(args.db, args.backend, actor="ai"), args.root)
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

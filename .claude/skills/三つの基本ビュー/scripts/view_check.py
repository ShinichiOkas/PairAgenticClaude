#!/usr/bin/env python3
"""設計の因果 DB のモデル（1 枚の図）を実装・論理・割り付けの三つの基本ビューに束ね、欠けたビュー・どのビューにも載らない要素・要素の種類が混ざった図を出す。

    python view_check.py [--db PATH] [--backend json|sqlite] [--json]

読む形（設計の因果 DB）:
  モデル  model（MO・1 枚の図）の attrs.viewpoint＝logical（論理）／implementation（実装）／allocation（割り付け）。
          同じ視点のモデルの集まりがビュー（視点そのものはビューポイント）
  載せる  shows（モデル → 要素）。要素の種類は attrs.stereotype があればそれ、無ければ DB の種類
  要素    論理コンポーネント（LC）は論理ビューに、実装部品（PT）は実装ビューに載るべき要素
出す:
  ビューごとのモデルの一覧と、その他の視点・視点の無いモデル・どのビューにも載らない要素
  [view_missing]  三つの基本ビューのどれかのモデルが無い（モデルを 1 枚でも作ったら検査が始まる）
  [no_view]       そのビューがあるのに、どのビューのモデルにも載っていない要素
  [mixed_kinds]   1 枚のモデルに要素の種類が混ざる（割り付けの図だけは 2 種類まで。attrs.whiteboard=true の図は問わない）
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
NEEDS = "views"  # 中核に要る API（古い中核を見分ける）
RULES = ("view_missing", "no_view", "mixed_kinds")
VIEW = {"logical": "論理ビュー", "implementation": "実装ビュー", "allocation": "割り付けビュー"}


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


def collect(g: Any) -> dict:
    findings = [f for f in g.check() if f["rule"] in RULES]
    return {"db": str(g.path), "backend": g.backend, "last_seq": g.last_seq, **g.views(), "findings": findings}


def _model(m: dict) -> str:
    kinds = "・".join(f"{k}×{len(ids)}" for k, ids in m["kinds"].items()) or "要素なし"
    mark = "（ホワイトボード）" if m["whiteboard"] else ("⚠種類が混ざる" if m["mixed"] else "")
    return f"{m['id']} {m['title']}（{kinds}）{mark}"


def render(data: dict) -> list[str]:
    L = [f"DB: {data['db']}（{data['backend']}・seq {data['last_seq']}）", ""]
    if not data["active"]:
        L += ["モデル（1 枚の図）が 1 枚も無い。三つの基本ビューはどれも示されていない。",
              "attrs.viewpoint を付けた model を作り、shows で要素を載せると検査が始まる。", ""]
    L += ["| ビュー | モデル |", "|---|---|"]
    for vp, label in VIEW.items():
        ms = [_model(m) for m in data["models"] if m["viewpoint"] == vp]
        L.append(f"| {label} | {'<br>'.join(ms) if ms else '（なし）⚠'} |")
    other = [m for m in data["models"] if m["viewpoint"] and not m["basic"]]
    none = [m for m in data["models"] if not m["viewpoint"]]
    if other:
        L += ["", "その他の視点のモデル:"] + [f"- [{m['viewpoint']}] {_model(m)}" for m in other]
    if none:
        L += ["", "視点（attrs.viewpoint）の無いモデル（どのビューにも属さない）:"] + [f"- {_model(m)}" for m in none]
    loose = [e for e in data["elements"] if not e["models"]]
    if loose:
        L += ["", "どのビューのモデルにも載っていない要素:"]
        L += [f"- {e['id']} {e['title']}（載るべきビュー: {VIEW[e['view']]}）" for e in loose]
    L += ["", "## 検出"]
    L += [f"- [{f['id']}] {f['message']}" for f in data["findings"]] or ["- なし"]
    return L


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    p = argparse.ArgumentParser(prog="view_check.py", description=(__doc__ or "").splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--db", help="DB の置き場（省くと中核の既定 .pair-agent/design/graph.jsonl）")
    p.add_argument("--backend", choices=["json", "sqlite"], help="省くと --db の拡張子で決める")
    p.add_argument("--json", action="store_true", help="機械向けの JSON で出す")
    args = p.parse_args(argv)
    dg = load_core()
    if dg is None:
        return 2
    try:
        data = collect(dg.DesignGraph(args.db, args.backend, actor="ai"))
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

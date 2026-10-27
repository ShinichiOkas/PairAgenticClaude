#!/usr/bin/env python3
"""設計の因果 DB の決断ごとに「捨てたもの」（却下した案・採用した案の代償・案どうしの衝突）と関わる関心事を並べ、代償の書かれていない採用案を出す。

    python atam_discards.py [--db PATH] [--backend json|sqlite] [--dp D1 ...] [--json]

読む形（設計の因果 DB）:
  決断    decide で採用した案（他の案は却下として残る）と背景事情
  代償    案の attrs.cons（[{text, origin（means／essential）, measure, owner}] か文字列）
  関係    案どうしの excludes（排他）・conflicts（衝突）・synergy（相乗）・linked（関係）
  関心事  決定点から上流へ辿った関心事（CN）
出す:
  決断ごとに、採用した案・捨てた案（却下・廃止）とその欠点・採用した案の代償・案どうしの関係・関わる関心事。
  関心事が 2 つ以上の決断は「トレードオフ点の候補」と書く（候補まで。トレードオフ点と認めるのはアーキテクト）
  [no_cons]  採用した案に代償が書かれていない（「全部満たした」は捨てたものが見えない）
未決の決定点は並べない（まだ何も捨てていない）。評価はしない。
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
NEEDS = "tradeoffs"  # 中核に要る API（古い中核を見分ける）
RULES = ("no_cons",)
ORIGIN = {"means": "手段由来", "手段由来": "手段由来", "essential": "本質的", "本質的": "本質的"}
RELATION = {"excludes": "排他", "conflicts": "衝突", "synergy": "相乗", "linked": "関係"}
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


def collect(g: Any, dps: list[str] | None) -> dict:
    rows = [r for r in g.tradeoffs() if not dps or r["dp"] in dps]
    for r in rows:
        r["candidate_tradeoff_point"] = len(r["concerns"]) >= 2
    titles = {n["id"]: n["title"] for n in g.find("concern")}
    adopted = {r["adopted"]["id"] for r in rows}
    findings = [f for f in g.check() if f["rule"] in RULES and (not dps or f["target"] in adopted)]
    return {"db": str(g.path), "backend": g.backend, "last_seq": g.last_seq, "decisions": rows,
            "concern_titles": titles, "findings": findings}


def _cons(c: dict) -> str:
    extra = [ORIGIN.get(str(c.get("origin")), "由来なし")]
    extra += [str(c[k]) for k in ("measure", "owner") if c.get(k)]
    return f"{c['text']}（{'・'.join(extra)}）"


def render(data: dict) -> list[str]:
    L = [f"DB: {data['db']}（{data['backend']}・seq {data['last_seq']}）", ""]
    ct = data["concern_titles"]
    for r in data["decisions"]:
        a = r["adopted"]
        L.append(f"## {r['dp']} {r['title']} → 採用 {a['id']} {a['title']}")
        cn = ", ".join(f"{c} {ct.get(c, '')}".strip() for c in r["concerns"]) or "なし（課題・関心事につながっていない）"
        L.append(f"- 関わる関心事: {cn}" + ("（2 つ以上: トレードオフ点の候補）" if r["candidate_tradeoff_point"] else ""))
        L.append(f"- 背景事情: {'／'.join(r['conditions']) or 'なし'}")
        L.append("- 採用した案の代償: " + ("、".join(_cons(c) for c in a["cons"]) or "⚠ 書かれていない"))
        for o in r["rejected"]:
            vp = f"（視点: {o['viewpoint']}）" if o["viewpoint"] else ""
            cons = "、".join(_cons(c) for c in o["cons"]) or "欠点の記録なし"
            L.append(f"- 捨てた案: {o['id']} {o['title']}{vp} [{STATE[o['state']]}] —— 欠点: {cons}")
        if not r["rejected"]:
            L.append("- 捨てた案: なし（案が 1 つだけで決めた）")
        for rel in r["relations"]:
            side = "採用" if rel["other_adopted"] else STATE.get(rel["other_state"] or "", "")
            L.append(f"- 案どうしの{RELATION[rel['kind']]}（{rel['link']}）: {rel['other']} {rel['other_title']} [{side}]")
        L.append("")
    if not data["decisions"]:
        L += ["決断がまだ無い（未決の決定点は、まだ何も捨てていない）。", ""]
    L.append("## 検出")
    L += [f"- [{f['id']}] {f['message']}" for f in data["findings"]] or ["- なし"]
    return L


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    p = argparse.ArgumentParser(prog="atam_discards.py", description=(__doc__ or "").splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--db", help="DB の置き場（省くと中核の既定 .pair-agent/design/graph.jsonl）")
    p.add_argument("--backend", choices=["json", "sqlite"], help="省くと --db の拡張子で決める")
    p.add_argument("--dp", action="append", metavar="D", help="この決定点だけ。繰り返せる")
    p.add_argument("--json", action="store_true", help="機械向けの JSON で出す")
    args = p.parse_args(argv)
    dg = load_core()
    if dg is None:
        return 2
    try:
        data = collect(dg.DesignGraph(args.db, args.backend, actor="ai"), args.dp)
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

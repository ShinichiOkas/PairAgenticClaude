#!/usr/bin/env python3
"""設計の因果 DB の状態（世界・システム・部品の三段）を読み、部品の状態の組合せに対する網羅漏れ・重複・「どちらでもよい」と、遷移の供給元なし・行き止まり・到達できない状態を出す。

    python state_space.py [--db PATH] [--backend json|sqlite] [--show N] [--json]

読む形（設計の因果 DB）:
  状態   world_state（WS）・system_state（SS）・component_state（CS。--parent に論理コンポーネント LC）
  定義   SS の attrs.of=[CS…]（部品ごとに 1 つ。指さない部品は「どちらでもよい」）。
         起きてはならない組合せは SS に attrs.forbidden=true と attrs.reason（理由）を付けて禁止にする
  遷移   transitions（同じ種類の状態どうし。CS は同じ部品の中）。attrs.mark＝initial／goal／external
         （初めの状態・目的達成の状態・外の状態）で、供給元なし・行き止まりの誤検出を避ける
出す:
  第 3 段の表（部品と状態・直積の数・定義・どちらでもよい部品・載せた課題）と、網羅漏れ・重複の組合せ
  遷移を描いた段ごとの、供給元なし・行き止まり・初めの状態から到達できない状態
  [state_flow] [state_undefined] [state_gap] [state_overlap]、情報として [state_dont_care]（課題に載せる未決事項）
判定はしない。どちらでもない組合せを、定義に当てるか、理由を付けて禁止にするかはアーキテクトが決める。
中核 design_graph.py の探し方: 環境変数 PAIR_AGENT_DESIGN_GRAPH → この場所から上の tools/design_graph.py
→ ~/.claude/pair-agent/tools/ → ~/.gemini/config/pair-agent/tools/。読むだけで DB には書かない。
終了コード: 0 = 検出なし（情報だけ）／ 1 = 検出あり ／ 2 = 中核が見つからない・入力の誤り
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
NEEDS = "state_space"  # 中核に要る API（古い中核を見分ける）
RULES = ("state_flow", "state_undefined", "state_gap", "state_overlap", "state_dont_care")
PROBLEM = {"no_source": "供給元なし", "dead_end": "行き止まり", "unreachable": "初めの状態から到達できない"}
GROUP = {"world_state": "第 1 段: 世界の状態", "system_state": "第 2 段: システムの状態"}


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
    sp = g.state_space()
    titles = {n["id"]: n["title"] for n in g.find() if n["kind"] in ("world_state", "system_state", "component_state")}
    findings = [f for f in g.check() if f["rule"] in RULES]
    return {"db": str(g.path), "backend": g.backend, "last_seq": g.last_seq, **sp, "titles": titles,
            "findings": findings}


def _combo(states: list[str], titles: dict) -> str:
    return " ∧ ".join(f"{c} {titles.get(c, '')}".strip() for c in states)


def render(data: dict, show: int) -> list[str]:
    t = data["titles"]
    L = [f"DB: {data['db']}（{data['backend']}・seq {data['last_seq']}）", ""]
    L.append("## 第 3 段: システムの状態 ＝ 部品の状態の組合せ")
    if not data["active"]:
        L.append("- まだ無い（attrs.of=[CS…] で正しく定義したシステム状態が 1 つも無い）")
    else:
        for c in data["components"]:
            L.append(f"- {c['id']} {c['title']}: " + "・".join(f"{s} {t.get(s, '')}" for s in c["states"]))
        L.append(f"- 直積 {data['size']} 通り" + ("" if data["enumerated"] else
                                                f"（数え上げの上限 {data['limit']} を超えるので網羅の検査をしていない）"))
        if data["unused_states"]:
            L.append("- どのシステム状態にも使われていない部品の状態: " + ", ".join(data["unused_states"]))
    if data["definitions"]:
        L += ["", "| システム状態 | 定義 | 禁止 | どちらでもよい部品 | 載せた課題 | 誤り |", "|---|---|---|---|---|---|"]
        for d in data["definitions"]:
            ban = f"禁止（{d['reason'] or '理由なし'}）" if d["forbidden"] else ""
            spec = " ∧ ".join(d["spec"].values()) if d["valid"] else "—"
            L.append(f"| {d['id']} {d['title']} | {spec} | {ban} | {', '.join(d['dont_care'])} | "
                     f"{', '.join(d['issues'])} | {'／'.join(d['problems'])} |")
    if data["gaps"]:
        L += ["", f"網羅漏れ {len(data['gaps'])} 通り（定義に当てるか、理由を付けて禁止にする）:"]
        L += [f"  - {_combo(c, t)}" for c in data["gaps"][:show]]
        if len(data["gaps"]) > show:
            L.append(f"  - …ほか {len(data['gaps']) - show} 通り（--show で増やす・--json で全部）")
    if data["overlaps"]:
        L += ["", f"重複 {len(data['overlaps'])} 通り:"]
        L += [f"  - {_combo(o['states'], t)} ← {'・'.join(o['by'])}" for o in data["overlaps"][:show]]
        if len(data["overlaps"]) > show:
            L.append(f"  - …ほか {len(data['overlaps']) - show} 通り")
    L += ["", "## 遷移（遷移を描いた段だけ）"]
    for f in data["flows"]:
        name = GROUP.get(f["group"]) or f"第 3 段: {f['group'].split(':', 1)[1]} の状態"
        L.append(f"- {name}: 状態 {len(f['states'])}・遷移 {f['transitions']}・初めの状態 {', '.join(f['initial']) or 'なし'}")
        for ident, ps in f["problems"].items():
            L.append(f"  - {ident} {t.get(ident, '')}: {'・'.join(PROBLEM[p] for p in ps)}")
    if not data["flows"]:
        L.append("- なし（transitions を張った段が無い）")
    L += ["", "## 検出"]
    L += [f"- [{f['id']}]{'（情報）' if f['level'] == 'info' else ''} {f['message']}" for f in data["findings"]] or ["- なし"]
    return L


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    p = argparse.ArgumentParser(prog="state_space.py", description=(__doc__ or "").splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--db", help="DB の置き場（省くと中核の既定 .pair-agent/design/graph.jsonl）")
    p.add_argument("--backend", choices=["json", "sqlite"], help="省くと --db の拡張子で決める")
    p.add_argument("--show", type=int, default=20, metavar="N", help="網羅漏れ・重複を何通りまで書くか（既定 20）")
    p.add_argument("--json", action="store_true", help="機械向けの JSON で出す（組合せは全部）")
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
        print("\n".join(render(data, max(args.show, 0))))
    return 1 if any(f["level"] != "info" for f in data["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())

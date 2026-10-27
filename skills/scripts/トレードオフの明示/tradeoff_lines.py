#!/usr/bin/env python3
"""設計の因果 DB の採用した案ごとに「X を得るために Y を失う」を 1 行 1 組で書き出し（由来・定量・引き受け手つき）、代償の書かれていない採用案を出す。

    python tradeoff_lines.py [--db PATH] [--backend json|sqlite] [--dp D1 ...] [--json]

読む形（設計の因果 DB）:
  手段  決断（decide）で採用した案の題。得るものは案の attrs.pros（あれば）
  代償  その案の attrs.cons（[{text, origin（means／essential）, measure（定量）, owner（引き受ける役割）}] か文字列）
  関係  採用した案と他の案の conflicts（対立）・synergy（相乗）・linked（連動）・excludes（排他）
出す:
  代償 1 件につき 1 行:「〈得るもの〉を得るために〈代償〉を失う（手段・由来・定量・引き受け）」。
  得るもの（pros）が無ければ「〈案〉を採るために」と書く。由来・定量・引き受けが無ければ無いと書く
  案どうしの関係（広義のトレードオフ）も 1 行ずつ
  [no_cons]  採用した案に代償が書かれていない（「代償なし」は測っていないだけかもしれない）
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
RELATION = {"conflicts": "対立する", "synergy": "相乗効果がある", "linked": "連動する", "excludes": "排他（両立しない）"}
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


def _gain(pros: Any) -> str | None:
    """案の attrs.pros（得るもの）を 1 つの語句にする。無ければ None。"""
    if isinstance(pros, list):
        items = [str(p.get("text", p)) if isinstance(p, dict) else str(p) for p in pros if p not in (None, "")]
        return "・".join(items) or None
    return str(pros) if pros not in (None, "") else None


def line_of(dp: str, option: str, means: str, gain: str | None, c: dict) -> dict:
    """代償 1 件を「手段と代償を同じ行」にする。得るもの（pros）があれば「X を得るために」、無ければ「案を採るために」。"""
    origin = ORIGIN.get(str(c.get("origin")))
    measure = c.get("measure") or c.get("amount")
    owner = c.get("owner") or c.get("bearer")
    head = f"「{gain}」を得るために" if gain else f"「{means}」を採るために"
    text = (f"{dp}: {head}「{c['text']}」を失う（手段: {option} {means}・由来: {origin or '未記入'}・"
            f"定量: {measure or '書いていない'}・引き受け: {owner or '書いていない'}）")
    return {"dp": dp, "option": option, "means": means, "gain": gain, "cost": c["text"], "origin": origin,
            "measure": measure, "owner": owner, "text": text}


def collect(g: Any, dps: list[str] | None) -> dict:
    lines, relations, missing = [], [], []
    seen: set[str] = set()
    for r in g.tradeoffs():
        if dps and r["dp"] not in dps:
            continue
        a = r["adopted"]
        if not a["cons"]:
            missing.append({"dp": r["dp"], "option": a["id"], "means": a["title"]})
        lines += [line_of(r["dp"], a["id"], a["title"], _gain(a.get("pros")), c) for c in a["cons"]]
        for rel in r["relations"]:
            if rel["link"] in seen:  # 採用どうしの関係は両側から見えるので 1 行にする
                continue
            seen.add(rel["link"])
            side = "採用" if rel["other_adopted"] else STATE.get(rel["other_state"] or "", "")
            relations.append({**rel, "dp": r["dp"], "option": a["id"],
                              "text": f"{a['id']} {a['title']} と {rel['other']} {rel['other_title']} [{side}] は"
                                      f"{RELATION[rel['kind']]}（{rel['link']}）"})
    targets = {m["option"] for m in missing}
    findings = [f for f in g.check() if f["rule"] in RULES and (not dps or f["target"] in targets)]
    return {"db": str(g.path), "backend": g.backend, "last_seq": g.last_seq, "lines": lines, "relations": relations,
            "no_cons": missing, "findings": findings}


def render(data: dict) -> list[str]:
    L = [f"DB: {data['db']}（{data['backend']}・seq {data['last_seq']}）", "", "## 手段と代償（1 行 1 組）"]
    L += [f"- {x['text']}" for x in data["lines"]]
    L += [f"- {m['dp']}: 「{m['means']}」を採るために …… ⚠ 代償が書かれていない（測っていないだけかもしれない）"
          for m in data["no_cons"]]
    if not data["lines"] and not data["no_cons"]:
        L.append("- なし（採用した案がまだ無い）")
    if data["relations"]:
        L += ["", "## 案どうしの関係（広義のトレードオフ）"] + [f"- {x['text']}" for x in data["relations"]]
    L += ["", "## 検出"]
    L += [f"- [{f['id']}] {f['message']}" for f in data["findings"]] or ["- なし"]
    return L


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    p = argparse.ArgumentParser(prog="tradeoff_lines.py", description=(__doc__ or "").splitlines()[0],
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

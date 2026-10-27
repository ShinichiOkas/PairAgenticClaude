#!/usr/bin/env python3
"""サブエージェント定義（agents/*.md）の maxTurns とモデルを tools/emit_agents.py の正典表と突き合わせ、費用を「呼び出し回数 x 文脈」で見積もる。

使い方:
  python cost_ops.py audit --agents .claude/agents          # 正典表とのずれ・低すぎる maxTurns・機械役のモデル過剰を検出（読むだけ）
  python cost_ops.py lookup build                           # 役名 -> tier / maxTurns / 推奨モデル
  python cost_ops.py estimate --calls 120 --context-tokens 150000 --model sonnet   # 文脈再読込の費用の目安
  python cost_ops.py usage -- --since 2026-10-20            # 実測は tools/measure_agent_usage.py に委ねる（薄い入口）

正典表は tools/emit_agents.py の ROLE_CONFIGS（複製しない。ここから読む）。--tools-dir で場所を変えられる。
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

DEFAULT_TOOLS = Path(__file__).resolve().parents[4] / "tools"
FLOOR_TURNS = 200  # 師匠の宣言: maxTurns は信用の数値。定型役でも 200 未満は低すぎる
# $/MTok の cache_read（measure_agent_usage.py の PRICE と同じ値。文脈の再読込が費用の主因なので read 価格で見る）
CACHE_READ = {"opus": 0.5, "sonnet": 0.2, "haiku": 0.1, "fable": 0.25}


def load_emit_agents(tools_dir: Path):
    path = tools_dir / "emit_agents.py"
    if not path.is_file():
        raise FileNotFoundError(f"emit_agents.py が無い: {path}")
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    spec = importlib.util.spec_from_file_location("emit_agents_for_cost_ops", path)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def parse_fm(text: str) -> dict[str, str]:
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---", text.lstrip("﻿"), re.S)
    fm: dict[str, str] = {}
    for ln in (m.group(1).splitlines() if m else []):
        km = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*?)\s*$", ln)
        if km:
            fm[km.group(1)] = km.group(2).strip("'\"")
    return fm


def cmd_audit(a) -> int:
    ea = load_emit_agents(Path(a.tools_dir))
    d = Path(a.agents)
    files = sorted(d.glob("*.md")) if d.is_dir() else []
    if not files:
        print(f"ERROR: エージェント定義が無い: {d}", file=sys.stderr)
        return 2
    bad = 0
    for f in files:
        fm = parse_fm(f.read_text(encoding="utf-8", errors="replace"))
        name = fm.get("name") or f.stem
        if "maxTurns" not in fm and "model" not in fm:
            continue  # 役割エージェントではない（手書きの agent）
        conf = ea.get_role_config(name)
        issues = []
        try:
            turns = int(fm.get("maxTurns", "0"))
        except ValueError:
            turns = 0
        if turns <= 0:
            issues.append("maxTurns が無い/不正")
        elif turns < FLOOR_TURNS:
            issues.append(f"maxTurns={turns} は低すぎる（下限 {FLOOR_TURNS}。低い数値は信用できないという意味）")
        elif turns != conf["max_turns"]:
            issues.append(f"maxTurns={turns} が正典表 {conf['max_turns']} と違う")
        model = fm.get("model", "")
        if model != conf["claude"]:
            issues.append(f"model={model or '無し'} が正典表 {conf['claude']} (tier {conf['tier']}) と違う")
        if conf["tier"] == 3 and model not in ("haiku", ""):
            issues.append("機械役（tier 3）が haiku でない")
        if issues:
            bad += 1
            print(f"- {f.name}: " + " / ".join(issues))
    print(f"\n{len(files)} 定義を検査 / ずれ {bad} 件")
    return 1 if bad else 0


def cmd_lookup(a) -> int:
    ea = load_emit_agents(Path(a.tools_dir))
    c = ea.get_role_config(a.role)
    print(f"{a.role}: tier {c['tier']} / maxTurns {c['max_turns']} / claude={c['claude']} / gemini={c['gemini']}")
    return 0


def cmd_estimate(a) -> int:
    price = CACHE_READ.get(a.model)
    if price is None:
        print(f"ERROR: model は {sorted(CACHE_READ)} のどれか", file=sys.stderr)
        return 2
    total_tokens = a.calls * a.context_tokens
    cost = total_tokens / 1_000_000 * price
    print(f"{a.calls} 回 x 文脈 {a.context_tokens:,} トークン = {total_tokens:,} トークン読み込み")
    print(f"目安: ${cost:.2f}（{a.model} の cache read ${price}/MTok。出力・書き込み分は含まない）")
    if a.split > 1:
        # 割って並列にすると、文脈が 1/split、呼び出し回数も 1/split になる（各体は短く走る）
        c2 = (a.calls / a.split) * (a.context_tokens / a.split) * a.split / 1_000_000 * price
        print(f"{a.split} 分割して並列にした場合の目安: ${c2:.2f}（各体の文脈・回数が 1/{a.split}）")
    return 0


def cmd_usage(a) -> int:
    script = Path(a.tools_dir) / "measure_agent_usage.py"
    rest = [x for x in a.rest if x != "--"]
    return subprocess.call([sys.executable, str(script), *rest])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--tools-dir", default=str(DEFAULT_TOOLS))
    sub = p.add_subparsers(dest="cmd", required=True)
    au = sub.add_parser("audit")
    au.add_argument("--agents", default=".claude/agents")
    lk = sub.add_parser("lookup")
    lk.add_argument("role")
    es = sub.add_parser("estimate")
    es.add_argument("--calls", type=int, required=True)
    es.add_argument("--context-tokens", type=int, required=True)
    es.add_argument("--model", default="sonnet")
    es.add_argument("--split", type=int, default=1)
    us = sub.add_parser("usage")
    us.add_argument("rest", nargs=argparse.REMAINDER)
    a = p.parse_args(argv)
    try:
        return {"audit": cmd_audit, "lookup": cmd_lookup, "estimate": cmd_estimate, "usage": cmd_usage}[a.cmd](a)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

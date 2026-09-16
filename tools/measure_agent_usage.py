#!/usr/bin/env python3
"""
measure_agent_usage.py -- 会話記録（JSONL）から、親セッションとサブエージェントの
呼び出し回数・文脈トークン・費用・所要時間を集計する計器（Mnemo 実走成果・2026-09-16）。

使用法:
    python tools/measure_agent_usage.py
    python tools/measure_agent_usage.py --project <project_path>
    python tools/measure_agent_usage.py --since 2026-09-15
"""
from __future__ import annotations

import argparse
import collections
import datetime
import glob
import json
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

PRICE = {  # $/MTok: input, output, cache_write, cache_read
    "fable": (10, 50, 12.5, 0.25),
    "opus": (5, 25, 6.25, 0.5),
    "sonnet": (2, 10, 2.5, 0.2),
    "haiku": (1, 5, 1.25, 0.1),
    "flash": (0.075, 0.3, 0.01875, 0.01875),  # 参考: Gemini Flash 系
    "pro": (1.25, 5.0, 0.3125, 0.3125),      # 参考: Gemini Pro 系
}

ROLE_PAT = [
    (r"build|構築者", "build"),
    (r"execute-acceptance|受入検査実施者", "accept"),
    (r"design-acceptance|受入検査設計者", "accept-design"),
    (r"run-regression|非回帰", "regression"),
    (r"keep-ledger|帳簿係", "ledger"),
    (r"sync-repository|同期担当", "sync"),
    (r"elicit-intent|意図取得者", "intent"),
    (r"run-probe|探針", "probe"),
    (r"write-specification|仕様作成者", "spec"),
    (r"reconcile-documents|ドキュメント整合", "docs"),
    (r"file-defect|起票者", "defect"),
    (r"evaluate-release|解除判定", "release"),
    (r"retrospective|振り返り", "retro"),
    (r"deliberation|協議", "delib"),
    (r"Explore|探索|影響範囲|調査", "explore"),
]


def tier(model: str) -> str:
    m = (model or "").lower()
    for k in PRICE:
        if k in m:
            return k
    return "opus"


def role_of(text: str) -> str:
    for pat, name in ROLE_PAT:
        if re.search(pat, text or "", re.IGNORECASE):
            return name
    return "other"


def parse_session(path: Path) -> tuple[list[dict], str]:
    calls = []
    first_user = None
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                t = d.get("type")
                if t == "user" and first_user is None:
                    c = d.get("message", {}).get("content")
                    if isinstance(c, list):
                        c = " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    first_user = str(c or "")[:4000]
                if t != "assistant":
                    continue
                m = d.get("message", {})
                u = m.get("usage") or {}
                if not u:
                    continue
                calls.append(
                    dict(
                        ts=d.get("timestamp"),
                        model=m.get("model"),
                        inp=u.get("input_tokens", 0) or 0,
                        cw=u.get("cache_creation_input_tokens", 0) or 0,
                        cr=u.get("cache_read_input_tokens", 0) or 0,
                        out=u.get("output_tokens", 0) or 0,
                    )
                )
    except Exception:
        pass
    return calls, first_user or ""


def aggregate(calls: list[dict]) -> tuple[dict, float, float, dict, Optional[str], Optional[str]]:
    r = collections.Counter()
    cost = 0.0
    for c in calls:
        r["calls"] += 1
        r["inp"] += c["inp"]
        r["cw"] += c["cw"]
        r["cr"] += c["cr"]
        r["out"] += c["out"]
        p = PRICE[tier(c["model"])]
        cost += (c["inp"] * p[0] + c["out"] * p[1] + c["cw"] * p[2] + c["cr"] * p[3]) / 1e6

    ts = [c["ts"] for c in calls if c.get("ts")]
    dur = 0.0
    t0, t1 = None, None
    if ts:
        t0, t1 = min(ts), max(ts)
        try:
            a = datetime.datetime.fromisoformat(t0.replace("Z", "+00:00"))
            b = datetime.datetime.fromisoformat(t1.replace("Z", "+00:00"))
            dur = (b - a).total_seconds() / 60
        except Exception:
            pass

    models = collections.Counter(tier(c["model"]) for c in calls)
    return dict(r), cost, dur, dict(models), t0, t1


def main() -> int:
    parser = argparse.ArgumentParser(description="エージェント使用量・コスト集計計器")
    parser.add_argument("--project", default=None, help="Claude プロジェクトディレクトリ名")
    parser.add_argument("--since", default="", help="集計開始日時 (YYYY-MM-DD)")
    args = parser.parse_args()

    claude_projects = Path.home() / ".claude" / "projects"
    if not claude_projects.exists():
        print(f"情報: {claude_projects} が存在しません。")
        return 0

    target_dirs = []
    if args.project:
        target_dirs = [claude_projects / args.project]
    else:
        target_dirs = [d for d in claude_projects.iterdir() if d.is_dir()]

    sessions = []
    for pdir in target_dirs:
        for mainf in pdir.glob("*.jsonl"):
            sid = mainf.stem
            calls, _ = parse_session(mainf)
            if not calls:
                continue
            r, cost, dur, models, t0, t1 = aggregate(calls)
            subs = []
            sub_dir = pdir / sid / "subagents"
            if sub_dir.exists():
                for sf in sub_dir.glob("*.jsonl"):
                    sc, fu = parse_session(sf)
                    if not sc:
                        continue
                    sr, scost, sdur, smodels, st0, _ = aggregate(sc)
                    fixed = sc[0]["cw"] + sc[0]["cr"] + sc[0]["inp"] if sc else 0
                    chosen_model = max(smodels, key=smodels.get) if smodels else "unknown"
                    subs.append(
                        dict(
                            id=sf.stem,
                            role=role_of(fu),
                            model=chosen_model,
                            calls=sr["calls"],
                            total=sr["inp"] + sr["cw"] + sr["cr"],
                            out=sr["out"],
                            cost=scost,
                            dur=sdur,
                            fixed=fixed,
                            t0=st0,
                        )
                    )
            sessions.append(
                dict(
                    sid=sid,
                    t0=t0,
                    t1=t1,
                    main=r,
                    main_cost=cost,
                    main_dur=dur,
                    models=models,
                    subs=subs,
                )
            )

    sessions.sort(key=lambda s: s["t0"] or "")
    if args.since:
        sessions = [x for x in sessions if (x["t0"] or "") >= args.since]

    if not sessions:
        print("集計対象のセッションが見つかりませんでした。")
        return 0

    print("# エージェント使用量・コスト集計 (Phase ROLE 計器)")
    print(
        "| session | start | main calls | main ctx tokens | main out | main $ | main min | sub n | sub ctx tokens | sub out | sub $ | total $ |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in sessions:
        m = s["main"]
        ctx = m["inp"] + m["cw"] + m["cr"]
        sn = len(s["subs"])
        sctx = sum(x["total"] for x in s["subs"])
        sout = sum(x["out"] for x in s["subs"])
        scost = sum(x["cost"] for x in s["subs"])
        t0_str = (s["t0"] or "")[:16]
        print(
            f"| {s['sid'][:8]} | {t0_str} | {m['calls']} | {ctx/1e6:.2f}M | {m['out']/1e3:.0f}k | {s['main_cost']:.0f} | {s['main_dur']:.0f} | {sn} | {sctx/1e6:.2f}M | {sout/1e3:.0f}k | {scost:.0f} | {s['main_cost']+scost:.0f} |"
        )

    print("\n## サブエージェント内訳")
    print("| session | role | model | calls | ctx tokens | out | fixed(1st) | $ | min |")
    print("|---|---|---|---|---|---|---|---|---|")
    for s in sessions:
        for x in sorted(s["subs"], key=lambda x: x["t0"] or ""):
            print(
                f"| {s['sid'][:8]} | {x['role']} | {x['model']} | {x['calls']} | {x['total']/1e3:.0f}k | {x['out']/1e3:.1f}k | {x['fixed']/1e3:.0f}k | {x['cost']:.2f} | {x['dur']:.0f} |"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())

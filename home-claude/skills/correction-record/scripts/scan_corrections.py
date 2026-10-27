#!/usr/bin/env python3
"""corrections/ を読んで一覧・集計・再発照合・昇格候補の抽出をする（読むだけ）。

使い方:
  python scan_corrections.py stats                          # trigger / severity / domain の件数
  python scan_corrections.py search --domain git --keyword push   # 同じ状況が再発していないか照合
  python scan_corrections.py unlinked                       # proposed_skill_id が空 = Skill に昇格していない記録と、昇格先の種別提案

昇格の目安（correction-record の規約）: high -> user_model/hard_boundary、medium -> user_model/preference_negative、
low -> 同じ trigger が 2 件以上たまったら提案。
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

DEFAULT_HOME = Path.home() / ".claude" / "pair-agent"
SEV_ORDER = {"low": 0, "medium": 1, "high": 2}


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    text = text.lstrip("﻿")
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fm: dict[str, object] = {}
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*?)\s*$", line)
        if not km:
            continue
        k, v = km.group(1), km.group(2)
        if v.startswith("[") and v.endswith("]"):
            fm[k] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
        else:
            fm[k] = v.strip("'\"")
    return fm, m.group(2)


def norm_severity(raw: object) -> str:
    s = str(raw or "").lower()
    if "high" in s:
        return "high"
    if "medium" in s:
        return "medium"
    return "low"


def first_quote(body: str) -> str:
    m = re.search(r"^>\s*(.+)$", body, re.M)
    if m:
        return m.group(1).strip()
    m = re.search(r"「(.+?)」", body, re.S)
    return m.group(1).strip() if m else ""


def load(home: Path) -> list[dict]:
    out = []
    d = home / "corrections"
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.md")):
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        dm = re.match(r"(\d{4}-\d{2}-\d{2})", f.name)
        date = str(fm.get("recorded_at") or fm.get("date") or (dm.group(1) if dm else ""))[:10]
        domains = fm.get("related_domains") or []
        if isinstance(domains, str):
            domains = [domains]
        psid = str(fm.get("proposed_skill_id") or "").strip()
        out.append({
            "file": f.name, "date": date, "trigger": str(fm.get("trigger") or "(不明)"),
            "severity": norm_severity(fm.get("severity")), "domains": list(domains),
            "proposed_skill_id": "" if psid.lower() in ("", "null", "none", "~") else psid,
            "quote": first_quote(body), "body": body,
        })
    return out


def cmd_stats(recs: list[dict]) -> int:
    print(f"記録 {len(recs)} 件")
    for title, key in (("trigger", "trigger"), ("severity", "severity")):
        c = collections.Counter(r[key] for r in recs)
        print(f"\n[{title}]")
        for k, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {k}: {n}")
    dc = collections.Counter(d for r in recs for d in r["domains"])
    print("\n[domain]")
    for k, n in sorted(dc.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {k}: {n}")
    return 0


def cmd_search(recs: list[dict], domains: list[str], keywords: list[str]) -> int:
    hits = []
    for r in recs:
        dom_hit = any(d in r["domains"] for d in domains)
        kw_hit = any(k.lower() in (r["body"] + r["file"]).lower() for k in keywords)
        if (domains or keywords) and (dom_hit or kw_hit):
            hits.append(r)
    if not hits:
        print("該当する過去の叱られ記録はありません")
        return 0
    hits.sort(key=lambda r: (-SEV_ORDER[r["severity"]], r["date"]))
    for r in hits:
        print(f"- [{r['severity']}] {r['date']} {r['file']}  trigger={r['trigger']}")
        if r["quote"]:
            print(f"  以前『{r['quote']}』と教わっています。今回は触ってよいですか？")
    return 0


def propose_kind(severity: str) -> str:
    return {"high": "user_model / hard_boundary", "medium": "user_model / preference_negative",
            "low": "蓄積（同 trigger 2 件以上で提案）"}[severity]


def cmd_unlinked(recs: list[dict]) -> int:
    un = [r for r in recs if not r["proposed_skill_id"]]
    low_by_trigger = collections.Counter(r["trigger"] for r in un if r["severity"] == "low")
    shown = 0
    for r in sorted(un, key=lambda r: (-SEV_ORDER[r["severity"]], r["date"])):
        if r["severity"] == "low" and low_by_trigger[r["trigger"]] < 2:
            continue
        shown += 1
        print(f"- [{r['severity']}] {r['date']} {r['file']} -> {propose_kind(r['severity'])}")
    print(f"\n昇格候補 {shown} 件 / 未昇格 {len(un)} 件 / 全 {len(recs)} 件")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--home", default=str(DEFAULT_HOME))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    s = sub.add_parser("search")
    s.add_argument("--domain", action="append", default=[])
    s.add_argument("--keyword", action="append", default=[])
    sub.add_parser("unlinked")
    a = p.parse_args(argv)
    recs = load(Path(a.home))
    if a.cmd == "stats":
        return cmd_stats(recs)
    if a.cmd == "search":
        return cmd_search(recs, a.domain, a.keyword)
    return cmd_unlinked(recs)


if __name__ == "__main__":
    sys.exit(main())

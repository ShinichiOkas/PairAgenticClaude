#!/usr/bin/env python3
"""振り返りの材料（期間内の叱られ記録・登録済み Skill・ジャーナルの経過・合意の叱られ/見切り発車）を集め、報告ブロックの雛形を作る（読むだけ）。

使い方:
  python retro_collect.py collect --since 2026-10-20 [--project .] [--sprint-id ID]
      # 叱られ記録ごとに「既存 Skill の更新候補」（domain_tags / related_domains の重なり）も添える。重複登録を防ぐ
  python retro_collect.py report --json registrations.json
      # [{"id","kind":"新規|更新","maturity","line","evidence","where"}] から「■ 登録した Skill」ブロックを描く

候補の判断（maturity をどうするか）は AI がする。このスクリプトは集めて突き合わせるだけ。
"""
from __future__ import annotations

import argparse
import json
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


def parse_fm(text: str) -> dict[str, object]:
    text = text.lstrip("﻿")
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---", text, re.S)
    fm: dict[str, object] = {}
    if not m:
        return fm
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*?)\s*$", line)
        if km:
            k, v = km.group(1), km.group(2)
            fm[k] = ([x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
                     if v.startswith("[") and v.endswith("]") else v.strip("'\""))
    return fm


def file_date(fm: dict, name: str, *keys: str) -> str:
    for k in keys:
        if fm.get(k):
            return str(fm[k])[:10]
    m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else ""


def as_list(v) -> list[str]:
    if isinstance(v, list):
        return v
    return [t.strip() for t in str(v or "").split(",") if t.strip()]


def corrections_since(home: Path, since: str) -> list[dict]:
    out = []
    d = home / "corrections"
    for f in sorted(d.glob("*.md")) if d.is_dir() else []:
        text = f.read_text(encoding="utf-8", errors="replace")
        fm = parse_fm(text)
        date = file_date(fm, f.name, "recorded_at", "date")
        if date and date >= since:
            qm = re.search(r"^>\s*(.+)$", text, re.M) or re.search(r"「(.+?)」", text, re.S)
            out.append({"file": f.name, "date": date, "trigger": str(fm.get("trigger", "")),
                        "severity": str(fm.get("severity", "")), "domains": as_list(fm.get("related_domains")),
                        "linked": str(fm.get("proposed_skill_id", "")).lower() not in ("", "null", "none"),
                        "quote": qm.group(1).strip() if qm else ""})
    return out


def skills_all(dirs: list[Path]) -> list[dict]:
    out = []
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(list(d.glob("*.md")) + list(d.glob("*/SKILL.md"))):
            fm = parse_fm(f.read_text(encoding="utf-8", errors="replace"))
            out.append({"file": f, "name": str(fm.get("name") or f.stem), "maturity": str(fm.get("maturity", "")),
                        "tags": as_list(fm.get("domain_tags")),
                        "created": file_date(fm, f.name, "created_at"), "updated": file_date(fm, f.name, "updated_at", "created_at")})
    return out


def block_of(text: str, heading: str) -> str:
    m = re.search(rf"^##\s*{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def cmd_collect(a) -> int:
    home, project = Path(a.home), Path(a.project)
    since = a.since
    corr = corrections_since(home, since)
    skills = skills_all([home / "skills", project / ".pair-agent" / "skills"])
    print(f"# 振り返りの材料（{since} 以降）\n")
    print(f"## 叱られ記録 {len(corr)} 件")
    for c in corr:
        cand = [s["name"] for s in skills if set(s["tags"]) & set(c["domains"])]
        mark = "（Skill 化済み）" if c["linked"] else "（未昇格）"
        print(f"- {c['date']} [{c['severity']}] {c['file']} {mark}")
        if c["quote"]:
            print(f"    原文: {c['quote']}")
        if cand:
            print(f"    既存 Skill の更新候補（同ドメイン）: {', '.join(cand[:5])}")
    changed = [s for s in skills if (s["created"] >= since or s["updated"] >= since)]
    print(f"\n## 期間内に作成/更新された Skill {len(changed)} 件")
    for s in changed:
        kind = "新規" if s["created"] >= since else "更新"
        print(f"- [{kind}] {s['name']} ({s['maturity']}) {s['file'].name}")
    ag_dir = project / ".pair-agent" / "agreements"
    print("\n## 合意ドキュメントの叱られ/見切り発車")
    n = 0
    for f in sorted(ag_dir.glob("*.md")) if ag_dir.is_dir() else []:
        t = f.read_text(encoding="utf-8", errors="replace")
        for h in ("修正・叱られ記録", "見切り発車の記録", "AIの懸念"):
            b = block_of(t, h)
            if b:
                n += 1
                print(f"- {f.name} / {h}: {b.splitlines()[0][:100]}")
    if not n:
        print("- なし")
    jdir = project / ".pair-agent" / "sprints"
    print("\n## ジャーナルの経過")
    jn = 0
    for f in sorted(jdir.glob("*.json")) if jdir.is_dir() else []:
        if a.sprint_id and a.sprint_id not in f.name:
            continue
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for e in j.get("経過", []) or []:
            at = str(e.get("at", "") if isinstance(e, dict) else "")[:10]
            if isinstance(e, dict) and at >= since:
                jn += 1
                print(f"- {f.name} {at} {e.get('status', '')} {e.get('note', '')}".rstrip())
    if not jn:
        print("- なし")
    return 0


def render_report(items: list[dict]) -> str:
    if not items:
        return "今回は Skill にする候補はありません\n"
    lines = ["■ 登録した Skill"]
    for it in items:
        lines.append(f" - [{it['id']}・{it.get('kind', '新規')}・{it['maturity']}] {it['line']}  "
                     f"根拠: {it['evidence']}  保存先: {it['where']}")
    lines += ["", "■ 取り消すとき", " - 師匠が「これは違う」と言ったら、その Skill を取り消す（削除、または maturity を下げる）。CorrectionRecord として記録する"]
    return "\n".join(lines) + "\n"


def cmd_report(a) -> int:
    items = json.loads(Path(a.json).read_text(encoding="utf-8"))
    need = {"id", "maturity", "line", "evidence", "where"}
    for i, it in enumerate(items):
        miss = need - set(it)
        if miss:
            print(f"ERROR: {i} 件目に {sorted(miss)} が無い", file=sys.stderr)
            return 2
        if it["maturity"] not in ("draft", "forming", "confirmed"):
            print(f"ERROR: {i} 件目の maturity が不正", file=sys.stderr)
            return 2
    sys.stdout.write(render_report(items))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--home", default=str(DEFAULT_HOME))
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--since", required=True, help="YYYY-MM-DD")
    c.add_argument("--project", default=".")
    c.add_argument("--sprint-id", default="")
    r = sub.add_parser("report")
    r.add_argument("--json", required=True)
    a = p.parse_args(argv)
    if a.cmd == "collect" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.since):
        print("ERROR: --since は YYYY-MM-DD", file=sys.stderr)
        return 2
    return cmd_collect(a) if a.cmd == "collect" else cmd_report(a)


if __name__ == "__main__":
    sys.exit(main())

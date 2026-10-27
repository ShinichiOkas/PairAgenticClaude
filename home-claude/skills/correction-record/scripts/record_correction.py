#!/usr/bin/env python3
"""師匠の叱責・否定フィードバックを CorrectionRecord の定形で corrections/ に書き出す（既定は下見、--apply で書く）。

使い方:
  python record_correction.py --trigger scope_violation --severity high \
      --quote "勝手なことするな" --action "頼まれていない修正をした" \
      --learning "頼まれた範囲の外は票にして託す" --domains scope,git --slug no-unrequested-fix --apply

発話の原文は --quote のまま保持する（解釈は --learning に分ける）。既存ファイルは上書きしない。
"""
from __future__ import annotations

import argparse
import datetime
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
TRIGGERS = (
    "human_reprimand", "work_interrupted", "scope_violation", "wrong_assumption",
    "unwanted_style", "overengineering", "under_specified", "terminology_mismatch",
)
SEVERITIES = ("low", "medium", "high")


def slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return s


def render(*, recorded_at: str, sprint_id: str, trigger: str, severity: str,
           domains: list[str], quote: str, action: str, learning: str) -> str:
    return (
        "---\n"
        f"recorded_at: {recorded_at}\n"
        f"sprint_id: {sprint_id}\n"
        f"trigger: {trigger}\n"
        f"severity: {severity}\n"
        f"related_domains: [{', '.join(domains)}]\n"
        "proposed_skill_id: null\n"
        "---\n\n"
        "## 人間の発話\n\n"
        f"「{quote}」\n\n"
        "## AIの直前の行動\n\n"
        f"{action}\n\n"
        "## 解釈した学び\n\n"
        f"{learning}\n"
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--home", default=str(DEFAULT_HOME), help="ペア固有の置き場（既定 ~/.claude/pair-agent）")
    p.add_argument("--trigger", required=True, choices=TRIGGERS)
    p.add_argument("--severity", required=True, choices=SEVERITIES)
    p.add_argument("--quote", required=True, help="師匠の発話の原文")
    p.add_argument("--action", required=True, help="AI の直前の行動")
    p.add_argument("--learning", required=True, help="解釈した境界線・ルール")
    p.add_argument("--domains", default="", help="related_domains（カンマ区切り）")
    p.add_argument("--sprint-id", default="none")
    p.add_argument("--slug", default="", help="ファイル名の後半（英数字・ハイフン）。省略時は trigger")
    p.add_argument("--date", default="", help="YYYY-MM-DD（既定は今日）")
    p.add_argument("--apply", action="store_true", help="書き込む（無ければ下見）")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    date = a.date or datetime.date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        print(f"ERROR: --date は YYYY-MM-DD: {date}", file=sys.stderr)
        return 2
    slug = slugify(a.slug) or slugify(a.trigger.replace("_", "-"))
    domains = [d.strip() for d in a.domains.split(",") if d.strip()]
    body = render(recorded_at=date, sprint_id=a.sprint_id, trigger=a.trigger, severity=a.severity,
                  domains=domains, quote=a.quote.strip(), action=a.action.strip(), learning=a.learning.strip())
    target = Path(a.home) / "corrections" / f"{date}-{slug}.md"
    if target.exists():
        print(f"ERROR: 既に有る（上書きしない）: {target}", file=sys.stderr)
        return 3
    if not a.apply:
        print(f"[下見] 書き出し先: {target}\n")
        print(body)
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")
    print(f"記録した: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

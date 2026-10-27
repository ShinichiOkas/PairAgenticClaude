#!/usr/bin/env python3
"""合意ドキュメントの雛形作成・版の更新（version/変更ログ/カウンタ）・追記セクション・構造検査をする。既定は下見、--apply で書く。

使い方:
  python agreement_ops.py new --slug login-fix --sprint-id S1 --goal "ログイン修正" --task "原因調査:AI" --apply
  python agreement_ops.py bump agreements/login-fix.md --reason "前提崩壊" --kind premise --apply   # premise|improvement|other
  python agreement_ops.py append agreements/login-fix.md --section concern --text "..." --severity high --apply
  python agreement_ops.py check agreements/login-fix.md       # フロントマター・必須節・1画面サイズ・ファイルパス列挙の検出

section: concern(AIの懸念) / abort(見切り発車の記録) / scold(修正・叱られ記録)
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

STATUSES = ("drafting", "deliberating", "agreed", "executing", "retrospecting", "completed")
REQUIRED_FM = ("sprint_id", "version", "status", "created_at", "updated_at")
REQUIRED_SECTIONS = ("スプリントゴール", "タスク", "スコープ", "完了条件", "前提", "既知リスク", "変更ログ")
SECTION_TITLES = {"concern": "AIの懸念", "abort": "見切り発車の記録", "scold": "修正・叱られ記録"}
MAX_LINES = 120  # 「1 画面で足りる大きさ」の目安
PATH_RE = re.compile(r"(?:[\w.-]+/)+[\w.-]+\.(?:py|js|ts|tsx|md|json|sh|c|cpp|h|go|rs|java|cs|html|css|yaml|yml)\b")


def stamp(now: str) -> str:
    return now or datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def template(a, ts: str) -> str:
    tasks = "\n".join(
        f"- [ ] {t.split(':', 1)[0]}（担当: {t.split(':', 1)[1] if ':' in t else 'AI'}）" for t in a.task
    ) or "- [ ] {タスク説明}（担当: AI / 人間 / 両方）"
    conds = "\n".join(f"- {c}" for c in a.done) or "- {検証可能な条件}"
    prem = "\n".join(f"- {c}" for c in a.premise) or "- {前提条件}"
    risk = "\n".join(f"- {c}" for c in a.risk) or "- {リスク}"
    return (
        "---\n"
        f"sprint_id: {a.sprint_id}\n"
        "version: 1\n"
        "status: drafting\n"
        f"created_at: {ts}\n"
        f"updated_at: {ts}\n"
        f"domain_tags: [{', '.join(t.strip() for t in a.tags.split(',') if t.strip())}]\n"
        "change_count_premise: 0\n"
        "change_count_improvement: 0\n"
        "---\n\n"
        f"# スプリントゴール\n\n{a.goal}\n\n"
        f"## タスク\n\n{tasks}\n\n"
        "## スコープ\n\n"
        f"{a.scope or '{自然言語で記述}'}\n"
        "事前にファイルパスは列挙しない。AIはタスク記述から判断し、迷ったら推奨で進めて判断一覧に書く（止まって聞かない）。\n\n"
        f"## 完了条件\n\n{conds}\n\n"
        f"## 前提\n\n{prem}\n\n"
        f"## 既知リスク\n\n{risk}\n\n"
        f"## 変更ログ\n\n- v1 [{ts}]: 初版\n"
    )


def cmd_new(a) -> int:
    ts = stamp(a.now)
    target = Path(a.dir) / f"{a.slug}.md"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", a.slug):
        print("ERROR: --slug は英数字とハイフン", file=sys.stderr)
        return 2
    if target.exists():
        print(f"ERROR: 既に有る（上書きしない）: {target}", file=sys.stderr)
        return 3
    body = template(a, ts)
    if not a.apply:
        print(f"[下見] {target}\n\n{body}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8", newline="\n")
    print(f"作成した: {target}")
    return 0


def fm_get(text: str, key: str) -> str | None:
    m = re.search(rf"^{key}:\s*(.*?)\s*$", text.split("\n---", 2)[0], re.M)
    return m.group(1) if m else None


def fm_set(text: str, key: str, value: str) -> str:
    head, sep, rest = text.partition("\n---")
    if re.search(rf"^{key}:", head, re.M):
        head = re.sub(rf"^{key}:.*$", f"{key}: {value}", head, count=1, flags=re.M)
    else:
        head += f"\n{key}: {value}"
    return head + sep + rest


def cmd_bump(a) -> int:
    path = Path(a.file)
    t = path.read_text(encoding="utf-8")
    ts = stamp(a.now)
    try:
        ver = int(fm_get(t, "version") or "0") + 1
    except ValueError:
        print("ERROR: version が整数でない", file=sys.stderr)
        return 2
    t = fm_set(t, "version", str(ver))
    t = fm_set(t, "updated_at", ts)
    if a.kind in ("premise", "improvement"):
        key = f"change_count_{a.kind}"
        t = fm_set(t, key, str(int(fm_get(t, key) or "0") + 1))
    if a.status:
        t = fm_set(t, "status", a.status)
    label = {"premise": "前提崩壊", "improvement": "より良い方法", "other": "その他"}[a.kind]
    entry = f"- v{ver} [{ts}]: {a.reason}（{label}）"
    m = re.search(r"^##\s*変更ログ\s*$(.*?)(?=^##\s|\Z)", t, re.S | re.M)
    if m:
        body = t[m.start(1):m.end(1)].rstrip("\n")
        tail = t[m.end(1):]
        t = t[:m.start(1)] + body + "\n" + entry + ("\n" if tail else "") + tail
    else:
        t = t.rstrip("\n") + f"\n\n## 変更ログ\n\n{entry}\n"
    if not a.apply:
        print(f"[下見] version -> {ver}, 変更ログ: {entry}")
        return 0
    path.write_text(t, encoding="utf-8", newline="\n")
    print(f"更新した: {path} (v{ver})")
    return 0


def cmd_append(a) -> int:
    path = Path(a.file)
    t = path.read_text(encoding="utf-8")
    ts = stamp(a.now)
    title = SECTION_TITLES[a.section]
    if a.section == "concern":
        entry = f"> [{ts}] severity: {a.severity}\n> {a.text}\n"
    elif a.section == "abort":
        entry = f"> [{ts}]\n> 理由: {a.text}\n> 承認したリスク: {a.risk}\n"
    else:
        entry = (f"> [{ts}] severity: {a.severity}\n> 人間: 「{a.text}」\n"
                 f"> AIがしたこと: {a.action}\n> 学び: {a.learning}\n")
    if re.search(rf"^##\s*{re.escape(title)}\s*$", t, re.M):
        # その節の末尾（次の ## の直前）へ
        m = re.search(rf"^##\s*{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)", t, re.S | re.M)
        end = m.end() if m else len(t)
        t = t[:end].rstrip("\n") + "\n\n" + entry + ("\n" if t[end:] else "") + t[end:]
    else:
        t = t.rstrip("\n") + f"\n\n## {title}\n\n{entry}"
    if not a.apply:
        print(f"[下見] ## {title} に追記:\n{entry}")
        return 0
    path.write_text(t, encoding="utf-8", newline="\n")
    print(f"追記した: {path} / {title}")
    return 0


def cmd_check(a) -> int:
    path = Path(a.file)
    t = path.read_text(encoding="utf-8")
    problems: list[str] = []
    if not t.startswith("---"):
        problems.append("フロントマターが無い")
    for k in REQUIRED_FM:
        if fm_get(t, k) is None:
            problems.append(f"フロントマターに {k} が無い")
    st = fm_get(t, "status")
    if st and st not in STATUSES:
        problems.append(f"status '{st}' は規定外 {STATUSES}")
    heads = set(re.findall(r"^#{1,2}\s*(.+?)\s*$", t, re.M))
    for s in REQUIRED_SECTIONS:
        if s not in heads:
            problems.append(f"必須の節 '{s}' が無い")
    nlines = len(t.splitlines())
    if nlines > MAX_LINES:
        problems.append(f"{nlines} 行 > {MAX_LINES}（1 画面で足りる大きさを超えている）")
    scope = re.search(r"^##\s*スコープ\s*$(.*?)(?=^##\s|\Z)", t, re.S | re.M)
    if scope:
        paths = PATH_RE.findall(scope.group(1))
        if len(paths) >= 3:
            problems.append(f"スコープにファイルパスが {len(paths)} 個列挙されている（事前に列挙しない規約）: {paths[:3]}")
    tasks_open = len(re.findall(r"^- \[ \]", t, re.M))
    tasks_done = len(re.findall(r"^- \[x\]", t, re.M | re.I))
    if st == "completed" and tasks_open:
        problems.append(f"completed なのに未完了タスクが {tasks_open} 件")
    for p in problems:
        print("NG ", p)
    print(f"\n{path.name}: status={st} lines={nlines} タスク 完了{tasks_done}/未{tasks_open} / 問題 {len(problems)} 件")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--now", default="", help="タイムスタンプ固定（テスト用）")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--slug", required=True)
    n.add_argument("--sprint-id", required=True)
    n.add_argument("--goal", required=True)
    n.add_argument("--task", action="append", default=[], help="'説明:担当'（繰り返し可）")
    n.add_argument("--done", action="append", default=[], help="完了条件（繰り返し可）")
    n.add_argument("--premise", action="append", default=[])
    n.add_argument("--risk", action="append", default=[])
    n.add_argument("--scope", default="")
    n.add_argument("--tags", default="")
    n.add_argument("--dir", default=".pair-agent/agreements")
    n.add_argument("--apply", action="store_true")
    b = sub.add_parser("bump")
    b.add_argument("file")
    b.add_argument("--reason", required=True)
    b.add_argument("--kind", choices=("premise", "improvement", "other"), default="other")
    b.add_argument("--status", choices=STATUSES, default="")
    b.add_argument("--apply", action="store_true")
    ap = sub.add_parser("append")
    ap.add_argument("file")
    ap.add_argument("--section", required=True, choices=list(SECTION_TITLES))
    ap.add_argument("--text", required=True)
    ap.add_argument("--severity", default="medium", choices=("low", "medium", "high"))
    ap.add_argument("--risk", default="", help="abort: 承認したリスク")
    ap.add_argument("--action", default="", help="scold: AIがしたこと")
    ap.add_argument("--learning", default="", help="scold: 学び")
    ap.add_argument("--apply", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("file")
    a = p.parse_args(argv)
    return {"new": cmd_new, "bump": cmd_bump, "append": cmd_append, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

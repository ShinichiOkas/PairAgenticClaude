#!/usr/bin/env python3
"""バグ票（markdown）を検査し、件名や事実欄に診断・解き方が混ざっていないか、症状と実測の欄が揃っているかを機械で数える。

使い方:
  python lint_defect.py TICKET.md          # 検査（読むだけ）
  python lint_defect.py --template         # 欄の雛形を標準出力へ
終了コード: 0=指摘なし(warn のみは 0) / 1=error あり / 2=入力不備
"""
import argparse
import json
import re
import sys
from pathlib import Path

# 件名に置いてはならない診断の語
SUBJECT_DIAG = [r"たぶん", r"多分", r"おそらく", r"恐らく", r"原因", r"のせい", r"が悪い",
                r"\bprobably\b", r"\bmaybe\b", r"root cause", r"caused by", r"\bdue to\b", r"\bbecause\b"]
# 事実の欄に置いてはならない診断・解き方の語
FACT_DIAG = [r"原因は", r"が原因", r"のはず", r"はずだ", r"修正(す)?(べき|すれば|案)", r"直す(には|べき)",
             r"解決策", r"対策", r"fix(es)? by", r"should be (changed|fixed)", r"the cause", r"root cause"]
SPECULATION_HEAD = re.compile(r"推測|仮説|speculat|hypothes", re.I)
REQUIRED = [("症状", r"症状|symptom"), ("期待", r"期待|expected"), ("実測", r"実測|実際|actual|observed"),
            ("再現手順", r"再現|手順|steps|reproduc"), ("証拠", r"証拠|evidence"), ("タイムライン", r"タイムライン|時刻|timeline")]

TEMPLATE = """# <症状で書く件名: 何をしたら何が起きた>

## 症状
<何をしたら何が起きたか。再現できる粒度で>

## 期待した結果

## 実際の結果（実測）
<数値・メッセージ・終了コードなど測ったもの>

## 再現手順

## 証拠
<入力 / ログ / 環境(版・設定) / 時刻 の 4 点。生ログは別に残す>

## タイムライン
<事象の時刻 と 採取の時刻 を分けて書く>

## 推測（任意・診断と解き方はここだけ）
"""


def sections(text):
    """(見出し, [(行番号, 行)]) の列。最初の # は件名として別に返す。"""
    subject, secs, cur = None, [], None
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)
        if m:
            if len(m.group(1)) == 1 and subject is None:
                subject = (i, m.group(2))
                cur = None
                continue
            cur = (m.group(2), [])
            secs.append(cur)
            continue
        if cur is not None:
            cur[1].append((i, line))
    return subject, secs


def lint(text):
    issues = []

    def add(sev, code, line, msg):
        issues.append({"severity": sev, "code": code, "line": line, "message": msg})

    subject, secs = sections(text)
    if subject is None:
        add("error", "no-subject", 0, "件名（# 見出し）が無い")
    else:
        for pat in SUBJECT_DIAG:
            if re.search(pat, subject[1], re.I):
                add("error", "subject-diagnosis", subject[0], f"件名に診断の語「{pat}」: 件名は症状で書く")
                break
    heads = [h for h, _ in secs]
    for label, pat in REQUIRED:
        if not any(re.search(pat, h, re.I) for h in heads):
            add("error" if label in ("症状", "実測") else "warn", "missing-section", 0, f"欄が無い: {label}")
    for head, lines in secs:
        if SPECULATION_HEAD.search(head):
            continue
        for ln, line in lines:
            if re.match(r"^\s*[-*>]?\s*(推測|仮説)\s*[:：]", line):
                continue
            for pat in FACT_DIAG:
                if re.search(pat, line, re.I):
                    add("warn", "diagnosis-in-fact", ln, f"「{head}」欄に診断/解き方の語「{pat}」: 推測欄へ分けるか「推測:」と明記")
                    break
    for head, lines in secs:
        if re.search(r"実測|実際|actual|observed", head, re.I):
            body = "\n".join(l for _, l in lines)
            if not re.search(r"\d", body):
                add("warn", "no-measurement", 0, f"「{head}」欄に数字が無い: 測ったものを書く")
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ticket", nargs="?")
    ap.add_argument("--template", action="store_true", help="雛形を標準出力へ出す")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.template:
        sys.stdout.write(TEMPLATE)
        return 0
    if not a.ticket or not Path(a.ticket).is_file():
        print("入力ファイルが無い", file=sys.stderr)
        return 2
    issues = lint(Path(a.ticket).read_text(encoding="utf-8"))
    errs = sum(1 for i in issues if i["severity"] == "error")
    if a.json:
        print(json.dumps({"issues": issues, "errors": errs}, ensure_ascii=False, indent=2))
    else:
        for i in issues:
            print(f"{i['severity']:5} {i['code']:18} L{i['line']}: {i['message']}")
        print(f"error {errs} 件 / warn {len(issues) - errs} 件")
    return 1 if errs else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

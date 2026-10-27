#!/usr/bin/env python3
"""設計保証（markdown）の主張とエビデンスの対応を数え、エビデンスの無い主張・「確認済み」だけの主張・検められない材料を指摘する。

受け付ける形（どちらでもよい）:
  表:   | 項目 | 主張 | エビデンス |   （見出し行に「主張」「エビデンス」を含む列。項目 ID 列は任意）
  節:   ### S-3 見出し   の下に   - 主張: ...   - エビデンス: ...
使い方:
  python lint_assurance.py upstream/設計保証.md [--json]
指摘: no-evidence(error) / weak-evidence(error: 「確認済み」等だけ) / unverifiable(warn: 手順・数・機械の出力が見えない)
      / quote-only(warn: ソース引用だけ) / no-unverified-section(warn: 確かめなかったことの節が無い)
終了コード: 0 / 1=error あり / 2=入力不備
"""
import argparse
import json
import re
import sys
from pathlib import Path

EMPTY = {"", "-", "—", "–", "なし", "無し", "tbd", "todo", "n/a", "なし。"}
WEAK = [r"レビュー(し|済)", r"確認(し|済|した)", r"問題(は)?(ない|なし|無い)", r"目視", r"チェック(し|済)", r"\bLGTM\b",
        r"reviewed", r"looks good", r"verified manually"]
VERIFIABLE = [r"`[^`]*\s[^`]*`", r"^\s*\$ ", r"\bpytest\b", r"\bpython\b", r"\bgrep\b", r"\d+\s*(件|個|/|本|行|%)",
              r"\d+\s*/\s*\d+", r"出力", r"終了コード", r"exit", r"手順", r"coverage|カバレッジ", r"静的解析|mypy|ruff|flake8"]
UNVERIFIED_HEAD = re.compile(r"確かめ(られ)?な|保証(し|でき)な|未確認|残留リスク|未カバー")


def parse(text):
    claims = []
    lines = text.splitlines()
    col = None
    cur = None
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            if any("主張" in c for c in cells) and any("エビデンス" in c or "証拠" in c for c in cells):
                col = {"claim": next(j for j, c in enumerate(cells) if "主張" in c),
                       "ev": next(j for j, c in enumerate(cells) if "エビデンス" in c or "証拠" in c),
                       "id": next((j for j, c in enumerate(cells) if c in ("項目", "ID", "仕様項目", "項目ID")), None)}
                continue
            if col and len(cells) > max(col["claim"], col["ev"]):
                claims.append({"line": i, "id": cells[col["id"]] if col["id"] is not None and col["id"] < len(cells) else None,
                               "claim": cells[col["claim"]], "evidence": cells[col["ev"]]})
            continue
        col = None if s and not s.startswith("|") else col
        m = re.match(r"^#{2,6}\s+(.*\S)", s)
        if m:
            cur = {"line": i, "id": m.group(1).split()[0], "claim": "", "evidence": "", "_ev": False}
            claims.append(cur)
            continue
        if cur is not None:
            mm = re.match(r"^[-*]?\s*(主張|claim)\s*[:：]\s*(.*)", s, re.I)
            me = re.match(r"^[-*]?\s*(エビデンス|証拠|evidence)\s*[:：]\s*(.*)", s, re.I)
            if mm:
                cur["claim"] = mm.group(2)
                cur["_ev"] = False
            elif me:
                cur["evidence"] = me.group(2)
                cur["_ev"] = True
            elif cur["_ev"] and s:
                cur["evidence"] += "\n" + line
    # 主張も無い見出し（残留リスク節など）は除く
    out = [c for c in claims if c["claim"] or c["evidence"]]
    for c in out:
        c.pop("_ev", None)
    return out


def lint(text):
    issues = []

    def add(sev, code, line, msg):
        issues.append({"severity": sev, "code": code, "line": line, "message": msg})

    claims = parse(text)
    if not claims:
        add("error", "no-claims", 0, "主張が 1 件も読み取れない（表か節の形か）")
    for c in claims:
        label = c["id"] or c["claim"][:20]
        ev = c["evidence"].strip()
        if ev.lower() in EMPTY:
            add("error", "no-evidence", c["line"], f"{label}: エビデンスが無い（主張だけの保証は保証ではない）")
            continue
        verifiable = any(re.search(p, ev, re.M | re.I) for p in VERIFIABLE)
        weak = any(re.search(p, ev, re.I) for p in WEAK)
        if weak and not verifiable:
            add("error", "weak-evidence", c["line"], f"{label}: 「確認済み」等のみ。受け手が検められない")
        elif not verifiable:
            add("warn", "unverifiable", c["line"], f"{label}: 手順・数・機械の出力のいずれも見えない")
        stripped = re.sub(r"```.*?```", "", ev, flags=re.S)
        if "```" in ev and len(stripped.strip()) < 15 and not verifiable:
            add("warn", "quote-only", c["line"], f"{label}: ソースの引用だけ（読ませることになる）")
    heads = re.findall(r"^#{1,6}\s+(.*)$", text, re.M)
    if not any(UNVERIFIED_HEAD.search(h) for h in heads):
        add("warn", "no-unverified-section", 0, "確かめられなかったこと／保証しなかったことの節が無い")
    return claims, issues


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("assurance")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    p = Path(a.assurance)
    if not p.is_file():
        print("設計保証ファイルが無い", file=sys.stderr)
        return 2
    claims, issues = lint(p.read_text(encoding="utf-8"))
    errs = sum(i["severity"] == "error" for i in issues)
    with_ev = sum(1 for c in claims if c["evidence"].strip().lower() not in EMPTY)
    summary = {"claims": len(claims), "with_evidence": with_ev, "errors": errs, "warnings": len(issues) - errs}
    if a.json:
        print(json.dumps({"summary": summary, "issues": issues}, ensure_ascii=False, indent=2))
    else:
        for i in issues:
            print(f"{i['severity']:5} {i['code']:22} L{i['line']}: {i['message']}")
        print(f"主張 {summary['claims']} 件のうちエビデンス付き {with_ev} 件 / error {errs} / warn {summary['warnings']}")
    return 1 if errs else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

#!/usr/bin/env python
"""受入検査報告書を受入検査仕様と突き合わせ、「全部通った」で終わっていないか（未カバー領域が書かれているか）を検める。

    python coverage_gaps.py REPORT.md [--spec SPEC.md] [--id-pattern 'T-\\d+']

項目 ID（既定 `[A-Z]{1,5}-\\d+`、例 T-01 / AC-12）を仕様と報告の双方から数え、次を指摘する:
  [結果なし]       仕様にあるのに報告に出てこない項目（黙って落ちている）
  [仕様外]         報告にあるのに仕様に無い項目
  [未カバー節なし] 「未カバー／試さなかった／確かめていない／判定できない」を見出しとする節が報告に無い
  [未カバー節が空] 節はあるが中身が「なし」だけ、または理由（データが無い／環境が無い／再現手順が無い 等）が無い
  [全部通った止まり] 「全部通った／全件合格」と書きつつ上の節が弱い
  [取りこぼし未記載] 合格と書いた項目の記述に、仕様項目のどこを判定できないかの言及が無い（参考。二値にしない）
判定はしない。指摘するだけ（人が読む）。終了コード: 0 = 指摘なし ／ 1 = 指摘あり ／ 2 = 入力不正
"""
from __future__ import annotations

import argparse
import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

SECTION_WORDS = ("未カバー", "試さなかった", "試せなかった", "確かめていない", "確かめられなかった", "判定できない", "カバーできなかった")
REASON_WORDS = ("データ", "環境", "再現", "手順", "権限", "時間", "期間", "ため", "から", "理由", "不足", "用意できない", "無い", "ない")
ALL_PASSED = re.compile(r"全部通った|全件(?:が)?合格|すべて(?:の項目が)?合格|全て(?:の項目が)?合格|all\s+(?:tests\s+)?pass", re.I)
PASS_MARK = re.compile(r"✅|合格|\bPASS\b|\bOK\b", re.I)
PARTIAL_WORDS = ("判定できない", "取りこぼし", "見ていない", "確かめていない", "カバーしていない", "部分的", "一部")
EMPTY_ONLY = re.compile(r"^[\s\-*・>]*(?:なし|無し|特になし|none|n/?a|-)?[\s。.]*$", re.I)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def sections(text: str):
    """見出し（# 始まり）ごとの (見出し, 本文行) を返す。"""
    out, title, buf = [], None, []
    for line in text.splitlines():
        if re.match(r"^\s{0,3}#{1,6}\s", line):
            if title is not None:
                out.append((title, buf))
            title, buf = re.sub(r"^\s*#+\s*", "", line).strip(), []
        elif title is not None:
            buf.append(line)
    if title is not None:
        out.append((title, buf))
    return out


def blocks_by_id(text: str, idre: re.Pattern):
    """ID を含む行から、次に ID を含む行か見出しの手前までを 1 ブロックとする。"""
    blocks: dict[str, str] = {}
    cur: list[str] = []
    for line in text.splitlines():
        ids = list(dict.fromkeys(idre.findall(line)))
        if re.match(r"^\s{0,3}#{1,6}\s", line) and not ids:
            cur = []
            continue
        if ids:
            cur = ids
        for i in cur:
            blocks[i] = blocks.get(i, "") + line + "\n"
    return blocks


def analyze(report: str, spec: str | None, id_pattern: str):
    idre = re.compile(id_pattern)
    problems: list[dict] = []

    def add(kind, msg):
        problems.append({"kind": kind, "message": msg})

    rep_blocks = blocks_by_id(report, idre)
    if spec is not None:
        spec_ids = list(dict.fromkeys(idre.findall(spec)))
        for i in spec_ids:
            if i not in rep_blocks:
                add("結果なし", f"{i}: 仕様にあるが報告に結果が無い")
        for i in rep_blocks:
            if i not in spec_ids:
                add("仕様外", f"{i}: 報告にあるが仕様に無い")
    secs = [(t, b) for t, b in sections(report) if any(w in t for w in SECTION_WORDS)]
    weak = False
    if not secs:
        add("未カバー節なし", "未カバー領域（試さなかった条件・判定できなかった箇所）を見出しとする節が無い")
        weak = True
    else:
        for t, body in secs:
            content = [ln for ln in body if ln.strip() and not ln.strip().startswith("<!--")]
            joined = "\n".join(content)
            if not content or all(EMPTY_ONLY.match(ln) for ln in content):
                add("未カバー節が空", f"「{t}」の中身が空か「なし」だけ。実行した者にしか分からない情報が出ていない")
                weak = True
            elif not any(w in joined for w in REASON_WORDS):
                add("未カバー節が空", f"「{t}」に試せなかった理由（データ／環境／再現手順 等）が読み取れない")
                weak = True
    m = ALL_PASSED.search(report)
    if m and weak:
        add("全部通った止まり", f"「{m.group(0)}」と書きつつ未カバー領域が書かれていない。合否は 1 ビットで、入力から導ける")
    for i, blk in rep_blocks.items():
        if PASS_MARK.search(blk) and not re.search(r"不合格|✗|❌|\bFAIL", blk) and not any(w in blk for w in PARTIAL_WORDS):
            add("取りこぼし未記載", f"{i}: 合格だが、仕様項目のどこを判定できないかの記述が無い（「なし」と明記するのでもよい）")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="受入検査報告書の未カバー領域の記述を検める（読むだけ）")
    ap.add_argument("report")
    ap.add_argument("--spec")
    ap.add_argument("--id-pattern", default=r"\b[A-Z]{1,5}-\d+\b")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        report = read(a.report)
        spec = read(a.spec) if a.spec else None
        re.compile(a.id_pattern)
    except (OSError, re.error) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    problems = analyze(report, spec, a.id_pattern)
    if a.json:
        print(json.dumps(problems, ensure_ascii=False, indent=2))
    else:
        print(f"指摘: {len(problems)} 件")
        for p in problems:
            print(f"  [{p['kind']}] {p['message']}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

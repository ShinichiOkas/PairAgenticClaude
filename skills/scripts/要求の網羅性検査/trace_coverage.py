#!/usr/bin/env python
"""入力の項目番号から出力を逆向きに走査し、落ちた項目・自分の発明・「すべて対応」報告の自己矛盾を洗い出す。

    python trace_coverage.py 項目.txt 出力.md [--report 完了報告.md] [--strict]

項目.txt は number_items.py の出力（`R1: ...`）。出力.md の箇条書き 1 項目につき、行内に次のどれかを付ける:
    [由来: R1, R3]        上流が言ったことを写した
    [発明: R2 理由]       上流が言っていないことを自分で決めて埋めた（R2 は埋めた穴）
    [扱い: 暫定 R4]       写せない項目の扱い（スコープ外／延期／代案／不可能／暫定）
「対応あり」を由来で割る: 発明で埋めた穴は対応ありに数えない。タグの無い箇条書きは「由来未記入」として指摘する。
--report があれば、報告が「自分で定義を選んでいない」等を ✅ と書きながら発明が残っていないかを突き合わせる。
断定はせず、疑いを指摘するだけ。読むだけ。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

TYPES = ["スコープ外", "延期", "代案", "不可能", "暫定"]
ID = r"[A-Za-z]+\d+"
ITEM_RE = re.compile(rf"^\s*(?:[-*+]\s*)?\[?({ID})\]?\s*[:：]\s*(.*)$")
TAG_RE = re.compile(r"\[(由来|発明|扱い)\s*[:：]?\s*([^\]]*)\]")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
CLAIM_RE = re.compile(r"自分で定義を選んでいない|発明(?:は)?(?:ない|なし|0)|過剰(?:は)?(?:ない|なし)|要求にないことを(?:追加|足)していない|漏れ(?:が)?(?:ない|なし|0|ゼロ)|すべて(?:対応|写)")
CONFESS_RE = re.compile(r"自分の解釈|自分で(?:決め|言語化|選|埋め)|私の解釈|独自に(?:決め|定め)")


def read_items(text: str) -> dict[str, str]:
    items: dict[str, str] = {}
    for line in text.splitlines():
        m = ITEM_RE.match(line)
        if m:
            items[m.group(1)] = re.sub(r"\s*\[曖昧語:[^\]]*\]\s*$", "", m.group(2)).strip()
    return items


def trace(items: dict[str, str], out_text: str) -> dict:
    derived: dict[str, list[int]] = {}
    treated: dict[str, list[tuple[str, int]]] = {}
    invented_holes: dict[str, list[int]] = {}
    invented: list[int] = []
    untagged: list[int] = []
    problems: list[str] = []
    for no, line in enumerate(out_text.splitlines(), 1):
        if not BULLET_RE.match(line):
            continue
        tags = TAG_RE.findall(line)
        if not tags:
            untagged.append(no)
            continue
        for kind, body in tags:
            ids = re.findall(ID, body)
            if kind == "由来":
                if not ids:
                    problems.append(f"[番号が無い] {no} 行目: 由来に項目番号が無い")
                for i in ids:
                    if i not in items:
                        problems.append(f"[存在しない番号] {no} 行目: {i} は入力に無い")
                    else:
                        derived.setdefault(i, []).append(no)
            elif kind == "発明":
                invented.append(no)
                for i in ids:
                    if i not in items:
                        problems.append(f"[存在しない番号] {no} 行目: {i} は入力に無い")
                    else:
                        invented_holes.setdefault(i, []).append(no)
            else:
                t = next((x for x in TYPES if x in body), None)
                if t is None:
                    problems.append(f"[扱いの型が不明] {no} 行目: 5 型（{'・'.join(TYPES)}）のどれでもない → {body.strip()}")
                if not ids:
                    problems.append(f"[番号が無い] {no} 行目: 扱いに項目番号が無い")
                for i in ids:
                    if i not in items:
                        problems.append(f"[存在しない番号] {no} 行目: {i} は入力に無い")
                    elif t:
                        treated.setdefault(i, []).append((t, no))
    missing = [i for i in items if i not in derived and i not in treated]
    only_invented = [i for i in missing if i in invented_holes]
    dropped = [i for i in missing if i not in invented_holes]
    return {"derived": derived, "treated": treated, "invented": invented, "invented_holes": invented_holes,
            "untagged": untagged, "problems": problems, "only_invented": only_invented, "dropped": dropped}


def check_report(report: str, res: dict) -> list[str]:
    out: list[str] = []
    n_inv = len(res["invented"])
    n_gap = len(res["dropped"]) + len(res["only_invented"])
    for no, line in enumerate(report.splitlines(), 1):
        if not CLAIM_RE.search(line):
            continue
        ok = "✅" in line or "充足" in line or "OK" in line
        if not ok:
            continue
        if n_inv and re.search(r"自分で定義を選んでいない|発明(?:は)?(?:ない|なし|0)|過剰(?:は)?(?:ない|なし)|要求にないことを", line):
            out.append(f"[自己矛盾の疑い] 報告 {no} 行目は発明なしを ✅ と書くが、出力に発明が {n_inv} 件ある → {line.strip()}")
        if n_gap and re.search(r"漏れ|すべて", line):
            out.append(f"[自己矛盾の疑い] 報告 {no} 行目は漏れなしを ✅ と書くが、写されていない項目が {n_gap} 件ある → {line.strip()}")
        for cn, cl in enumerate(report.splitlines(), 1):
            if CONFESS_RE.search(cl) and cn != no:
                out.append(f"[自己矛盾の疑い] 報告 {no} 行目の ✅ と、{cn} 行目の自己申告（自分の解釈）が同じ報告に載っている → {cl.strip()}")
                break
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("items", type=Path, help="採番済みの入力項目（R1: ...）")
    ap.add_argument("output", type=Path, help="由来タグ付きの出力")
    ap.add_argument("--report", type=Path, help="突き合わせる完了報告")
    ap.add_argument("--strict", action="store_true", help="指摘があれば終了コード 1")
    a = ap.parse_args(argv)
    for p in (a.items, a.output) + ((a.report,) if a.report else ()):
        if not p.is_file():
            print(f"エラー: ファイルが無い: {p}", file=sys.stderr)
            return 2
    items = read_items(a.items.read_text(encoding="utf-8"))
    if not items:
        print("エラー: 入力項目が読めない（`R1: ...` の形の行が無い）", file=sys.stderr)
        return 2
    res = trace(items, a.output.read_text(encoding="utf-8"))
    findings = list(res["problems"])
    print(f"入力項目: {len(items)} ／ 入力由来で対応: {len(res['derived'])} ／ 扱い付き: {len(res['treated'])}"
          f" ／ 出力側の発明: {len(res['invented'])} 件")
    for i in res["dropped"]:
        findings.append(f"[落ちた項目] {i}: {items[i]}")
    for i in res["only_invented"]:
        findings.append(f"[発明で埋めた穴] {i}: 上流の言葉で答えられておらず、自分で決めて埋めた → {items[i]}")
    for no in res["untagged"]:
        findings.append(f"[由来未記入] 出力 {no} 行目の箇条書きに [由来:]/[発明:]/[扱い:] が無い（発明の疑い）")
    if a.report:
        findings += check_report(a.report.read_text(encoding="utf-8"), res)
    for f in findings:
        print(f)
    if not findings:
        print("指摘なし（逆向き走査では全項目が由来または扱いで対応し、発明の申告もない）")
    else:
        print("※ 疑いの指摘であって断定ではない。判定は人間が行う。")
    return 1 if (a.strict and findings) else 0


if __name__ == "__main__":
    sys.exit(main())

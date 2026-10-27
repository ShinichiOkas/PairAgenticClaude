#!/usr/bin/env python3
"""探針の計画書（Markdown）を、走らせる前に検査・凍結し、走らせた後に計画が書き換わっていないかと遮断語の混入を確かめる。

  lint PLAN.md      : 必須の節（何を測るか／測定条件／判定基準／できなかった・原理的にできないの区別）の有無と、
                      遮断語（期日・見積もり・締切・deadline・estimate）が計画に混ざっていないかを検査
  freeze PLAN.md --out PLAN.lock : 計画の SHA-256 と時刻を記録（既存 lock は上書きしない）
  verify PLAN.md PLAN.lock       : 凍結後に計画が書き換えられていないか（測ってから対象を変えていないか）
  classify RESULT.md : 結果の「できなかった」「原理的にできない」の主張を拾い、後者に根拠（上限を決める量・反証条件）があるか検査
終了コード: 指摘があれば 1。lint/classify/verify は読むだけ。
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

REQUIRED = {
    "何を測るか": r"何を測る|測定対象|測る対象|目的",
    "測定条件": r"測定条件|環境|データ.*版|再現",
    "判定基準": r"判定基準|合格基準|しきい値|閾値|何が示されたら",
    "できない区別": r"原理的にできない|できなかった",
}
BLOCKED = re.compile(r"期日|見積もり|見積り|締切|締め切り|納期|deadline|estimate", re.I)
IMPOSSIBLE = re.compile(r"原理的に(?:は)?(?:できない|不可能)")
GROUND = re.compile(r"上限|帯域|光速|メモリ|容量|限界|bound|limit", re.I)
FALSIFY = re.compile(r"反証|覆る|覆す|示されたら|falsif", re.I)


def read(p):
    return Path(p).read_text(encoding="utf-8")


def lint(text):
    issues = []
    for name, pat in REQUIRED.items():
        if not re.search(pat, text):
            issues.append(f"必須項目が無い: {name}")
    for n, line in enumerate(text.splitlines(), start=1):
        m = BLOCKED.search(line)
        if m:
            issues.append(f"遮断語の混入: 行{n} 「{m.group(0)}」（見れば合う結果を報告してしまう）")
    return issues


def classify(text):
    issues = []
    for n, line in enumerate(text.splitlines(), start=1):
        if IMPOSSIBLE.search(line):
            # 同じ行と前後 2 行を根拠の探索範囲にする
            lines = text.splitlines()
            ctx = "\n".join(lines[max(0, n - 3): n + 2])
            if not GROUND.search(ctx):
                issues.append(f"行{n}: 「原理的にできない」に上限を決める量の名指しが無い（「できなかった」と書くべきか）")
            if not FALSIFY.search(ctx):
                issues.append(f"行{n}: 「原理的にできない」に反証条件が無い")
    return issues


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    sub.add_parser("lint").add_argument("plan")
    sub.add_parser("classify").add_argument("result")
    f = sub.add_parser("freeze")
    f.add_argument("plan")
    f.add_argument("--out", required=True)
    v = sub.add_parser("verify")
    v.add_argument("plan")
    v.add_argument("lock")
    a = ap.parse_args(argv)
    issues = []
    if a.mode == "lint":
        issues = lint(read(a.plan))
    elif a.mode == "classify":
        issues = classify(read(a.result))
    elif a.mode == "freeze":
        pre = lint(read(a.plan))
        if pre:
            for i in pre:
                print("[指摘] " + i)
            print("計画に不備があるので凍結しない")
            return 1
        rec = {"plan": str(a.plan), "sha256": sha(a.plan),
               "frozen_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
        try:
            with open(a.out, "x", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        except FileExistsError:
            print(f"既存ファイルは上書きしない: {a.out}", file=sys.stderr)
            return 2
        print(f"凍結: {a.out} sha256={rec['sha256'][:12]}")
        return 0
    elif a.mode == "verify":
        lock = json.loads(read(a.lock))
        if sha(a.plan) != lock["sha256"]:
            issues.append(f"計画が凍結({lock['frozen_at']})後に書き換わっている")
    for i in issues:
        print("[指摘] " + i)
    print(f"指摘 {len(issues)} 件")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())

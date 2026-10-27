#!/usr/bin/env python3
"""git の変更履歴から、分担の候補（ディレクトリ等の括り）を跨いで一緒に変わる頻度を数え、境界を移す候補を出す。

使い方:
  python co_change.py --repo . --depth 2                       # 先頭 2 階層を括りとして集計（git を呼ぶ）
  python co_change.py --log hist.txt --group ui='src/ui/*' --group core='src/core/*' --suggest 0.3
hist.txt は `git log --no-merges --name-only --pretty=format:@@COMMIT@@%H` の出力。
「片方だけ変更して済むか」= 括りごとの単独変更率、「境界を跨ぐ変更の頻度」= 跨ぎ率、を出す。
巨大コミット（--max-files 超）は一括整形の可能性が高いので除外して件数を報告する。
終了コード: 0 / 2=入力不備
"""
import argparse
import fnmatch
import json
import subprocess
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

MARK = "@@COMMIT@@"


def parse_log(text):
    commits, cur = [], None
    for line in text.splitlines():
        if line.startswith(MARK):
            cur = {"id": line[len(MARK):].strip(), "files": []}
            commits.append(cur)
        elif line.strip() and cur is not None:
            cur["files"].append(line.strip().replace("\\", "/"))
    return commits


def group_of(path, depth, groups):
    if groups:
        for name, pat in groups:
            if fnmatch.fnmatch(path, pat):
                return name
        return None
    parts = path.split("/")
    return "/".join(parts[:depth]) if len(parts) > depth else "(root)"


def analyze(commits, depth=1, groups=None, max_files=50):
    pairs, singles, touched, big, skipped = Counter(), Counter(), Counter(), 0, 0
    cross = used = 0
    for c in commits:
        if len(c["files"]) > max_files:
            big += 1
            continue
        gs = sorted({g for g in (group_of(f, depth, groups) for f in c["files"]) if g})
        if not gs:
            skipped += 1
            continue
        used += 1
        for g in gs:
            touched[g] += 1
        if len(gs) == 1:
            singles[gs[0]] += 1
        else:
            cross += 1
            for p in combinations(gs, 2):
                pairs[p] += 1
    out = {"commits_total": len(commits), "commits_used": used, "excluded_large": big, "excluded_unmatched": skipped,
           "cross_boundary_commits": cross, "cross_ratio": round(cross / used, 3) if used else None, "groups": [], "pairs": []}
    for g in sorted(touched):
        out["groups"].append({"group": g, "commits": touched[g], "solo_commits": singles[g],
                              "solo_ratio": round(singles[g] / touched[g], 3)})
    for (x, y), n in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0])):
        jac = n / (touched[x] + touched[y] - n)
        out["pairs"].append({"a": x, "b": y, "co_commits": n, "jaccard": round(jac, 3)})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--repo")
    src.add_argument("--log", help="git log 出力ファイル（- で標準入力）")
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--group", action="append", default=[], metavar="NAME=GLOB")
    ap.add_argument("--since", default=None)
    ap.add_argument("--max-files", type=int, default=50)
    ap.add_argument("--suggest", type=float, default=None, help="jaccard がこの値以上の対を境界移動候補として出す")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.repo:
        cmd = ["git", "-c", "core.quotepath=off", "log", "--no-merges", "--name-only", f"--pretty=format:{MARK}%H"]
        if a.since:
            cmd.append(f"--since={a.since}")
        try:
            r = subprocess.run(cmd, cwd=a.repo, capture_output=True, text=True, encoding="utf-8", timeout=120)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"git を呼べない: {e}", file=sys.stderr)
            return 2
        if r.returncode:
            print(r.stderr.strip(), file=sys.stderr)
            return 2
        text = r.stdout
    else:
        try:
            text = sys.stdin.read() if a.log == "-" else Path(a.log).read_text(encoding="utf-8")
        except OSError as e:
            print(f"読めない: {e}", file=sys.stderr)
            return 2
    groups = []
    for g in a.group:
        n, _, pat = g.partition("=")
        if not pat:
            print(f"--group は NAME=GLOB: {g}", file=sys.stderr)
            return 2
        groups.append((n, pat))
    commits = parse_log(text)
    if not commits:
        print("コミットが読み取れない（@@COMMIT@@ 形式か）", file=sys.stderr)
        return 2
    res = analyze(commits, a.depth, groups, a.max_files)
    if a.suggest is not None:
        res["suggest_move_boundary"] = [p for p in res["pairs"] if p["jaccard"] >= a.suggest]
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    print(f"コミット {res['commits_used']} 件を集計（巨大 {res['excluded_large']} / 対象外 {res['excluded_unmatched']} を除外）")
    print(f"境界を跨ぐ変更: {res['cross_boundary_commits']} 件（跨ぎ率 {res['cross_ratio']}）")
    for g in res["groups"]:
        print(f"  {g['group']:<30} 変更 {g['commits']:>4} 件 / 単独で済んだ {g['solo_commits']:>4}（{g['solo_ratio']}）")
    for p in res["pairs"][:10]:
        print(f"  同時に変わる: {p['a']} <-> {p['b']} {p['co_commits']} 回（jaccard {p['jaccard']}）")
    for p in res.get("suggest_move_boundary", []):
        print(f"境界を移す候補: {p['a']} と {p['b']} は同じ担い手に置く方が合意が減る可能性（jaccard {p['jaccard']}）")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

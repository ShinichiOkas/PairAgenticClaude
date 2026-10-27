#!/usr/bin/env python3
"""コマンドを N 回走らせて所要時間のゼロ点（基準）を環境・git 版つきで記録し、後の測定との差がばらつきを超えるかを判定する。

  record  -- CMD...   : N 回測って JSON を出力する。--out を付けたときだけ書く（既存は上書きしない）
  compare BASE.json -- CMD... : 現在を測り、ゼロ点との差が基準のばらつき(k*sd)を超えるか・条件が一致するかを出す
使い方: zero_point.py record -n 5 --out base.json -- python bench.py
注意: 変更に着手する前に record すること。git の HEAD と未コミット有無を記録するので、後から取ったかの手掛かりになる。
"""
import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time


def git_state(cwd):
    def g(*args):
        try:
            r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
            return r.stdout.strip() if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None
    head = g("rev-parse", "HEAD")
    dirty = g("status", "--porcelain")
    return {"head": head, "dirty": None if dirty is None else bool(dirty)}


def environment(cwd):
    return {"python": platform.python_version(), "platform": platform.platform(),
            "machine": platform.machine(), "cpu_count": os.cpu_count(), "git": git_state(cwd)}


def measure(cmd, n, warmup, cwd):
    for _ in range(warmup):
        subprocess.run(cmd, cwd=cwd, capture_output=True)
    times = []
    for _ in range(n):
        t = time.perf_counter()
        r = subprocess.run(cmd, cwd=cwd, capture_output=True)
        times.append(time.perf_counter() - t)
        if r.returncode != 0:
            raise SystemExit(f"コマンドが失敗 (exit {r.returncode}): 失敗する対象のゼロ点は取れない")
    return times


def stats(times):
    return {"n": len(times), "mean": statistics.fmean(times),
            "stdev": statistics.stdev(times) if len(times) > 1 else None,
            "min": min(times), "max": max(times), "median": statistics.median(times)}


def compare(base, cur, k):
    notes = []
    bs, cs = base["stats"], cur["stats"]
    if bs["n"] < 2 or bs["stdev"] is None:
        notes.append("ゼロ点が 1 回しか無く、ばらつきが不明。差が有意かは判定できない")
        verdict = "UNKNOWN"
    else:
        delta = cs["mean"] - bs["mean"]
        thr = k * bs["stdev"]
        verdict = "SAME" if abs(delta) <= thr else ("SLOWER" if delta > 0 else "FASTER")
        notes.append(f"差 {delta:+.6g}s、閾値 ±{thr:.6g}s ({k}*sd)")
    for key in ("python", "platform", "machine", "cpu_count"):
        if base["environment"].get(key) != cur["environment"].get(key):
            notes.append(f"条件不一致: {key}: {base['environment'].get(key)!r} -> {cur['environment'].get(key)!r}")
    if base["command"] != cur["command"]:
        notes.append("条件不一致: command が違う")
    if base["environment"]["git"]["head"] and base["environment"]["git"]["head"] == cur["environment"]["git"]["head"] \
            and not cur["environment"]["git"]["dirty"]:
        notes.append("注意: HEAD が同じで作業ツリーも綺麗。変更前後の比較になっていない")
    if any(n.startswith("条件不一致") for n in notes):
        verdict = "INVALID"  # 条件が違う測定どうしは比べない（時間の差がたまたま閾値内でも SAME と言わない）
    return {"verdict": verdict, "notes": notes}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = []
    if "--" in argv:
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    for name in ("record", "compare"):
        p = sub.add_parser(name)
        p.add_argument("-n", type=int, default=5)
        p.add_argument("--warmup", type=int, default=1)
        p.add_argument("--cwd", default=".")
        if name == "record":
            p.add_argument("--out")
        else:
            p.add_argument("base")
            p.add_argument("-k", type=float, default=2.0)
    a = ap.parse_args(argv)
    if not cmd:
        ap.error("`--` の後に測るコマンドを書く")
    times = measure(cmd, a.n, a.warmup, a.cwd)
    rec = {"command": cmd, "warmup": a.warmup, "environment": environment(a.cwd),
           "times": times, "stats": stats(times)}
    if a.mode == "record":
        text = json.dumps(rec, ensure_ascii=False, indent=2, sort_keys=True)
        if a.out:
            try:
                with open(a.out, "x", encoding="utf-8", newline="\n") as f:
                    f.write(text + "\n")
            except FileExistsError:
                print(f"既存ファイルは上書きしない: {a.out}", file=sys.stderr)
                return 2
            print(f"ゼロ点を記録: {a.out} (n={a.n}, mean={rec['stats']['mean']:.6g}s)")
        else:
            print(text)
        return 0
    with open(a.base, encoding="utf-8") as f:
        base = json.load(f)
    res = compare(base, rec, a.k)
    print(f"判定: {res['verdict']}")
    for n in res["notes"]:
        print(" - " + n)
    return 0 if res["verdict"] in ("SAME", "FASTER") else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""同じ条件のままコマンドを N 回測り直し、「再現する／再現しない／不安定」を判定して、条件の指紋と一緒に出す。

使い方:
  python remeasure.py --runs 3 --cwd . -- python -m pytest tests/test_x.py -q
  python remeasure.py --red-pattern "Traceback" --out r.json -- ./run.sh
赤の定義: 終了コードが 0 以外、または --red-pattern が出力に当たる。
条件（コマンド・cwd・追加環境変数）は全回で同一。再現しなくても結果は出す（起票を止める根拠にしない）。
終了コード: 0=測れた（判定は出力を見る） / 2=入力不備。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def sig(text):
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]


def measure_once(cmd, cwd, env, timeout, red_re):
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        code, out, err, to = r.returncode, r.stdout, r.stderr, False
    except subprocess.TimeoutExpired as e:
        code, out, err, to = None, (e.stdout or ""), (e.stderr or ""), True
        out = out if isinstance(out, str) else out.decode("utf-8", "replace")
        err = err if isinstance(err, str) else err.decode("utf-8", "replace")
    except OSError as e:
        return {"red": True, "exit": None, "timeout": False, "error": str(e), "stdout_sig": "", "stderr_sig": ""}
    red = to or code != 0 or bool(red_re and red_re.search(out + "\n" + err))
    return {"red": red, "exit": code, "timeout": to, "stdout_sig": sig(out), "stderr_sig": sig(err),
            "stderr_tail": err.strip().splitlines()[-1][:200] if err.strip() else ""}


def verdict(runs):
    reds = [r for r in runs if r["red"]]
    if not reds:
        return "再現しない"
    if len(reds) < len(runs):
        return "不安定"
    # 全部赤: 症状が同じか
    if len({(r["exit"], r["stderr_sig"]) for r in reds}) > 1:
        return "再現する(症状が揺れる)"
    return "再現する"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = []
    if "--" in argv:
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--cwd", default=".")
    ap.add_argument("--env", action="append", default=[], metavar="K=V", help="追加環境変数（全回同一）")
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--red-pattern", default=None)
    ap.add_argument("--out", default=None, help="JSON を書く先（既存なら書かない）")
    a = ap.parse_args(argv)
    if not cmd or a.runs < 1:
        print("`-- コマンド...` と --runs>=1 が要る", file=sys.stderr)
        return 2
    env = dict(os.environ)
    extra = {}
    for kv in a.env:
        k, _, v = kv.partition("=")
        extra[k] = v
    env.update(extra)
    red_re = re.compile(a.red_pattern) if a.red_pattern else None
    runs = [measure_once(cmd, a.cwd, env, a.timeout, red_re) for _ in range(a.runs)]
    res = {"conditions": {"cmd": cmd, "cwd": str(Path(a.cwd).resolve()), "env_added": extra,
                          "red_pattern": a.red_pattern, "timeout": a.timeout, "runs": a.runs},
           "runs": runs, "red_count": sum(r["red"] for r in runs), "verdict": verdict(runs),
           "note": "再現しなくても起票する。測り直す条件を変えない。"}
    text = json.dumps(res, ensure_ascii=False, indent=2)
    if a.out:
        if Path(a.out).exists():
            print(f"出力先が既に在る（上書きしない）: {a.out}", file=sys.stderr)
            return 2
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

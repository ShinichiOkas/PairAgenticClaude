#!/usr/bin/env python3
"""計器（コマンド）に既知入力を当て、既知値との一致・反復での決定性・較正点の数を検査して較正記録を出す。

較正ケース JSON: {"cases":[{"input":"...","expected":"...","tol":0.0}, ...]}
  tol を省くと文字列一致、数値なら絶対誤差 tol 以内。ケースは 2 点以上要る。
  計器コマンドに {input} があれば置換、無ければ標準入力へ渡す。標準出力の前後空白は除く。
使い方: calibrate.py cases.json [--repeat 3] [--out cal.json] -- python my_instrument.py
--out を付けたときだけ書く（既存は上書きしない）。終了コード: 不合格や 2 点未満なら 1。
"""
import argparse
import datetime
import json
import platform
import subprocess
import sys


def run_once(cmd, inp):
    if any("{input}" in c for c in cmd):
        full, stdin = [c.replace("{input}", inp) for c in cmd], None
    else:
        full, stdin = cmd, inp
    r = subprocess.run(full, input=stdin, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout.strip()


def matches(got, expected, tol):
    if tol is None:
        return got == str(expected)
    try:
        return abs(float(got) - float(expected)) <= float(tol)
    except ValueError:
        return False


def calibrate(cmd, cases, repeat):
    results = []
    for c in cases:
        outs = [run_once(cmd, str(c["input"])) for _ in range(repeat)]
        codes = {o[0] for o in outs}
        vals = [o[1] for o in outs]
        deterministic = len(set(vals)) == 1
        ok = codes == {0} and matches(vals[0], c["expected"], c.get("tol"))
        results.append({"input": c["input"], "expected": c["expected"], "tol": c.get("tol"),
                        "got": vals[0], "deterministic": deterministic, "exit_ok": codes == {0}, "pass": ok and deterministic})
    problems = []
    if len(cases) < 2:
        problems.append("較正点が 2 点未満")
    problems += [f"不合格: input={r['input']!r} expected={r['expected']!r} got={r['got']!r}"
                 + ("" if r["deterministic"] else "（反復で値が揺れた）") for r in results if not r["pass"]]
    return results, problems


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = []
    if "--" in argv:
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("cases")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if not cmd:
        ap.error("`--` の後に計器コマンドを書く")
    with open(a.cases, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    results, problems = calibrate(cmd, cases, a.repeat)
    rec = {"calibrated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "instrument": cmd, "repeat": a.repeat, "python": platform.python_version(),
           "platform": platform.platform(), "results": results, "problems": problems, "calibrated": not problems}
    for r in results:
        print(("OK  " if r["pass"] else "NG  ") + f"input={r['input']!r} expected={r['expected']!r} got={r['got']!r}")
    for p in problems:
        print("[問題] " + p)
    print("較正済み" if not problems else "未較正（この計器の値は測定値ではなく意見）")
    if a.out:
        try:
            with open(a.out, "x", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(rec, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        except FileExistsError:
            print(f"既存ファイルは上書きしない: {a.out}", file=sys.stderr)
            return 2
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())

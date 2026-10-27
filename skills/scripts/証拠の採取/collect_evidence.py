#!/usr/bin/env python3
"""不具合の証拠（入力・ログ・環境・時刻）を加工せずに採取ディレクトリへ固め、ハッシュ付きの manifest を作る。

使い方:
  python collect_evidence.py --input in.json --log app.log --env PATH --out ev1            # 下見（何も書かない）
  python collect_evidence.py --input in.json --log app.log --out ev1 --apply --event-time 2026-10-27T09:00:00Z
採るのは 4 点: 入力そのもの / ログ / 環境(版・設定) / 時刻。生ファイルはバイト単位でそのまま複写する。
既存の出力先には書かない。再現を試みる前に実行すること。
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_head(cwd):
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def plan(inputs, logs, env_names, now, event_time, cwd):
    files = []
    for kind, paths in (("input", inputs), ("log", logs)):
        for n, p in enumerate(paths, 1):
            p = Path(p)
            if not p.is_file():
                raise FileNotFoundError(str(p))
            st = p.stat()
            files.append({"kind": kind, "source": str(p), "stored": f"raw/{kind}/{n:02d}_{p.name}",
                          "sha256": sha256(p), "size": st.st_size, "mtime": iso(st.st_mtime)})
    env = {"python": platform.python_version(), "platform": platform.platform(), "cwd": str(cwd),
           "git_head": git_head(cwd), "vars": {k: os.environ.get(k) for k in sorted(env_names)}}
    return {"captured_at": now, "event_time": event_time, "files": files, "environment": env}


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--input", action="append", default=[], help="入力そのもの（複数可）")
    ap.add_argument("--log", action="append", default=[], help="ログ（複数可）")
    ap.add_argument("--env", action="append", default=[], help="記録する環境変数名")
    ap.add_argument("--out", required=True, help="採取ディレクトリ（存在してはならない）")
    ap.add_argument("--event-time", default=None, help="事象の時刻（採取の時刻とは別）。不明なら省略")
    ap.add_argument("--now", default=None, help="採取時刻を固定（テスト用）。省略時は現在 UTC")
    ap.add_argument("--excerpt", type=int, default=0, help="ログ末尾 N 行を excerpt/ に別ファイルで作る")
    ap.add_argument("--apply", action="store_true", help="実際に書く（既定は下見）")
    a = ap.parse_args(argv)
    if not a.input and not a.log:
        print("--input か --log が要る", file=sys.stderr)
        return 2
    now = a.now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        m = plan(a.input, a.log, a.env, now, a.event_time, Path.cwd())
    except FileNotFoundError as e:
        print(f"ファイルが無い: {e}", file=sys.stderr)
        return 2
    out = Path(a.out)
    if out.exists():
        print(f"出力先が既に在る（上書きしない）: {out}", file=sys.stderr)
        return 2
    if not a.apply:
        print(json.dumps({"dry_run": True, **m}, ensure_ascii=False, indent=2))
        return 0
    out.mkdir(parents=True)
    for f in m["files"]:
        dst = out / f["stored"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f["source"], dst)
        if sha256(dst) != f["sha256"]:
            print(f"複写後のハッシュ不一致: {f['source']}", file=sys.stderr)
            return 1
        if a.excerpt and f["kind"] == "log":
            lines = Path(f["source"]).read_text(encoding="utf-8", errors="replace").splitlines()
            ex = out / "excerpt" / (Path(f["stored"]).name + ".tail.txt")
            ex.parent.mkdir(exist_ok=True)
            ex.write_text("\n".join(lines[-a.excerpt:]) + "\n", encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"採取した: {len(m['files'])} ファイル -> {out}（採取時刻 {now}）")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main())

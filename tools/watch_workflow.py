#!/usr/bin/env python
"""走っているワークフローが**いま何をしているか**を見る。

    python tools/watch_workflow.py --follow    # 動きを追記で流す（Ctrl+C で抜ける）
    python tools/watch_workflow.py             # いまの状態を 1 枚の表で
    python tools/watch_workflow.py --run=wf_8b11e5c1 --root=experiments/pair-agent-fit

2 つの見方がある:

  `--follow`  **イベント**を流す。担い手が道具を叩くたびに 1 行出る。
              画面を塗り替えない —— 塗り替えると「何をしたか」が消えるため
  （既定）    **状態**を 1 枚で見る。完了した担い手・走っている担い手・生えたファイル

⚠ これは進行の可視化であって、判定ではない。合否を出すのは受入検査実施者である（P-12）。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

NL = chr(10)
BASE = Path.home() / ".claude" / "projects"
POLL = 2.0


def latest_run(run: str | None) -> Path | None:
    dirs = [d for p in BASE.glob("*/*/subagents/workflows") if p.is_dir()
            for d in p.iterdir() if d.is_dir()]
    if run:
        dirs = [d for d in dirs if run in d.name]
    return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None


def parse(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def agent_type(jsonl: Path) -> str:
    meta = jsonl.parent / (jsonl.stem + ".meta.json")
    if meta.exists():
        try:
            return str(json.loads(meta.read_text(encoding="utf-8")).get("agentType", "?"))
        except Exception:
            pass
    return jsonl.stem[:14]


def short(name: str) -> str:
    """`inquiry-small-normalize-request` → `normalize-request`（モデル名は全行に付くので落とす）"""
    parts = name.split("-")
    return "-".join(parts[2:]) if len(parts) > 2 else name


def moves(obj: dict) -> list[str]:
    """1 行から、担い手の動きを取り出す。無ければ空"""
    msg = obj.get("message")
    if not isinstance(msg, dict) or msg.get("role") != "assistant":
        return []
    out = []
    for c in msg.get("content") or []:
        if not isinstance(c, dict):
            continue
        if c.get("type") == "tool_use":
            inp = c.get("input") or {}
            detail = (inp.get("description") or inp.get("file_path")
                      or inp.get("pattern") or inp.get("command")
                      or inp.get("prompt") or "")
            out.append(str(c.get("name", "?")).ljust(6) + " "
                       + str(detail)[:78].replace(NL, " "))
        elif c.get("type") == "text" and str(c.get("text", "")).strip():
            out.append("思考   " + str(c["text"]).strip()[:78].replace(NL, " "))
    return out


def follow(d: Path, root: Path) -> int:
    """動きを追記で流す。**画面を塗り替えない**"""
    offs: dict[Path, int] = {}
    # 起点として**すでに在るファイル**は「生えた」ではない。先に控えておく
    seen_files: set[str] = ({x.relative_to(root).as_posix()
                             for x in root.rglob("*") if x.is_file()}
                            if root.exists() else set())
    seen_done: set[str] = set()
    started = time.time()
    quiet = 0.0
    print("# " + d.name + "  —— 動きを流す（Ctrl+C で抜ける）")
    print("")
    while True:
        moved = False

        # 担い手の動き
        for q in sorted(d.glob("agent-*.jsonl")):
            if q.name.endswith(".meta.json"):
                continue
            size = q.stat().st_size
            off = offs.get(q, 0)
            if size <= off:
                continue
            with open(q, "r", encoding="utf-8", errors="replace") as f:
                f.seek(off)
                chunk = f.read()
                offs[q] = f.tell()
            # 末尾が行の途中なら、その分は次回に回す
            if chunk and not chunk.endswith(NL):
                cut = chunk.rfind(NL)
                if cut < 0:
                    offs[q] = off
                    continue
                offs[q] = off + len(chunk[:cut + 1].encode("utf-8"))
                chunk = chunk[:cut + 1]
            tag = short(agent_type(q))
            for o in parse(chunk.splitlines()):
                for m in moves(o):
                    print("  " + tag.ljust(24) + " │ " + m)
                    moved = True

        # 完了（journal）
        jl = d / "journal.jsonl"
        if jl.exists():
            for o in parse(jl.read_text(encoding="utf-8", errors="replace").splitlines()):
                if o.get("type") != "result":
                    continue
                key = str(o.get("agentId") or o.get("key"))
                if key in seen_done:
                    continue
                seen_done.add(key)
                r = o.get("result")
                tgt = r.get("target") if isinstance(r, dict) else o.get("label")
                posts = (r.get("postconditions") or []) if isinstance(r, dict) else []
                ng = sum(1 for p in posts if isinstance(p, dict) and not p.get("met"))
                print("  ✅ 完了: " + str(tgt) + "　事後条件 "
                      + str(len(posts) - ng) + "/" + str(len(posts))
                      + ("　⚠ 未達 " + str(ng) if ng else ""))
                moved = True

        # 生えたファイル
        if root.exists():
            for f in sorted(x for x in root.rglob("*") if x.is_file()):
                rel = f.relative_to(root).as_posix()
                if rel in seen_files:
                    continue
                seen_files.add(rel)
                print("  📄 生えた: " + rel + "　" + str(f.stat().st_size) + " B")
                moved = True

        if moved:
            quiet = 0.0
        else:
            quiet += POLL
            if quiet >= 30:
                print("  … " + str(int(time.time() - started)) + " 秒経過（動きなし）")
                quiet = 0.0
        time.sleep(POLL)


def events(d: Path, expect: int, stall: int = 600) -> int:
    """完了ごとに 1 行だけ出して、全部終わったら抜ける（Monitor 用）。

    ⚠ **沈黙は成功ではない。** 完了だけを出すと、落ちたときも止まったときも
      黙ったままになる。だから**停止の疑い**も出す（ログが動かない時間で見る）。
    """
    seen: set[str] = set()
    jl = d / "journal.jsonl"
    quiet_since = time.time()
    while True:
        if jl.exists():
            for o in parse(jl.read_text(encoding="utf-8", errors="replace").splitlines()):
                if o.get("type") != "result":
                    continue
                key = str(o.get("agentId") or o.get("key"))
                if key in seen:
                    continue
                seen.add(key)
                r = o.get("result")
                tgt = r.get("target") if isinstance(r, dict) else o.get("label")
                posts = (r.get("postconditions") or []) if isinstance(r, dict) else []
                ng = sum(1 for x in posts if isinstance(x, dict) and not x.get("met"))
                empt = (r.get("emptyDeps") or []) if isinstance(r, dict) else []
                print("[" + str(len(seen)) + "/" + str(expect) + "] 完了 " + str(tgt)
                      + "　事後条件 " + str(len(posts) - ng) + "/" + str(len(posts))
                      + ("　⚠ 未達 " + str(ng) if ng else "")
                      + ("　空だった dep " + str(len(empt)) if empt else ""))
                quiet_since = time.time()
        if len(seen) >= expect:
            print("全 " + str(expect) + " 体が完了した")
            return 0
        logs = [q for q in d.glob("*.jsonl")]
        newest = max((q.stat().st_mtime for q in logs), default=0)
        idle = time.time() - max(newest, quiet_since)
        if idle > stall:
            print("⚠ 停止の疑い: ログが " + str(int(idle)) + " 秒更新されていない（完了 "
                  + str(len(seen)) + "/" + str(expect) + "）")
            quiet_since = time.time()
        time.sleep(15)


def snapshot(d: Path, root: Path) -> None:
    print("# run " + d.name)
    print("")
    done: list[str] = []
    finished: set[str] = set()
    jl = d / "journal.jsonl"
    if jl.exists():
        for o in parse(jl.read_text(encoding="utf-8", errors="replace").splitlines()):
            if o.get("type") != "result":
                continue
            finished.add(str(o.get("agentId") or ""))
            r = o.get("result")
            if not isinstance(r, dict):
                done.append("  ✅ " + str(o.get("label") or "?"))
                continue
            posts = r.get("postconditions") or []
            ng = sum(1 for p in posts if isinstance(p, dict) and not p.get("met"))
            line = "  " + ("⚠" if ng else "✅") + " " + str(r.get("target") or "?").ljust(16)
            line += " 事後条件 " + str(len(posts) - ng) + "/" + str(len(posts))
            if r.get("path"):
                line += "  → " + str(r["path"])
            done.append(line)
    print("## 完了 " + str(len(done)) + " 体")
    print("")
    for line in done or ["  （まだ無し）"]:
        print(line)
    print("")

    print("## いま動いているもの")
    print("")
    shown = 0
    for q in sorted(d.glob("agent-*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        if q.name.endswith(".meta.json"):
            continue
        if q.stem.replace("agent-", "") in finished:
            continue
        last = "（起動直後）"
        for o in reversed(parse(q.read_text(encoding="utf-8", errors="replace").splitlines())):
            mv = moves(o)
            if mv:
                last = mv[-1]
                break
        print("  ▸ " + agent_type(q).ljust(38) + str(round(q.stat().st_size / 1024)).rjust(4)
              + " KB  " + last)
        shown += 1
    if not shown:
        print("  （動いているものは無し）")
    print("")

    print("## 作業根に生えたもの")
    print("")
    if root.exists():
        for f in sorted(x for x in root.rglob("*") if x.is_file()):
            print("  " + f.relative_to(root).as_posix().ljust(34)
                  + str(f.stat().st_size).rjust(8) + " B")
    else:
        print("  （作業根が無い）")
    print("")



def main() -> int:
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    run = next((f.split("=", 1)[1] for f in flags if f.startswith("--run=")), None)
    root = Path(next((f.split("=", 1)[1] for f in flags if f.startswith("--root=")),
                     "experiments/pair-agent-fit"))
    d = latest_run(run)
    if d is None:
        print("走っている run が見つからない")
        return 1
    if "--events" in flags:
        expect = int(next((f.split("=", 1)[1] for f in flags
                           if f.startswith("--expect=")), "9"))
        # ⚠ 既定を 240 秒にしたら**誤報が出た**（実測 2026-09-06）。
        #   長文の生成中は道具を叩かないので、ログが 4 分以上動かないことがある。
        #   仕様 60 KB を判定手続きに落とす段で誤検出した。600 秒に緩めた
        stall = int(next((f.split("=", 1)[1] for f in flags
                          if f.startswith("--stall=")), "600"))
        return events(d, expect, stall)
    if "--follow" in flags:
        try:
            return follow(d, root)
        except KeyboardInterrupt:
            print("")
            print("（抜けた。ワークフロー自体は走り続けている）")
            return 0
    snapshot(d, root)
    return 0


if __name__ == "__main__":
    sys.exit(main())

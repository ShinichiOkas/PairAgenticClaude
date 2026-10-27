#!/usr/bin/env python
"""設計の因果 DB の ID を種類ごとに数え、振った ID が欠けていないか（欠番は状態として残っているか）・種類と接頭辞が合っているかを検める。

    python id_ledger.py [--db PATH] [--backend json|sqlite] [--json]

設計の因果 DB（tools/design_graph.py）を読むだけで、書かない。一度振った ID は変えず、解決・却下・廃止しても残し、再利用しない。
その約束を、DB に残っている ID と採番の最大値から検める:
  [欠け]       採番した番号なのに、その要素・リンクが DB に無い（イベント列が書き換わった疑い）
  [接頭辞違い] 要素の種類に合わない ID（RQ… が component など）
  [案の親違い] 案 ID（D3-A）の決定点部分と、親（parent）が一致しない
却下・廃止になった ID は「欠番として残っている」ものとして数える（問題にしない）。
design_graph.py は 環境変数 PAIR_AGENT_DESIGN_GRAPH → 上位の tools/ → ~/.claude/pair-agent/tools/ の順で探す。
終了コード: 0 = 異常なし ／ 1 = 異常あり ／ 2 = 入力不正・中核や DB が見つからない
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

sys.dont_write_bytecode = True
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

ENV_CORE = "PAIR_AGENT_DESIGN_GRAPH"
ALIVE = ("hypothesis", "confirmed")
CORE: Any = None


class CoreError(Exception):
    """中核が見つからない・DB が無い・入力が誤り（終了コード 2）。"""


def find_core() -> Path:
    """design_graph.py を探す。環境変数 → 上位の tools/ → install 先の順。見つからなければ探した場所を添えて止まる。"""
    tried: list[str] = []
    env = os.environ.get(ENV_CORE)
    if env:
        tried.append(f"環境変数 {ENV_CORE}={env}")
        if Path(env).is_file():
            return Path(env)
    here = Path(__file__).resolve().parent
    tried.append(f"{here} から上へ辿った tools/design_graph.py")
    for d in (here, *here.parents):
        if (d / "tools" / "design_graph.py").is_file():
            return d / "tools" / "design_graph.py"
    for rel in (".claude/pair-agent/tools/design_graph.py", ".gemini/config/pair-agent/tools/design_graph.py"):
        p = Path.home() / rel
        tried.append(str(p))
        if p.is_file():
            return p
    raise CoreError("design_graph.py が見つからない。探した場所:\n  " + "\n  ".join(tried))


def open_graph(db: str | None, backend: str | None) -> Any:
    """中核を読み込み、DB を読み取り専用の使い方で開く（この入口は書き込みの API を呼ばない）。"""
    global CORE
    path = find_core()
    spec = importlib.util.spec_from_file_location("_design_graph_core", path)
    if spec is None or spec.loader is None:
        raise CoreError(f"design_graph.py を読み込めない: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    CORE = mod
    try:
        _, dbpath = mod.resolve_backend(db, backend)
        if not Path(dbpath).exists():
            raise CoreError(f"DB が無い: {dbpath}（--db で指す。既定は .pair-agent/design/graph.jsonl）")
        return mod.DesignGraph(db, backend, "ai")
    except mod.DesignGraphError as e:
        raise CoreError(str(e)) from e


def natkey(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def entity(g: Any, ident: str) -> dict:
    return g.nodes.get(ident) or g.links.get(ident) or {}


def alive_nodes(g: Any, *kinds: str) -> list[dict]:
    return sorted((n for n in g.nodes.values() if n["kind"] in kinds and n["state"] in ALIVE),
                  key=lambda n: natkey(n["id"]))


def alive_links(g: Any, *kinds: str) -> list[dict]:
    return sorted((l for l in g.links.values() if l["kind"] in kinds and l["state"] in ALIVE),
                  key=lambda l: natkey(l["id"]))


def check_ids(g: Any, ids: list[str] | None) -> set[str]:
    out = set(ids or [])
    for i in sorted(out, key=natkey):
        if i not in g.nodes and i not in g.links:
            raise CoreError(f"その ID は DB に無い: {i}")
    return out


def findings(g: Any, rules: tuple[str, ...], ids: set[str] | None = None) -> list[dict]:
    """中核の check のうち、指定した規則の検出だけ（見送り済みは出ない）。"""
    return [f for f in g.check() if f["rule"] in rules and (not ids or f["target"] in ids)]


def fline(f: dict) -> str:
    return f"[{f['id']}] {f['message']}"


def tree_lines(g: Any, rows: list[dict]) -> list[str]:
    """why の行を木で出す（各段の状態・指している根拠・要再確認）。"""
    out = []
    for r in rows:
        lid = f" {r['link']}" if r["link"] and r["via"] != "ends" else ""
        head = "" if r["depth"] == 0 else f"← {r['via']}{lid} ← "
        ev = ""
        if not r["kind"].startswith("link:"):
            ev = f"  根拠: {', '.join(r['evidence'])}" if r["evidence"] else "  根拠: なし"
        out.append(f"{'  ' * r['depth']}{head}{g.label(r['id'])}{ev}{'  ⚠要再確認' if r['stale'] else ''}")
    return out


def run(argv: list[str] | None, description: str, add_args: Callable[[argparse.ArgumentParser], None],
        analyze: Callable[[Any, argparse.Namespace], tuple[Any, list[str], bool]]) -> int:
    p = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", help="DB の置き場（既定 .pair-agent/design/graph.jsonl）")
    p.add_argument("--backend", choices=["json", "sqlite"], help="省くと --db の拡張子で決める")
    p.add_argument("--json", action="store_true", help="機械向けの JSON で出す")
    add_args(p)
    args = p.parse_args(argv)
    try:
        g = open_graph(args.db, args.backend)
    except CoreError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    try:
        data, lines, bad = analyze(g, args)
    except (CoreError, CORE.DesignGraphError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print("\n".join(lines))
    return 1 if bad else 0


def add_id_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--id", action="append", metavar="ID", help="この ID だけを対象にする（繰り返せる）")

TAIL = re.compile(r"^([A-Z]+)(\d+)$")
OPT = re.compile(r"^(.+)-([A-Z]+)$")


def letters_value(s: str) -> int:
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - 64)
    return n


def analyze(g: Any, args: argparse.Namespace) -> tuple[Any, list[str], bool]:
    nums: dict[str, set[int]] = {}
    opts: dict[str, set[int]] = {}
    problems: list[dict] = []
    kept = {"rejected": [], "retired": []}
    for n in sorted(g.nodes.values(), key=lambda n: natkey(n["id"])):
        ident, kind = n["id"], n["kind"]
        if n["state"] in kept:
            kept[n["state"]].append(ident)
        if kind == "option":
            m = OPT.match(ident)
            if not m or m.group(1) != n.get("parent"):
                problems.append({"id": ident, "problem": "案の親違い", "detail": f"親 {n.get('parent')}"})
            else:
                opts.setdefault(m.group(1), set()).add(letters_value(m.group(2)))
            continue
        m = TAIL.match(ident)
        if not m or m.group(1) != CORE.KINDS[kind][0]:
            problems.append({"id": ident, "problem": "接頭辞違い", "detail": f"{kind} の接頭辞は {CORE.KINDS[kind][0]}"})
        else:
            nums.setdefault(m.group(1), set()).add(int(m.group(2)))
    for lid in g.links:
        m = TAIL.match(lid)
        if m:
            nums.setdefault(m.group(1), set()).add(int(m.group(2)))
    for l in g.links.values():
        if l["state"] in kept:
            kept[l["state"]].append(l["id"])
    series = []
    for prefix in sorted(set(nums) | set(g.counters), key=natkey):
        have = nums.get(prefix, set())
        top = max(have | {g.counters.get(prefix, 0)})
        missing = [n for n in range(1, top + 1) if n not in have]
        series.append({"prefix": prefix, "count": len(have), "max": top, "missing": [f"{prefix}{n}" for n in missing]})
        for n in missing:
            problems.append({"id": f"{prefix}{n}", "problem": "欠け", "detail": f"{prefix} の採番は {top} まで進んでいる"})
    for dp in sorted(set(opts) | set(g.option_counters), key=natkey):
        have = opts.get(dp, set())
        top = max(have | {g.option_counters.get(dp, 0)})
        for n in range(1, top + 1):
            if n not in have:
                problems.append({"id": f"{dp}-#{n}", "problem": "欠け", "detail": f"{dp} の案は {top} 番目まで採番済み"})
    problems.sort(key=lambda p: (p["problem"], natkey(p["id"])))
    data = {"series": series, "kept": {k: sorted(v, key=natkey) for k, v in kept.items()}, "problems": problems}
    lines = ["採番の状況（接頭辞 件数 最大）:"]
    lines += [f"  {s['prefix']}: {s['count']} 件・最大 {s['max']}" for s in series]
    lines.append(f"欠番として残っている ID: 却下 {len(kept['rejected'])} ・廃止 {len(kept['retired'])}")
    lines += [f"  [{p['problem']}] {p['id']}（{p['detail']}）" for p in problems] or ["異常なし"]
    return data, lines, bool(problems)


def main(argv: list[str] | None = None) -> int:
    return run(argv, __doc__ or "", lambda p: None, analyze)


if __name__ == "__main__":
    sys.exit(main())

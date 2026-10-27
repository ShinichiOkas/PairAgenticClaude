#!/usr/bin/env python
"""設計の記録から生成した Markdown が、いまの記録を書き出し直した結果と一致するかを調べる（手で補った差分を見つける）。

    python regen_check.py [--db PATH] [--backend json|sqlite] [--json] [--md FILE]

読む規則: undecided（未決。情報）。
--md FILE を渡すと、g.export_markdown() の結果と FILE を比べる。違えば problems に差分（先頭 40 行）を出して終了コード 1。
違いは手で直さず、生成の元（DB）を直して再生成する（design_graph.py export --out FILE）。--md を省くと、書き出し直す手順を出すだけ。
読むだけ（DB に書かない）。--db --backend --json は中核 design_graph.py と同じ名前。
design_graph.py の探し方: 環境変数 PAIR_AGENT_DESIGN_GRAPH → このスクリプトから上へ辿った tools/design_graph.py
  → ~/.claude/pair-agent/tools/ → ~/.gemini/config/pair-agent/tools/。見つからなければ探した場所を出して終了コード 2。
終了コード: 0 = 指摘なし ／ 1 = 指摘あり ／ 2 = 入力不正・DB が無い・中核が見つからない
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ENV_CORE = "PAIR_AGENT_DESIGN_GRAPH"
ALIVE = ("hypothesis", "confirmed")


class CoreNotFound(Exception):
    """design_graph.py がどこにも無い。tried に探した場所を持つ。"""

    def __init__(self, tried: list[Path]) -> None:
        super().__init__("design_graph.py が見つからない")
        self.tried = tried


def core_candidates() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get(ENV_CORE)
    if env:
        out.append(Path(env))
    here = Path(__file__).resolve().parent
    for d in (here, *here.parents):
        out.append(d / "tools" / "design_graph.py")
    home = Path.home()
    out.append(home / ".claude" / "pair-agent" / "tools" / "design_graph.py")
    out.append(home / ".gemini" / "config" / "pair-agent" / "tools" / "design_graph.py")
    return out


def load_core() -> Any:
    tried = core_candidates()
    for p in tried:
        if p.is_file():
            spec = importlib.util.spec_from_file_location("design_graph", p)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules["design_graph"] = mod
            spec.loader.exec_module(mod)
            return mod
    raise CoreNotFound(tried)


def is_core_error(e: BaseException) -> bool:
    return any(c.__name__ == "DesignGraphError" for c in type(e).__mro__)


def empty(v: Any) -> bool:
    return v is None or (isinstance(v, (str, list, dict, tuple)) and len(v) == 0) or (isinstance(v, str) and not v.strip())


def txt(v: Any) -> str:
    if empty(v):
        return "なし"
    if isinstance(v, str):
        return v
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return "／".join(v)
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def pick(g: Any, rules: tuple[str, ...]) -> list[dict[str, Any]]:
    """この Skill の観点の検出だけ（見送り済みは除く）。"""
    return [{"id": f["id"], "rule": f["rule"], "target": f["target"], "level": f["level"], "message": f["message"]}
            for f in g.check() if f["rule"] in rules]


def finding_lines(findings: list[dict[str, Any]]) -> list[str]:
    out = ["## 検出（design_graph.py check の該当規則）"]
    out += [f"- [{f['id']}] {f['message']}" + ("（情報）" if f["level"] == "info" else "") for f in findings]
    if not findings:
        out.append("- なし")
    return out



DESC = '生成した Markdown を再生成の結果と比べ、手で補った差分を見つける。'
RULES: tuple[str, ...] = ('undecided',)


import difflib


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--md", metavar="FILE", help="比べる生成物（design_graph.py export の出力）")


def collect(core: Any, g: Any, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    fresh = g.export_markdown()
    data: dict[str, Any] = {"md": args.md, "findings": pick(g, RULES), "problems": [], "diff": []}
    lines = ["## 生成物の照合"]
    if args.md is None:
        lines.append("--md FILE を渡すと、いまの記録を書き出し直した結果と比べる。")
        lines.append("書き出し直す: python design_graph.py export --out FILE（生成物は手で直さない。違っていたら元を直して再生成する）")
        data["same"] = None
    else:
        p = Path(args.md)
        if not p.is_file():
            raise core.DesignGraphError(f"ファイルが無い: {p}")
        have = p.read_text(encoding="utf-8").replace("\r\n", "\n")
        want = fresh.replace("\r\n", "\n")
        same = have.rstrip("\n") == want.rstrip("\n")
        data["same"] = same
        if same:
            lines.append(f"一致: {p} は記録の書き出し直しと同じ")
        else:
            diff = list(difflib.unified_diff(have.splitlines(), want.splitlines(), str(p), "再生成", n=0, lineterm=""))
            data["diff"] = diff[:40]
            data["problems"].append({"id": "stale_generated", "message": f"{p} は記録の書き出し直しと違う。手で補わず、生成の元を直して再生成する"})
            lines.append(f"不一致: {p} は記録の書き出し直しと違う（手で補った・古くなった）")
            lines += ["  " + x for x in diff[:40]]
            if len(diff) > 40:
                lines.append(f"  …（差分 {len(diff)} 行のうち先頭 40 行）")
    return data, lines + [""] + finding_lines(data["findings"])


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=DESC)
    ap.add_argument("--db", default=None, help="DB の置き場（既定は中核の既定 .pair-agent/design/graph.jsonl）")
    ap.add_argument("--backend", choices=["json", "sqlite"], default=None, help="省くと --db の拡張子で決める")
    ap.add_argument("--json", action="store_true", help="機械向けの JSON で出す")
    add_args(ap)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        core = load_core()
        _, path = core.resolve_backend(args.db, args.backend)
        if not Path(path).exists():
            raise core.DesignGraphError(f"DB が無い: {path}")
        g = core.DesignGraph(args.db, args.backend, "ai")
        data, lines = collect(core, g, args)
    except CoreNotFound as e:
        print("エラー: design_graph.py が見つからない。探した場所:", file=sys.stderr)
        for p in e.tried:
            print(f"  {p}", file=sys.stderr)
        return 2
    except Exception as e:
        if is_core_error(e):
            print(f"エラー: {e}", file=sys.stderr)
            return 2
        raise
    if args.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print("\n".join(lines))
    bad = any(f["level"] != "info" for f in data["findings"]) or bool(data.get("problems"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

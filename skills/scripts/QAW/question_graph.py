#!/usr/bin/env python
"""曖昧な語を潰す問いの依存グラフを検査し、聞く順序を出し、回答から確定数と A の帯域（答えた数 ÷ 確定した数）を数える。

    python question_graph.py 問い.txt [--answers 回答.json]

問いの書式（1 行 1 問・縦棒区切り）:  ID | 疑問文？ | 回答=ID,ID ; 回答=ID
    例:  Q1 | 「ログ」とはアプリログのことですか？ | yes=Q2,Q3 ; no=Q4
  `回答=` の右は「その回答で確定する／消える問い」。`*=` はどの回答でも、`auto=` はその問いが自動確定したときに働く。
  拡張子 .json なら [{"id","text","resolves":{回答:[ID...]}}] も受ける。
絞らない（問いを捨てない）。順序と依存だけを付ける。読むだけ。同じ入力なら同じ出力。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def natkey(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def parse(text: str, as_json: bool = False) -> tuple[list[dict], list[str]]:
    errs: list[str] = []
    qs: list[dict] = []
    if as_json:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return [], [f"[JSON が壊れている] {e}"]
        for d in data:
            qs.append({"id": str(d.get("id", "")), "text": str(d.get("text", "")),
                       "resolves": {str(k): [str(x) for x in v] for k, v in (d.get("resolves") or {}).items()}})
        return qs, errs
    for no, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2 or not parts[0]:
            errs.append(f"[書式] {no} 行目: `ID | 疑問文 | 回答=ID,ID` の形ではない")
            continue
        res: dict[str, list[str]] = {}
        if len(parts) >= 3 and parts[2]:
            for seg in re.split(r"[;；]", parts[2]):
                seg = seg.strip()
                if not seg:
                    continue
                if "=" not in seg:
                    errs.append(f"[書式] {no} 行目: `{seg}` に `=` が無い")
                    continue
                k, v = seg.split("=", 1)
                res[k.strip()] = [x.strip() for x in re.split(r"[,、]", v) if x.strip()]
        qs.append({"id": parts[0], "text": parts[1], "resolves": res})
    return qs, errs


def edges(qs: list[dict]) -> dict[str, set[str]]:
    return {q["id"]: {t for ts in q["resolves"].values() for t in ts} for q in qs}


def lint(qs: list[dict]) -> list[str]:
    out: list[str] = []
    ids = [q["id"] for q in qs]
    for i in sorted(set(x for x in ids if ids.count(x) > 1), key=natkey):
        out.append(f"[ID 重複] {i}")
    idset = set(ids)
    for q in qs:
        if not re.search(r"[?？]\s*$|か[。]?\s*$", q["text"]):
            out.append(f"[疑問形でない] {q['id']}: 平叙文は「読んでおいてください」で済んでしまう → {q['text']}")
        for k, ts in q["resolves"].items():
            for t in ts:
                if t not in idset:
                    out.append(f"[未知の ID] {q['id']} の `{k}=` が存在しない {t} を指す")
                if t == q["id"]:
                    out.append(f"[自己参照] {q['id']}")
    # 循環（深さ優先）
    g = edges(qs)
    state: dict[str, int] = {}
    cyc: set[str] = set()

    def dfs(n: str, stack: list[str]):
        state[n] = 1
        for m in sorted(g.get(n, ()), key=natkey):
            if m not in g:
                continue
            if state.get(m) == 1:
                cyc.add(" -> ".join(stack[stack.index(m):] + [n, m]) if m in stack else f"{n} -> {m}")
            elif m not in state:
                dfs(m, stack + [n])
        state[n] = 2

    for n in sorted(g, key=natkey):
        if n not in state:
            dfs(n, [])
    for c in sorted(cyc):
        out.append(f"[循環] {c}")
    return out


def reach(g: dict[str, set[str]], n: str) -> set[str]:
    seen: set[str] = set()
    todo = list(g.get(n, ()))
    while todo:
        x = todo.pop()
        if x in seen or x == n:
            continue
        seen.add(x)
        todo.extend(g.get(x, ()))
    return seen


def ask_order(qs: list[dict]) -> list[tuple[str, int]]:
    """根（他から確定されない問い）を、確定させる下位の数が多い順に。"""
    g = edges(qs)
    incoming = {t for ts in g.values() for t in ts}
    roots = [q["id"] for q in qs if q["id"] not in incoming]
    return sorted(((r, len(reach(g, r))) for r in roots), key=lambda x: (-x[1], natkey(x[0])))


def status(qs: list[dict], answers: dict[str, str]) -> dict:
    by = {q["id"]: q for q in qs}
    errs = [f"[回答先が無い] {k}" for k in sorted(answers, key=natkey) if k not in by]
    answered = {k for k in answers if k in by}
    determined: set[str] = set()
    fired: set[str] = set()
    changed = True
    while changed:
        changed = False
        for q in qs:
            i = q["id"]
            if i in fired:
                continue
            if i in answered:
                keys = [answers[i], "*"]
            elif i in determined:
                keys = ["auto", "*"]
            else:
                continue
            fired.add(i)
            changed = True
            for k in keys:
                for t in q["resolves"].get(k, ()):
                    if t in by and t not in answered:
                        determined.add(t)
    confirmed = answered | determined
    open_ = sorted((q["id"] for q in qs if q["id"] not in confirmed), key=natkey)
    g = edges(qs)
    inc: dict[str, set[str]] = {}
    for s, ts in g.items():
        for t in ts:
            inc.setdefault(t, set()).add(s)
    nxt = []
    for i in open_:
        if all(p in answered or p in determined for p in inc.get(i, ())):
            nxt.append((i, len(reach(g, i) & set(open_))))
    nxt.sort(key=lambda x: (-x[1], natkey(x[0])))
    band = (len(answered) / len(confirmed)) if confirmed else None
    return {"errors": errs, "answered": sorted(answered, key=natkey), "determined": sorted(determined, key=natkey),
            "open": open_, "next": nxt, "band": band, "total": len(qs)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("questions", type=Path)
    ap.add_argument("--answers", type=Path, help='回答の JSON（{"Q1": "yes"}）')
    a = ap.parse_args(argv)
    if not a.questions.is_file():
        print(f"エラー: ファイルが無い: {a.questions}", file=sys.stderr)
        return 2
    qs, errs = parse(a.questions.read_text(encoding="utf-8"), a.questions.suffix.lower() == ".json")
    errs += lint(qs)
    print(f"問いの総数: {len(qs)}")
    for e in errs:
        print(e)
    if errs:
        print("※ 指摘を直してから順序・帯域を見る")
        return 1
    print("聞く順序（根の問い・確定させる下位の数）:")
    for i, n in ask_order(qs):
        print(f"  {i}: 下位 {n} 問を確定／消去")
    if a.answers:
        ans = json.loads(a.answers.read_text(encoding="utf-8"))
        st = status(qs, {str(k): str(v) for k, v in ans.items()})
        for e in st["errors"]:
            print(e)
        c = len(st["answered"]) + len(st["determined"])
        print(f"答えた数: {len(st['answered'])} ／ 自動で確定・消去: {len(st['determined'])} ／ 未確定: {len(st['open'])}")
        if st["band"] is not None:
            print(f"A の帯域 ＝ 答えた数 ÷ 確定した数 ＝ {len(st['answered'])} / {c} ≒ {st['band']:.2f}")
        else:
            print("A の帯域: 未算出（確定した問いがまだ無い）")
        if st["next"]:
            print("次に聞く問い（上位が解決済みのもの）:")
            for i, n in st["next"]:
                print(f"  {i}: 未確定の下位 {n} 問に効く")
    return 0


if __name__ == "__main__":
    sys.exit(main())

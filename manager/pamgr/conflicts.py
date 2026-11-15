"""同時に効く規則どうしの矛盾（J1・docs/usecases.md §4 の 1）。

効いている集合 = 同じエージェントが同時に読む規則（全体 ~/.claude の CLAUDE.md・rules ＋ そのプロジェクトの CLAUDE.md・AGENTS.md・.claude/rules）。
別々のプロジェクトの規則どうしは同時に効かないので見ない。スキル・エージェント定義は必要なときだけ読まれるので、ここでは見ない。

- 全体の規則どうし: すべての組を LLM が判定する（矛盾は意味の上で起き、文字の類似では拾えない。実測 2026-11-15）
- プロジェクトの規則: 文（箇条・句点）単位の文字の類似で、全体・同じプロジェクトの規則から相手を絞る
- 判定は組（2 つの節の中身のハッシュ）ごとに残し、使い回す。節が変われば組が変わり、判定し直す
- 判定は仮説。矛盾・状況依存と見た組を判断待ち（J1）に上げ、決めるのは師匠
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import checks, store, survey, targets
from .similarity import similarity_matrix

VERDICTS = "verdicts.json"
J1_RELATIONS = ("conflict", "context_dependent")
PROJECT_TOP = 3
PROJECT_MIN = 0.15
ERROR_RETRY_SEC = 6 * 3600
REL_LABEL = {"conflict": "矛盾（同じ状況で両方には従えない）", "context_dependent": "状況次第で両方真"}


@dataclass
class Cand:
    key: str
    a: dict[str, Any]
    b: dict[str, Any]
    score: float
    applies: set[str] = field(default_factory=set)   # "*" は全プロジェクト
    rank: int = 1                                    # 0 = 全体どうし（先に判定する）


def pair_key(a: dict[str, Any], b: dict[str, Any]) -> str:
    return "|".join(sorted((a["hash"], b["hash"])))


def substantive(u: dict[str, Any]) -> bool:
    """見出しだけの節（本文が無い）は規則ではない。"""
    return any(ln.strip() and not ln.lstrip().startswith("#") for ln in u["text"].splitlines())


def global_units(tlist: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    out = []
    for t in (targets.list_targets() if tlist is None else tlist):
        if t["kind"] == "claude_home":
            out += [u for u in survey.survey_home(t) if u["kind"] == "rule-section" and u["scope"] == "global" and substantive(u)]
    return out


def project_units(t: dict[str, Any], global_hashes: set[str]) -> list[dict[str, Any]]:
    """プロジェクトの規則の節。全体の節の写し（同じ中身）と、見出しだけの節は除く。"""
    return [u for u in survey.survey_project(t)
            if u["kind"] == "rule-section" and u["hash"] not in global_hashes and substantive(u)]


def statements(text: str) -> list[str]:
    out, in_code = [], False
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_code = not in_code
            continue
        if in_code or not s or s.startswith("#") or s.startswith("|"):
            continue
        s = re.sub(r"^(>\s*)?([-*]|\d+\.)\s*", "", s)
        out += [p.strip() for p in re.split(r"(?<=。)", s) if len(p.strip()) >= 10]
    return out or [text[:500]]


def section_scores(units: list[dict[str, Any]]) -> np.ndarray:
    """節どうしの近さ = 文どうしの文字の類似の最大値。"""
    owner, stm = [], []
    for k, u in enumerate(units):
        for s in statements(u["text"]):
            owner.append(k)
            stm.append(s)
    n = len(units)
    out = np.zeros((n, n), dtype=np.float32)
    if len(stm) < 2:
        return out
    S = similarity_matrix(stm).tocoo()
    own = np.array(owner)
    a, b, v = own[S.row], own[S.col], S.data
    m = a != b
    np.maximum.at(out, (a[m], b[m]), v[m])
    return out


def candidates(tlist: list[dict[str, Any]] | None = None) -> tuple[list[Cand], dict[str, Any]]:
    tlist = targets.list_targets() if tlist is None else tlist
    g = global_units(tlist)
    ghash = {u["hash"] for u in g}
    cands: dict[str, Cand] = {}

    def add(a: dict[str, Any], b: dict[str, Any], score: float, applies: str, rank: int) -> None:
        if a["hash"] == b["hash"]:
            return
        k = pair_key(a, b)
        c = cands.get(k)
        if c is None:
            c = cands[k] = Cand(k, a, b, round(float(score), 3), set(), rank)
        c.applies.add(applies)
        c.rank = min(c.rank, rank)

    gs = section_scores(g)
    for i in range(len(g)):
        for j in range(i + 1, len(g)):
            add(g[i], g[j], gs[i, j], "*", 0)
    projects = [t for t in tlist if t["kind"] == "project"]
    per_project: dict[str, int] = {}
    for t in projects:
        pu = project_units(t, ghash)
        per_project[t["name"]] = len(pu)
        if not pu:
            continue
        both = pu + g
        sc = section_scores(both)
        for i in range(len(pu)):
            order = np.argsort(-sc[i])
            for j in order[:PROJECT_TOP]:
                if j != i and sc[i, j] >= PROJECT_MIN:
                    add(pu[i], both[j], sc[i, j], t["name"], 1)
    ordered = sorted(cands.values(), key=lambda c: (c.rank, -c.score))
    return ordered, {"global_sections": len(g), "projects": per_project}


def verdicts() -> dict[str, Any]:
    return store.load(VERDICTS, {})


def pending(cands: list[Cand], vd: dict[str, Any] | None = None) -> list[Cand]:
    vd = verdicts() if vd is None else vd
    now = time.time()
    out = []
    for c in cands:
        v = vd.get(c.key)
        if v is None or (v.get("relation") == "error" and now - v.get("ts", 0) > ERROR_RETRY_SEC):
            out.append(c)
    return out


def work(cands: list[Cand], budget_sec: float, model: str | None = None,
         progress: Callable[..., Any] | None = None) -> dict[str, Any]:
    """未判定の組を LLM で判定する（時間の上限まで）。LLM が使えなければ止めて、残りは保留。"""
    todo = pending(cands)
    t0, done, failed, stop = time.time(), 0, 0, ""
    vd = verdicts()
    for n, c in enumerate(todo):
        if time.time() - t0 > budget_sec:
            stop = "時間の上限"
            break
        if progress:
            progress(n, len(todo), f"矛盾の判定: {c.a['name']} × {c.b['name']}")
        try:
            v, model_name = checks.judge_pair(c.a, c.b, model)
            vd[c.key] = {**v.model_dump(), "model": model_name, "at": store.now_iso(), "ts": time.time()}
            done += 1
        except Exception as exc:          # 1 組の失敗で止めない。接続できないときだけ止める
            vd[c.key] = {"relation": "error", "error": f"{type(exc).__name__}: {exc}"[:500], "ts": time.time()}
            failed += 1
            if "connect" in str(exc).lower() or type(exc).__name__ in ("LLMNotConfigured", "ConnectError"):
                stop = "LLM に接続できない"
                break
        if done % 10 == 0:
            store.save(VERDICTS, vd)
    store.save(VERDICTS, vd)
    return {"judged": done, "failed": failed, "remaining": len(pending(cands, vd)), "stopped": stop}


def _ref(u: dict[str, Any]) -> dict[str, Any]:
    return {k: u.get(k) for k in ("target_id", "target", "scope", "path", "rel", "anchor", "hash", "name")}


def _where(u: dict[str, Any]) -> str:
    return f"{u['target']}/{u['rel']} › {u['anchor']}"


def _when(u: dict[str, Any]) -> str:
    m = re.search(r"20\d\d-\d\d-\d\d", u.get("anchor", "") + " " + u["text"][:400])
    return f"{m.group(0)} の記述" if m else ""


def is_stale_copy(c: Cand) -> bool:
    """プロジェクトにある全体の節の写し（同じ見出し）が、全体の節と食い違う。判断ではなく、写しが古い（実測 2026-11-15: llmbenchmark）。"""
    from .sections import anchor_key
    return c.a["scope"] != c.b["scope"] and anchor_key(c.a["anchor"]) == anchor_key(c.b["anchor"])


def stale_copies(cands: list[Cand]) -> list[dict[str, Any]]:
    vd = verdicts()
    out = []
    for c in cands:
        if is_stale_copy(c) and (vd.get(c.key) or {}).get("relation") in J1_RELATIONS + ("overlap", "subsumes"):
            p = c.a if c.a["scope"] == "project" else c.b
            out.append({"what": "プロジェクトに全体の規則の古い写しがある", "detail": f"{p['target']}/{p['rel']} › {p['anchor']}",
                        "why": "全体の同じ見出しの節と食い違う。プロジェクトへの書き込みは後の段（いまは直さない）"})
    return out


def items(cands: list[Cand]) -> list[dict[str, Any]]:
    vd = verdicts()
    out = []
    for c in cands:
        v = vd.get(c.key) or {}
        rel = v.get("relation")
        if rel not in J1_RELATIONS or is_stale_copy(c):
            continue
        applies = "全プロジェクト（どちらも全体の規則）" if "*" in c.applies else "、".join(sorted(c.applies))
        sit = ""
        if v.get("situation_a") or v.get("situation_b"):
            sit = f" 状況: A={v.get('situation_a') or '-'} ／ B={v.get('situation_b') or '-'}。"
        if v.get("proposed_situation"):
            sit += f" 新しい状況の提案: {v['proposed_situation']}。"
        what = ("2 つの規則が同時に効き、同じ状況で両方には従えないと AI は見ています。" if rel == "conflict" else
                "2 つの規則が同時に効きます。AI は、状況が違えばどちらも正しいと見ています。エージェントが迷わないよう、状況を書き分けるか決めてください。")
        out.append({
            "kind": "J1", "key": f"J1|{c.key}", "title": f"{c.a['anchor']} × {c.b['anchor']}", "what": what,
            "a": {"where": _where(c.a), "when": _when(c.a), "text": c.a["text"]},
            "b": {"where": _where(c.b), "when": _when(c.b), "text": c.b["text"]},
            "applies": applies, "ai": f"{REL_LABEL[rel]}。{v.get('reason', '')}{sit}（{v.get('model', '')}）",
            "relation": rel, "refs": {"a": _ref(c.a), "b": _ref(c.b), "pair": c.key, "verdict": v},
            "initial_status": "open" if rel == "conflict" else "info",
            "options": [{"id": "split", "label": "状況で分ける（AI の案を直せる）", "primary": rel == "context_dependent"},
                        {"id": "a", "label": "A を採る（B を A に合わせる）", "primary": rel == "conflict"},
                        {"id": "b", "label": "B を採る（A を B に合わせる）"},
                        {"id": "merge", "label": "統合した文案にする"},
                        {"id": "ok", "label": "このままでよい"}, {"id": "later", "label": "あとで"}]})
    out.sort(key=lambda i: (i["relation"] != "conflict",))
    return out


def effective(tid: str) -> dict[str, Any]:
    """あるプロジェクト（またはホーム）のエージェントが同時に読む規則の全部を、出所つきで。"""
    t = targets.get_target(tid)
    if t is None:
        raise KeyError(f"配布先が無い: {tid}")
    g = global_units()
    layers = [{"layer": "全体（~/.claude の CLAUDE.md・rules）", "units": g}]
    if t["kind"] == "project":
        layers.append({"layer": f"プロジェクト（{t['name']}）", "units": project_units(t, {u['hash'] for u in g})})
    hashes = {u["hash"] for L in layers for u in L["units"]}
    return {"target": t, "layers": layers, "hashes": sorted(hashes),
            "note": "スキル（~/.claude/skills・ペア固有・プロジェクト固有）は必要なときだけ読まれるので、ここには含めない。Antigravity（~/.gemini/config）は同じ中身の写し"}


def path_of(ref: dict[str, Any]) -> Path:
    return Path(ref["path"])

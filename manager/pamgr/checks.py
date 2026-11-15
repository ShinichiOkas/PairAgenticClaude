"""検査: 冗長（機械）と、矛盾・状況依存（LLM・仮説）。

- 写し（同じ名前・同じ中身が複数の場所にある）は配布の結果なので、冗長として数えない
- 冗長:
    exact     名前の違う単位が、同じ中身
    variants  同じ名前の単位が、場所によって中身が違う（プロジェクトで改変された写し）
    near      名前の違う単位が、文字の上でよく似ている
- 矛盾・状況依存: 文字の類似で話題の近い組を絞り、LLM が関係を判定する。判定は仮説（資産は書き換えない）
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import llm, situations, store, survey
from .similarity import similarity_matrix, top_pairs

FILE = "checks.json"
SCOPE_RANK = {"master": 0, "global": 1, "user": 2, "project": 3}
NEAR_MIN = 0.6
CONFLICT_MIN = 0.25
VARIANT_SECTION_MIN = 0.4
CHECK_KINDS = ("skill", "rule-section")


def identity(u: dict[str, Any]) -> str:
    if u["kind"] == "rule-section":
        return "section:" + re.sub(r"\s+", "", u.get("anchor", "")).lower()
    return "skill:" + re.sub(r"[\s_]+", "-", str(u.get("name", "")).strip().lower())


def _brief(u: dict[str, Any]) -> dict[str, Any]:
    return {k: u.get(k) for k in ("id", "name", "title", "scope", "kind", "target", "target_id", "rel", "anchor")}


def representatives(units: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """同じ中身の単位を 1 つにまとめる（マスター＞全体＞ユーザー＞プロジェクトの順に代表を選ぶ）。"""
    by_hash: dict[str, list[dict[str, Any]]] = {}
    for u in units:
        if u["kind"] in CHECK_KINDS:
            by_hash.setdefault(u["hash"], []).append(u)
    reps = []
    for members in by_hash.values():
        members.sort(key=lambda u: (SCOPE_RANK.get(u["scope"], 9), u["rel"]))
        reps.append(members[0])
    return reps, by_hash


def redundancy(units: list[dict[str, Any]]) -> dict[str, Any]:
    reps, by_hash = representatives(units)
    exact, copies = [], 0
    for members in by_hash.values():
        ids = {identity(u) for u in members}
        if len(members) > 1 and len(ids) == 1:
            copies += 1
        elif len(ids) > 1:
            exact.append({"units": [_brief(u) for u in members]})
    sim = similarity_matrix([u["text"] for u in reps]) if len(reps) > 1 else None

    def score(i: int, j: int) -> float:
        return round(float(sim[i, j]), 3) if sim is not None else 0.0

    idx = {u["id"]: i for i, u in enumerate(reps)}
    by_id: dict[str, list[dict[str, Any]]] = {}
    for u in reps:
        by_id.setdefault(identity(u), []).append(u)
    variants = []
    for ident, us in by_id.items():
        if len(us) < 2 or ident in ("section:(全文)", "section:(冒頭)"):
            continue
        if us[0]["kind"] == "rule-section":
            base = idx[us[0]["id"]]
            us = [us[0]] + [u for u in us[1:] if score(base, idx[u["id"]]) >= VARIANT_SECTION_MIN]
            if len(us) < 2:
                continue
        variants.append({"name": us[0]["name"], "units": [_brief(u) for u in us]})
    near = []
    if sim is not None:
        for i, j, v in top_pairs(sim, k=5, lo=NEAR_MIN):
            if identity(reps[i]) != identity(reps[j]):
                near.append({"a": _brief(reps[i]), "b": _brief(reps[j]), "score": v})
    return {"checked_at": store.now_iso(), "units": len(units), "representatives": len(reps), "copies": copies,
            "exact": exact, "variants": variants, "near": near}


def conflict_candidates(units: list[dict[str, Any]], limit: int) -> list[tuple[dict[str, Any], dict[str, Any], float]]:
    reps, _ = representatives(units)
    if len(reps) < 2:
        return []
    sim = similarity_matrix([u["text"] for u in reps])
    pairs = [(reps[i], reps[j], v) for i, j, v in top_pairs(sim, k=5, lo=CONFLICT_MIN, hi=0.97)]
    return pairs[:limit]


class PairVerdict(BaseModel):
    relation: Literal["duplicate", "subsumes", "overlap", "conflict", "context_dependent", "unrelated"] = Field(
        description="duplicate=同じ規則 / subsumes=片方が他方を含む / overlap=一部重なる / conflict=同じ状況で両立しない / "
                    "context_dependent=矛盾して見えるが別の状況ではそれぞれ真 / unrelated=無関係")
    situation_a: str = Field(default="", description="A が真になる状況（状況定義の ID か、短い説明）。conflict・context_dependent のときだけ")
    situation_b: str = Field(default="", description="B が真になる状況（同上）")
    proposed_situation: str = Field(default="", description="既存の状況定義で表せないとき、新しい状況の『ID: 定義』。無ければ空")
    reason: str = Field(description="判定の理由。日本語で 3 文以内。どの文とどの文がぶつかるかを引用して示す")


SYSTEM = """あなたは、AI コーディングエージェントに与えるルール・スキル文書の監査役です。
2 つの文書 A と B の関係を判定します。

- 文書は AI と人間（師匠）のペア作業の規範です。師匠の原文の引用が含まれることがあります
- 「矛盾（conflict）」は、同じ状況で両方に従うことができない場合だけです
- 一見ぶつかっても、適用される状況（誰が・いつ・どの規模の作業で）が違えば両方とも真です。そのときは context_dependent とし、
  それぞれが真になる状況を、下の状況定義の ID で答えてください。当てはまるものが無ければ proposed_situation に新しい状況を書いてください
- 推測で断定しないでください。根拠の文を引用してください

状況定義:
{situations}"""

MAX_DOC = 5000


def judge_pair(a: dict[str, Any], b: dict[str, Any], model: str | None = None) -> tuple[PairVerdict, str]:
    sys_ = SYSTEM.format(situations=situations.as_prompt(situations.load()))
    user = (f"## 文書 A（{a['scope']}・{a['target']}・{a['rel']} {a.get('anchor', '')}）\n{a['text'][:MAX_DOC]}\n\n"
            f"## 文書 B（{b['scope']}・{b['target']}・{b['rel']} {b.get('anchor', '')}）\n{b['text'][:MAX_DOC]}\n\n"
            "A と B の関係を判定してください。")
    return llm.chat_structured(sys_, user, PairVerdict, role="judge", model=model)


def run_conflict(units: list[dict[str, Any]], limit: int, progress: Any, model: str | None = None) -> dict[str, Any]:
    cands = conflict_candidates(units, limit)
    model_name = model or ""
    out = []
    for n, (a, b, v) in enumerate(cands):
        progress(n, len(cands), f"判定中: {a['name']} × {b['name']}")
        rec: dict[str, Any] = {"a": _brief(a), "b": _brief(b), "score": v, "hypothesis": True}
        try:
            verdict, model_name = judge_pair(a, b, model)
            rec.update(verdict.model_dump())
        except Exception as exc:  # 1 組の失敗で全体を止めない。組の識別子を残す
            rec.update({"relation": "error", "error": f"{type(exc).__name__}: {exc}"})
        out.append(rec)
        _save_part("conflict", {"checked_at": store.now_iso(), "model": model_name, "pairs": out, "candidates": len(cands)})
    progress(len(cands), len(cands), "完了")
    order = {"conflict": 0, "context_dependent": 1, "duplicate": 2, "subsumes": 3, "overlap": 4, "unrelated": 5, "error": 6}
    out.sort(key=lambda r: (order.get(r.get("relation", ""), 9), -r["score"]))
    res = {"checked_at": store.now_iso(), "model": model_name, "pairs": out, "candidates": len(cands)}
    _save_part("conflict", res)
    return res


def _save_part(key: str, value: dict[str, Any]) -> None:
    data = store.load(FILE, {})
    data[key] = value
    store.save(FILE, data)


def run_redundancy(units: list[dict[str, Any]]) -> dict[str, Any]:
    res = redundancy(units)
    _save_part("redundancy", res)
    return res


def load() -> dict[str, Any]:
    return store.load(FILE, {})


def units_or_raise() -> list[dict[str, Any]]:
    data = survey.load()
    if not data:
        raise ValueError("先にサーベイを実行してください")
    return data["units"]

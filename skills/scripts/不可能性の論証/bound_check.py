#!/usr/bin/env python3
"""「原理的にできない」の主張を、上限を決める量・需要式・最良ケース・反証条件の JSON で検算し、主張が成り立つ境目の値を求める。

主張 JSON:
 {"claim":"...", "limit":{"name":"メモリ","value":8,"unit":"GiB"},
  "demand":"n*size/2**30", "vars":{"n":2e9,"size":16},
  "best_case":{"size":8}, "falsifier":"n が 1e9 未満と示されたら覆る"}
 demand は四則・累乗・括弧・数値・変数だけの式（ast で検証。eval しない）。
判定: 最良ケース（best_case で vars を上書き）でも需要 > 上限 なら IMPOSSIBLE_BY_SYSTEM。
      通常値でだけ超えるなら NOT_PROVEN（「できなかった」と書く）。超えないなら FEASIBLE。
各変数について主張が反転する境目（二分探索・単調を仮定）を出す。必須項目が欠ければ指摘して 1。読むだけ。
使い方: bound_check.py claim.json [--json]
"""
import argparse
import ast
import json
import operator
import sys

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos, ast.FloorDiv: operator.floordiv}


def evaluate(expr, env):
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in env:
                raise ValueError(f"未定義の変数: {n.id}")
            return env[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.operand))
        raise ValueError(f"使えない構文: {ast.dump(n)[:40]}")
    return ev(ast.parse(expr, mode="eval"))


def threshold(expr, env, limit, var):
    """var を動かして demand==limit になる値を二分探索。見つからなければ None。"""
    base = env[var]
    if base == 0:
        return None
    lo, hi = 0.0, abs(base) * 1e6
    f = lambda x: evaluate(expr, {**env, var: x}) - limit
    try:
        flo, fhi = f(lo), f(hi)
    except (ZeroDivisionError, ValueError, OverflowError):
        return None
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(mid) * flo <= 0:
            hi = mid
        else:
            lo, flo = mid, f(mid)
    return (lo + hi) / 2


def check(spec):
    problems = []
    for k in ("claim", "limit", "demand", "vars", "falsifier"):
        if not spec.get(k):
            problems.append(f"必須項目が無い: {k}")
    lim = spec.get("limit") or {}
    for k in ("name", "value", "unit"):
        if k not in lim or lim[k] in (None, ""):
            problems.append(f"limit.{k} が無い（上限を決めている量を名指しする）")
    if "best_case" not in spec:
        problems.append("best_case が無い（自分の技量の限界と系の限界を分けるため、最良の条件での需要が要る）")
    if problems:
        return {"verdict": "INCOMPLETE", "problems": problems}
    env = {k: float(v) for k, v in spec["vars"].items()}
    best = {**env, **{k: float(v) for k, v in spec.get("best_case", {}).items()}}
    L = float(lim["value"])
    d_norm = evaluate(spec["demand"], env)
    d_best = evaluate(spec["demand"], best)
    if d_best > L:
        verdict = "IMPOSSIBLE_BY_SYSTEM"
    elif d_norm > L:
        verdict = "NOT_PROVEN"
    else:
        verdict = "FEASIBLE"
    thr = {v: threshold(spec["demand"], best, L, v) for v in best}
    return {"verdict": verdict, "limit": f"{lim['name']}={L:g}{lim['unit']}", "demand_normal": d_norm,
            "demand_best_case": d_best, "ratio_best_case": d_best / L if L else None,
            "flip_thresholds_at_best_case": thr, "falsifier": spec["falsifier"], "problems": []}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("claim")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    with open(a.claim, encoding="utf-8") as f:
        res = check(json.load(f))
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"判定: {res['verdict']}")
        for k, v in res.items():
            if k not in ("verdict", "problems"):
                print(f"  {k}: {v}")
        for p in res["problems"]:
            print(f"[指摘] {p}")
        if res["verdict"] == "NOT_PROVEN":
            print("→ 最良ケースでは足りる。「原理的にできない」ではなく「できなかった」と書く")
    return 0 if res["verdict"] in ("IMPOSSIBLE_BY_SYSTEM", "FEASIBLE") else 1


if __name__ == "__main__":
    sys.exit(main())

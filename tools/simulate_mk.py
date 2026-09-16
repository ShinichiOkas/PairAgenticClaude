#!/usr/bin/env python
"""`.mk` を状態から空回しして、**書かれた定義が何を起動するか**を見せる。

G-47 の一般解。

  **欠落が読み手から隠れるのは、読み手が黙って補修するからである。**
  **機械には補修する材料が無い。だから機械に当てる。**

読み手を増やしても足りない —— A-6 では 4 体全員が
「受入検査実施者が初回から起動する」を見落とした。全員が同じ常識で補修したからである。
見つけたのは、書かれた検出条件を機械的に当てたときだった。

この道具は答えを判定しない。**書かれた定義の答えを可視化するだけ**である。
不合理かどうかを見るのは人間の仕事（P-12）。

    python tools/simulate_mk.py models/waterfall-core.mk
    python tools/simulate_mk.py models/waterfall-core.mk --absent=用語資産
    python tools/simulate_mk.py models/waterfall-core.mk --steps=30
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_roles import Rule, base_name, parse_mk  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

MISSING = -1  # 存在しない target の時刻。どの起点（時刻 0）より古い


class State:
    """成果物の存在と更新時刻。時刻は論理ステップ番号"""

    def __init__(self, origins: list[str], absent: set[str]) -> None:
        self.t: dict[str, int] = {o: 0 for o in origins if o not in absent}
        self.absent = absent
        # H-8 用: 前回起動したときに「存在していた dep」の集合
        self.seen: dict[str, frozenset[str]] = {}

    def exists(self, node: str) -> bool:
        return node in self.t

    def time(self, node: str) -> int:
        return self.t.get(node, MISSING)

    def put(self, node: str, step: int) -> None:
        self.t[node] = step


def runnable(r: Rule, st: State) -> tuple[bool, bool, str]:
    """(実行可能, 検出, 理由) —— P-53 の 2 条件を別々に返す"""
    missing = [d for d in r.required_deps if not st.exists(base_name(d))]
    if missing:
        return False, False, "必須 dep が無い: " + "、".join(missing)

    tgt = st.time(r.node)
    newer = [d for d in r.deps
             if st.exists(base_name(d)) and st.time(base_name(d)) > tgt]
    if not newer:
        return True, False, "自分より新しい dep が無い"
    return True, True, "新しい: " + "、".join(newer)


def unchanged(r: Rule, st: State) -> bool:
    """H-8 の近似 —— **前回起動時と同じ dep 集合しか見えていないなら、出力は変わらない**

    ⚠ 近似である。シミュレータは内容を持たないので「同じ出力か」は判定できない。
    ここで捉えているのは **「新しい入力が入ったときだけ変化する」** という読みだけで、
    **同じ入力から違う出力が出る揺らぎは捉えない。**
    """
    cur = frozenset(base_name(d) for d in r.deps if st.exists(base_name(d)))
    return st.seen.get(r.node) == cur


def simulate(rules: list[Rule], absent: set[str], max_steps: int,
             h8: bool = False) -> int:
    origins = [r.node for r in rules if r.is_origin]
    work = [r for r in rules if not r.is_origin]
    st = State(origins, absent)

    print("# 空回し — " + str(len(work)) + " rule"
          + ("　**H-8 あり**（内容が変わらなければ時刻を進めない）" if h8 else ""))
    print("")
    print("**起点**: " + "、".join(
        (o + ("（**不在**）" if o in absent else "")) for o in origins))
    print("")

    fired_at: dict[str, list[int]] = {}
    widths: list[int] = []
    step = 0

    while step < max_steps:
        step += 1
        cands = [r for r in work if runnable(r, st)[1]]
        if not cands:
            break
        widths.append(len(cands))

        # 判定はステップ開始時の状態で行う（同一ステップ内の順序に依存させない）
        still = [r for r in cands if h8 and unchanged(r, st)]
        moved = [r for r in cands if r not in still]

        print("## ステップ " + str(step) + " — **候補 " + str(len(cands)) + " 件**"
              + ("（うち **不変 " + str(len(still)) + " 件**）" if still else ""))
        print("")
        for r in cands:
            tag = {"agent": "", "machine": " `機械`", "human": " `人間`"}[r.by]
            mark = " —— **不変。下流を起こさない**" if r in still else ""
            print("- " + r.target + tag + mark)
        print("")

        snapshot = {r.node: frozenset(base_name(d) for d in r.deps
                                      if st.exists(base_name(d))) for r in cands}
        for r in moved:
            st.put(r.node, step)
        for r in cands:
            st.seen[r.node] = snapshot[r.node]
            fired_at.setdefault(r.node, []).append(step)
        if not moved:
            print("**→ 全候補が不変。ここで停止する**")
            print("")
            break

    print("---")
    print("")

    # ── 所見 ────────────────────────────────────────────────
    findings: list[str] = []

    never = [r for r in work if r.node not in fired_at]
    for r in never:
        _, _, why = runnable(r, st)
        findings.append("**[一度も起動しない]** `" + r.target + "` —— " + why)

    if step >= max_steps:
        loop = sorted(n for n, ts in fired_at.items() if len(ts) > 1)
        findings.append("**[停止しない]** " + str(max_steps)
                        + " ステップで打ち切った。**繰り返し起動**: "
                        + "、".join(loop))

    if widths and widths[0] > 1:
        findings.append("**[初手が一意でない]** 最初のステップで候補が "
                        + str(widths[0]) + " 件。**割り当てが要る**（H-4）")

    print("## 候補数の推移")
    print("")
    print("`" + " → ".join(str(w) for w in widths) + "`")
    print("")
    if widths:
        mx = max(widths)
        amb = sum(1 for w in widths if w > 1)
        print("- **最大 " + str(mx) + " 件**（同時に走れる上限。**並列度の上限**）")
        print("- **候補が 2 件以上のステップ: " + str(amb) + " / "
              + str(len(widths)) + "**")
        print("  —— **ここが割り当ての要る箇所**。定義では決まらない（P-54）")
    print("")

    print("## 到達")
    print("")
    print("- 起動した rule: **" + str(len(fired_at)) + " / " + str(len(work)) + "**")
    print("")

    print("## 所見")
    print("")
    if findings:
        for f in findings:
            print("- " + f)
    else:
        print("- ⭕ 一度も起動しない rule は無い。打ち切りにも達していない")
    print("")
    print("> ⚠ **この道具は「不合理かどうか」を判定しない。**")
    print("> **書かれた定義が何を起動するかを見せるだけである。**")
    print("> **不合理を見つけるのは人間の仕事**（P-12）。")
    print("> **A-6 では 4 体全員が見落とした欠落を、この形の出力なら 1 行で見つけられた。**")

    return 1 if never else 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if not args:
        print(__doc__)
        return 2

    absent: set[str] = set()
    steps = 20
    h8 = False
    for f in flags:
        if f.startswith("--absent="):
            absent |= {s.strip() for s in f.split("=", 1)[1].split(",") if s.strip()}
        elif f.startswith("--steps="):
            steps = int(f.split("=", 1)[1])
        elif f == "--h8":
            h8 = True

    rules = parse_mk(Path(args[0]))
    known = {r.node for r in rules}
    for a in absent:
        if a not in known:
            print("⚠ `" + a + "` は " + args[0] + " に無い名前")
            return 2
    return simulate(rules, absent, steps, h8)


if __name__ == "__main__":
    sys.exit(main())

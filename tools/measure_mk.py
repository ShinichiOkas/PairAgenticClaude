#!/usr/bin/env python
"""
`.mk` から、静的に測れる量だけを出す計器。

  python tools/measure_mk.py models/*.mk
  python tools/measure_mk.py --diff models/waterfall-core.mk models/waterfall-small.mk

⚠ これが測れるのは「コスト側」だけである。
   **注入量（IN を満たす OUT の空間の大きさ・P-23）は静的には測れない。**
   実走が要る（→ 未実装）。

設計方針（build-the-measuring-tool-first / continuous-scalars-from-code-not-llm）:
  - LLM を通さない。宣言だけから決定論的に出す
  - 代理でしかない量は「代理」と明記する
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from derive_roles import (  # noqa: E402
    parse_mk, parse_tasks, derive_edges, color, split_by_skill, base_name,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def measure(mk: Path) -> dict[str, object]:
    rules = parse_mk(mk)
    tk = mk.with_suffix(".tasks")
    tasks = parse_tasks(tk)
    produced = [r for r in rules if not r.is_origin]
    agents = [r for r in produced if r.is_role]
    machines = [r for r in produced if r.by == "machine"]
    humans = [r for r in produced if r.by == "human"]

    edges = derive_edges(agents)
    edge_set: set[tuple[str, str]] = set()
    for a, b, _, _ in edges:
        u, v = sorted((base_name(a), base_name(b)))
        edge_set.add((u, v))
    assign = color([r.node for r in agents], edge_set)
    groups: dict[int, list] = {}
    for r in agents:
        groups.setdefault(assign[r.node], []).append(r)
    roles = split_by_skill(groups, tasks)

    gates = {r.gate for r in produced if r.gate}
    return {
        "name": mk.stem,
        "役割": len(roles),
        "agent rule": len(agents),
        "機械 rule": len(machines),
        "人間 rule": len(humans),
        "人間ゲート": len(gates),
        "起点": len([r for r in rules if r.is_origin]),
        "Σdeps": sum(len(r.deps) for r in produced),
        "遮断本数": sum(len(r.blocks) for r in produced),
        "分離線": len(edges),
    }


COLS = ["役割", "agent rule", "機械 rule", "人間 rule", "人間ゲート", "起点",
        "Σdeps", "遮断本数", "分離線"]

NOTES = {
    "役割": "別コンテキストの数（§11-7: 遮断の実効化はコンテキスト分離）",
    "agent rule": "LLM 呼び出し回数の下限",
    "機械 rule": "決定論。LLM を通さないので安い（P-11）",
    "人間ゲート": "**A の帯域の消費**。役割数を律速する",
    "Σdeps": "渡す資料の総量の**代理**（本数であって、量ではない）",
    "遮断本数": "宣言された遮断の数",
}


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--diff":
        a, b = measure(Path(argv[1])), measure(Path(argv[2]))
        print("# 差分 — " + str(a["name"]) + " → " + str(b["name"]) + "\n")
        print("| 量 | " + str(a["name"]) + " | " + str(b["name"]) + " | 差 | 意味 |")
        print("|---|---|---|---|---|")
        for c in COLS:
            va, vb = int(a[c]), int(b[c])  # type: ignore[arg-type]
            d = vb - va
            mark = "—" if d == 0 else ("**" + ("+" if d > 0 else "") + str(d) + "**")
            print("| " + c + " | " + str(va) + " | " + str(vb) + " | " + mark
                  + " | " + NOTES.get(c, "") + " |")
        return 0

    rows = [measure(Path(p)) for p in argv]
    print("# `.mk` カタログの静的計測\n")
    print("| モデル | " + " | ".join(COLS) + " |")
    print("|---" * (len(COLS) + 1) + "|")
    for r in sorted(rows, key=lambda x: int(x["役割"])):  # type: ignore[arg-type]
        print("| " + str(r["name"]) + " | " + " | ".join(str(r[c]) for c in COLS) + " |")
    print("\n## 各量の意味\n")
    for c in COLS:
        if c in NOTES:
            print("- **" + c + "** — " + NOTES[c])
    print("\n## ⚠ 測れていないもの\n")
    print("- **注入量**（IN を満たす OUT の空間の大きさ・P-23）—— **静的には測れない。実走が要る**")
    print("- **トークン数** —— `Σdeps` は本数であって量ではない。成果物の実サイズが要る")
    print("- **判断の喪失** —— 降ろした結果どれだけ品質が落ちるかは、走らせないと出ない")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

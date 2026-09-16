#!/usr/bin/env python
"""
成果物定義（Makefile 形式）から、役割・アサイン・必要スキルを導出する。

  python tools/derive_roles.py models/waterfall-core.mk models/waterfall-core.tasks
  python tools/derive_roles.py ... --emit-roles=docs/roles-coding.md

設計方針:
  - 判断を一切入れない。宣言だけから導く
  - 導けないものは「導けない」と報告する（黙って埋めない）
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

NL = "\n"
VERSION_SUFFIX = re.compile(r"_v\([a-z](?:[+-]\d+)?\)$")
OPTIONAL_SUFFIX = re.compile(r"\?$")
BACK_VERSION = re.compile(r"_v\([a-z]-\d+\)$")


def base_name(name: str) -> str:
    """実装物_v(n) と 実装物_v(n-1) と 用語資産? を同一ノードとして扱う（P-21: 版で解ける）"""
    return VERSION_SUFFIX.sub("", OPTIONAL_SUFFIX.sub("", name.strip())).strip()


def dep_kind(dep: str) -> str:
    """dep の 3 種（P-53）。**存在しないときの意味がそれぞれ違う**

    必須 : 存在しなければ**走れない**（待つ）
    前版 : `_v(k-1)` 形。初回は必ず存在しない。**空として読む。走れる**
    任意 : `?` 付き。存在しなければ**空として読む。走れる**（空だったことを申告する）
    """
    d = dep.strip()
    if OPTIONAL_SUFFIX.search(d):
        return "任意"
    if BACK_VERSION.search(d):
        return "前版"
    return "必須"


@dataclass
class Rule:
    target: str
    deps: list[str] = field(default_factory=list)
    role: str | None = None
    task: str | None = None
    by: str = "agent"
    blocks: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    gate: str | None = None
    writes: list[str] = field(default_factory=list)
    out: list[str] = field(default_factory=list)
    post: list[str] = field(default_factory=list)
    detect: str | None = None
    # ⚠ 以下 2 つは**導出できない**。ハーネスに渡す値なので、要るなら .mk で宣言する
    tools: str | None = None          # read | write | exec（既定は write）
    agent: dict = field(default_factory=dict)  # `agent.<key> : <値>` の素通し
    line: int = 0

    @property
    def node(self) -> str:
        return base_name(self.target)

    @property
    def role_name(self) -> str:
        return self.role or self.node

    @property
    def is_role(self) -> bool:
        """機械（P-11）と人間（P-12）は役割ではない"""
        return self.by == "agent"

    @property
    def dep_nodes(self) -> list[str]:
        return [base_name(d) for d in self.deps]

    @property
    def is_origin(self) -> bool:
        return not self.deps and self.task is None

    @property
    def required_deps(self) -> list[str]:
        """存在しなければ走れない dep（P-53）"""
        return [d for d in self.deps if dep_kind(d) == "必須"]

    @property
    def soft_deps(self) -> list[str]:
        """存在しなくても走れる dep。無ければ**空として読む**（P-53）"""
        return [d for d in self.deps if dep_kind(d) != "必須"]

    @property
    def ready_rule(self) -> str:
        """実行可能条件 —— 検出条件より先に判定する（P-53）"""
        if not self.required_deps:
            return "**無条件**（必須 dep が無い）"
        return "、".join(self.required_deps) + " が**すべて存在する**"

    @property
    def detect_rule(self) -> str:
        if self.detect:
            return self.detect
        return " / ".join(self.deps) + " のいずれかが `" + self.target + "` より新しい"


FIELD_ALIASES = {
    "role": "role", "役割": "role",
    "task": "task", "タスク": "task",
    "by": "by", "担い手": "by",
    "blocks": "blocks", "遮断": "blocks",
    "checks": "checks", "検査対象": "checks",
    "gate": "gate", "ゲート": "gate",
    "writes": "writes", "書き込み": "writes",
    "out": "out", "内訳": "out",
    "post": "post", "事後": "post",
    "detect": "detect", "検出": "detect",
    "tools": "tools", "ツール": "tools",
}
LIST_FIELDS = {"blocks", "checks", "writes"}
APPEND_FIELDS = {"out", "post"}


def split_list(value: str) -> list[str]:
    parts = re.split(r"[,、]", value)
    return [p.strip() for p in parts if p.strip() and p.strip() not in {"-", "none", "なし"}]


def parse_mk(path: Path) -> list[Rule]:
    rules: list[Rule] = []
    current: Rule | None = None
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            body = line.lstrip()[1:].strip()
            if not body or current is None or ":" not in body:
                continue
            key, _, value = body.partition(":")
            key = key.strip().lower()
            # `agent.<key> : <値>` —— ハーネス固有の欄を**導出せずに素通しする**入口。
            # 導出できないものを勝手に埋めないための逃がし（emit_claude.py が使う）
            if key.startswith("agent."):
                current.agent[key[len("agent."):].strip()] = value.strip()
                continue
            if key not in FIELD_ALIASES:
                continue
            name = FIELD_ALIASES[key]
            value = value.strip()
            if name in APPEND_FIELDS:
                getattr(current, name).append(value)
            elif name in LIST_FIELDS:
                setattr(current, name, split_list(value))
            else:
                setattr(current, name, value or None)
            continue
        if ":" in line and not line.startswith((" ", "\t")):
            target, _, deps = line.partition(":")
            current = Rule(target=target.strip(), deps=split_list(deps), line=lineno)
            rules.append(current)
    return rules


def parse_tasks(path: Path) -> dict[str, list[str]]:
    lib: dict[str, list[str]] = {}
    if not path.exists():
        return lib
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        name, _, skills = line.partition(":")
        lib[name.strip()] = split_list(skills)
    return lib


# ---------------------------------------------------------------- 分離線

def derive_edges(work: list[Rule]) -> list[tuple[str, str, str, str]]:
    """(rule_a, rule_b, 規則名, 根拠)。担い手を分けねばならない対。"""
    edges: list[tuple[str, str, str, str]] = []
    for a, b in combinations(work, 2):
        # NTK: 同一担い手なら deps は互いに見えている（§11-7）
        for x, y in ((a, b), (b, a)):
            # ⚠ y 自身が作る target は、y にとって「見た」ではなく「作った」である。
            #   x がそれを遮断していても、それは x ↮ y の根拠になるが、
            #   根拠の文言は「作る」でなければならない（自己参照の誤読を招く）
            leaked = sorted(set(x.blocks) & set(y.dep_nodes + [y.node]))
            if leaked:
                own = [z for z in leaked if z == y.node]
                seen = [z for z in leaked if z != y.node]
                parts = []
                if own:
                    parts.append(y.target + " の担い手は " + "/".join(own) + " を**作る**")
                if seen:
                    parts.append(y.target + " の担い手は " + "/".join(seen) + " を**見る**")
                why = "、".join(parts) + "。" + x.target + " の遮断に当たる"
                edges.append((a.target, b.target, "NTK", why))
                break
        # SoD 第1形: 生成する者と、それを検査する者
        for x, y in ((a, b), (b, a)):
            if y.node in [base_name(c) for c in x.checks]:
                edges.append((a.target, b.target, "SoD-1",
                              x.target + " が " + y.target + " を検査する"))
                break
        # SoD 第2形: 承認を求める者と、その承認を前提に次を作る者
        for x, y in ((a, b), (b, a)):
            if x.gate and x.node in y.dep_nodes:
                why = (x.target + " にゲート " + x.gate + " があり、"
                       + y.target + " がそれを前提にする")
                edges.append((a.target, b.target, "SoD-2", why))
                break
    return edges


def find_cycles(rules: list[Rule]) -> list[tuple[list[str], bool]]:
    """循環を検出する。(経路, 版で解けるか) を返す。

    版で解ける ＝ 循環を構成する辺のどれかが `_v(n-1)` のような過去版参照である（P-21）。
    """
    dep_map = {r.node: [(base_name(d), d != base_name(d)) for d in r.deps] for r in rules}
    found: list[tuple[list[str], bool]] = []
    seen_keys: set[frozenset[str]] = set()

    def walk(node: str, path: list[str], versioned: bool) -> None:
        for dep, is_ver in dep_map.get(node, []):
            if dep in path:
                cyc = path[path.index(dep):] + [dep]
                key = frozenset(cyc)
                if key not in seen_keys:
                    seen_keys.add(key)
                    found.append((cyc, versioned or is_ver))
                continue
            if len(path) < 12:
                walk(dep, path + [dep], versioned or is_ver)

    for r in rules:
        walk(r.node, [r.node], False)
    return found


def check_lp(rules: list[Rule]) -> list[str]:
    """Least Privilege: 成果物への書き込みが自分の target に閉じているか。

    ⚠ **作業空間は規定の対象外**（師匠、2026-08-31）。
    継ぎ目を跨がないので、誰の判断も汚染せず、誰の成果物も壊さない。
    したがって `writes` に書くのは**成果物への書き込み先だけ**である。
    """
    out = []
    for r in rules:
        for w in (r.writes or [r.target]):
            if base_name(w) != r.node:
                out.append(r.target + " が他人の成果物 `" + w + "` に書いている（line "
                           + str(r.line) + "）")
    return out


# ---------------------------------------------------------------- 彩色

def color(nodes: list[str], edges: set[tuple[str, str]]) -> dict[str, int]:
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for u, v in edges:
        adj[u].add(v)
        adj[v].add(u)
    for k in range(1, len(nodes) + 1):
        assign: dict[str, int] = {}

        def bt(i: int) -> bool:
            if i == len(nodes):
                return True
            n = nodes[i]
            used = {assign[m] for m in adj[n] if m in assign}
            for c in range(k):
                if c not in used:
                    assign[n] = c
                    if bt(i + 1):
                        return True
                    del assign[n]
            return False

        if bt(0):
            return assign
    return {n: i for i, n in enumerate(nodes)}


def split_by_checking(groups: dict[int, list[Rule]]) -> list[list[Rule]]:
    """旧: 同じ群の中を「検査対象あり／なし」で割る（P-41・撤回済み。比較用に残す）"""
    out: list[list[Rule]] = []
    for members in groups.values():
        for bucket in ([r for r in members if not r.checks],
                       [r for r in members if r.checks]):
            if bucket:
                out.append(bucket)
    return out


def load_capabilities() -> dict[str, str]:
    """skill → 技能領域 の対応（skills/capabilities.cap）。

    **重なりを測る単位は skill ではなく技能領域である**（skill-definition.md §1-3）。
    `@規約` `@警戒` `@境界線` は技能領域ではないので、重なりに寄与しない（§2）。
    """
    path = Path(__file__).resolve().parent.parent / "skills" / "capabilities.cap"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        if name.startswith("@"):
            continue
        for s in (x.strip() for x in rest.split(",")):
            if s:
                out[s] = name
    return out


def derive_role_groups(work: list[Rule], tasks: dict[str, list[str]],
                       by_capability: bool = False
                       ) -> tuple[list[tuple[str, str, str, str]],
                                  dict[int, list[Rule]], list[list[Rule]]]:
    """安全軸（分離線→彩色）と性能軸（skill の重なり）を通して役割を出す。

    `run()` と `emit_claude.py` が**同じ導出**を共有するための入口。
    ここに判断は無い。順序は run() が書いていたものと同一である。
    """
    edges = derive_edges(work)
    edge_set: set[tuple[str, str]] = set()
    for a, b, _, _ in edges:
        u, v = sorted((base_name(a), base_name(b)))
        edge_set.add((u, v))
    assign = color([r.node for r in work], edge_set)
    groups: dict[int, list[Rule]] = {}
    for r in work:
        groups.setdefault(assign[r.node], []).append(r)
    return edges, groups, split_by_skill(groups, tasks, by_capability)


def split_by_skill(groups: dict[int, list[Rule]],
                   tasks: dict[str, list[str]],
                   by_capability: bool = False) -> list[list[Rule]]:
    """性能軸（目的の単一化・C-1）: task が要求する skill が重なる rule だけをまとめる。

    skill 集合が交わらない task を同じ担い手に持たせると「何でもできるロール」になる。
    重なりの連結成分をとる（A-B が重なり B-C が重なれば A,B,C は同じ役割）。

    by_capability=True なら **技能領域**で測る（skill-definition.md §1-3）。
    """
    cap = load_capabilities() if by_capability else {}

    def keys(task: str | None) -> set[str]:
        raw = tasks.get(task or "", [])
        if not by_capability:
            return set(raw)
        # 技能領域に属さない skill（規約・警戒・境界線）は重なりに寄与しない
        return {cap[s] for s in raw if s in cap}

    out: list[list[Rule]] = []
    for members in groups.values():
        skills = {r.node: keys(r.task) for r in members}
        parent = {r.node: r.node for r in members}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for a, b in combinations(members, 2):
            if skills[a.node] & skills[b.node]:
                ra, rb = find(a.node), find(b.node)
                if ra != rb:
                    parent[ra] = rb

        buckets: dict[str, list[Rule]] = {}
        for r in members:
            buckets.setdefault(find(r.node), []).append(r)
        out.extend(buckets.values())
    return out


# ---------------------------------------------------------------- 生成

PREAMBLE = """<!-- 自動生成。手で編集しない。正は {src} -->
# コーディングドメインの役割定義（生成物）

- 生成元: `{src}` ＋ `{tasks}`
- 生成: `python tools/derive_roles.py {src} {tasks} --emit-roles=docs/roles-coding.md`
- **成果物定義が正。役割はその分割として導出される**

## 記述形式

**ここにあるのは「エージェントに渡る定義」だけである。**
姿勢・分離の物語は人間が読む説明であり、[`principles.md`](principles.md) 側にある
（P-3 改訂・2026-08-31）。

**書いてはならないもの: 作業手順**（P-3）。手順は task が指す skill にある。
**順序も書かない**（P-20）。依存だけを書く。

## すべての役割に共通する規則

### 決定権限（P-23）

> **deps を満たす OUT の空間の内側では自由。外に出るなら範囲外。**
> 勝手にドロップしない（不足）／要求にないことを追加しない（過剰）／
> 範囲内であることを示せないものは範囲外として扱う。

### OUT の形（P-4）

    OUT ＝ 成果物 ＋ その理由 ＋ 残留リスク

### 作業領域

すべての役割は自分の作業領域に書ける。誰も消費しないので独立性を壊さない。

### 遮断の読み方

**deps に書かれていないものは読めない**（ホワイトリスト・P-29）。
`deps に無いもの` 欄は、**明示的に宣言された遮断**（見ると判断が汚染されるもの）である。

---
"""


def emit_roles(mk, tk, rules, tasks, roles, edges, nonrole, origins, problems) -> str:
    L: list[str] = [PREAMBLE.format(src=mk.as_posix(), tasks=tk.as_posix())]
    add = L.append

    add("## 役割一覧")
    add("")
    add("| # | 役割 | 担当 rule | task | 検査対象 | ゲート |")
    add("|---|---|---|---|---|---|")
    for i, ms in enumerate(roles, 1):
        rl = " / ".join(m.target for m in ms)
        tks = " / ".join("`" + (m.task or "?") + "`" for m in ms)
        ck = " / ".join(",".join(m.checks) or "—" for m in ms)
        gt = " / ".join(m.gate or "—" for m in ms)
        add("| " + str(i) + " | **" + ms[0].role_name + "** | " + rl + " | " + tks
            + " | " + ck + " | " + gt + " |")
    add("")

    if nonrole:
        add("**役割ではないもの**（P-11 機械 / P-12 人間）")
        add("")
        add("| target | 担い手 | task | 事後条件 |")
        add("|---|---|---|---|")
        for r in nonrole:
            add("| " + r.target + " | **" + r.by + "** | `" + (r.task or "?") + "` | "
                + "／".join(r.post) + " |")
        add("")
    add("---")
    add("")

    for i, ms in enumerate(roles, 1):
        add("# " + str(i) + ". " + ms[0].role_name)
        add("")
        for m in ms:
            if len(ms) > 1:
                add("## rule: `" + m.target + "`")
                add("")
            add("| 欄 | 内容 |")
            add("|---|---|")
            add("| **担当 rule** | `" + m.target + " : " + ", ".join(m.deps) + "` |")
            add("| **deps** | "
                + "、".join(d + "（" + dep_kind(d) + "）" for d in m.deps) + " |")
            add("| **実行可能条件** | " + m.ready_rule + " |")
            add("| **検出条件** | " + m.detect_rule + " |")
            add("| **検査対象** | " + (", ".join(m.checks) or "—") + " |")
            add("| **書き込んでよい成果物** | " + (", ".join(m.writes) or m.target)
                + "（＋ 作業空間は自由。規定の対象外）" + " |")
            add("| **承認ゲート** | " + (m.gate or "無い") + " |")
            add("| **task** | `" + (m.task or "?") + "` |")
            add("")
            if m.blocks:
                add("**deps に無いもの（＝遮断）: " + ", ".join(m.blocks) + "**")
                add("")
            if m.out:
                add("**OUT の内訳:**")
                add("")
                for o in m.out:
                    add("- " + o)
                add("")
            if m.post:
                add("**事後条件:**")
                add("")
                for n, c in enumerate(m.post, 1):
                    add(str(n) + ". " + c)
                add("")
            else:
                add("**事後条件: ⚠ 未宣言**")
                add("")
        skills = sorted({s for m in ms if m.task in tasks for s in tasks[m.task]})
        add("**必要 skill**（task から導出）: "
            + (", ".join(skills) if skills else "⚠ 導出不能"))
        add("")
        mine = {m.node for m in ms}
        seps = []
        for x, y, kind, why in edges:
            bx, by_ = base_name(x), base_name(y)
            if (bx in mine) != (by_ in mine):
                seps.append((by_ if bx in mine else bx, kind, why))
        if seps:
            add("**分離（同じ担い手が持てない相手）:**")
            add("")
            add("| 相手 | 規則 | 根拠 |")
            add("|---|---|---|")
            for other, kind, why in seps:
                add("| " + other + " | `" + kind + "` | " + why + " |")
            add("")
        add("---")
        add("")

    add("## 全体像")
    add("")
    add("```makefile")
    for r in origins:
        add(r.target + " :")
    add("")
    for r in rules:
        if r.is_origin:
            continue
        owner = r.role_name if r.is_role else "[" + r.by + "]"
        add((r.target + " : " + ", ".join(r.deps)).ljust(56) + "# " + owner)
    add("```")
    add("")
    add("**矢印ではなく依存である。順序ではない**（P-20）。入力が揃ったものは同時に走れる。")
    add("")
    add("## 抜け漏れ検査")
    add("")
    if problems:
        for pr in problems:
            add("- ❌ " + pr)
    else:
        add("- ⭕ 抜けなし（全 target に担い手が 1 つ）")
    add("")
    return NL.join(L)


AGENT_TOOLS = {
    "read": "Read, Grep, Glob",
    "write": "Read, Grep, Glob, Write, Edit",
    "exec": "Read, Grep, Glob, Write, Edit, Bash",
}


def emit_agents(out_dir: Path, roles, tasks) -> list[Path]:
    """生成された役割定義を、そのまま Claude Code のサブエージェント定義にする。

    ⚠ 姿勢を書かない（P-3 改訂）。deps / 遮断 / 事後条件 / task だけを渡す。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for ms in roles:
        name = ms[0].role_name
        needs_exec = any("実装物" in m.node or "報告書" in m.node for m in ms)
        tools = AGENT_TOOLS["exec"] if needs_exec else AGENT_TOOLS["write"]
        skills = sorted({s for m in ms if m.task in tasks for s in tasks[m.task]})

        L = ["---",
             "name: " + name,
             "description: " + "／".join(m.target for m in ms) + " を作る。"
             + "生成元 " + out_dir.name,
             "tools: " + tools,
             "model: inherit",
             "---",
             "",
             "**この定義は自動生成である。姿勢は書かれていない（P-3 改訂）。**",
             "**deps に無いものは読んではならない。読んだ時点で定義違反である。**",
             ""]
        for m in ms:
            L += ["## 担当: `" + m.target + "`", "",
                  "| 欄 | 内容 |", "|---|---|",
                  "| **作るもの** | `" + m.target + "` |",
                  "| **読んでよいもの（deps）** | "
                  + "、".join(d + "（" + dep_kind(d) + "）" for d in m.deps) + " |",
                  "| **実行可能条件** | " + m.ready_rule + " |",
                  "| **検出条件** | " + m.detect_rule + " |",
                  "| **読んではならないもの** | "
                  + (", ".join(m.blocks) if m.blocks else "（deps 以外すべて）") + " |",
                  "| **書き込んでよい成果物** | " + (", ".join(m.writes) or m.target)
                  + "。**作業空間は自由に使ってよい**（規定の対象外） |",
                  "| **検査対象** | " + (", ".join(m.checks) or "—") + " |",
                  ""]
            if m.out:
                L += ["**OUT の内訳:**", ""] + ["- " + o for o in m.out] + [""]
            if m.post:
                L += ["**事後条件（これを満たさなければ完了ではない）:**", ""]
                L += [str(i) + ". " + c for i, c in enumerate(m.post, 1)]
                L += [""]
        L += ["## 共通の規則", "",
              "- **起動の 2 条件（P-53）**: **実行可能条件**（必須 dep がすべて存在する）を"
              "先に判定し、満たしていなければ**走らない**。"
              "そのうえで**検出条件**（deps のどれかが自分の target より新しい）で起動する。"
              "**片方だけでは起動条件にならない**",
              "- **dep の 3 種（P-53）**: **必須** ＝ 無ければ走れない。"
              "**前版** `_v(k-1)` ＝ 初回は必ず無い。**空として読み、走る**。"
              "**任意** `?` ＝ 無ければ**空として読み、走る**。"
              "⚠ **空を空のまま扱うこと。埋めてはならない**（P-23）。"
              "**空だった dep は完了報告に列挙する**",
              "- **決定権限（P-23）**: deps を満たす OUT の空間の内側では自由。"
              "**勝手にドロップしない／要求にないことを追加しない。**"
              "範囲内であることを示せないものは範囲外として扱い、**上げる**",
              "- **OUT の形（P-4）**: 成果物 ＋ **その理由**（入力に無かった知識・判断の由来）"
              " ＋ **残留リスク**（何が起こりうるか ＋ 何を確かめていないか）",
              "- **作業空間**は自由に使ってよい。**規定しているのは成果物への書き込みだけ**である"
              "（作業空間は継ぎ目を跨がないので、誰の判断も汚染せず、誰の成果物も壊さない）",
              ""]
        if skills:
            L += ["## 要求される skill", ""] + ["- " + s for s in skills] + [""]
        L += ["## 完了時の報告", "",
              "1. 作った成果物のパス",
              "2. **事後条件を 1 つずつ、満たしたかどうか**",
              "3. **deps 以外を読んでいないこと**（読んだファイルを列挙する）",
              "4. **空だった dep**（前版・任意で存在しなかったもの）を列挙する。"
              "**埋めていないことを示す**",
              "5. **deps に無かった知識で決めた箇所**（P-4 の「入力に無かった知識・判断の由来」）。"
              "**遮断はファイルにしか掛かっていない。**"
              "自分が持ち込んだ流儀・慣習・方法論は、読んだファイルには現れないので、"
              "**申告しなければ誰にも見えない**",
              "6. 範囲外と判断して上げた項目（あれば）", ""]

        f = out_dir / (name + ".md")
        f.write_text(NL.join(L), encoding="utf-8")
        written.append(f)
    return written


def emit_briefs(out_dir: Path, roles, tasks) -> list[Path]:
    """役割定義に **skill の本文を装着して** 1 ファイルにする。

    `--emit-agents` は skill を**名前でしか**渡していない。
    **名前だけ渡しても、担い手はその skill を持っていない。**
    ここが「装着」の段である（skill-definition.md: skill は装着の単位）。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    skill_dir = Path(__file__).resolve().parent.parent / "skills"
    written: list[Path] = []
    for ms in roles:
        name = ms[0].role_name
        agent_files = emit_agents(out_dir, [ms], tasks)
        body = agent_files[0].read_text(encoding="utf-8")

        # ⚠ skill は role ではなく **task** に付く。役割が複数 rule を持つとき、
        #   混ぜて渡すと「いま要らない skill」が混ざる（試走で実測・G-49）
        seen_s: set[str] = set()
        total = sum(len(set(tasks.get(m.task or "", []))) for m in ms)
        parts = [body, "", "---", "",
                 "# 装着された skill（" + str(total) + " 件）", "",
                 "**skill は rule ごとに付く。** いま担当していない rule の skill は、"
                 "**いま使う場面が無いのが正常である。**",
                 "**⚠ `draft` は仮説である。当てて、効かなければそう報告してよい。**", ""]
        for m in ms:
            names = [s for s in tasks.get(m.task or "", [])]
            parts += ["## rule `" + m.target + "`（task `" + (m.task or "?")
                      + "`）に付く skill: " + (", ".join(names) or "—"), ""]
            for s in names:
                f = skill_dir / (s + ".md")
                if not f.exists():
                    parts += ["### ⚠ `" + s + "` —— 本体が無い", ""]
                    continue
                if s in seen_s:
                    parts += ["### `" + s + "` —— 上に既出（同じ内容）", ""]
                    continue
                seen_s.add(s)
                parts += ["---", "", f.read_text(encoding="utf-8").strip(), ""]

        p = out_dir / (name + ".md")
        p.write_text(NL.join(parts), encoding="utf-8")
        written.append(p)
    return written


# ---------------------------------------------------------------- 実行

def run(mk_path: Path, tasks_path: Path, emit: Path | None = None,
        agents_dir: Path | None = None, by_capability: bool = False,
        briefs_dir: Path | None = None) -> int:
    rules = parse_mk(mk_path)
    tasks = parse_tasks(tasks_path)
    origins = [r for r in rules if r.is_origin]
    produced = [r for r in rules if not r.is_origin]
    work = [r for r in produced if r.is_role]
    nonrole = [r for r in produced if not r.is_role]

    print("# 導出結果 — " + mk_path.name)
    print("")
    print("- 起点 " + str(len(origins)) + "　rule " + str(len(produced))
          + "（役割対象 " + str(len(work)) + " / 機械・人間 " + str(len(nonrole)) + "）"
          + "　タスクライブラリ " + str(len(tasks)) + " 件")
    print("")

    problems: list[str] = []
    known = {r.node for r in rules}
    for r in produced:
        for d in r.dep_nodes:
            if d not in known:
                problems.append("[未定義] `" + d + "` が " + r.target
                                + " の deps に居るが target でも起点でもない")
        if r.task is None:
            problems.append("[task 欠落] " + r.target)
        elif tasks and r.task not in tasks:
            problems.append("[library 欠落] task `" + r.task + "`（" + r.target + "）")
        if not r.post:
            problems.append("[事後条件 未宣言] " + r.target)
        for b in r.blocks:
            if base_name(b) not in known:
                problems.append("[遮断が未定義] " + r.target + " の遮断 `" + b
                                + "` は target でも起点でもない。**線を一本も生まない**")
        for c in r.checks:
            if base_name(c) not in known:
                problems.append("[検査対象が未定義] " + r.target + " の検査対象 `" + c + "`")
        # P-53: 作る担い手が居るものを「任意」にすると、待たずに走る
        #
        # ⚠ `by: human` は除外する（G-53 の是正で緩めた。理由を残す）:
        #   この検査が防ぐのは「入力が揃う前に走り出す競合」である。
        #   **A は待つ主体ではなく決める主体である**（P-12: A は委譲不能）。
        #   H1 で `要求` を差し戻すとき、A が `受入検査報告書` を待つことはない。
        #   「どのゲートでも差し戻せる」を書くには、全 dep を任意にするしかない。
        #   **機械 rule には競合の懸念が残るので、除外は human に限る。**
        if r.by == "human":
            continue
        for d in r.soft_deps:
            if dep_kind(d) != "任意":
                continue
            producer = next((p for p in produced if p.node == base_name(d)), None)
            if producer is not None:
                problems.append("[任意の誤用] " + r.target + " の `" + d
                                + "` は " + producer.target
                                + " が作る。**任意にすると待たずに走る**")
    seen: dict[str, str] = {}
    for r in produced:
        if r.node in seen:
            problems.append("[単一書き手違反] `" + r.node + "` を " + seen[r.node]
                            + " と " + r.target + " が作る")
        seen[r.node] = r.target
    problems.extend("[LP 違反] " + v for v in check_lp(produced))

    # 同じ役割名を、分離線を跨いで付けてはならない（名前は導出できないので人が間違える）
    named: dict[str, list[Rule]] = {}
    for r in work:
        named.setdefault(r.role_name, []).append(r)
    sep = {frozenset((a, b)) for a, b, _, _ in derive_edges(work)}
    for name, ms in named.items():
        for x, y in combinations(ms, 2):
            if frozenset((x.target, y.target)) in sep:
                problems.append("[役割名の衝突] `" + name + "` が " + x.target
                                + " と " + y.target
                                + " の両方に付いているが、**両者には分離線がある**"
                                + "（同じ担い手にできない）")

    cycles = find_cycles(produced)
    resolved = [c for c, ok in cycles if ok]
    unresolved = [c for c, ok in cycles if not ok]
    for c in unresolved:
        problems.append("[循環・未解決] " + " → ".join(c) + "　版参照が無い（P-21 で解けない）")

    edges, groups, roles = derive_role_groups(work, tasks, by_capability)
    print("## 分離線")
    print("")
    for a, b, kind, why in edges:
        print("- **" + a + " ↮ " + b + "**　`" + kind + "`　— " + why)
    print("")

    print("## 安全軸だけの最小分割: **" + str(len(groups)) + " 群**")
    print("")
    for c, ms in sorted(groups.items()):
        print("- 群" + str(c) + ": " + ", ".join(m.target for m in ms))
    print("")

    old_roles = split_by_checking(groups)
    axis = "技能領域" if by_capability else "task の skill"
    print("## 性能軸（" + axis + "の重なり）で割った後: **" + str(len(roles)) + " 役**")
    if len(old_roles) != len(roles):
        print("")
        print("  （旧・検査対象の有無で割った場合: " + str(len(old_roles)) + " 役）")
    print("")
    for i, ms in enumerate(roles, 1):
        print("- 役割" + str(i) + " **" + ms[0].role_name + "**: "
              + ", ".join(m.target for m in ms))
    print("")

    assigned = {m.node for ms in roles for m in ms}
    for r in work:
        if r.node not in assigned:
            problems.append("[担い手なし] " + r.target)

    if resolved:
        print("## 循環（版で解ける・P-21）")
        print("")
        for c in resolved:
            print("- " + " → ".join(c))
        print("")

    print("## 抜け漏れ検査")
    print("")
    if problems:
        for p in problems:
            print("- ❌ " + p)
    else:
        print("- ⭕ 抜けなし")
    print("")
    print("**target " + str(len(work)) + " / 担い手 " + str(len(assigned))
          + "　問題 " + str(len(problems)) + " 件**")

    if emit:
        doc = emit_roles(mk_path, tasks_path, rules, tasks, roles, edges,
                         nonrole, origins, problems)
        emit.write_text(doc, encoding="utf-8")
        print("")
        print("→ 生成: " + str(emit))
    if agents_dir:
        files = emit_agents(agents_dir, roles, tasks)
        print("")
        print("→ エージェント定義 " + str(len(files)) + " 件: " + str(agents_dir))
    if briefs_dir:
        bfiles = emit_briefs(briefs_dir, roles, tasks)
        print("")
        print("→ 装着済みブリーフ " + str(len(bfiles)) + " 件: " + str(briefs_dir))
    return 1 if problems else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    mk = Path(args[0]) if args else Path("models/waterfall-core.mk")
    tk = Path(args[1]) if len(args) > 1 else mk.with_suffix(".tasks")
    emit_path = None
    for f in flags:
        if f.startswith("--emit-roles"):
            emit_path = Path(f.split("=", 1)[1]) if "=" in f else Path("docs/roles-coding.md")
    agents_dir = None
    for f in flags:
        if f.startswith("--emit-agents"):
            agents_dir = Path(f.split("=", 1)[1]) if "=" in f else Path(".claude/agents/generated")
    briefs = None
    for f in flags:
        if f.startswith("--emit-briefs="):
            briefs = Path(f.split("=", 1)[1])
    sys.exit(run(mk, tk, emit_path, agents_dir, "--by-capability" in flags, briefs))

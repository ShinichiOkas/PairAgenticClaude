#!/usr/bin/env python
"""
成果物定義（`.mk`）＋タスクライブラリ（`.tasks`）＋ skill カタログ（`skills/`）から、
**Claude Code のマルチエージェント書式**を書き出す。

    python tools/emit_claude.py models/waterfall-core.mk
    python tools/emit_claude.py models/*.mk --dest=global
    python tools/emit_claude.py models/devops.mk --dry-run

出すもの（3 種）:

    <dest>/agents/<model>-<task>.md    役割定義   → サブエージェント定義
    <dest>/skills/<skill>/SKILL.md     skill      → スキル
    <dest>/workflows/<model>.js        `.mk` の DAG → ワークフロー台本

`<dest>` は既定でプロジェクトの `.claude/`。`--dest=global` で `~/.claude/`。

設計方針は `derive_roles.py` と同じ:

  - **判断を一切入れない。宣言だけから導く**
  - **導けないものは「導けない」と報告する（黙って埋めない）**

したがって `effort` / `permissionMode` / `maxTurns` / `memory` は**書かない**。
要るなら `.mk` に `#   agent.effort : high` と宣言する（素通しされる）。

⚠ `isolation: worktree` は既定で付けない。
   **成果物は継ぎ目を跨いで流れる**（仕様 → 実装物 → 実行可能物 → 受入検査報告書）。
   worktree に隔離すると下流が上流の成果物を読めない。付けるなら
   `#   agent.isolation : worktree` と rule ごとに宣言する。

命名（師匠の裁定 2026-09-05）:

  - エージェント名は **`<model>-<task>`**。`name` は小文字とハイフンのみという書式に従う。
    task 名は `.tasks` に宣言済みなので**導出できる**（役割名の日本語は導出できない）。
    `<model>` を冠するのは、`build` が 4 モデルに居て**中身が違う**から（衝突する）
  - skill 名は **ASCII に導出できない**。宣言が無いので日本語のまま出す。
    ASCII にしたければ `skills/slugs.map` に人が書く（`日本語名 : ascii-slug`）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_roles import (  # noqa: E402
    Rule, base_name, dep_kind, derive_role_groups, parse_mk, parse_tasks,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills"
SLUG_MAP = SKILL_DIR / "slugs.map"
NL = "\n"

# `tools` は導出できない。宣言（`#   tools : exec`）が無ければ write を当てて**報告する**
TOOLSETS = {
    "read": "Read, Grep, Glob",
    "write": "Read, Grep, Glob, Write, Edit",
    "exec": "Read, Grep, Glob, Write, Edit, Bash",
}
DEFAULT_TOOLS = "write"
FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.S)


# ---------------------------------------------------------------- 素材

def slug(text: str) -> str:
    """ASCII の宣言（task 名・モデル名）から `name` を作る。日本語は落ちる（空になる）"""
    return re.sub(r"[^0-9a-z]+", "-", text.strip().lower()).strip("-")


def yaml_str(text: str) -> str:
    """`: ` を含みうる値を YAML の二重引用スカラにする（JSON 文字列はそのまま通る）"""
    return json.dumps(text, ensure_ascii=False)


def load_slug_map() -> dict[str, str]:
    """skill 名 → ASCII slug。**導出できないので人が書く**（`role:` と同じ位置づけ）"""
    out: dict[str, str] = {}
    if not SLUG_MAP.exists():
        return out
    for raw in SLUG_MAP.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        if name.strip() and value.strip():
            out[name.strip()] = value.strip()
    return out


def first_claim(body: str) -> str:
    """skill 本文の**主張 1 行**。引用（`>`）と見出しは主張ではない"""
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith((">", "#", "-", "|", "`")):
            continue
        text = re.sub(r"[*`⚠✅🆕]", "", line).strip()
        if text:
            return text
    return ""


def load_skill(name: str) -> dict | None:
    path = SKILL_DIR / (name + ".md")
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = text
    m = FRONTMATTER.match(text)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        body = m.group(2)
    body = body.strip()
    return {"name": name, "meta": meta, "body": body, "claim": first_claim(body)}


def skill_description(sk: dict) -> str:
    """スキルの description —— **いつ効くか**を書く欄。`applies_when` が宣言されていれば載せる"""
    meta = sk["meta"]
    parts = [sk["claim"] or (sk["name"] + " の技法")]
    tail = []
    if meta.get("capability"):
        tail.append("技能領域: " + meta["capability"])
    if meta.get("type"):
        tail.append("型: " + meta["type"])
    if meta.get("maturity"):
        tail.append("maturity: " + meta["maturity"])
    applies = re.sub(r"[*]", "", meta.get("applies_when", "")).strip()
    if applies and applies != "未測定":
        tail.append("効く場面: " + applies)
    if tail:
        parts.append("（" + " ／ ".join(tail) + "）")
    return "".join(parts).replace("\n", " ")


# ---------------------------------------------------------------- 導出

class Emit:
    """1 モデル分の書き出し。**判断はここに置かない。導けなかったものは notes に積む**"""

    def __init__(self, mk: Path, tasks_path: Path, by_capability: bool = False) -> None:
        self.mk = mk
        self.tasks_path = tasks_path
        self.model = slug(mk.stem)
        self.rules = parse_mk(mk)
        self.tasks = parse_tasks(tasks_path)
        self.origins = [r for r in self.rules if r.is_origin]
        self.produced = [r for r in self.rules if not r.is_origin]
        self.work = [r for r in self.produced if r.is_role]
        self.machines = [r for r in self.produced if r.by == "machine"]
        self.humans = [r for r in self.produced if r.by == "human"]
        _, _, self.roles = derive_role_groups(self.work, self.tasks, by_capability)
        self.notes: list[str] = []
        self.slugs = load_slug_map()
        self.names: dict[str, str] = {}      # node → エージェント名
        self._assign_names()

    # -- 名前

    def _unique(self, base: str, taken: set[str]) -> str:
        if base not in taken:
            return base
        for i in range(2, 100):
            cand = base + "-" + str(i)
            if cand not in taken:
                self.notes.append("[名前の衝突] `" + base + "` が重複した → `" + cand + "`")
                return cand
        raise RuntimeError("名前を割り当てられない: " + base)

    def _assign_names(self) -> None:
        taken: set[str] = set()
        for i, ms in enumerate(self.roles, 1):
            body = slug(ms[0].task or "") or ("role-" + str(i))
            if not slug(ms[0].task or ""):
                self.notes.append("[名前が導けない] 役割 `" + ms[0].role_name
                                  + "` の task が ASCII でない → `" + body + "`")
            name = self._unique(self.model + "-" + body, taken)
            taken.add(name)
            for m in ms:
                self.names[m.node] = name
        for r in self.machines:
            body = slug(r.task or "") or slug(r.node) or "machine"
            name = self._unique(self.model + "-" + body, taken)
            taken.add(name)
            self.names[r.node] = name

    # -- 欄

    def tools_of(self, rules: list[Rule]) -> str:
        """`tools:` の宣言が無ければ既定を当て、**当てたことを報告する**"""
        order = ["read", "write", "exec"]
        best = None
        for r in rules:
            declared = (r.tools or "").strip().lower()
            if declared in TOOLSETS:
                if best is None or order.index(declared) > order.index(best):
                    best = declared
            elif declared:
                self.notes.append("[tools が不明] " + r.target + " の `tools : " + declared
                                  + "` は read/write/exec のどれでもない")
            elif r.by == "machine":
                # `by: machine` は**走らせるのが仕事**である。宣言から導ける
                if best is None or order.index("exec") > order.index(best):
                    best = "exec"
            else:
                self.notes.append("[tools 未宣言] " + r.target
                                  + " → 既定 `" + DEFAULT_TOOLS + "` を当てた"
                                  + "（実行が要るなら .mk に `#   tools : exec`）")
        return TOOLSETS[best or DEFAULT_TOOLS]

    def skills_of(self, rules: list[Rule]) -> list[str]:
        return sorted({s for r in rules if r.task in self.tasks
                       for s in self.tasks[r.task] if not s.startswith("（")})

    def path_of(self, node: str) -> str:
        """成果物の置き場所。**`.mk` に無いので導けない。** 宣言があれば使う"""
        for r in self.rules:
            if r.node == node and r.agent.get("path"):
                return r.agent["path"]
        return node

    def rule_of(self, node: str) -> Rule | None:
        return next((r for r in self.rules if r.node == node), None)

    # -- 依存の段

    def levels(self) -> list[list[str]]:
        """`by: human` を除いた初回パスの DAG を段に割る。

        必須 dep だけが辺になる（P-53）:
          前版 `_v(n-1)` は**初回は必ず存在しない**ので待たない
          任意 `?` は**空として読んで走る**ので待たない
        """
        nodes = [r for r in self.produced if r.by != "human"]
        index = {r.node: r for r in nodes}
        waits: dict[str, list[str]] = {}
        for r in nodes:
            waits[r.node] = [base_name(d) for d in r.required_deps
                             if base_name(d) in index]
        out: list[list[str]] = []
        done: set[str] = set()
        remaining = set(index)
        while remaining:
            ready = sorted(n for n in remaining if set(waits[n]) <= done)
            if not ready:
                self.notes.append("[段に割れない] 必須 dep が循環している: "
                                  + " / ".join(sorted(remaining)))
                out.append(sorted(remaining))
                break
            out.append(ready)
            done |= set(ready)
            remaining -= set(ready)
        return out

    # -- エージェント定義

    def agent_files(self) -> dict[str, str]:
        files: dict[str, str] = {}
        groups: list[list[Rule]] = [list(ms) for ms in self.roles] \
            + [[r] for r in self.machines]
        for ms in groups:
            name = self.names[ms[0].node]
            files[name + ".md"] = self.agent_body(name, ms)
        return files

    def agent_body(self, name: str, ms: list[Rule]) -> str:
        first = ms[0]
        machine = first.by == "machine"
        role = "機械（" + first.node + "）" if machine else first.role_name
        skills = self.skills_of(ms)
        targets = "／".join(m.target for m in ms)
        deps = sorted({base_name(d) for m in ms for d in m.deps})
        blocks = sorted({b for m in ms for b in m.blocks})
        desc = (role + " — " + targets + " を作る（" + self.model + "）。"
                + "deps: " + ("、".join(deps) or "無し") + "。"
                + "読んではならない: " + ("、".join(blocks) or "deps 以外すべて"))

        fm = ["---", "name: " + name, "description: " + yaml_str(desc),
              "tools: " + self.tools_of(ms), "model: inherit"]
        if skills:
            fm.append("skills: [" + ", ".join(yaml_str(s) for s in skills) + "]")
        # 宣言された欄だけを素通しする（effort / permissionMode / maxTurns / memory / isolation）
        for m in ms:
            for k, v in sorted(m.agent.items()):
                if k == "path":
                    continue
                fm.append(k + ": " + v)
        fm.append("---")

        L = fm + ["", "<!-- 自動生成。手で編集しない。正は " + self.mk.as_posix()
                  + " ／ 生成: python tools/emit_claude.py " + self.mk.as_posix()
                  + " -->", "",
                  "**この定義は自動生成である。姿勢は書かれていない（P-3 改訂）。**",
                  "**deps に無いものは読んではならない。読んだ時点で定義違反である。**", ""]
        if machine:
            L += ["> ⚠ **この rule は `by: machine` である**（P-11: 機械は役割ではない）。"
                  "**決定論的に出せ。** 判断が要ると思ったら、それは範囲外として上げる。", ""]

        for m in ms:
            L += ["## 担当: `" + m.target + "`", "",
                  "| 欄 | 内容 |", "|---|---|",
                  "| **作るもの** | `" + m.target + "`（置き場所: `"
                  + self.path_of(m.node) + "`） |",
                  "| **task** | `" + (m.task or "—") + "` |",
                  "| **読んでよいもの（deps）** | "
                  + ("、".join(d + "（" + dep_kind(d) + "）" for d in m.deps)
                     or "（無し。起点から始まる）") + " |",
                  "| **実行可能条件** | " + m.ready_rule + " |",
                  "| **検出条件** | " + m.detect_rule + " |",
                  "| **読んではならないもの** | "
                  + ("、".join(m.blocks) if m.blocks else "（deps 以外すべて）") + " |",
                  "| **書き込んでよい成果物** | " + ("、".join(m.writes) or m.target)
                  + "。**作業空間は自由に使ってよい**（規定の対象外） |",
                  "| **検査対象** | " + ("、".join(m.checks) or "—") + " |",
                  "| **人間ゲート** | " + (m.gate or "—") + " |", ""]
            if m.out:
                L += ["**OUT の内訳:**", ""] + ["- " + o for o in m.out] + [""]
            if m.post:
                L += ["**事後条件（これを満たさなければ完了ではない）:**", ""]
                L += [str(i) + ". " + c for i, c in enumerate(m.post, 1)] + [""]

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
              "（作業空間は継ぎ目を跨がないので、誰の判断も汚染せず、誰の成果物も壊さない）", ""]

        if skills:
            L += ["## 装着された skill（" + str(len(skills)) + " 件）", "",
                  "**skill は役割ではなく task に付く**（G-49）。"
                  "本文は同名のスキル（`skills/<名前>/SKILL.md`）にある —— "
                  "frontmatter の `skills:` で先に読み込まれる。"
                  "**⚠ `draft` は仮説である。当てて、効かなければそう報告してよい。**", ""]
            for s in skills:
                sk = load_skill(s)
                if sk is None:
                    L += ["- ⚠ **" + s + "** —— 本体が無い（`skills/" + s
                          + ".md` が存在しない）"]
                    continue
                mat = sk["meta"].get("maturity", "?")
                L += ["- **" + s + "**（" + mat + "）—— " + (sk["claim"] or "（主張が空）")]
            L += [""]

        L += ["## 完了時の報告", "",
              "**構造化して返す**（ワークフロー台本が機械で検める）。"
              "自由記述で返す場合も同じ 6 項目を節に立てる。", "",
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
        return NL.join(L)

    # -- skill

    def skill_files(self, names: list[str]) -> dict[str, str]:
        files: dict[str, str] = {}
        for s in names:
            sk = load_skill(s)
            if sk is None:
                self.notes.append("[skill の本体が無い] `" + s
                                  + "` が `.tasks` に居るが `skills/" + s + ".md` が無い")
                continue
            key = self.slugs.get(s, s)
            meta = sk["meta"]
            L = ["---", "name: " + key,
                 "description: " + yaml_str(skill_description(sk)), "---", "",
                 "<!-- 自動生成。手で編集しない。正は skills/" + s + ".md -->", ""]
            if key != s:
                L += ["**原名: " + s + "**", ""]
            rows = [(k, meta[k]) for k in
                    ("capability", "type", "layer", "applies_when", "maturity",
                     "observations", "requires_deps", "provenance") if k in meta]
            if rows:
                L += ["| 欄 | 値 |", "|---|---|"]
                L += ["| `" + k + "` | " + v.replace("|", "\\|") + " |" for k, v in rows]
                L += [""]
            if meta.get("maturity") == "draft":
                L += ["> ⚠ **draft —— これは仮説である。**"
                      "当てて、効かなければ「効かなかった」と報告してよい。", ""]
            L += [sk["body"], ""]
            files[key + "/SKILL.md"] = NL.join(L)
        return files

    # -- ワークフロー台本

    def workflow(self) -> str:
        levels = self.levels()
        nodes: dict[str, dict] = {}
        for r in self.produced:
            if r.by == "human":
                continue
            nodes[r.node] = {
                "target": r.target,
                "role": r.role_name if r.is_role else "機械",
                "task": r.task or "",
                "by": r.by,
                "agentType": self.names[r.node],
                "gate": r.gate or "",
                "path": self.path_of(r.node),
                "deps": [{"name": d, "node": base_name(d), "kind": dep_kind(d),
                          "path": self.path_of(base_name(d))} for d in r.deps],
                "blocks": list(r.blocks),
                "checks": list(r.checks),
                "writes": list(r.writes) or [r.target],
                "post": list(r.post),
                "out": list(r.out),
                "skills": self.skills_of([r]),
            }
        origins = [{"name": r.target, "path": self.path_of(r.node)} for r in self.origins]
        humans = [{"target": r.target, "gate": r.gate or "",
                   "path": self.path_of(r.node),
                   "deps": [d for d in r.deps], "post": list(r.post),
                   "out": list(r.out)} for r in self.humans]
        gates = sorted({r.gate for r in self.produced if r.gate})

        phases = [{"title": "第" + str(i + 1) + "段",
                   "detail": " / ".join(nodes[n]["target"] for n in lv)}
                  for i, lv in enumerate(levels)]
        desc = (self.model + " の成果物 DAG を 1 巡させる（役 "
                + str(len(self.roles)) + " ／ 機械 " + str(len(self.machines))
                + " ／ 人間ゲート " + str(len(gates)) + "）")
        when = ("成果物定義 " + self.mk.name + " に沿って、要求から受入検査まで"
                "1 パス通したいとき。args.root に作業根を渡す")

        def dump(obj) -> str:
            return json.dumps(obj, ensure_ascii=False, indent=2)

        parts = [
            "export const meta = {",
            "  name: " + json.dumps(self.model) + ",",
            "  description: " + json.dumps(desc, ensure_ascii=False) + ",",
            "  whenToUse: " + json.dumps(when, ensure_ascii=False) + ",",
            "  phases: [",
        ]
        for p in phases:
            parts.append("    { title: " + json.dumps(p["title"], ensure_ascii=False)
                         + ", detail: " + json.dumps(p["detail"], ensure_ascii=False) + " },")
        parts += ["  ],", "}", "",
                  "// 自動生成。手で編集しない。正は " + self.mk.as_posix(),
                  "// 生成: python tools/emit_claude.py " + self.mk.as_posix(),
                  "//",
                  "// ⚠ 段ごとに parallel（バリア）を張っている。**ここでは正しい** ——",
                  "//    次の段の担い手は、前の段が**ファイルとして置いた成果物**を読む。",
                  "//    台本にファイルシステムは無いので、置かれたことは前段の完了でしか分からない。",
                  "//",
                  "// ⚠ `by: human` の rule は走らせない（P-12: A は委譲不能）。",
                  "//    最後に「人間に渡すもの」として列挙して台本を終える。",
                  "",
                  "const MODEL = " + json.dumps(self.model) + "",
                  "const NODES = " + dump(nodes),
                  "const LEVELS = " + dump(levels),
                  "const ORIGINS = " + dump(origins),
                  "const HUMAN = " + dump(humans),
                  "",
                  "// 完了報告（ブリーフの 6 項目）。schema を付けた呼び出しは検証済みで返る",
                  "const REPORT = {",
                  "  type: 'object',",
                  "  required: ['target', 'path', 'postconditions', 'readFiles',"
                  " 'emptyDeps', 'broughtKnowledge', 'escalated'],",
                  "  properties: {",
                  "    target: { type: 'string' },",
                  "    path: { type: 'string' },",
                  "    postconditions: { type: 'array', items: { type: 'object',",
                  "      required: ['condition', 'met'],",
                  "      properties: { condition: { type: 'string' },"
                  " met: { type: 'boolean' }, note: { type: 'string' } } } },",
                  "    readFiles: { type: 'array', items: { type: 'string' } },",
                  "    emptyDeps: { type: 'array', items: { type: 'string' } },",
                  "    broughtKnowledge: { type: 'array', items: { type: 'string' } },",
                  "    escalated: { type: 'array', items: { type: 'string' } },",
                  "  },",
                  "}",
                  "",
                  "const root = (args && args.root) || 'workspace'",
                  "const stopAtGate = !!(args && args.stopAtGate)",
                  "// args.force で検出条件を無視して全部走らせる（初回や、状態を疑うとき）",
                  "const force = !!(args && args.force)",
                  "",
                  "// 遵守の申告を違反として拾わないための否定語（check_report.py の DENIAL と同じ）",
                  "const DENIAL = /読ま|読んでいない|読んでない|遮断|禁止"
                  "|見ていない|参照していない|開いていない|触れていない/",
                  "const BSLASH = String.fromCharCode(92)",
                  "",
                  "function at(p) { return root + '/' + p }",
                  "const chr10 = String.fromCharCode(10)",
                  "function norm0(x)"
                  " { return String(x).split(BSLASH).join('/').toLowerCase() }",
                  "",
                  "function briefOf(s) {",
                  "  const L = []",
                  "  L.push('作業根は ' + root + ' である。担当は ' + s.target + ' ただ一つ。')",
                  "  L.push('')",
                  "  L.push('## 読んでよいもの（deps）—— これ以外を読んではならない')",
                  "  if (!s.deps.length) L.push('- （無し。起点から始まる）')",
                  "  s.deps.forEach(function (d) {",
                  "    L.push('- ' + d.name + '（' + d.kind + '）: ' + at(d.path))",
                  "  })",
                  "  if (s.blocks.length) {",
                  "    L.push('')",
                  "    L.push('## 読んではならないもの（遮断）')",
                  "    s.blocks.forEach(function (b) { L.push('- ' + b) })",
                  "  }",
                  "  L.push('')",
                  "  L.push('## 書くもの')",
                  "  L.push('- ' + s.target + ' を ' + at(s.path) + ' に置く"
                  "（単一ファイルなら .md を付けてよい。複数ならディレクトリにする）')",
                  "  L.push('- 作業空間は自由に使ってよい。他人の成果物には書き込まない')",
                  "  if (s.post.length) {",
                  "    L.push('')",
                  "    L.push('## 事後条件（これを満たさなければ完了ではない）')",
                  "    s.post.forEach(function (c, i) { L.push((i + 1) + '. ' + c) })",
                  "  }",
                  "  L.push('')",
                  "  L.push('## 返す形')",
                  "  L.push('StructuredOutput で返す。postconditions は"
                  "**上の事後条件を 1 つずつ**、原文のまま condition に入れて met を付ける。')",
                  "  L.push('readFiles には**実際に読んだファイルを全部**挙げる"
                  "（遮断が効いていたかを機械が検める）。')",
                  "  L.push('emptyDeps には**空だった dep**（前版・任意で存在しなかったもの）を挙げる。"
                  "埋めていないことを示す。')",
                  "  L.push('broughtKnowledge には**deps に無かった知識で決めた箇所**を挙げる。"
                  "遮断はファイルにしか掛かっていない —— 申告しなければ誰にも見えない。')",
                  "  return L.join('\\n')",
                  "}",
                  "",
                  "log('起点（外から与えられる。誰も作らない）: ' + (ORIGINS.length",
                  "  ? ORIGINS.map(function (o) { return o.name + ' → ' + at(o.path) }).join(' / ')",
                  "  : 'なし'))",
                  "",
                  "// ── 起動の 2 条件（P-53）─────────────────────────────",
                  "//",
                  "// ⚠ **台本にファイルシステムは無い。** 存在と更新時刻は測れないので、",
                  "//    それだけを見る担い手を 1 体立て、**判定は台本側で決定的に行う。**",
                  "//    測らせるのは存在と時刻だけである。中身は読ませない（遮断を跨がないため）。",
                  "const PROBE = {",
                  "  type: 'object', required: ['files'],",
                  "  properties: { files: { type: 'array', items: { type: 'object',",
                  "    required: ['path', 'exists'],",
                  "    properties: { path: { type: 'string' }, exists: { type: 'boolean' },",
                  "      mtime: { type: 'number' } } } } },",
                  "}",
                  "",
                  "const stat = {}",
                  "if (!force) {",
                  "  // ⚠ NODES だけでは足りない。`by: human` の成果物（差し戻し指示）は",
                  "  //    NODES に居ないので、**dep のパスも観測対象に入れる。**",
                  "  //    入れないと、差し戻しても検出できない（実測前に気づいた漏れ）",
                  "  const seen0 = {}",
                  "  const paths = []",
                  "  const addPath = function (x) {",
                  "    if (x && !seen0[x]) { seen0[x] = 1; paths.push(x) }",
                  "  }",
                  "  ORIGINS.forEach(function (o) { addPath(o.path) })",
                  "  Object.keys(NODES).forEach(function (n) {",
                  "    addPath(NODES[n].path)",
                  "    NODES[n].deps.forEach(function (d) { addPath(d.path) })",
                  "  })",
                  "  phase('検出')",
                  "  const probe = await agent(",
                  "    ['次のパスについて、**存在するかどうかと最終更新時刻だけ**を調べて返す。',",
                  "     '',",
                  "     '⚠ **中身は読まない。** 存在と時刻だけを見る。',",
                  "     '⚠ ディレクトリなら、**その中で最も新しいファイルの時刻**を返す。',",
                  "     '⚠ 存在しないものは exists=false / mtime=0 とする。',",
                  "     'mtime は**エポック秒の整数**で返す。path は渡した文字列をそのまま返す。',",
                  "     '',",
                  "     paths.map(function (t) { return '- ' + at(t) }).join(chr10)].join(chr10),",
                  "    { label: '状態の観測', phase: '検出', schema: PROBE })",
                  "  ;((probe && probe.files) || []).forEach(function (f) {",
                  "    stat[norm0(f.path)] = f.exists ? (f.mtime || 0) : null",
                  "  })",
                  "}",
                  "",
                  "// パスの表記ゆれ（区切り・大小・絶対と相対）を吸収して引く",
                  "function look(p) {",
                  "  const key = norm0(at(p))",
                  "  if (key in stat) return stat[key]",
                  "  const tail = norm0(p)",
                  "  const hit = Object.keys(stat).filter(function (k)",
                  "    { return k.indexOf(tail) >= 0 })",
                  "  return hit.length ? stat[hit[0]] : null",
                  "}",
                  "const updated = {}",
                  "",
                  "// **実行可能条件を先に判定し、そのうえで検出条件で起動する。**",
                  "// **片方だけでは起動条件にならない**（P-53）",
                  "function fires(n) {",
                  "  if (force) return { run: true, why: 'args.force' }",
                  "  const s = NODES[n]",
                  "  // 自分自身を指す dep（前版）は判定に使わない",
                  "  const other = s.deps.filter(function (d) { return d.node !== n })",
                  "  const missing = other.filter(function (d)",
                  "    { return d.kind === '必須' && look(d.path) === null })",
                  "  if (missing.length) return { run: false, wait: true,",
                  "    why: '必須 dep が無い: ' + missing.map(function (d)",
                  "      { return d.name }).join('/') }",
                  "  const mine = look(s.path)",
                  "  if (mine === null) return { run: true, why: 'target がまだ無い' }",
                  "  const newer = other.filter(function (d) {",
                  "    if (updated[d.node]) return true",
                  "    const t = look(d.path)",
                  "    return t !== null && t > mine",
                  "  })",
                  "  if (newer.length) return { run: true,",
                  "    why: '新しい dep: ' + newer.map(function (d)",
                  "      { return d.name }).join('/') }",
                  "  return { run: false, why: 'deps はどれも target より新しくない' }",
                  "}",
                  "",
                  "const produced = []",
                  "const skipped = []",
                  "const unmet = []",
                  "const blocked = []",
                  "const outside = []",
                  "const openGates = []",
                  "let halted = null",
                  "",
                  "for (let i = 0; i < LEVELS.length && !halted; i++) {",
                  "  const title = '第' + (i + 1) + '段'",
                  "  const names = []",
                  "  LEVELS[i].forEach(function (n) {",
                  "    const f = fires(n)",
                  "    if (f.run) { names.push(n); return }",
                  "    skipped.push({ target: NODES[n].target, why: f.why, wait: !!f.wait })",
                  "    log('  — ' + NODES[n].target + ' は走らせない（' + f.why + '）')",
                  "  })",
                  "  if (!names.length) continue",
                  "  phase(title)",
                  "  log(title + ': ' + names.map(function (n) { return NODES[n].target })"
                  ".join(' / '))",
                  "  const reports = await parallel(names.map(function (n) {",
                  "    return function () {",
                  "      const s = NODES[n]",
                  "      return agent(briefOf(s), {",
                  "        label: s.target,",
                  "        phase: title,",
                  "        agentType: s.agentType,",
                  "        schema: REPORT,",
                  "      })",
                  "    }",
                  "  }))",
                  "  for (let k = 0; k < names.length; k++) {",
                  "    const s = NODES[names[k]]",
                  "    const rep = reports[k]",
                  "    if (!rep) {",
                  "      unmet.push({ target: s.target, condition: '(報告なし)',"
                  " note: 'エージェントが結果を返さなかった' })",
                  "      continue",
                  "    }",
                  "    produced.push({ target: s.target, path: rep.path, by: s.by })",
                  "    updated[names[k]] = true",
                  "    ;(rep.postconditions || []).forEach(function (p) {",
                  "      if (!p.met) unmet.push({ target: s.target, condition: p.condition,"
                  " note: p.note || '' })",
                  "    })",
                  "    // 遮断の機械検査 —— check_report.py の [遮断の疑い] と同じ位置づけ。",
                  "    // ⚠ **申告しなかった読み取りは、報告からは原理的に見えない**（P-13）",
                  "    //",
                  "    // 2 種を分けて見る:",
                  "    //   blocked … blocks に挙がった成果物名が、読んだ申告に現れる（ブラックリスト）",
                  "    //   outside … deps でも作業空間でもないパスを読んでいる（ホワイトリスト）",
                  "    //",
                  "    // ⚠ **否定の申告を違反として拾ってはならない。**",
                  "    //    「実装物は読んでいない」は違反ではなく**遵守の申告**である。",
                  "    //    実測（2026-09-06）: これで偽陽性が 6 件出た。",
                  "    //    check_report.py の DENIAL と同じ扱いにする（あちらは先に解いていた）。",
                  "    // ⚠ 申告のパスは `BSLASH` 区切りで来る（Windows）。"
                  "`.mk` 由来の宣言は `/` 区切りである。",
                  "    //    揃えずに比べると**すべてが deps 外に見える**（実測 2026-09-06: 偽陽性 21 件）。",
                  "    var norm = function (x) { return String(x).split(BSLASH).join('/')"
                  ".toLowerCase() }",
                  "    var allowed = s.deps.map(function (d) { return norm(d.path) })"
                  ".concat([norm(s.path), 'workspace'])",
                  "    ;(rep.readFiles || []).forEach(function (f) {",
                  "      var t = String(f)",
                  "      if (DENIAL.test(t)) return",
                  "      s.blocks.forEach(function (b) {",
                  "        if (t.indexOf(b) >= 0)"
                  " blocked.push({ target: s.target, forbidden: b, read: t })",
                  "      })",
                  "      // パスに見えないもの（散文の申告）は、ホワイトリストでは判定しない",
                  "      if (t.indexOf('/') < 0 && t.indexOf(BSLASH) < 0) return",
                  "      var nt = norm(t)",
                  "      var ok = allowed.some(function (a)"
                  " { return a && nt.indexOf(a) >= 0 })",
                  "      if (!ok) outside.push({ target: s.target, read: t })",
                  "    })",
                  "    if (s.gate) {",
                  "      openGates.push({ gate: s.gate, target: s.target, path: rep.path })",
                  "      log('⏸ 人間ゲート ' + s.gate + ': ' + s.target + ' —— A の判定が要る')",
                  "      if (stopAtGate) halted = s.gate",
                  "    }",
                  "  }",
                  "  if (halted) log('args.stopAtGate により ' + halted + ' で止めた')",
                  "}",
                  "",
                  "if (HUMAN.length) {",
                  "  log('人間に渡すもの（by: human。台本は走らせない・P-12）: '",
                  "    + HUMAN.map(function (h) { return h.target }).join(' / '))",
                  "}",
                  "if (skipped.length)",
                  "  log('走らせなかった rule ' + skipped.length + ' 件（P-53 の起動条件）')",
                  "if (unmet.length) log('未達の事後条件 ' + unmet.length + ' 件')",
                  "if (blocked.length) log('⚠ 遮断の疑い ' + blocked.length + ' 件')",
                  "if (outside.length)"
                  " log('⚠ deps 外の読み取りの疑い ' + outside.length + ' 件')",
                  "",
                  "return {",
                  "  model: MODEL,",
                  "  root: root,",
                  "  produced: produced,",
                  "  skipped: skipped,",
                  "  unmet: unmet,",
                  "  blocked: blocked,",
                  "  outside: outside,",
                  "  openGates: openGates,",
                  "  haltedAt: halted,",
                  "  human: HUMAN,",
                  "}",
                  ""]
        return NL.join(parts)


# ---------------------------------------------------------------- 書き出し

def dest_root(spec: str) -> Path:
    if spec == "project":
        return ROOT / ".claude"
    if spec == "global":
        return Path.home() / ".claude"
    return Path(spec).expanduser()


def write_all(files: dict[Path, str], dry: bool) -> tuple[int, int, int]:
    new = changed = same = 0
    for path, text in sorted(files.items()):
        old = (path.read_text(encoding="utf-8", newline=chr(10))
               if path.exists() else None)
        if old is None:
            new += 1
            mark = "＋"
        elif old != text:
            changed += 1
            mark = "±"
        else:
            same += 1
            mark = "="
        if not dry and old != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            # ⚠ 改行を LF に固定する。Windows の既定は CRLF になり、生成した `.js` に
            #   CR が混ざる。**ワークフローの承認ダイアログが制御文字として弾く**（実測）
            with open(path, "w", encoding="utf-8", newline=chr(10)) as f:
                f.write(text)
        print("  " + mark + " " + path.as_posix())
    return new, changed, same


def main() -> int:
    argv = sys.argv[1:]
    flags = [a for a in argv if a.startswith("--")]
    args = [a for a in argv if not a.startswith("--")]
    mks = [Path(a) for a in args] or [ROOT / "models" / "waterfall-core.mk"]
    dry = "--dry-run" in flags
    prune = "--prune" in flags
    by_cap = "--by-capability" in flags
    dest = dest_root(next((f.split("=", 1)[1] for f in flags
                           if f.startswith("--dest=")), "project"))

    print("# Claude Code 書式の書き出し")
    print("")
    print("- 出力先: `" + dest.as_posix() + "`" + ("　**--dry-run（書かない）**" if dry else ""))
    print("")

    files: dict[Path, str] = {}
    notes: list[str] = []
    kept_agents: set[str] = set()
    prefixes: set[str] = set()
    for mk in mks:
        tasks_path = mk.with_suffix(".tasks")
        e = Emit(mk, tasks_path, by_cap)
        prefixes.add(e.model + "-")
        agents = e.agent_files()
        skill_names = sorted({s for ms in e.roles for s in e.skills_of(ms)}
                             | {s for r in e.machines for s in e.skills_of([r])})
        skills = e.skill_files(skill_names)
        for rel, text in agents.items():
            files[dest / "agents" / rel] = text
            kept_agents.add(rel)
        for rel, text in skills.items():
            files[dest / "skills" / rel] = text
        files[dest / "workflows" / (e.model + ".js")] = e.workflow()
        notes += [mk.name + ": " + n for n in e.notes]
        print("- **" + mk.name + "** → 役 " + str(len(e.roles)) + " ／ 機械 "
              + str(len(e.machines)) + " ／ 人間 " + str(len(e.humans))
              + " ／ skill " + str(len(skills)) + " ／ 段 " + str(len(e.levels())))
    print("")

    print("## 書き出し")
    print("")
    new, changed, same = write_all(files, dry)
    print("")
    print("**新規 " + str(new) + " ／ 更新 " + str(changed) + " ／ 変化なし "
          + str(same) + "**")
    print("")

    stale = []
    adir = dest / "agents"
    if adir.exists():
        for p in sorted(adir.glob("*.md")):
            if p.name in kept_agents:
                continue
            if any(p.name.startswith(pref) for pref in prefixes):
                stale.append(p)
    if stale:
        print("## 古い生成物（同じモデルの接頭辞を持つが、今回は作られなかった）")
        print("")
        for p in stale:
            if prune and not dry:
                p.unlink()
                print("  − " + p.as_posix() + "（削除した）")
            else:
                print("  ? " + p.as_posix() + "（`--prune` で削除する）")
        print("")

    legacy = [p for p in sorted(adir.glob("*.md"))
              if adir.exists() and not re.match(r"^[a-z0-9-]+\.md$", p.name)]
    if legacy:
        print("## 書式に合わない既存ファイル（この道具の生成物ではない）")
        print("")
        for p in legacy:
            print("  ! " + p.as_posix() + " —— `name` が小文字とハイフンのみでない")
        print("")

    print("## 導けなかったもの")
    print("")
    seen: set[str] = set()
    ordered = [n for n in notes if not (n in seen or seen.add(n))]
    if ordered:
        for n in ordered:
            print("- ⚠ " + n)
    else:
        print("- ⭕ なし")
    print("")
    print("- ⚠ **skill 名は ASCII に導出できない**（宣言が無い）。日本語のまま出した。"
          "ASCII にするなら `skills/slugs.map` に人が書く（`日本語名 : ascii-slug`）")
    print("- ⚠ **`effort` / `permissionMode` / `maxTurns` / `memory` / `isolation` は書いていない。**"
          "導出できないため。要るなら `.mk` に `#   agent.<欄> : <値>` と宣言する")
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""skill カタログを検める。

`.mk` を `derive_roles.py` が検めるのと同じ位置づけ。
**カタログは人が書く正典なので、書き忘れと言い替えを機械が拾う。**

    python tools/check_skills.py
    python tools/check_skills.py --tasks=models/devops.tasks

**様式の検査（2026-09-01 追加・G-63 / G-57 / G-67）:**

- `layer:`        どの層に装着するか（メタ／ドメイン／両方）。`.tasks` の実際の使われ方と突き合わせる
- `applies_when:` いつ効くか。**未測定と書いてよい。書かないのは駄目**
- `requires_deps:` この skill が働くために dep に無ければならない成果物。`.mk` と突き合わせる

**装着の上限の検査（2026-10-28 追加）:** サブエージェントに本文が入る skill は先頭 32 件まで。
`.tasks` の 1 task と、生成済みエージェント定義の `skills:` の両方を数える
"""
from __future__ import annotations

import ast
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
CAP_FILE = ROOT / "skills" / "capabilities.cap"
SKILL_DIR = ROOT / "skills"
MACHINE = "（機械）"
# サブエージェントの frontmatter `skills:` は、先頭 32 件（重複を除く）しか本文として読み込まれない。
#   出典: https://code.claude.com/docs/en/sub-agents 「Preload skills into subagents」
#         "up to the first 32 distinct names in the list"
#   2026-10-28 に実機で確かめた: 65 件を装着した役に本文が入っていたのは辞書順の先頭 32 件だけ。
#   33 件目以降は名前と要約しか無く、**黙って落ちていた**（生成も検査も何も言わなかった）
PRELOAD_LIMIT = 32
# 生成済みエージェント定義の置き場（emit_agents.py の --dest=local と --dest=home-claude）
AGENT_DIRS = (".claude/agents", ".agents/agents", "home-claude/.claude/agents")


def parse_cap(path: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """(技能領域 -> 技法 skill, 別掲の類型 -> skill)"""
    caps: dict[str, list[str]] = {}
    other: dict[str, list[str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        name, rest = line.split(":", 1)
        items = [s.strip() for s in rest.split(",") if s.strip()]
        (other if name.strip().startswith("@") else caps)[name.strip()] = items
    return caps, other


def parse_tasks(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        name, rest = line.split(":", 1)
        items = [s.strip() for s in rest.split(",") if s.strip()]
        out[name.strip()] = [] if items == [MACHINE] else items
    return out


RULE_HEAD = re.compile(r"^([^\s#:][^:]*?)\s*:\s*(.*)$")
FIELD = re.compile(r"^#\s+(\w+)\s*:\s*(.*)$")
VER = re.compile(r"_v\([a-z][-+]\d+\)$")


def base(n: str) -> str:
    return VER.sub("", n.strip().rstrip("?")).strip()


def parse_mk(path: Path) -> tuple[dict[str, list[str]], set[str]]:
    """(task 名 -> その task を持つ rule の deps を全部集めたもの, 全 target 名)"""
    by_task: dict[str, list[str]] = {}
    targets: set[str] = set()
    cur: list[str] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = RULE_HEAD.match(raw)
        if m:
            targets.add(base(m.group(1)))
            cur = [base(d) for d in m.group(2).split(",") if d.strip()]
            continue
        f = FIELD.match(raw.strip()) if raw.strip().startswith("#") else None
        if f and f.group(1) == "task" and cur is not None:
            by_task.setdefault(f.group(2).strip(), []).extend(cur)
    return by_task, targets


def frontmatter(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").split("---")[1].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def norm(s: str) -> str:
    """比較用の正規化 —— 全半角・記号・送り仮名の揺れを落とす"""
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[のをにはがへとで・\s]", "", s)


def _docstring_problem(py: Path, label: str) -> str | None:
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as e:
        return "[武器] `" + label + "` を解析できない（" + type(e).__name__ + "）"
    doc = ast.get_docstring(tree) or ""
    if not any(ln.strip() for ln in doc.splitlines()):
        return ("[武器] `" + label + "` にモジュール docstring が無い"
                " —— 配布時に SKILL.md の「武器」節の説明になる 1 行目が要る")
    return None


def check_weapons(skill_dir: Path, home_skills_dir: Path | None = None) -> list[str]:
    """Skill 専用スクリプト（武器）の検査。

    - `skills/scripts/<名前>/` の `<名前>` が `skills/<名前>.md` と対応するか（孤児ディレクトリ）
    - `home-claude/skills/<名前>/scripts/` は `SKILL.md` を伴うか
    - 各 `.py` にモジュール docstring（1 行目の説明）があるか
    """
    problems: list[str] = []
    wroot = skill_dir / "scripts"
    if wroot.is_dir():
        for d in sorted(p for p in wroot.iterdir() if p.is_dir() and p.name != "__pycache__"):
            if not (skill_dir / (d.name + ".md")).exists():
                problems.append("[武器の孤児] `skills/scripts/" + d.name + "/` —— 対応する Skill"
                                " `skills/" + d.name + ".md` が無い")
            for py in sorted(d.glob("*.py")):
                p = _docstring_problem(py, "skills/scripts/" + d.name + "/" + py.name)
                if p:
                    problems.append(p)
        for f in sorted(p for p in wroot.iterdir() if p.is_file()):
            problems.append("[武器の孤児] `skills/scripts/" + f.name
                            + "` —— Skill 名のディレクトリの外に置かれている")
    if home_skills_dir is not None and home_skills_dir.is_dir():
        for d in sorted(p for p in home_skills_dir.iterdir() if p.is_dir()):
            sd = d / "scripts"
            if not sd.is_dir():
                continue
            if not (d / "SKILL.md").exists():
                problems.append("[武器の孤児] `" + d.name + "/scripts/` —— `SKILL.md` が無い")
            for py in sorted(sd.glob("*.py")):
                p = _docstring_problem(py, d.name + "/scripts/" + py.name)
                if p:
                    problems.append(p)
    return problems


PRELOAD_TAIL = (" —— サブエージェントに本文が入るのは先頭 " + str(PRELOAD_LIMIT)
                + " 件まで。超えた分は名前と要約だけになり、**黙って落ちる**")


def check_preload_tasks(task_files: list[Path]) -> list[str]:
    """`.tasks` の 1 task が要求する skill（重複を除く）が上限を超えていないか"""
    problems: list[str] = []
    for tf in task_files:
        for task, skills in parse_tasks(tf).items():
            n = len(set(skills))
            if n > PRELOAD_LIMIT:
                problems.append("[装着の上限超え] " + tf.name + " の `" + task
                                + "` が要求する skill が " + str(n) + " 件" + PRELOAD_TAIL
                                + "（役を割るか、装着を減らす）")
    return problems


def agent_skills(path: Path) -> list[str] | None:
    """エージェント定義の frontmatter `skills:` を読む。欄が無ければ None。

    emit_claude.py は `skills: ["a", "b"]`（JSON の配列）で書く。手書きの `[a, b]` と、
    ブロック形式（次の行から `- a`）も読む
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm: list[str] = []
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        fm.append(ln)
    for i, ln in enumerate(fm):
        if not ln.startswith("skills:"):
            continue
        rest = ln.split(":", 1)[1].strip()
        if rest.startswith("["):
            try:
                return [str(s) for s in json.loads(rest)]
            except ValueError:
                return [s.strip().strip("\"'") for s in rest.strip("[]").split(",") if s.strip()]
        out: list[str] = []
        for b in fm[i + 1:]:
            if not b.strip().startswith("-"):
                break
            out.append(b.strip()[1:].strip().strip("\"'"))
        return out
    return None


def check_preload_agents(agent_dirs: list[Path]) -> list[str]:
    """生成済みエージェント定義の `skills:`（重複を除く）が上限を超えていないか。

    task ごとに上限を守っても、1 役が複数の task を束ねれば超えうる（`split_by_skill`）。
    だから生成物の側でも数える
    """
    problems: list[str] = []
    for d in agent_dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            skills = agent_skills(f)
            if skills is None:
                continue
            names = list(dict.fromkeys(skills))
            if len(names) <= PRELOAD_LIMIT:
                continue
            try:
                label = f.relative_to(ROOT).as_posix()
            except ValueError:
                label = f.as_posix()
            problems.append("[装着の上限超え] `" + label + "` の `skills:` が "
                            + str(len(names)) + " 件" + PRELOAD_TAIL + "（"
                            + str(PRELOAD_LIMIT + 1) + " 件目の `" + names[PRELOAD_LIMIT]
                            + "` から " + str(len(names) - PRELOAD_LIMIT) + " 件）")
    return problems


def main() -> int:
    args = [a for a in sys.argv[1:] if a.startswith("--tasks=")]
    task_files = ([Path(a.split("=", 1)[1]) for a in args]
                  or sorted((ROOT / "models").glob("*.tasks")))

    caps, other = parse_cap(CAP_FILE)
    registered = {s for v in caps.values() for s in v}
    aside = {s for v in other.values() for s in v}
    known = registered | aside

    print("# skill カタログの検査")
    print("")
    print("- 技能領域 **" + str(len(caps)) + "**　技法 skill **" + str(len(registered))
          + "**　別掲（規約・警戒・境界線） **" + str(len(aside)) + "**")
    print("- 参照元 `.tasks` **" + str(len(task_files)) + "** 件")
    print("")

    problems: list[str] = []
    used: set[str] = set()
    # skill -> {モデル名}／skill -> [(モデル, task)]
    seen_in: dict[str, set[str]] = {}
    demand: list[tuple[str, str, str]] = []

    for tf in task_files:
        for task, skills in parse_tasks(tf).items():
            for s in skills:
                used.add(s)
                seen_in.setdefault(s, set()).add(tf.stem)
                demand.append((s, tf.stem, task))
                if s not in known:
                    problems.append("[未登録] `" + s + "` —— " + tf.name
                                    + " の `" + task + "` が要求するが、カタログに無い")

    for s in sorted(known - used):
        problems.append("[孤児] `" + s + "` —— カタログにあるが、どの task も要求しない")

    # 言い替えの検出。**文字列一致で重なりを測るので、別名は永久に重ならない**
    names = sorted(known | used)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if a == b:
                continue
            na, nb = norm(a), norm(b)
            if na == nb or (len(na) > 3 and SequenceMatcher(None, na, nb).ratio() > 0.86):
                problems.append("[言い替えの疑い] `" + a + "` と `" + b
                                + "` —— **重なりは文字列一致で測るので、別名は永久に重ならない**")

    dup = [s for s in registered
           if sum(1 for v in caps.values() if s in v) > 1]
    for s in sorted(set(dup)):
        problems.append("[二重所属] `" + s + "` が複数の技能領域に属する"
                        + " —— 領域が「一緒に保持される束」でなくなる")

    for s in sorted(registered & aside):
        problems.append("[類型の衝突] `" + s + "` が技能領域と別掲の両方にある")

    # ── 様式（2026-09-01・G-63 / G-57）────────────────────────────────
    # **「いつ効くか」「どの層に装着するか」が書かれていない skill は、
    #   担い手が毎回判定することになる**（G-63 の実測）。
    fm: dict[str, dict[str, str]] = {}
    for s in sorted(known):
        f = SKILL_DIR / (s + ".md")
        if not f.exists():
            continue
        fm[s] = frontmatter(f)
        for key, why in (("layer", "どの層に装着するか"),
                         ("applies_when", "いつ効くか")):
            if not fm[s].get(key):
                problems.append("[様式] `" + s + "` に `" + key + ":` が無い —— "
                                + why + "が書かれていない")

    # ── 層の不一致 ────────────────────────────────────────────────
    # 宣言した層と、`.tasks` での実際の使われ方を突き合わせる。
    for s, d in sorted(fm.items()):
        decl = d.get("layer")
        if not decl:
            continue
        obs = seen_in.get(s, set())
        if not obs:
            continue
        actual = ("メタ" if obs == {"meta"}
                  else "両方" if "meta" in obs else "ドメイン")
        if decl != actual:
            problems.append("[層の不一致] `" + s + "` は `layer: " + decl
                            + "` と宣言しているが、`.tasks` での使われ方は **"
                            + actual + "**（" + "／".join(sorted(obs)) + "）")

    # ── skill と `.mk` の食い違い（G-67）──────────────────────────
    # **skill が要求する入力が、その skill を要求する rule の deps に無い。**
    # 「変更の履歴から引け」と言う skill に、履歴が渡っていなかった。
    mk_cache: dict[str, tuple[dict[str, list[str]], set[str]]] = {}
    for s, d in sorted(fm.items()):
        req = [x.strip() for x in d.get("requires_deps", "").split(",") if x.strip()]
        if not req:
            continue
        for skill, model, task in demand:
            if skill != s:
                continue
            mk = ROOT / "models" / (model + ".mk")
            if not mk.exists():
                continue
            if model not in mk_cache:
                mk_cache[model] = parse_mk(mk)
            by_task, targets = mk_cache[model]
            deps = set(by_task.get(task, []))
            for r in req:
                if r in deps:
                    continue
                tail = ("`.mk` に target としても存在しない —— **誰も作っていない**"
                        if r not in targets else
                        "target としては在るが、この rule の deps に無い")
                problems.append("[dep 不足] `" + s + "` は `" + r
                                + "` を要求するが、" + model + ".mk の `"
                                + task + "` の deps に無い —— " + tail)

    # ── 装着の上限（2026-10-28）──────────────────────────────────
    # **65 件を装着した役が、実際には辞書順の先頭 32 件しか読んでいなかった。**
    # 生成も検査も黙っていた。task と、生成済みの役（複数の task を束ねうる）の両方を数える
    problems += check_preload_tasks(task_files)
    problems += check_preload_agents([ROOT / d for d in AGENT_DIRS])

    problems += check_weapons(SKILL_DIR, ROOT / "home-claude" / "skills")

    print("## 技能領域")
    print("")
    print("| 技能領域 | skill 数 | 実体のある skill |")
    print("|---|---|---|")
    for name, items in caps.items():
        have = sum(1 for s in items if (SKILL_DIR / (s + ".md")).exists())
        print("| **" + name + "** | " + str(len(items)) + " | "
              + (str(have) if have else "—") + " |")
    print("")

    mat: dict[str, int] = {}
    missing: list[str] = []
    for s in sorted(known):
        f = SKILL_DIR / (s + ".md")
        if not f.exists():
            missing.append(s)
            continue
        m = re.search(r"^maturity:\s*(\S+)", f.read_text(encoding="utf-8"), re.M)
        key = m.group(1) if m else "（宣言なし）"
        mat[key] = mat.get(key, 0) + 1
    for s in missing:
        problems.append("[実体なし] `" + s + "` —— カタログにあるがファイルが無い")

    print("## 実体と成熟度")
    print("")
    print("- **" + str(len(known) - len(missing)) + " / " + str(len(known))
          + "** の skill に本体ファイルがある")
    for k in ("confirmed", "forming", "draft", "（宣言なし）"):
        if k in mat:
            print("- **" + k + " " + str(mat[k]) + " 件**")
    print("")
    print("> **draft は仮説である。実走で当てて、効いた回数で昇格させる**（§3）。")
    print("> **書かなければ検証もできない。**")
    print("")

    unmeasured = sorted(k for k, v in fm.items() if "未測定" in v.get("applies_when", ""))
    print("## 適用条件（いつ効くか）")
    print("")
    print("- **記入済み " + str(len(fm) - len(unmeasured)) + " / " + str(len(fm))
          + "**　**未測定 " + str(len(unmeasured)) + " 件**")
    print("")
    print("> **未測定は欠陥ではない。実走で当てるまで書けないだけである。**")
    print("> **書けないことを書いてある状態が正しい**（想像で埋めない）。")
    print("")

    print("## 検査結果")
    print("")
    if problems:
        for p in problems:
            print("- ❌ " + p)
    else:
        print("- ⭕ 問題 0 件")
    print("")
    print("**問題 " + str(len(problems)) + " 件**")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

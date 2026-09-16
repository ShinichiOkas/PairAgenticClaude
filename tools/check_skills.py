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
"""
from __future__ import annotations

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

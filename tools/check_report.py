#!/usr/bin/env python
"""完了報告を、その役割ブリーフと突き合わせて検める。

**自己評価は信頼できない。しかし反証は同じ報告の中に載っている**（実測・G-52 / G-66）。
実走で **6 体中 3 体**が、事後条件を ✅ と書いた同じ報告の中に、それを否定する記述を残した。

    python tools/check_report.py --brief=BRIEF.md REPORT.md [REPORT.md ...]

**⚠ この道具は「矛盾している」と断定しない。「同じ報告の中に反証がある」と指摘するだけである。**
**判定は人間が行う**（P-12）。`check_skills.py` の `[言い替えの疑い]` と同じ位置づけ。

検査（6 種）:

  [節の欠落]          完了報告の 6 項目に対応する節が無い
  [判定漏れ]          ブリーフの事後条件に、対応する判定が報告に無い
  [自己矛盾の疑い]    ✅ と書いた事後条件の節の中に、否定の語がある
  [空 dep の申告漏れ] 前版・任意 dep があるのに「空だった dep: なし」と書いてある
  [過剰の疑い]        持ち込んだ知識の申告に「将来」「拡張」等がある（P-23 の逸脱の徴候）
  [遮断の疑い]        読んではならない成果物名が、否定の文脈なしに現れる
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# 否定の語 —— **「やった」と書いた節の中に現れたら、同じ報告が自分を否定している**
NEGATION = ("未実装", "実装していない", "実装しなかった", "できなかった", "できていない",
            "断念", "対象外", "未対応", "未検証", "満たしていない", "満たせなかった",
            "見送", "未着手", "保留", "省略した", "対応していない")

# 過剰の徴候 —— **P-23「要求にないことを追加しない」の逸脱は、この語で申告される**
EXCESS = ("将来", "拡張可能性", "念のため", "汎用", "後々", "先を見越", "あとで使える")

# 完了報告の 6 項目（`derive_roles.py` の emit_agents が出す）
ITEMS = (
    ("成果物のパス", ("成果物",)),
    ("事後条件の判定", ("事後条件",)),
    ("読んだファイルの列挙", ("読んだファイル", "読んだもの", "deps 以外")),
    ("空だった dep", ("空だった", "空の dep")),
    ("持ち込んだ知識の申告", ("無かった知識", "ない知識", "持ち込")),
    ("範囲外として上げた項目", ("範囲外",)),
)

HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
ROW = re.compile(r"^\|\s*\*\*(.+?)\*\*\s*\|\s*(.*?)\s*\|\s*$", re.M)
NUM = re.compile(r"^\s*\d+\.\s*(.+)$", re.M)
POST_BLOCK = re.compile(r"\*\*事後条件[^\n]*\*\*\s*\n(.*?)(?=\n##|\Z)", re.S)
RULE_SPLIT = re.compile(r"^## 担当:\s*(.+?)\s*$", re.M)
COMMON = re.compile(r"^## 共通の規則", re.M)
JUDGED_TITLE = re.compile(r"^\d+(?:[-.]\d+)*[.\s]")
# **否定の語が「条件の名前そのもの」であることがある** ——
#   「カバーできなかった領域が明示されている」を「できなかった」で拾ってはならない。
POSITIVE = re.compile(r"✅|明示され|明示した|記載され|記録され|書かれている|列挙し")
# **引用の中の否定語は、その節の主張ではない** ——
#   「第3節『カバーできなかった領域』で詳述」は矛盾ではなく参照である。
QUOTED = re.compile(r"「[^」]*」|『[^』]*』|`[^`]*`")
WORD = re.compile(r"[一-鿿ァ-ヶA-Za-z]{2,}")
DENIAL = re.compile(r"読ま|読んでいない|遮断|禁止|見ていない|参照していない")
NONE_DECL = re.compile(r"^\*{0,2}(なし|無し|該当なし)")


def sections(text: str) -> list[tuple[int, str, str]]:
    """(見出しレベル, 見出し, 本文) —— 本文は次の同レベル以上の見出しまで"""
    lines = text.splitlines()
    heads = []
    for i, line in enumerate(lines):
        m = HEAD.match(line)
        if m:
            heads.append((i, m.group(1), m.group(2).strip()))
    out = []
    for k, (i, hashes, title) in enumerate(heads):
        lv = len(hashes)
        end = len(lines)
        for j, hs, _ in heads[k + 1:]:
            if len(hs) <= lv:
                end = j
                break
        out.append((lv, title, "\n".join(lines[i + 1:end])))
    return out


def brief_rules(path: Path) -> list[dict]:
    """ブリーフを rule 単位に割る。

    **1 つの役割が複数の rule を持つことがある**（構築者 ＝ 設計書 ＋ 実装物）。
    rule ごとに完了報告が 1 通出るので、突き合わせも rule 単位でなければならない。
    """
    parts = RULE_SPLIT.split(path.read_text(encoding="utf-8"))
    rules = []
    for i in range(1, len(parts), 2):
        target = parts[i].strip().strip("`")
        body = COMMON.split(parts[i + 1])[0]
        r: dict = {"target": target, "post": [], "deps_raw": "", "forbidden": [],
                   "vocab": body}
        for key, val in ROW.findall(body):
            if "deps" in key:
                r["deps_raw"] = val.strip()
            elif "読んではならない" in key:
                r["forbidden"] = [x.strip() for x in re.split(r"[、,]", val)
                                  if x.strip() and x.strip() not in ("—", "-")]
        m = POST_BLOCK.search(body)
        if m:
            r["post"] = [x.strip() for x in NUM.findall(m.group(1))]
        r["may_be_empty"] = [x.strip() for x in re.split(r"[、,]", r["deps_raw"])
                             if "前版" in x or "任意" in x]
        rules.append(r)
    return rules


def keywords(s: str) -> set:
    return set(WORD.findall(s))


def pick_rule(rules: list[dict], judged_titles: list[str]) -> dict:
    """報告が扱っている rule を、判定見出しとの語の重なりで選ぶ。"""
    jk = keywords(" ".join(judged_titles))
    best, score = rules[0], -1
    for r in rules:
        n = len(keywords(" ".join(r["post"])) & jk)
        if n > score:
            best, score = r, n
    return best


def check(brief: Path, report: Path) -> tuple[list[str], dict]:
    rules = brief_rules(brief)
    text = report.read_text(encoding="utf-8")
    secs = sections(text)
    titles = "\n".join(t for _, t, _ in secs)
    out: list[str] = []
    tag = report.name + ": "

    judged = [(t, body) for _, t, body in secs
              if JUDGED_TITLE.match(t) and ("✅" in body or "❌" in body
                                            or "満たし" in body)]
    b = (pick_rule(rules, [t for t, _ in judged]) if rules else
         {"target": "?", "post": [], "forbidden": [], "may_be_empty": []})

    for label, keys in ITEMS:
        if not any(k in titles for k in keys):
            out.append(tag + "[節の欠落] **" + label + "** に対応する節が無い")

    # **数ではなく条件ごとに突き合わせる** —— 1 件を 2 つに割って報告することがある
    jk = keywords(" ".join(t for t, _ in judged))
    for cond in b["post"]:
        # **1 つの事後条件が複数の主張を持つことがある** ——
        #   「A ／ B」も「A —— B」も、どちらか片方が判定されていれば通す。
        parts = [p for p in re.split(r"[／/]|——|--", cond) if p.strip()]
        if not any(len(keywords(p) & jk) >= max(1, len(keywords(p)) // 2)
                   for p in parts):
            out.append(tag + "[判定漏れ] 事後条件「" + cond
                       + "」に対応する判定が報告に無い")

    # **役割の語彙に入っている否定語は、告白ではなく用語である。**
    # 「カバーできなかった領域が明示されている」は事後条件そのものである（実測 FP）。
    vocab = str(b.get("vocab", ""))
    negation = tuple(w for w in NEGATION if w not in vocab)

    for t, body in judged:
        if "✅" not in body:
            continue
        for line in body.splitlines():
            if POSITIVE.search(line):
                continue
            bare = QUOTED.sub("", line)
            hit = next((w for w in negation if w in bare), None)
            if hit:
                out.append(tag + "[自己矛盾の疑い] ✅ とした節「" + t
                           + "」の中に **「" + hit
                           + "」** がある —— `" + line.strip()[:70] + "`")
                break

    empty_sec = next((body for _, t, body in secs if "空だった" in t), None)
    if empty_sec is not None and b["may_be_empty"]:
        if NONE_DECL.match(empty_sec.strip()):
            out.append(tag + "[空 dep の申告漏れ] 「空だった dep: なし」と書いてあるが、"
                       + "この rule には前版・任意 dep が **"
                       + str(len(b["may_be_empty"])) + " 件**ある —— "
                       + "／".join(b["may_be_empty"]))

    know_sec = next((body for _, t, body in secs
                     if any(k in t for k in ("無かった知識", "ない知識", "持ち込"))), None)
    if know_sec:
        for line in know_sec.splitlines():
            hit = next((w for w in EXCESS if w in line), None)
            if hit:
                out.append(tag + "[過剰の疑い] 持ち込んだ知識の申告に **「" + hit
                           + "」** がある —— P-23（要求にないことを追加しない）の逸脱かを"
                           + "検める —— `" + line.strip()[:70] + "`")

    # **遮断の検査は「読んだファイル」の申告に限る。**
    # 本文全体を見ると成果物名は普通に出てくるので、雑音しか出ない
    # （実測: `仕様` が「仕様要件」に当たった）。
    # ⚠ **申告しなかった読み取りは、報告からは原理的に見えない**（P-13）。
    read_sec = next((body for _, t, body in secs
                     if "読んだファイル" in t or "読んだもの" in t), None)
    if read_sec:
        for name in b["forbidden"]:
            for line in read_sec.splitlines():
                if name in line and not DENIAL.search(line):
                    out.append(tag + "[遮断の疑い] 読んではならない `" + name
                               + "` が、読んだファイルの申告に現れる —— `"
                               + line.strip()[:70] + "`")
                    break
    return out, b


def main() -> int:
    briefs = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--brief=")]
    reports = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not briefs or not reports:
        print(__doc__)
        return 2
    brief = Path(briefs[0])

    print("# 完了報告の検査")
    print("")
    print("- ブリーフ **" + brief.stem + "**　rule **"
          + str(len(brief_rules(brief))) + " 件**")

    problems: list[str] = []
    for r in reports:
        probs, used = check(brief, Path(r))
        print("- `" + Path(r).name + "` → rule **`" + str(used["target"])
              + "`**（事後条件 " + str(len(used["post"])) + " 件／空になりうる dep "
              + str(len(used["may_be_empty"])) + " 件／遮断 "
              + str(len(used["forbidden"])) + " 件）")
        problems += probs
    print("")

    print("## 検査結果")
    print("")
    if problems:
        for p in problems:
            print("- ❌ " + p)
    else:
        print("- ⭕ 指摘 0 件")
    print("")
    print("**指摘 " + str(len(problems)) + " 件**")
    print("")
    print("> ⚠ **指摘は矛盾の証明ではない。「同じ報告の中に反証がある」という報せである。**")
    print("> **判定は人間が行う**（P-12）。")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

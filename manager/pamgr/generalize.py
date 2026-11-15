"""一般化: プロジェクト固有の語（プロジェクト名・絶対パス・固有の環境変数・ユーザー名）を外し、マスターへ昇格する。

1. 固有の語を機械で検出する（登録済みのプロジェクト名・パス・環境変数）
2. LLM（OmniAISDK 経由の Ollama）が書き換える。師匠の原文の引用・実測値・コード例は残す
3. 書き換え後に残った固有の語を機械で検める（コードブロックの中は数えない）
4. 師匠が案を見て（必要なら直して）、マスターへ昇格する。昇格先はユーザー固有（ペア固有スキル）か全体（home-claude/skills）
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from . import llm, survey, targets
from .paths import master_root, user_home

STOP_NAMES = {"temp", "test", "tmp", "docs", "src", "lib", "bin", "work", "tools", "skills", "agents", "home"}
_ABS = re.compile(r"(?:[A-Za-z]:[\\/](?:[^\s`'\"）)\]>|]+)|/(?:Users|home)/[^\s`'\"）)\]>|]+)")
_ENV = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b")
_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.S)


def project_names() -> list[str]:
    names = {t["name"] for t in targets.list_targets() if t["kind"] == "project"}
    data = survey.load()
    if data:
        names |= {u["target"] for u in data["units"] if u["scope"] == "project"}
    return sorted((n for n in names if len(n) >= 3 and n.lower() not in STOP_NAMES), key=len, reverse=True)


def _name_re(name: str) -> re.Pattern[str]:
    if name.isascii():
        return re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.I)
    return re.compile(re.escape(name))


def detect(text: str, names: list[str] | None = None) -> list[dict[str, Any]]:
    names = project_names() if names is None else names
    found: Counter[tuple[str, str]] = Counter()
    for n in names:
        for m in _name_re(n).finditer(text):
            found[(m.group(0), "プロジェクト名")] += 1
    for m in _ABS.finditer(text):
        found[(m.group(0), "絶対パス")] += 1
    prefixes = {re.sub(r"[^A-Z0-9]", "", n.upper()) for n in names}
    for m in _ENV.finditer(text):
        head = m.group(0).split("_")[0]
        if head in prefixes:
            found[(m.group(0), "固有の環境変数")] += 1
    uname = user_home().name
    if len(uname) >= 3:
        for m in _name_re(uname).finditer(text):
            found[(m.group(0), "ユーザー名")] += 1
    return [{"term": t, "kind": k, "count": c} for (t, k), c in found.most_common()]


def remaining(text: str, names: list[str] | None = None) -> list[str]:
    """書き換え後に残った固有の語（コードブロックの中は数えない）。"""
    body = _FENCE.sub("", text)
    return sorted({f["term"] for f in detect(body, names)})


SYSTEM = """あなたは、AI と人間のペア作業で育ったスキル文書（Markdown＋YAML フロントマター）を、
どのプロジェクトでも使える形に一般化する編集者です。

## 方針
- 固有のプロジェクト名・パス・環境変数名・ユーザー名は、概念の説明に置き換える
  （例: 「Mnemo で」→「この製品で」、`src/mnemo/core/hook.py` →「先行実装」、`MNEMO_WORK_DIR` →「データルートの環境変数」）
- 本質的なルール・原則は保持する
- 師匠（ユーザー）の発言の原文引用（`>` で始まる引用や「」内の発言）は削らずに残す。実際に踏んだ失敗・実測値・コード例も保持する。
  削ると「もっともらしいが使えない一般論」になる。ただし引用の中の固有名も置き換える
- コードブロックの中は変えなくてよい
- フロントマターは `---` で始め、name / description / type / maturity を残す。name に固有名が入っているときだけ外した英語ケバブケースにする
- フロントマターの source_sprint_ids・source_project・source_path・survey_date は削除する
- 出力は一般化した文書の全文だけ。前置き・後書き・コードフェンスで囲むことはしない"""


def run(unit_id: str, model: str | None = None) -> dict[str, Any]:
    u = survey.get_unit(unit_id)
    if u is None:
        raise KeyError(f"単位が無い（サーベイをやり直してください）: {unit_id}")
    names = project_names()
    findings = detect(u["text"], names)
    hint = "\n".join(f"- {f['term']}（{f['kind']}）" for f in findings) or "- （機械では見つからなかった。文中の固有の事情を探して外す）"
    user = f"## 機械で見つけた固有の語\n{hint}\n\n## 元の文書\n{u['text']}"
    proposal, m = llm.chat_text(SYSTEM, user, role="rewrite", model=model)
    fm, _ = survey.split_frontmatter(proposal)
    sug = str(fm.get("name") or u["name"])
    for n in names:
        sug = _name_re(n).sub("", sug)
    sug = re.sub(r"[\\/:*?\"<>|]+", "-", sug).strip(" -_") or "generalized-skill"
    return {"unit": {k: u[k] for k in ("id", "name", "scope", "target", "rel", "text")}, "findings": findings,
            "proposal": proposal, "remaining": remaining(proposal, names), "model": m, "suggested_name": sug}


def promote(text: str, scope: str, name: str, overwrite: bool = False) -> Path:
    name = name.strip().removesuffix(".md")
    if not name or re.search(r"[\\/:*?\"<>|]|\.\.", name):
        raise ValueError("ファイル名に使えない文字がある")
    master = master_root()
    if scope == "user":
        root = master / "external" / "pair-agent-skills"
        if not (root / ".git").exists():
            raise ValueError("external/pair-agent-skills が空（サブモジュール未取得）。git submodule update --init が要る")
        dest = root / f"{name}.md"
    elif scope == "global":
        dest = master / "home-claude" / "skills" / name / "SKILL.md"
    else:
        raise ValueError(f"昇格先のスコープが不明: {scope}")
    if dest.exists() and not overwrite:
        raise FileExistsError(f"マスターに同じ名前がある: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text.replace("\r\n", "\n"), encoding="utf-8")
    return dest

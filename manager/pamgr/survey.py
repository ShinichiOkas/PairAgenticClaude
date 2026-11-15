"""サーベイ: マスターと登録済みの配布先から、ルール・スキルを「単位」に切って集める。

単位の種類:
  skill         スキル 1 ファイル（SKILL.md・ペア固有スキル・プロジェクト固有スキル）
  rule-section  規範（CLAUDE.md・GEMINI.md・AGENTS.md・rules/*.md）を見出し（##）で切った 1 節
  agent         エージェント定義 1 ファイル（検査の既定からは外す）
スコープ: master（このリポジトリ）／global／user／project
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterator

import yaml

from . import store, targets
from .paths import master_root

FILE = "survey.json"
MAX_TEXT = 60_000
_FENCE = re.compile(r"^\s*(```|~~~)")
_HEAD = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\r\n", "\n")).strip()


def text_hash(s: str) -> str:
    return hashlib.sha1(norm_text(s).encode("utf-8")).hexdigest()


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if text.startswith("---"):
        m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", text, re.S)
        if m:
            try:
                fm = yaml.safe_load(m.group(1)) or {}
                if isinstance(fm, dict):
                    return fm, text[m.end():]
            except yaml.YAMLError:
                pass
    return {}, text


def split_sections(text: str) -> list[tuple[str, str]]:
    """見出しで節に切る。最も浅い「2 番目の深さ」（ふつう ##）で切り、下位の見出しは節に含める。"""
    lines = text.replace("\r\n", "\n").split("\n")
    heads: list[tuple[int, int, str]] = []
    in_code = False
    for i, ln in enumerate(lines):
        if _FENCE.match(ln):
            in_code = not in_code
            continue
        if not in_code:
            m = _HEAD.match(ln)
            if m:
                heads.append((i, len(m.group(1)), m.group(2).strip("* ").strip()))
    levels = sorted({lv for _, lv, _ in heads})
    if not levels:
        return [("(全文)", text)]
    cut = levels[1] if len(levels) > 1 and levels[0] == 1 else levels[0]
    starts = [(i, t) for i, lv, t in heads if lv == cut]
    out: list[tuple[str, str]] = []
    first = starts[0][0] if starts else len(lines)
    pre = "\n".join(lines[:first]).strip()
    if pre:
        top = next((t for _, lv, t in heads if lv < cut), "(冒頭)")
        out.append((top, pre))
    for k, (i, t) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        out.append((t, "\n".join(lines[i:end]).strip()))
    return out


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT]


def _unit(tid: str, tname: str, scope: str, kind: str, root: Path, p: Path, text: str, *, anchor: str = "", name: str = "",
          meta: dict[str, Any] | None = None) -> dict[str, Any]:
    rel = p.relative_to(root).as_posix() if root in p.parents or p == root else str(p)
    meta = meta or {}
    uid = hashlib.sha1(f"{tid}|{rel}|{anchor}".encode("utf-8")).hexdigest()[:12]
    return {
        "id": uid, "target_id": tid, "target": tname, "scope": scope, "kind": kind,
        "path": str(p), "rel": rel, "anchor": anchor,
        "name": str(meta.get("name") or name or p.stem), "title": anchor or str(meta.get("name") or name or p.stem),
        "description": str(meta.get("description") or "")[:500], "maturity": str(meta.get("maturity") or ""),
        "situation": meta.get("situation") or meta.get("applies_when") or "",
        "hash": text_hash(text), "size": len(text), "text": text,
    }


def _skill(tid: str, tname: str, scope: str, root: Path, p: Path) -> dict[str, Any]:
    text = _read(p)
    fm, _ = split_frontmatter(text)
    name = p.parent.name if p.name.upper() == "SKILL.MD" else p.stem
    return _unit(tid, tname, scope, "skill", root, p, text, name=name, meta=fm)


def _rule_doc(tid: str, tname: str, scope: str, root: Path, p: Path, seen_hash: set[str]) -> Iterator[dict[str, Any]]:
    text = _read(p)
    h = text_hash(text)
    if h in seen_hash:   # GEMINI.md が CLAUDE.md の写しなど、同じ場所の同じ中身は 1 回だけ
        return
    seen_hash.add(h)
    _, body = split_frontmatter(text)
    for title, sec in split_sections(body):
        if norm_text(sec):
            yield _unit(tid, tname, scope, "rule-section", root, p, sec, anchor=title, name=f"{p.name} › {title}")


def _files(d: Path, *globs: str) -> list[Path]:
    if not d.is_dir():
        return []
    return sorted({p for g in globs for p in d.glob(g) if p.is_file() and "__pycache__" not in p.parts})


def survey_home(t: dict[str, Any]) -> Iterator[dict[str, Any]]:
    root, tid, tn = Path(t["path"]), t["id"], t["name"]
    seen: set[str] = set()
    for f in ("CLAUDE.md", "GEMINI.md", "AGENTS.md"):
        if (root / f).is_file():
            yield from _rule_doc(tid, tn, "global", root, root / f, seen)
    for p in _files(root / "rules", "*.md"):
        yield from _rule_doc(tid, tn, "global", root, p, seen)
    for p in _files(root / "skills", "*/SKILL.md"):
        yield _skill(tid, tn, "global", root, p)
    for p in _files(root / "agents", "*.md"):
        yield _unit(tid, tn, "global", "agent", root, p, _read(p))
    for p in _files(root / "pair-agent" / "skills", "*.md"):
        yield _skill(tid, tn, "user", root, p)


def survey_project(t: dict[str, Any]) -> Iterator[dict[str, Any]]:
    root, tid, tn = Path(t["path"]), t["id"], t["name"]
    seen: set[str] = set()
    for f in ("CLAUDE.md", "GEMINI.md", "AGENTS.md", ".claude/CLAUDE.md"):
        if (root / f).is_file():
            yield from _rule_doc(tid, tn, "project", root, root / f, seen)
    for p in _files(root / ".claude" / "rules", "*.md"):
        yield from _rule_doc(tid, tn, "project", root, p, seen)
    for p in _files(root / ".pair-agent" / "skills", "*.md", "*/SKILL.md"):
        yield _skill(tid, tn, "project", root, p)
    for p in _files(root / ".claude" / "skills", "*/SKILL.md"):
        yield _skill(tid, tn, "project", root, p)
    for p in _files(root / ".agents" / "skills", "*.md", "*/SKILL.md"):
        yield _skill(tid, tn, "project", root, p)
    for p in _files(root / ".claude" / "agents", "*.md"):
        yield _unit(tid, tn, "project", "agent", root, p, _read(p))


def survey_master() -> Iterator[dict[str, Any]]:
    root = master_root()
    tid, tn = "master", "マスター"
    seen: set[str] = set()
    for f in ("home-claude/CLAUDE.md", "home-claude/GEMINI.md"):
        if (root / f).is_file():
            yield from _rule_doc(tid, tn, "master", root, root / f, seen)
    for p in _files(root / "home-claude" / "rules", "*.md"):
        yield from _rule_doc(tid, tn, "master", root, p, seen)
    for p in _files(root / "home-claude" / "skills", "*/SKILL.md"):
        yield _skill(tid, tn, "master", root, p)
    for p in _files(root / "home-claude" / "agents", "*.md"):
        yield _unit(tid, tn, "master", "agent", root, p, _read(p))
    for p in _files(root / "external" / "pair-agent-skills", "*.md"):
        yield _skill(tid, tn, "master", root, p)


def run() -> dict[str, Any]:
    units: list[dict[str, Any]] = list(survey_master())
    for t in targets.list_targets():
        if t["kind"] == "project":
            units.extend(survey_project(t))
        else:
            units.extend(survey_home(t))
    data = {"surveyed_at": store.now_iso(), "units": units}
    store.save(FILE, data)
    return data


def load() -> dict[str, Any] | None:
    return store.load(FILE, None)


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    by_scope: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for u in data["units"]:
        by_scope[u["scope"]] = by_scope.get(u["scope"], 0) + 1
        by_kind[u["kind"]] = by_kind.get(u["kind"], 0) + 1
    return {"total": len(data["units"]), "by_scope": by_scope, "by_kind": by_kind, "surveyed_at": data.get("surveyed_at")}


def public(u: dict[str, Any]) -> dict[str, Any]:
    """一覧用（本文を外す）。"""
    return {k: v for k, v in u.items() if k != "text"}


def get_unit(uid: str) -> dict[str, Any] | None:
    data = load()
    if not data:
        return None
    return next((u for u in data["units"] if u["id"] == uid), None)

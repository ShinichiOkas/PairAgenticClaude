"""マスターの git 履歴: ファイルの過去の版（HEAD を含む）。

台帳（最後に配った版）が無い配布先で、向きを推定するのに使う:
  配布先の版（または節）が、マスターの過去の版のどれかと一致する → 配布先が古い（マスターが新しい）
  どの過去の版とも一致しない → 配布先で書き換えられた
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

from . import sections
from .paths import master_root
from .survey import norm_text

MAX_VERSIONS = 80


def _git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "-c", "core.quotepath=false", *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def head() -> str:
    return (_git(master_root(), "rev-parse", "HEAD") or "").strip()


@lru_cache(maxsize=256)
def _versions(root: str, rel: str, head_sha: str) -> tuple[str, ...]:
    if not head_sha:
        return ()
    log = _git(Path(root), "log", "--format=%H", "-n", str(MAX_VERSIONS), "--", rel) or ""
    out: list[str] = []
    for sha in log.split():
        text = _git(Path(root), "show", f"{sha}:{rel}")
        if text is not None:
            out.append(text)
    return tuple(out)


def versions(rel: str) -> tuple[str, ...]:
    """マスターの rel（マスターの根からの相対パス）の過去の版。新しい順。HEAD の版を含む。作業ツリーの版は含まない。"""
    return _versions(str(master_root()), rel, head())


def file_seen(rel: str, text: str) -> bool:
    n = norm_text(text)
    return any(norm_text(v) == n for v in versions(rel))


def section_history(rel: str) -> dict[str, set[str]]:
    """節（見出しの鍵）ごとの、過去に現れた本文（正規化）の集合。"""
    out: dict[str, set[str]] = {}
    for v in versions(rel):
        for c in sections.parse(v):
            out.setdefault(c.key, set()).add(c.norm)
    return out

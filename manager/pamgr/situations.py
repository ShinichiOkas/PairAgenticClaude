"""状況定義: 矛盾して見える指示が、それぞれ真になる「状況」の登録簿。

マスター（リポジトリ）の situations/situations.yaml に置く（GitHub で PC・ユーザー間に共有するため）。
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from .paths import master_root

SEED: list[dict[str, Any]] = [
    {"id": "main-agent", "name": "主エージェントとして師匠と対話している",
     "definition": "師匠（ユーザー）と直接対話し、スプリントを進めている主エージェント。",
     "signals": ["師匠の発話を直接受けている", "サブエージェントとして起動されていない"]},
    {"id": "subagent", "name": "サブエージェント（役割エージェント）として動いている",
     "definition": "主エージェントやワークフローから起動され、単一の成果物に責任を負う役。対話規範は適用除外。",
     "signals": ["Agent ツール・Workflow から起動された", "deps・blocks が与えられている"]},
    {"id": "session-start-no-request", "name": "セッション開始直後で依頼がまだ無い",
     "definition": "Claude Code・Antigravity を立ち上げた直後で、師匠からの依頼をまだ受けていない。",
     "signals": ["最初の発話が依頼でない（「.」など）"]},
    {"id": "omakase", "name": "おまかせ",
     "definition": "師匠がスライスサイズや方針を「おまかせ」と指定した。推奨で進め、判断は事後報告する。",
     "signals": ["「おまかせ」の発話"]},
    {"id": "irreversible-or-external", "name": "破壊的・不可逆・外部送信を伴う作業",
     "definition": "削除・上書き・外部への送信・公開など、元に戻せないか外に影響する操作をする。",
     "signals": ["削除・上書き・push --force・送信・公開"]},
]


def path():
    return master_root() / "situations" / "situations.yaml"


def load() -> list[dict[str, Any]]:
    p = path()
    if not p.is_file():
        return [dict(s) for s in SEED]
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return list(data.get("situations") or [])


def save_one(item: dict[str, Any]) -> list[dict[str, Any]]:
    sid = str(item.get("id", "")).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-]*", sid):
        raise ValueError("ID は英小文字・数字・ハイフン（例: main-agent）")
    if not str(item.get("name", "")).strip():
        raise ValueError("名前が空")
    rec = {"id": sid, "name": str(item["name"]).strip(), "definition": str(item.get("definition", "")).strip(),
           "signals": [str(s).strip() for s in item.get("signals") or [] if str(s).strip()]}
    items = [s for s in load() if s.get("id") != sid] + [rec]
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# 状況定義（Pair Agent Manager が読み書きする）\n" +
                 yaml.safe_dump({"situations": items}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return items


def as_prompt(items: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {s['id']}: {s['name']} — {s.get('definition', '')}" for s in items)

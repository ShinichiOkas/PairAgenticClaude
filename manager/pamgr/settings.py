"""設定（マシン固有）: Ollama の口・判定用と書き換え用のモデル・探索の既定。"""

from __future__ import annotations

import os
from typing import Any

from . import store
from .paths import master_root

FILE = "settings.json"


def _default_base_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "").strip()
    if not host:
        return "http://127.0.0.1:11434"
    if not host.startswith("http"):
        host = "http://" + host
    return host.rstrip("/")


# 既定はクラウドのモデル（GPU を使わない）。師匠の指示 2026-11-15「どうしてもLLMが必要な場面では gemma4:31b-cloud を使って」
DEFAULT_MODEL = "gemma4:31b-cloud"


def defaults() -> dict[str, Any]:
    return {
        "ollama_base_url": _default_base_url(),
        "model_judge": DEFAULT_MODEL,
        "model_rewrite": DEFAULT_MODEL,
        "scan_roots": [str(master_root().parent)],
        "scan_depth": 2,
        "llm_budget_sec": 300,        # 点検 1 回で LLM の判定に使う時間の上限（秒）。残りは次の点検で
        "resident_enabled": False,    # 常駐（監視・定期の点検）。師匠が「常駐を始める」を押して入れる
        "interval_min": 30,           # 定期の点検の間隔（分）
        "watch": True,                # 規則・スキルのファイルが変わったら点検する
        "notify": True,               # 判断待ちができたら Windows の通知を出す
        "git_sync": True,             # 点検でマスターを pull し、取り込んだ変更を commit・push する（UC4）
    }


def get() -> dict[str, Any]:
    s = defaults()
    s.update({k: v for k, v in store.load(FILE, {}).items() if k in s})
    return s


def put(values: dict[str, Any]) -> dict[str, Any]:
    s = get()
    for k in s:
        if k in values and values[k] is not None:
            s[k] = values[k]
    s["scan_roots"] = [str(r) for r in s["scan_roots"] if str(r).strip()]
    s["scan_depth"] = max(1, min(5, int(s["scan_depth"])))
    s["llm_budget_sec"] = max(0, min(3600, int(s["llm_budget_sec"])))
    s["interval_min"] = max(5, min(24 * 60, int(s["interval_min"])))
    for k in ("resident_enabled", "watch", "notify", "git_sync"):
        s[k] = bool(s[k])
    s["ollama_base_url"] = str(s["ollama_base_url"]).strip().rstrip("/") or _default_base_url()
    store.save(FILE, s)
    return s

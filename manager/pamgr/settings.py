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
    s["ollama_base_url"] = str(s["ollama_base_url"]).strip().rstrip("/") or _default_base_url()
    store.save(FILE, s)
    return s

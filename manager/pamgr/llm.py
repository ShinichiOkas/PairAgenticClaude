"""LLM の口。OmniAISDK（omni_ai）の Ollama アダプタを通す（師匠の指示 2026-11-15）。

構造化出力は三段構え: response_schema（ネイティブ指定）＋プロンプト末尾にスキーマを明示＋受信側の検証（SDK が
pydantic で照合し、外れたら SchemaValidationError）。外れたら 1 回だけ再送する。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, TypeVar

import httpx
from omni_ai import ChatMessage, SchemaValidationError
from omni_ai.model_info import parse_ollama_tags
from omni_ai.providers import OllamaChatAdapter
from pydantic import BaseModel

from . import settings

T = TypeVar("T", bound=BaseModel)


class LLMNotConfigured(RuntimeError):
    pass


def base_url(override: str | None = None) -> str:
    return (override or settings.get()["ollama_base_url"]).rstrip("/")


def list_models(override: str | None = None) -> tuple[str, list[str]]:
    url = base_url(override)
    data = httpx.get(f"{url}/api/tags", timeout=10).json()
    return url, sorted(parse_ollama_tags(data))


def _adapter(url: str | None = None) -> OllamaChatAdapter:
    return OllamaChatAdapter(base_url=base_url(url), timeout=600.0)


def _model(role: str, override: str | None = None) -> str:
    m = override or settings.get().get("model_judge" if role == "judge" else "model_rewrite") or ""
    if not m:
        raise LLMNotConfigured("モデルが選ばれていません。設定（LLM）で選んで保存してください")
    return m


def chat_text(system: str, user: str, *, role: str = "rewrite", model: str | None = None, url: str | None = None,
              temperature: float = 0.2) -> tuple[str, str]:
    m = _model(role, model)
    with _adapter(url) as ad:
        res = ad.generate([ChatMessage.system(system), ChatMessage.user(user)], model=m, temperature=temperature, think=False)
    return strip_fence(res.content or ""), m


def chat_structured(system: str, user: str, schema: type[T], *, role: str = "judge", model: str | None = None,
                    url: str | None = None) -> tuple[T, str]:
    m = _model(role, model)
    spec = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    prompt = (f"{user}\n\n以下の JSON Schema に厳密に一致する JSON オブジェクトだけを出力してください。"
              f"コードフェンス・前置き・後書きは書かないでください。\n{spec}")
    last: Exception | None = None
    with _adapter(url) as ad:
        for attempt in range(2):
            msgs = [ChatMessage.system(system), ChatMessage.user(prompt if attempt == 0 else prompt + "\n\n【再送】前回の出力はスキーマに合いませんでした。")]
            try:
                res = ad.generate(msgs, model=m, temperature=0.0, response_schema=schema, think=False)
            except SchemaValidationError as exc:
                last = exc
                continue
            if res.parsed is not None:
                return res.parsed, m  # type: ignore[return-value]
            last = ValueError("構造化出力が空")
    raise RuntimeError(f"LLM の出力がスキーマに合いませんでした（2 回）: {last}")


def ping(model: str | None = None, url: str | None = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        text, m = chat_text("あなたは簡潔に答えるアシスタントです。", "「了解」とだけ返してください。", role="judge", model=model, url=url)
        return {"ok": True, "model": m, "content": text, "elapsed_ms": int((time.perf_counter() - t0) * 1000)}
    except Exception as exc:
        return {"ok": False, "model": model or "", "error": f"{type(exc).__name__}: {exc}", "elapsed_ms": int((time.perf_counter() - t0) * 1000)}


def strip_fence(s: str) -> str:
    """全体が 1 つのコードフェンスで囲まれているときだけ外す（部分の抽出はしない）。"""
    m = re.fullmatch(r"\s*```[a-zA-Z]*\n(.*)\n```\s*", s, re.S)
    return m.group(1) if m else s.strip()

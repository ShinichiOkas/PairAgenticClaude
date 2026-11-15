"""裏で走る仕事（LLM の検査など）。画面は /api/jobs/{id} で進み具合を読む。"""

from __future__ import annotations

import threading
import traceback
import uuid
from typing import Any, Callable

from .store import now_iso

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


class Progress:
    def __init__(self, job: dict[str, Any]) -> None:
        self.job = job

    def __call__(self, done: int, total: int, message: str = "") -> None:
        with _LOCK:
            self.job["progress"] = {"done": done, "total": total}
            if message:
                self.job["message"] = message


def start(kind: str, fn: Callable[[Progress], Any]) -> str:
    jid = uuid.uuid4().hex[:10]
    job: dict[str, Any] = {"id": jid, "kind": kind, "state": "running", "progress": {"done": 0, "total": 0},
                           "message": "", "started_at": now_iso(), "error": None}
    with _LOCK:
        _JOBS[jid] = job

    def run() -> None:
        try:
            fn(Progress(job))
            with _LOCK:
                job["state"] = "done"
        except Exception as exc:  # 裏の仕事の失敗は job に載せて画面に出す
            with _LOCK:
                job["state"] = "error"
                job["error"] = f"{type(exc).__name__}: {exc}"
                job["trace"] = traceback.format_exc()[-2000:]
        with _LOCK:
            job["finished_at"] = now_iso()

    threading.Thread(target=run, name=f"pamgr-{kind}-{jid}", daemon=True).start()
    return jid


def get(jid: str) -> dict[str, Any] | None:
    with _LOCK:
        j = _JOBS.get(jid)
        return dict(j) if j else None

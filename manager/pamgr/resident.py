"""常駐（docs/usecases.md §2・§5）: ファイルの変更（監視）と定期（既定 30 分）で点検する。

- 監視は、規則・スキルのファイルの更新時刻と大きさを数十秒ごとに見る（点検が自分で書いた分は、点検の後に基準を取り直して無視する）
- 変更を見つけたら、落ち着く（次の見回りで変わっていない）のを待って点検する
- 矛盾の判定が残っていれば、次の点検を早める（LLM の判定を順に進める）
- 判断待ちが新しくできたら、Windows の通知を 1 回だけ出す（押すと GUI の判断待ちが開く）
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import inbox, notify, runtime, settings, sweep, targets
from .paths import master_root

POLL_SEC = 20
BACKLOG_SEC = 90
_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"thread": None, "stop": None, "next_sweep": None, "last_error": None, "last_reason": None}


def watched_files() -> list[Path]:
    m = master_root()
    out: list[Path] = []

    def g(base: Path, *pats: str) -> None:
        if base.is_dir():
            for pat in pats:
                out.extend(p for p in base.glob(pat) if p.is_file())

    g(m / "home-claude", "CLAUDE.md", "GEMINI.md", "rules/*.md", "skills/*/SKILL.md")
    g(m / "situations", "*.yaml")
    for t in targets.list_targets():
        root = Path(t["path"])
        if t["kind"] == "project":
            g(root, "CLAUDE.md", "GEMINI.md", "AGENTS.md", ".claude/CLAUDE.md", ".claude/rules/*.md")
        else:
            g(root, "CLAUDE.md", "GEMINI.md", "rules/*.md", "skills/*/SKILL.md", "pair-agent/skills/*.md")
    return out


def fingerprint() -> str:
    h = hashlib.sha1()
    for p in sorted(watched_files()):
        try:
            st = p.stat()
            h.update(f"{p}|{st.st_mtime_ns}|{st.st_size}\n".encode("utf-8"))
        except OSError:
            continue
    for r in settings.get()["scan_roots"]:          # 新しいリポジトリが置かれたことも拾う
        try:
            h.update(f"{r}|{Path(r).stat().st_mtime_ns}\n".encode("utf-8"))
        except OSError:
            pass
    return h.hexdigest()


def notify_new() -> dict[str, Any] | None:
    """まだ知らせていない判断待ちがあれば、通知を 1 回だけ出す。"""
    new = inbox.unnotified()
    if not new:
        return None
    inbox.mark_notified([i["id"] for i in new])
    if not settings.get().get("notify", True):
        return None
    title = f"判断待ち {len(new)} 件"
    body = new[0]["title"] + (f" ほか {len(new) - 1} 件" if len(new) > 1 else "")
    return notify.toast(f"Pair Agent Manager: {title}", body, f"{runtime.base_url()}#inbox")


def sweep_and_notify(dry_run: bool = False, progress: Any = None, reason: str = "手動") -> dict[str, Any]:
    res = sweep.run(dry_run, progress)
    if not dry_run:
        notify_new()
        _STATE["last_reason"] = reason
        _schedule(res)
    return res


def _schedule(res: dict[str, Any] | None) -> None:
    s = settings.get()
    backlog = ((res or {}).get("conflicts") or {}).get("remaining", 0)
    sec = BACKLOG_SEC if backlog and not ((res or {}).get("conflicts") or {}).get("stopped", "").startswith("LLM") else int(s["interval_min"]) * 60
    _STATE["next_sweep"] = (datetime.now() + timedelta(seconds=sec)).isoformat(timespec="seconds")


def _loop(stop: threading.Event) -> None:
    last_fp = fingerprint()
    changed_at: float | None = None
    _schedule(sweep.last())
    if not sweep.last():
        _STATE["next_sweep"] = datetime.now().isoformat(timespec="seconds")   # 初めては、すぐ点検する
    while not stop.wait(POLL_SEC if _STATE.get("next_sweep") else 1):
        try:
            s = settings.get()
            reason = None
            if s.get("watch", True):
                fp = fingerprint()
                if fp != last_fp:
                    changed_at, last_fp = time.time(), fp       # 変わった。落ち着くまで待つ
                elif changed_at is not None:
                    reason, changed_at = "ファイルの変更", None
            if reason is None and _STATE.get("next_sweep") and datetime.now().isoformat(timespec="seconds") >= _STATE["next_sweep"]:
                reason = "定期"
            if reason and not sweep.running():
                sweep_and_notify(False, None, reason)
                last_fp = fingerprint()                         # 点検が自分で書いた分は無視する
                _STATE["last_error"] = None
        except Exception as exc:     # 常駐は止めない。理由を画面に出す
            _STATE["last_error"] = f"{type(exc).__name__}: {exc}"
            _schedule(None)


def running() -> bool:
    t = _STATE.get("thread")
    return bool(t and t.is_alive())


def start() -> None:
    with _LOCK:
        if running():
            return
        stop = threading.Event()
        t = threading.Thread(target=_loop, args=(stop,), name="pamgr-resident", daemon=True)
        _STATE.update(thread=t, stop=stop)
        t.start()


def stop() -> None:
    with _LOCK:
        ev = _STATE.get("stop")
        if ev:
            ev.set()
        _STATE.update(thread=None, stop=None, next_sweep=None)


def state() -> dict[str, Any]:
    s = settings.get()
    last = sweep.last() or {}
    from . import autostart
    return {"enabled": bool(s.get("resident_enabled")), "running": running(), "sweeping": sweep.running(),
            "last_sweep": last.get("at"), "next_sweep": _STATE.get("next_sweep") if running() else None,
            "last_reason": _STATE.get("last_reason"), "last_error": _STATE.get("last_error"),
            "open": len(inbox.items(("open",))), "remaining": (last.get("conflicts") or {}).get("remaining"),
            "settings": {k: s.get(k) for k in ("interval_min", "watch", "notify", "git_sync", "llm_budget_sec", "pair_sync_url")},
            "autostart": autostart.is_enabled()}


def configure(body: dict[str, Any]) -> dict[str, Any]:
    from . import autostart
    keys = ("resident_enabled", "interval_min", "watch", "notify", "git_sync", "llm_budget_sec", "pair_sync_url")
    vals = {k: body[k] for k in keys if k in body}
    if "enabled" in body:
        vals["resident_enabled"] = bool(body["enabled"])
    if vals:
        settings.put(vals)
    if "autostart" in body:
        if body["autostart"]:
            autostart.enable()
        else:
            autostart.disable()
    if settings.get().get("resident_enabled"):
        start()
    else:
        stop()
    return state()

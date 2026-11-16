"""API の口。中身の無い口は「未実装」を返す（落とさない・黙らない）。

応答の形:
  実装済み: {"implemented": true, ...}
  失敗:     HTTP 4xx/5xx {"implemented": true, "error": "<理由>"}
  未実装:   {"implemented": false, "message": "未実装", "feature": "<口の名前>"}
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from . import __version__, changes, checks, conflicts, decide, distribute, fleet, generalize, gitsync, inbox, jobs, llm, managed, resident, settings, situations, status, survey, sweep, targets
from .paths import data_home, master_root

router = APIRouter()


def not_implemented(feature: str) -> dict[str, Any]:
    return {"implemented": False, "message": "未実装", "feature": feature}


def safe(fn: Callable[..., dict[str, Any]]) -> Callable[..., Any]:
    """利用者の入力の誤り（無い・空・重複）は 400、それ以外は 500 で理由を返す。"""

    @functools.wraps(fn)
    def wrap(*a: Any, **kw: Any) -> Any:
        try:
            return {"implemented": True, **fn(*a, **kw)}
        except NotImplementedError as exc:      # 中身の無い分岐は「未実装」
            return not_implemented(str(exc) or fn.__name__)
        except (ValueError, KeyError, FileExistsError, llm.LLMNotConfigured) as exc:
            msg = exc.args[0] if exc.args else str(exc)
            return JSONResponse({"implemented": True, "error": str(msg)}, status_code=400)
        except Exception as exc:
            return JSONResponse({"implemented": True, "error": f"{type(exc).__name__}: {exc}"}, status_code=500)

    return wrap


# ---------------------------------------------------------------- 全体
@router.get("/health")
def health() -> dict[str, Any]:
    return {"implemented": True, "version": __version__, "master_root": str(master_root()), "data_home": str(data_home())}


@router.get("/dashboard")
@safe
def dashboard() -> dict[str, Any]:
    summ = status.summary()
    drift = sum(v for t in summ for k, v in t["counts"].items() if k not in ("same", "missing", "extra"))
    sv = survey.load()
    ck = checks.load()
    red, cf = ck.get("redundancy") or {}, ck.get("conflict") or {}
    findings = len(red.get("exact", [])) + len(red.get("variants", [])) + len(red.get("near", [])) + \
        sum(1 for p in cf.get("pairs", []) if p.get("relation") in ("conflict", "context_dependent", "duplicate", "subsumes"))
    notes = []
    if not summ:
        notes.append("配布先が登録されていません。「配布先（探索・登録）」から始めてください。")
    if not (master_root() / "external" / "pair-agent-skills" / ".git").exists():
        notes.append("マスターの external/pair-agent-skills（ペア固有スキル）が空です。ユーザー固有の照合・昇格には git submodule update --init が要ります。")
    return {"stats": {"targets": len(summ), "drift": drift, "units": len(sv["units"]) if sv else None,
                      "findings": findings if ck else None, "situations": len(situations.load())}, "notes": notes}


# ---------------------------------------------------------------- 配布先（探索・登録）
@router.get("/targets")
@safe
def list_targets() -> dict[str, Any]:
    return {"targets": targets.list_targets()}


@router.post("/targets/discover")
@safe
def discover_targets(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    s = settings.get()
    roots = body.get("roots") or s["scan_roots"]
    return {"candidates": targets.discover(roots, int(body.get("depth") or s["scan_depth"])), "roots": roots}


@router.post("/targets")
@safe
def register_target(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    items = body.get("targets") or ([body] if body.get("path") else [])
    if not items:
        raise ValueError("登録するものが無い")
    added, ts = targets.register(items)
    return {"added": added, "targets": ts}


@router.delete("/targets/{target_id}")
@safe
def unregister_target(target_id: str) -> dict[str, Any]:
    if not targets.unregister(target_id):
        raise KeyError(f"配布先が無い: {target_id}")
    return {"removed": target_id}


# ---------------------------------------------------------------- 配布状況・差分
@router.get("/status")
@safe
def status_all() -> dict[str, Any]:
    return {"targets": status.summary()}


@router.get("/status/{target_id}")
@safe
def status_target(target_id: str) -> dict[str, Any]:
    t = targets.get_target(target_id)
    if t is None:
        raise KeyError(f"配布先が無い: {target_id}")
    return {"target": t, "files": status.target_files(t)}


@router.get("/diff")
@safe
def diff(target_id: str, rel: str) -> dict[str, Any]:
    return status.diff(target_id, rel)


@router.post("/status/adopt")
@safe
def adopt(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return status.adopt(body["target_id"], body["rel"])


# ---------------------------------------------------------------- サーベイ
@router.post("/survey/run")
@safe
def survey_run() -> dict[str, Any]:
    data = survey.run()
    return {"summary": survey.summarize(data), "units": [survey.public(u) for u in data["units"]]}


@router.get("/survey")
@safe
def survey_get() -> dict[str, Any]:
    data = survey.load()
    if not data:
        raise ValueError("まだサーベイしていません。「収集を実行」を押してください")
    return {"summary": survey.summarize(data), "units": [survey.public(u) for u in data["units"]]}


@router.get("/survey/unit/{unit_id}")
@safe
def survey_unit(unit_id: str) -> dict[str, Any]:
    u = survey.get_unit(unit_id)
    if u is None:
        raise KeyError(f"単位が無い: {unit_id}")
    return {"unit": u}


# ---------------------------------------------------------------- 検査（冗長・矛盾）
@router.post("/checks/run")
@safe
def checks_run(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    mode = body.get("mode", "redundancy")
    units = checks.units_or_raise()
    if mode == "redundancy":
        jid = jobs.start("redundancy", lambda p: (p(0, 1, "文字の類似を計算中"), checks.run_redundancy(units), p(1, 1, "完了")))
    elif mode == "conflict":
        limit = max(1, int(body.get("limit") or 20))
        llm._model("judge", body.get("model"))  # モデル未設定はここで 400 にする
        jid = jobs.start("conflict", lambda p: checks.run_conflict(units, limit, p, body.get("model")))
    else:
        raise ValueError(f"検査の種類が不明: {mode}")
    return {"job_id": jid}


@router.get("/checks")
@safe
def checks_get() -> dict[str, Any]:
    return checks.load()


@router.get("/jobs/{job_id}")
@safe
def job_get(job_id: str) -> dict[str, Any]:
    j = jobs.get(job_id)
    if j is None:
        raise KeyError(f"仕事が無い: {job_id}")
    return j


# ---------------------------------------------------------------- 状況定義
@router.get("/situations")
@safe
def situations_get() -> dict[str, Any]:
    return {"situations": situations.load(), "path": str(situations.path())}


@router.post("/situations")
@safe
def situations_put(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return {"situations": situations.save_one(body)}


# ---------------------------------------------------------------- 一般化
@router.post("/generalize")
@safe
def generalize_run(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return generalize.run(body["unit_id"], body.get("model"))


@router.post("/generalize/promote")
@safe
def generalize_promote(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    p = generalize.promote(body["text"], body.get("scope", "user"), body.get("name", ""), bool(body.get("overwrite")))
    return {"written": str(p)}


# ---------------------------------------------------------------- 再配布
@router.post("/distribute/plan")
@safe
def distribute_plan(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return distribute.plan(body.get("scope", "global"), list(body.get("target_ids") or []))


@router.post("/distribute/apply")
@safe
def distribute_apply(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return distribute.apply(body["plan_id"], list(body.get("action_ids") or []))


# ---------------------------------------------------------------- 常駐と点検（docs/usecases.md §2）
@router.get("/resident")
@safe
def resident_get() -> dict[str, Any]:
    return resident.state()


@router.put("/resident")
@safe
def resident_put(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """常駐の入り切り・ログオン起動・点検の間隔・監視・通知・GitHub 同期。"""
    return resident.configure(body)


def start_sweep(dry_run: bool) -> str:
    if sweep.running():
        raise ValueError("点検はいま走っています")
    return jobs.start("sweep-preview" if dry_run else "sweep", lambda p: resident.sweep_and_notify(dry_run, p, "手動"))


@router.post("/sweep")
@safe
def sweep_start(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """点検を始める。dry_run=true は予行（計画だけ・何も書かない）。"""
    return {"job_id": start_sweep(bool(body.get("dry_run")))}


@router.get("/sweep")
@safe
def sweep_get() -> dict[str, Any]:
    return {"last": sweep.last(), "preview": sweep.preview(), "running": sweep.running()}


# ---------------------------------------------------------------- 判断待ち（UC1・J1〜J4）
@router.get("/inbox")
@safe
def inbox_get() -> dict[str, Any]:
    return {"items": inbox.items()}


@router.post("/inbox/{item_id}/draft")
@safe
def inbox_draft(item_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """J1 の文案（AI）。師匠が直してから decide に edits を渡す。"""
    return decide.draft(item_id, str(body.get("option", "")))


@router.post("/inbox/{item_id}/summary")
@safe
def inbox_summary(item_id: str) -> dict[str, Any]:
    """J1 の A と B の違いを意味で要約する（LLM・仮説）。DIFF では見づらいときに使う。"""
    return decide.summarize_diff(item_id)


@router.post("/inbox/{item_id}/decide")
@safe
def inbox_decide(item_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    res = decide.decide(item_id, str(body.get("option", "")), body.get("edits"))
    if res.get("status") == "decided" and not sweep.running():
        res["sweep_job"] = jobs.start("sweep", lambda p: resident.sweep_and_notify(False, p, "判断の反映"))   # 判断をほかの配布先へ広げる
    return res


# ---------------------------------------------------------------- 自動でやったこと（UC2）
@router.get("/activity")
@safe
def activity_get() -> dict[str, Any]:
    last = sweep.last() or {}
    return {"events": list(reversed(changes.events()))[:500], "held": last.get("held", []), "notes": last.get("notes", []),
            "last_sweep": last.get("at")}


@router.get("/activity/{event_id}/diff")
@safe
def activity_diff(event_id: str) -> dict[str, Any]:
    return {"files": changes.diff(event_id)}


@router.post("/activity/{event_id}/undo")
@safe
def activity_undo(event_id: str) -> dict[str, Any]:
    res = changes.undo(event_id)
    managed.after_undo(res.get("refs") or {})
    decide.after_undo(res.get("refs") or {})
    return res


# ---------------------------------------------------------------- 効いている規則（UC5）・管理下（UC3）
@router.get("/effective/{target_id}")
@safe
def effective_get(target_id: str) -> dict[str, Any]:
    eff = conflicts.effective(target_id)
    hs = set(eff["hashes"])
    eff["j1"] = [i for i in inbox.items(("open", "info", "later", "decided", "dismissed"))
                 if i["kind"] == "J1" and {i["refs"]["a"]["hash"], i["refs"]["b"]["hash"]} <= hs]
    return eff


@router.get("/managed")
@safe
def managed_get() -> dict[str, Any]:
    return managed.overview()


@router.post("/managed/{target_id}/exclude")
@safe
def managed_exclude(target_id: str) -> dict[str, Any]:
    if targets.get_target(target_id) is None:
        raise KeyError(f"配布先が無い: {target_id}")
    return {"event": managed.exclude(target_id, "師匠が管理から外した。二度と自動で入れない")}


@router.post("/managed/unexclude")
@safe
def managed_unexclude(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    inbox.unexclude(str(body["path"]))
    return {"excluded": inbox.excluded()}


# ---------------------------------------------------------------- GitHub（PC・ユーザー横断・UC4）
@router.get("/fleet")
@safe
def fleet_get() -> dict[str, Any]:
    st = fleet.status(fetch=True)
    return {"status": st, "tool_written": [x for x in gitsync.tool_written() if x in set(st.get("dirty") or [])],
            "sync": settings.get().get("git_sync"), "last": (sweep.last() or {}).get("git")}


@router.post("/fleet/publish")
@safe
def fleet_publish() -> dict[str, Any]:
    """この PC でツールが書いた変更（マスターの規則）だけを commit・push する。"""
    return {"publish": gitsync.publish_step("- 手動で出した")}


@router.post("/fleet/pull")
@safe
def fleet_pull() -> dict[str, Any]:
    """pull して点検する（ほかの PC の変更をこの PC へ配る）。点検は GitHub の段で pull する。"""
    return {"job_id": start_sweep(False)}


# ---------------------------------------------------------------- 設定・LLM
@router.get("/settings")
@safe
def settings_get() -> dict[str, Any]:
    return {"settings": settings.get()}


@router.put("/settings")
@safe
def settings_put(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return {"settings": settings.put(body)}


@router.get("/llm/models")
@safe
def llm_models(base_url: str = "") -> dict[str, Any]:
    url, models = llm.list_models(base_url or None)
    return {"base_url": url, "models": models}


@router.post("/llm/test")
@safe
def llm_test(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return llm.ping(body.get("model") or None, body.get("base_url") or None)

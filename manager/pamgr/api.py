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

from . import __version__, checks, distribute, generalize, jobs, llm, settings, situations, status, survey, targets
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


# ---------------------------------------------------------------- GitHub（PC・ユーザー横断）
@router.get("/fleet")
def fleet_get() -> dict[str, Any]:
    return not_implemented("fleet.get")


@router.post("/fleet/publish")
def fleet_publish() -> dict[str, Any]:
    return not_implemented("fleet.publish")


@router.post("/fleet/pull")
def fleet_pull() -> dict[str, Any]:
    return not_implemented("fleet.pull")


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

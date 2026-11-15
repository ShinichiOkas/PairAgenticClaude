"""API の口（骨格）。中身の無い口は「未実装」を返す（落とさない・黙らない）。

応答の形:
  実装済み: {"implemented": true, ...}
  未実装:   {"implemented": false, "message": "未実装", "feature": "<口の名前>"}
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from . import __version__
from .paths import data_home, master_root

router = APIRouter()


def not_implemented(feature: str) -> dict[str, Any]:
    return {"implemented": False, "message": "未実装", "feature": feature}


# ---------------------------------------------------------------- 全体
@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "implemented": True,
        "version": __version__,
        "master_root": str(master_root()),
        "data_home": str(data_home()),
    }


@router.get("/dashboard")
def dashboard() -> dict[str, Any]:
    return not_implemented("dashboard")


# ---------------------------------------------------------------- 配布先（探索・登録）
@router.get("/targets")
def list_targets() -> dict[str, Any]:
    return not_implemented("targets.list")


@router.post("/targets/discover")
def discover_targets(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return not_implemented("targets.discover")


@router.post("/targets")
def register_target(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return not_implemented("targets.register")


@router.delete("/targets/{target_id}")
def unregister_target(target_id: str) -> dict[str, Any]:
    return not_implemented("targets.unregister")


# ---------------------------------------------------------------- 配布状況・差分
@router.get("/status")
def status_all() -> dict[str, Any]:
    return not_implemented("status.all")


@router.get("/status/{target_id}")
def status_target(target_id: str) -> dict[str, Any]:
    return not_implemented("status.target")


@router.get("/diff")
def diff(target_id: str, rel: str) -> dict[str, Any]:
    return not_implemented("diff")


# ---------------------------------------------------------------- サーベイ
@router.post("/survey/run")
def survey_run() -> dict[str, Any]:
    return not_implemented("survey.run")


@router.get("/survey")
def survey_get() -> dict[str, Any]:
    return not_implemented("survey.get")


@router.get("/survey/unit/{unit_id}")
def survey_unit(unit_id: str) -> dict[str, Any]:
    return not_implemented("survey.unit")


# ---------------------------------------------------------------- 検査（冗長・矛盾）
@router.post("/checks/run")
def checks_run(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return not_implemented("checks.run")


@router.get("/checks")
def checks_get() -> dict[str, Any]:
    return not_implemented("checks.get")


@router.get("/jobs/{job_id}")
def job_get(job_id: str) -> dict[str, Any]:
    return not_implemented("jobs.get")


# ---------------------------------------------------------------- 状況定義
@router.get("/situations")
def situations_get() -> dict[str, Any]:
    return not_implemented("situations.get")


@router.post("/situations")
def situations_put(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return not_implemented("situations.put")


# ---------------------------------------------------------------- 一般化
@router.post("/generalize")
def generalize(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return not_implemented("generalize")


@router.post("/generalize/promote")
def generalize_promote(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return not_implemented("generalize.promote")


# ---------------------------------------------------------------- 再配布
@router.post("/distribute/plan")
def distribute_plan(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return not_implemented("distribute.plan")


@router.post("/distribute/apply")
def distribute_apply(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return not_implemented("distribute.apply")


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
def settings_get() -> dict[str, Any]:
    return not_implemented("settings.get")


@router.put("/settings")
def settings_put(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return not_implemented("settings.put")


@router.get("/llm/models")
def llm_models() -> dict[str, Any]:
    return not_implemented("llm.models")


@router.post("/llm/test")
def llm_test(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return not_implemented("llm.test")

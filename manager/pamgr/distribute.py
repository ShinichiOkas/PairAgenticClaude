"""再配布: マスター → 配布先。計画（何をどこへ）を作り、選んだ行だけを適用する。

- 一致の行は計画から外す
- 「配布先で改変」「双方で変更」「向き不明」の行は既定で選ばない（配布先の改変を黙って潰さない）
- 適用の前に、計画を作った後で配布先が変わっていないか確かめる（変わっていたら飛ばす）
- 上書きする前のファイルはデータ置き場の backups/<時刻>/ に退避する。適用した版を台帳に記録する
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from . import status, store, targets
from .paths import data_home, master_root

SELECT = {"missing": ("create", True), "master-ahead": ("update", True), "target-ahead": ("conflict", False),
          "diverged": ("conflict", False), "differs": ("conflict", False)}


def plan(scope: str, target_ids: list[str]) -> dict[str, Any]:
    if scope not in ("global", "user", "project"):
        raise ValueError(f"スコープが不明: {scope}")
    if not target_ids:
        raise ValueError("配布先を 1 つ以上選んでください")
    master = master_root()
    actions, skipped = [], 0
    for tid in target_ids:
        t = targets.get_target(tid)
        if t is None:
            raise KeyError(f"配布先が無い: {tid}")
        for r in status.target_files(t, scope):
            if r["state"] == "same":
                skipped += 1
                continue
            if r["state"] not in SELECT:
                continue
            act, sel = SELECT[r["state"]]
            dest = Path(t["path"]) / r["dest_rel"]
            actions.append({"id": uuid.uuid4().hex[:8], "target_id": tid, "target_name": t["name"], "src_rel": r["src_rel"],
                            "dest_rel": r["dest_rel"], "dest_path": str(dest), "src_path": str(master / r["src_rel"]),
                            "action": act, "state": r["state"], "selected_default": sel,
                            "target_hash": status.file_hash(dest) if dest.is_file() else None})
    pid = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    p = {"plan_id": pid, "scope": scope, "created_at": store.now_iso(), "actions": actions, "skipped_same": skipped}
    store.save(f"plans/{pid}.json", p)
    return p


def apply(plan_id: str, action_ids: list[str]) -> dict[str, Any]:
    p = store.load(f"plans/{plan_id}.json", None)
    if p is None:
        raise KeyError(f"計画が無い: {plan_id}")
    chosen = [a for a in p["actions"] if a["id"] in set(action_ids)]
    if not chosen:
        raise ValueError("適用する行が選ばれていない")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = data_home() / "backups" / stamp
    applied, skipped = [], []
    for a in chosen:
        src, dest = Path(a["src_path"]), Path(a["dest_path"])
        now_hash = status.file_hash(dest) if dest.is_file() else None
        if now_hash != a["target_hash"]:
            skipped.append({**a, "reason": "計画の後で配布先が変わった（計画を作り直してください）"})
            continue
        if not src.is_file():
            skipped.append({**a, "reason": "マスターのファイルが無い"})
            continue
        if dest.is_file():
            b = backup / a["target_id"] / a["dest_rel"]
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, b)
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        dest.write_bytes(data)
        status.record_ledger(a["target_id"], a["dest_rel"], hashlib.sha1(data).hexdigest())
        applied.append(a)
    p["applied_at"] = store.now_iso()
    p["applied"] = [a["id"] for a in applied]
    store.save(f"plans/{plan_id}.json", p)
    return {"applied": applied, "skipped": skipped, "backup_dir": str(backup) if backup.exists() else None}

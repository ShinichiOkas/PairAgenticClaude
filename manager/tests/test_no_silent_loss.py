"""丸ごと置き換えで、片側にしか無い箇所を黙って消さない（票 docs/bugs/2026-11-23-upstream-core-rules-lost-local-blocks-in-pamgr-6378f12.md）。

2026-11-17 の 6378f12 で、マスターの rules/pair-agent-core.md が別の PC の配布先の版に丸ごと置き換わり、
冒頭の「> [!IMPORTANT]」の塊 2 つと「セッションの始め」の節が消えた。冒頭の塊は節（##）の単位では見えない（冒頭は 1 つの節）。
ここでは縮めた同じ形で、点検・判断（J2）・状況画面の取り込み・publish の本文を確かめる。すべて一時フォルダの中。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import write
from pamgr import changes, decide, inbox, sections, sweep
from test_resident_git import git, remote_master  # noqa: F401  （fixture）
from test_sweep import commit_all, make_git_master, register_home

MASTER = """# Pair Agent コア動作原則

このルールは全プロジェクト・全セッションで常時適用される。

> [!IMPORTANT]
> **運転方針（2026-10-27）: 速度・回転・不停止。** 推奨で即着手し、判断は事後報告。小さく速く回す。

> [!IMPORTANT]
> **絶対的規範（2026-11-01）: AI は友であり、上位者も奴隷も居ない。** 権限は責務の実行のために取得する。

> [!IMPORTANT]
> **応答は 1 分以内・指示していないことは裏の役に（2026-11-05）** 師匠への応答は 1 分以内に返す。

## セッションの始め（主エージェント）— 自分から始めない

- セッションの始めに自分から何も始めない。ツールを 1 つも走らせない。

## Skill保存先の判断基準

- 師匠の好み・用語・境界線・プロセスルール → ペア固有側
"""

# 別の PC の配布先の版（別の系統）: 冒頭の塊 2 つと節 1 つが無く、運転方針には 11-09 の文が足してある
TARGET = """# Pair Agent コア動作原則

このルールは全プロジェクト・全セッションで常時適用される。

> [!IMPORTANT]
> **運転方針（2026-10-27）: 速度・回転・不停止。** 推奨で即着手し、判断は事後報告。小さく速く回す。いつ終わるかを時刻で宣言する（2026-11-09）。

## セッション開始時の手順（対話側）

1. `.pair-agent/` の有無を確認する。無ければ初期化する

## Skill保存先の判断基準

- 師匠の好み・用語・境界線・プロセスルール → ペア固有側
"""

LOST = ("絶対的規範", "応答は 1 分以内", "セッションの始め")
RULE = "home-claude/rules/core.md"


def _has_all(xs: list[str] | str, names: tuple[str, ...] = LOST) -> bool:
    text = "、".join(xs) if isinstance(xs, list) else xs
    return all(n in text for n in names)


def test_lost_blocks_sees_callouts_in_the_preamble() -> None:
    # 節（##）の単位では、冒頭の塊は 1 つの節にまとまっていて、消えた塊が見えない
    assert {c.anchor for c in sections.parse(MASTER)} >= {sections.PREAMBLE}
    assert "絶対的規範" not in "、".join(c.anchor for c in sections.parse(MASTER))
    lost = sections.lost_blocks(MASTER, TARGET)
    assert _has_all(lost), lost
    assert not any("運転方針" in x for x in lost), "文を足しただけの段落は消えたとみなさない"
    assert sections.lost_blocks(MASTER, MASTER + "\n## 追記\n新しい節。\n") == []


def _target_ahead(world: dict[str, Path]) -> str:
    """台帳が「マスターは最後に配った版のまま」を指す状態で、配布先だけが別の系統の版になる。"""
    m, home = world["master"], world["home"]
    write(m / RULE, MASTER)
    write(home / "rules/core.md", MASTER)
    make_git_master(m)
    tid = register_home(world)
    sweep.run(llm_budget=0)                    # 一致 → 台帳に記録
    write(home / "rules/core.md", TARGET)
    return tid


def _j2_for_rule() -> dict:
    items = [i for i in inbox.items() if i["kind"] == "J2" and i["refs"].get("rel") == "rules/core.md"]
    assert len(items) == 1, inbox.items()
    return items[0]


def test_sweep_stops_instead_of_adopting_over_master_only_blocks(world: dict[str, Path]) -> None:
    _target_ahead(world)
    res = sweep.run(llm_budget=0)
    assert (world["master"] / RULE).read_text(encoding="utf-8") == MASTER, "マスターを丸ごと置き換えない"
    assert not any(a["kind"] == "adopt" and "rules/core.md" in a["detail"] for a in res["actions"])
    it = _j2_for_rule()
    assert _has_all(it["what"]) and _has_all(it["refs"]["m_lost"])
    target_opt = next(o for o in it["options"] if o["id"] == "target")
    assert "消える" in target_opt["label"]


def test_first_meeting_without_ledger_names_the_losses(world: dict[str, Path]) -> None:
    m, home = world["master"], world["home"]
    make_git_master(m)
    write(m / RULE, MASTER)
    commit_all(m, "v2")
    write(home / "rules/core.md", TARGET)
    register_home(world)
    sweep.run(llm_budget=0)
    it = _j2_for_rule()
    assert _has_all(it["what"]) and (world["master"] / RULE).read_text(encoding="utf-8") == MASTER


def test_j2_target_applies_when_losses_were_shown_and_refuses_when_not(world: dict[str, Path]) -> None:
    _target_ahead(world)
    sweep.run(llm_budget=0)
    it = _j2_for_rule()
    # 消える箇所を見せていない項目（この直しの前に上げた項目）では止める
    old_refs = {k: v for k, v in it["refs"].items() if k not in ("m_lost", "t_lost")}
    inbox.update(it["id"], refs=old_refs)
    with pytest.raises(ValueError, match="消えます"):
        decide.decide(it["id"], "target")
    assert (world["master"] / RULE).read_text(encoding="utf-8") == MASTER
    # 点検し直すと消える箇所が載り、選べる（選んだのは消えると知ったうえ）
    sweep.run(llm_budget=0)
    out = decide.decide(_j2_for_rule()["id"], "target")
    assert out["status"] == "decided"
    assert (world["master"] / RULE).read_text(encoding="utf-8") == TARGET
    changes.undo(out["event"]["id"])
    assert (world["master"] / RULE).read_text(encoding="utf-8") == MASTER


def test_status_adopt_refuses_until_forced(world: dict[str, Path], client: TestClient) -> None:
    tid = _target_ahead(world)
    r = client.post("/api/status/adopt", json={"target_id": tid, "rel": "rules/core.md"})
    assert r.status_code == 400 and "消える" in r.json()["error"] and _has_all(r.json()["error"])
    assert (world["master"] / RULE).read_text(encoding="utf-8") == MASTER
    r = client.post("/api/status/adopt", json={"target_id": tid, "rel": "rules/core.md", "force": True})
    assert r.status_code == 200 and (world["master"] / RULE).read_text(encoding="utf-8") == TARGET


def test_publish_body_names_files_written_by_earlier_decisions(remote_master: dict[str, Path]) -> None:  # noqa: F811
    m, home = remote_master["master"], remote_master["home"]
    write(m / RULE, MASTER)
    write(home / "rules/core.md", MASTER)
    git(m, "add", "-A"); git(m, "commit", "-q", "-m", "rules"); git(m, "push", "-q")
    sweep.run(llm_budget=0)
    write(home / "rules/core.md", TARGET)
    sweep.run(llm_budget=0)
    decide.decide(_j2_for_rule()["id"], "target")          # 点検の外の判断がマスターを書く
    sweep.run(llm_budget=0)                                 # 次の点検の publish がそのファイルを入れる
    body = git(remote_master["bare"], "log", "-1", "--format=%B", "main")
    assert "home-claude/rules/core.md" in body and "判断: 配布先の版をマスターへ" in body, body

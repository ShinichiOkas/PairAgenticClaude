# BUG-20261124-12: tests/skills/test_w6_flow.py::test_survey_project が存在しないスクリプトを開く

- 起票日: 2026-11-24
- 状態: fixed（2026-11-24。対処は末尾）
- 分類: 試験

## 症状（見たことだけ）

- `python -m pytest tests -q` で 1 件赤: `tests/skills/test_w6_flow.py::test_survey_project` が `FileNotFoundError: home-claude/skills/project-start-existing/scripts/survey_project.py`。
- `home-claude/skills/` に `project-start-existing/` は無い（`git ls-files home-claude/skills/project-start-existing` は空）。
- ペア固有の配り道の修理（BUG-20261124-11）とは無関係の差分で再現（その修理は install・tools・manager・README だけ）。

## 対処（2026-11-24）

- 原因: 試験が古い。`project-start-existing`（と `project-start-empty`）は師匠の指示（2026-11-05「一分で応答が得られないシステムは無価値だ。それを邪魔するフックやらスキルやらは消しとけ」）でコミット d5e28ce が消した。試験だけが残っていた。スクリプトの移動ではない（`home-claude/skills/` のどこにも `survey_project.py` は無い）。
- 直し: `tests/skills/test_w6_flow.py` から `test_survey_project`（と節の見出し）を削除し、冒頭の説明から `project-start-existing` を外した。消えたスキルの試験なので復活させない。
- 確かめ: `tests/skills/test_w6_flow.py` 緑。
- 同日に前の役が見た pamgr の `test_configure_autostart_and_resident` の PermissionError は、`manager/.venv`（omni_ai 入り）で単独・全 69 件とも緑で再現せず。前の役はシステムの python に omni_ai の stub を当てて回しており、その環境の産物とみられる（コードの欠陥ではない）。

# BUG-20261124-12: tests/skills/test_w6_flow.py::test_survey_project が存在しないスクリプトを開く

- 起票日: 2026-11-24
- 状態: open
- 分類: 試験

## 症状（見たことだけ）

- `python -m pytest tests -q` で 1 件赤: `tests/skills/test_w6_flow.py::test_survey_project` が `FileNotFoundError: home-claude/skills/project-start-existing/scripts/survey_project.py`。
- `home-claude/skills/` に `project-start-existing/` は無い（`git ls-files home-claude/skills/project-start-existing` は空）。
- ペア固有の配り道の修理（BUG-20261124-11）とは無関係の差分で再現（その修理は install・tools・manager・README だけ）。

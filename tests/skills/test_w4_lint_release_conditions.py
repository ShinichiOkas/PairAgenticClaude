import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w4_load import load

m = load("解除条件の書き方", "lint_release_conditions.py")

TABLE = """# 観測項目

| 項目 | 解除条件 | 判定者 | 期限 | 解除時の動作 |
|---|---|---|---|---|
| A | エラー率が 7 日間 0.1% 未満 | 運用担当 | 2026-12-01 | 本番へ昇格 |
| B | 様子を見る | 運用担当 | 2026-12-01 | 昇格 |
| C | 安定したら | | | |
| D | 全ジョブが成功 | 開発 | 2026-09-01 | 閉じる |
"""
NOW = dt.date(2026, 10, 27)


def levels(probs):
    return sorted(lv for lv, _ in probs)


def test_table_lint():
    rows = {r["項目"]: m.lint_row(r, NOW) for r in m.parse_tables(TABLE)}
    assert rows["A"] == []
    assert any("曖昧語" in msg for _, msg in rows["B"])
    assert levels(rows["C"]) == ["error", "error", "error", "warn"]  # 判定者・期限・動作が無い + 述語に見えない
    assert levels(rows["D"]) == ["warn"] and "期限" in rows["D"][0][1]


def test_template_is_rejected_until_filled(tmp_path):
    rows = m.parse_tables(m.TEMPLATE)
    assert len(rows) == 1
    assert all(lv == "error" for lv, _ in m.lint_row(rows[0], NOW))


def test_cli(tmp_path):
    p = tmp_path / "o.md"
    p.write_text(TABLE, encoding="utf-8")
    assert m.main([str(p), "--now", "2026-10-27"]) == 1
    p.write_text(TABLE.split("| B")[0], encoding="utf-8")
    assert m.main([str(p), "--now", "2026-10-27"]) == 0
    p.write_text("表なし", encoding="utf-8")
    assert m.main([str(p)]) == 2
    assert m.main(["template"]) == 0


def test_json_input(tmp_path):
    p = tmp_path / "o.json"
    p.write_text('[{"項目":"X","解除条件":"件数 0 以下","判定者":"A","期限":"2026-12-31","解除時の動作":"閉じる"}]',
                 encoding="utf-8")
    assert m.main([str(p)]) == 0

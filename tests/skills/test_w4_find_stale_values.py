import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w4_load import load

m = load("記録の腐敗の検出", "find_stale_values.py")
NOW = dt.date(2026, 10, 27)


def test_untimed_and_old_and_fresh():
    text = (
        "前回の観測ではエラー率 0.1% だった。\n\n"
        "2026-09-01 に計測: 成功 41 行 / 失敗 60 行\n\n"
        "2026-10-26 に計測: p95 は 120ms\n\n"
        "```\n99% (コード内は見ない)\n```\n\n"
        "5 分前に書いた値: 30件\n"
    )
    fs = m.scan_text(text, NOW, 30)
    assert [(f["line"], f["kind"]) for f in fs] == [(1, "時刻なし"), (3, "古い")]
    assert fs[1]["age_days"] == 56
    assert fs[1]["values"] == ["41 行", "60 行"]


def test_date_digits_not_taken_as_value():
    assert m.scan_text("2026年9月1日 に確認した\n", NOW, 30) == []


def test_block_scope_date_covers_neighbors():
    text = "## 結果 (2026-10-20)\n- 失敗率 2%\n- 件数 10件\n"
    assert m.scan_text(text, NOW, 30) == []


def test_age_boundary():
    # ちょうど 30 日前は古くない、31 日前は古い
    assert m.scan_text("2026-09-27 に 5件\n", NOW, 30) == []
    assert len(m.scan_text("2026-09-26 に 5件\n", NOW, 30)) == 1


def test_cli(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("成功率 99%\n", encoding="utf-8")
    assert m.main([str(f), "--now", "2026-10-27"]) == 1
    f.write_text("確認済み\n", encoding="utf-8")
    assert m.main([str(f), "--now", "2026-10-27"]) == 0
    assert m.main([str(tmp_path / "none.md")]) == 2

"""復唱・確認 の武器（restate_check.py / correction_log.py）のテスト。"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parents[2] / "skills" / "scripts" / "復唱・確認"


def load(name):
    spec = importlib.util.spec_from_file_location(name, D / f"{name}.py")
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rc = load("restate_check")
cl = load("correction_log")

ORIG = "ログはこんな感じで出してほしい。結果が出るようにしてくれ。"


def test_verbatim_copy_is_suspected():
    r = rc.analyze(ORIG, ORIG)
    assert r["ratio"] == 1.0
    assert any("逐語率" in f for f in r["findings"])


def test_rephrase_is_not_flagged_for_ratio_and_has_negative():
    rest = "つまり、処理の経過を後から追える記録を残す、という理解でよいですか。画面表示は含まないという理解でよいですか。"
    r = rc.analyze(ORIG, rest)
    assert r["ratio"] < 0.2
    assert r["has_negative"]
    assert r["findings"] == []


def test_missing_negative_is_flagged():
    r = rc.analyze(ORIG, "処理の経過を後から追える記録を残す、ということですね。")
    assert any("含まないもの" in f for f in r["findings"])


def test_quote_of_original_is_flagged():
    r = rc.analyze(ORIG, "「結果が出るようにしてくれ」ということですね。含まないものはない。")
    assert r["quoted_verbatim"]


def test_cli_exit_codes(tmp_path):
    o, s = tmp_path / "o.txt", tmp_path / "s.txt"
    o.write_text(ORIG, encoding="utf-8")
    s.write_text(ORIG, encoding="utf-8")
    assert rc.main([str(o), str(s)]) == 0
    assert rc.main([str(o), str(s), "--strict"]) == 1
    assert rc.main([str(o), str(tmp_path / "none.txt")]) == 2


def test_correction_log_preview_does_not_write(tmp_path, capsys):
    out = tmp_path / "c.md"
    assert cl.main(["--restated", "XですかY", "--correction", "いや、Zだ"]) == 0
    assert not out.exists()
    assert "いや、Zだ" in capsys.readouterr().out


def test_correction_log_appends_and_numbers(tmp_path):
    out = tmp_path / "c.md"
    cl.main(["--restated", "a", "--correction", "訂正1", "--out", str(out), "--date", "2026-10-27"])
    first = out.read_text(encoding="utf-8")
    cl.main(["--restated", "b", "--correction", "訂正2\n二行目", "--out", str(out)])
    text = out.read_text(encoding="utf-8")
    assert text.startswith(first)  # 既存部分は書き換えない
    assert "## 訂正 1" in text and "## 訂正 2" in text
    assert "  > 訂正2\n  > 二行目" in text
    assert "日付: 2026-10-27" in text


def test_correction_log_deterministic(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    for p in (a, b):
        cl.main(["--restated", "r", "--correction", "c", "--out", str(p)])
    assert a.read_bytes() == b.read_bytes()
    assert cl.main(["--restated", "r", "--correction", " "]) == 2

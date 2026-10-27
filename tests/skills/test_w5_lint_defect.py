import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def load(skill, name):
    p = ROOT / "skills" / "scripts" / skill / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"w5_{name}", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


ld = load("症状の記述", "lint_defect")

GOOD = """# 保存ボタンを押すと 500 が返る

## 症状
設定画面で保存を押すと HTTP 500 が返った。

## 期待した結果
200 が返る。

## 実際の結果（実測）
HTTP 500 、応答時間 3012ms。

## 再現手順
1. 設定画面を開く 2. 保存を押す

## 証拠
ログ raw/log/01_app.log

## タイムライン
09:00 事象 / 09:10 採取

## 推測
原因は null の設定値かもしれない。修正すべきは設定ローダ。
"""


def codes(text):
    return {(i["severity"], i["code"]) for i in ld.lint(text)}


def test_good_ticket_has_no_issue():
    assert ld.lint(GOOD) == []


def test_diagnosis_in_subject_is_error():
    t = GOOD.replace("保存ボタンを押すと 500 が返る", "たぶんローダが原因で保存できない")
    assert ("error", "subject-diagnosis") in codes(t)


def test_diagnosis_in_fact_section_is_warned_but_not_in_speculation():
    t = GOOD.replace("200 が返る。", "200 が返る。原因はローダのはず。")
    found = [i for i in ld.lint(t) if i["code"] == "diagnosis-in-fact"]
    assert len(found) == 1 and "期待" in found[0]["message"]


def test_explicit_speculation_prefix_is_exempt():
    t = GOOD.replace("200 が返る。", "200 が返る。\n- 推測: 原因はローダ")
    assert not [i for i in ld.lint(t) if i["code"] == "diagnosis-in-fact"]


def test_missing_measurement_section_is_error():
    t = GOOD.replace("## 実際の結果（実測）\nHTTP 500 、応答時間 3012ms。\n\n", "")
    assert ("error", "missing-section") in codes(t)


def test_measurement_without_number_is_warned():
    t = GOOD.replace("HTTP 500 、応答時間 3012ms。", "遅かった。")
    assert ("warn", "no-measurement") in codes(t)


def test_cli_exit_codes(tmp_path, capsys):
    p = tmp_path / "t.md"
    p.write_text(GOOD, encoding="utf-8")
    assert ld.main([str(p)]) == 0
    p.write_text("本文だけ", encoding="utf-8")
    assert ld.main([str(p)]) == 1
    assert ld.main([str(tmp_path / "none.md")]) == 2


def test_template_passes_its_own_lint(capsys):
    ld.main(["--template"])
    tpl = capsys.readouterr().out
    errs = [i for i in ld.lint(tpl) if i["severity"] == "error"]
    assert not [e for e in errs if e["code"] in ("missing-section", "subject-diagnosis")]

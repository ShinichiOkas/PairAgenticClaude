"""境界値分析 / 同値分割 の武器スクリプトのテスト。"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2] / "skills" / "scripts"


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bv = load("境界値分析/boundary_values.py", "w2_bv")
pc = load("同値分割/partition_check.py", "w2_pc")


def pts(capsys, *args):
    assert bv.main([*args, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def test_closed_interval_three_points_each_side(capsys):
    r = pts(capsys, "--range", "年齢=[0,120]")[0]["points"]
    got = {p["value"]: p["valid"] for p in r}
    assert got == {"-1": False, "0": True, "1": True, "119": True, "120": True, "121": False}


def test_open_bounds_flip_validity(capsys):
    got = {p["value"]: p["valid"] for p in pts(capsys, "--range", "n=(0,10)")[0]["points"]}
    assert got["0"] is False and got["1"] is True and got["10"] is False and got["9"] is True


def test_half_open_and_shorthand(capsys):
    got = {p["value"]: p["valid"] for p in pts(capsys, "--range", "n=[1,100)")[0]["points"]}
    assert got["100"] is False and got["99"] is True and got["1"] is True
    got = {p["value"]: p["valid"] for p in pts(capsys, "--range", "n=1..5")[0]["points"]}
    assert got["5"] is True and got["6"] is False
    got = {p["value"]: p["valid"] for p in pts(capsys, "--range", ">=3")[0]["points"]}
    assert got == {"2": False, "3": True, "4": True}
    got = {p["value"]: p["valid"] for p in pts(capsys, "--range", "<3")[0]["points"]}
    assert got == {"2": True, "3": False, "4": False}


def test_decimal_step(capsys):
    got = {p["value"]: p["valid"] for p in pts(capsys, "--range", "x=[0,1]", "--step", "0.01")[0]["points"]}
    assert got["-0.01"] is False and got["0.01"] is True and got["0.99"] is True and got["1.01"] is False


def test_length_adds_empty_and_drops_negative(capsys):
    r = pts(capsys, "--range", "名前:length=1..64")[0]["points"]
    vals = {p["value"]: p for p in r}
    assert vals["0"]["valid"] is False and "空" in vals["0"]["why"]
    assert "63" in vals and "65" in vals


def test_type_overflow_points(capsys):
    r = pts(capsys, "--range", "n=[0,10]", "--type", "int8")[0]["points"]
    vals = {p["value"]: p["valid"] for p in r}
    assert vals["127"] is False and vals["128"] is False and vals["-129"] is False


def test_unreadable_interval_stops_without_guessing(capsys):
    assert bv.main(["--range", "n=1から10"]) == 2
    assert "区間" in capsys.readouterr().err


def test_infinite_both_sides_rejected(capsys):
    assert bv.main(["--range", "[,]"]) == 2


def test_deterministic(capsys):
    a = pts(capsys, "--range", "a=[1,9]", "--range", "b=(0,5]")
    b = pts(capsys, "--range", "a=[1,9]", "--range", "b=(0,5]")
    assert a == b


# ------------------------------------------------------------ partition

def write(tmp_path, text):
    p = tmp_path / "p.txt"
    p.write_text(text, encoding="utf-8")
    return str(p)


GOOD = """# 年齢
負 | <0 | 無効 | 年齢は負にならない（仕様 3.1）
子ども | [0,17] | 有効 | 未成年料金（仕様 3.2）
大人 | [18,65] | 有効 | 通常料金
高齢 | (65,120] | 有効 | 65 超は割引
超過 | >120 | 無効 | 上限超過は拒否
"""


def test_full_cover_ok_and_representatives(tmp_path, capsys):
    assert pc.main([write(tmp_path, GOOD), "--domain", "[-10,200]", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["problems"] == []
    reps = {r["name"]: int(r["representative"]) for r in out["representatives"]}
    assert 0 <= reps["子ども"] <= 17 and 18 <= reps["大人"] <= 65 and 66 <= reps["高齢"] <= 120 and reps["負"] < 0


def test_gap_detected(tmp_path, capsys):
    t = GOOD.replace("大人 | [18,65]", "大人 | [20,65]")
    assert pc.main([write(tmp_path, t), "--domain", "[-10,200]"]) == 1
    assert "[隙間] 18..19" in capsys.readouterr().out


def test_overlap_detected(tmp_path, capsys):
    t = GOOD.replace("大人 | [18,65]", "大人 | [17,65]")
    assert pc.main([write(tmp_path, t), "--domain", "[-10,200]"]) == 1
    assert "[重なり]" in capsys.readouterr().out


def test_open_closed_boundary_is_not_a_gap(tmp_path, capsys):
    t = "a | [0,10) | 有効 | x\nb | [10,20] | 無効 | y\n"
    assert pc.main([write(tmp_path, t), "--domain", "[0,20]"]) == 0


def test_missing_rationale_and_impl_reference(tmp_path, capsys):
    t = "a | [0,10] | 有効 |\nb | [11,20] | 無効 | 実装の if 文で分岐しているから\n"
    assert pc.main([write(tmp_path, t), "--domain", "[0,20]"]) == 1
    out = capsys.readouterr().out
    assert "[根拠なし] a" in out and "[実装参照の疑い] b" in out


def test_no_invalid_class_flagged(tmp_path, capsys):
    t = "a | [0,10] | 有効 | x\n"
    assert pc.main([write(tmp_path, t), "--domain", "[0,10]"]) == 1
    assert "[無効類なし]" in capsys.readouterr().out


def test_tail_gap_to_infinity(tmp_path, capsys):
    t = "a | [0,10] | 有効 | x\nb | <0 | 無効 | y\n"
    assert pc.main([write(tmp_path, t), "--domain", ">=-5"]) == 1
    assert "11..∞" in capsys.readouterr().out


def test_bad_input_exit2(tmp_path, capsys):
    assert pc.main([write(tmp_path, "a | [0,10] | たぶん | x\n"), "--domain", "[0,10]"]) == 2
    assert pc.main([str(tmp_path / "none.txt"), "--domain", "[0,10]"]) == 2

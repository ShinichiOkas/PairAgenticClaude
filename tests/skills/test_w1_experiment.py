"""実験・計器製作系 Skill の武器スクリプト 7 本のテスト。"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2] / "skills" / "scripts"


def load(skill, name):
    spec = importlib.util.spec_from_file_location(f"w1_{name}", ROOT / skill / f"{name}.py")
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---- 測定条件の統制
def test_lint_measurements(tmp_path, capsys):
    m = load("測定条件の統制", "lint_measurements")
    f = tmp_path / "m.csv"
    f.write_text(
        "name,value,unit,conditions,group\n"
        "t,1.0,s,os=win;ver=1,a\nt,1.2,s,os=win;ver=1,a\nt,1.1,s,os=win;ver=1,a\n"
        "t,2.0,s,os=mac;ver=2,b\n"
        "u,5,,,\n", encoding="utf-8")
    assert m.main([str(f)]) == 1
    out = capsys.readouterr().out
    assert "条件なしの数値" in out and "単位なし" in out
    assert "変えた条件が 2 つ以上" in out
    assert "試行回数不足" in out  # b は n=1
    assert "n=3 mean=1.1" in out


def test_lint_measurements_clean(tmp_path):
    m = load("測定条件の統制", "lint_measurements")
    f = tmp_path / "m.csv"
    f.write_text("name,value,unit,conditions,group\n" + "".join(f"t,{v},s,os=win,a\n" for v in (1, 2, 3)), encoding="utf-8")
    assert m.main([str(f)]) == 0


# ---- 測定
def test_ledger_check(tmp_path, capsys):
    m = load("測定", "ledger_check")
    f = tmp_path / "l.csv"
    f.write_text(
        "item,kind,value,instrument,error,note\n"
        "a,measured,12.5,timer,0.1,\n"
        "b,measured,約30,timer,0.1,\n"
        "c,measured,,,,\n"  # 空欄は正常
        "d,measured,7,,,\n"
        "e,guess,1,,,\n"
        "f,estimated,3,,,\n", encoding="utf-8")
    assert m.main([str(f)]) == 1
    out = capsys.readouterr().out
    assert "測定欄に推定の語" in out and "計器なし" in out and "誤差なし" in out and "kind不正" in out
    assert "c:" not in out  # 空欄の measured は指摘しない
    assert "指摘 4 件" in out


# ---- ゼロ点
def test_zero_point_record_compare(tmp_path, capsys):
    z = load("ゼロ点の取り方", "zero_point")
    base = tmp_path / "base.json"
    cmd = ["--", sys.executable, "-c", "pass"]
    assert z.main(["record", "-n", "3", "--warmup", "0", "--cwd", str(tmp_path), "--out", str(base), *cmd]) == 0
    rec = json.loads(base.read_text(encoding="utf-8"))
    assert rec["stats"]["n"] == 3 and rec["command"][0] == sys.executable
    assert z.main(["record", "-n", "1", "--out", str(base), *cmd]) == 2  # 上書きしない
    capsys.readouterr()
    slow = ["--", sys.executable, "-c", "import time; time.sleep(0.6)"]
    assert z.main(["compare", str(base), "-n", "2", "--warmup", "0", "--cwd", str(tmp_path), *slow]) == 1
    assert "条件不一致: command" in capsys.readouterr().out


def test_zero_point_compare_logic():
    z = load("ゼロ点の取り方", "zero_point")
    env = {"python": "3", "platform": "x", "machine": "m", "cpu_count": 1, "git": {"head": None, "dirty": None}}
    b = {"command": ["x"], "environment": env, "stats": z.stats([1.0, 1.1, 0.9])}
    same = {"command": ["x"], "environment": env, "stats": z.stats([1.0, 1.0])}
    assert z.compare(b, same, 2)["verdict"] == "SAME"
    slower = {"command": ["x"], "environment": env, "stats": z.stats([2.0, 2.0])}
    assert z.compare(b, slower, 2)["verdict"] == "SLOWER"
    one = {"command": ["x"], "environment": env, "stats": z.stats([1.0])}
    assert z.compare(one, same, 2)["verdict"] == "UNKNOWN"
    # 条件（コマンド）が違えば、時間の差が閾値内でも比べない
    other = {"command": ["y"], "environment": env, "stats": z.stats([1.0, 1.0])}
    assert z.compare(b, other, 2)["verdict"] == "INVALID"


# ---- 較正
def test_calibrate(tmp_path, capsys):
    c = load("計器の較正", "calibrate")
    inst = tmp_path / "inst.py"
    inst.write_text("import sys; print(int(sys.stdin.read())*2)", encoding="utf-8")
    cases = tmp_path / "c.json"
    cases.write_text(json.dumps({"cases": [{"input": "2", "expected": "4"}, {"input": "5", "expected": 10, "tol": 0}]}))
    out = tmp_path / "cal.json"
    assert c.main([str(cases), "--out", str(out), "--", sys.executable, str(inst)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["calibrated"] is True
    assert c.main([str(cases), "--out", str(out), "--", sys.executable, str(inst)]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"cases": [{"input": "2", "expected": "5"}, {"input": "3", "expected": "6"}]}))
    assert c.main([str(bad), "--", sys.executable, str(inst)]) == 1
    one = tmp_path / "one.json"
    one.write_text(json.dumps({"cases": [{"input": "2", "expected": "4"}]}))
    assert c.main([str(one), "--", sys.executable, str(inst)]) == 1
    assert "2 点未満" in capsys.readouterr().out


def test_calibrate_nondeterministic(tmp_path):
    c = load("計器の較正", "calibrate")
    inst = tmp_path / "rnd.py"
    state = tmp_path / "n.txt"
    state.write_text("0")
    inst.write_text(f"import pathlib; p=pathlib.Path(r'{state}'); n=int(p.read_text()); p.write_text(str(n+1)); print(4 if n%2==0 else 5)")
    cases = tmp_path / "c.json"
    cases.write_text(json.dumps({"cases": [{"input": "a", "expected": "4"}, {"input": "b", "expected": "4"}]}))
    assert c.main([str(cases), "--repeat", "2", "--", sys.executable, str(inst)]) == 1


# ---- 外部契約
def test_scan_internal_deps(tmp_path, capsys):
    s = load("外部契約からの計測設計", "scan_internal_deps")
    src = tmp_path / "src"
    src.mkdir()
    (src / "engine.py").write_text("x=1")
    ins = tmp_path / "ins"
    ins.mkdir()
    (ins / "good.py").write_text("import subprocess, json\nsubprocess.run(['app','--version'])\n")
    (ins / "bad.py").write_text("import engine\nfrom engine import x\nimport sys\nsys.path.insert(0, 'src')\n"
                                "def t(monkeypatch): monkeypatch.setattr(engine,'x',2)\n")
    assert s.main([str(ins / "good.py"), "--internal-dir", str(src)]) == 0
    assert s.main([str(ins), "--internal-dir", str(src)]) == 1
    out = capsys.readouterr().out
    assert "内部モジュールの import" in out and "実装の書き換え" in out and "sys.path" in out
    assert "good.py:" not in out


# ---- 実験の設計
PLAN = "# 計画\n## 何を測るか\nQPS\n## 測定条件\n環境 win、再現手順あり\n## 判定基準\n閾値 100\n区別: できなかった / 原理的にできない\n"


def test_probe_plan(tmp_path, capsys):
    p = load("実験の設計", "probe_plan")
    plan = tmp_path / "p.md"
    plan.write_text(PLAN, encoding="utf-8")
    assert p.main(["lint", str(plan)]) == 0
    lock = tmp_path / "p.lock"
    assert p.main(["freeze", str(plan), "--out", str(lock)]) == 0
    assert p.main(["verify", str(plan), str(lock)]) == 0
    assert p.main(["freeze", str(plan), "--out", str(lock)]) == 2
    plan.write_text(PLAN + "測る対象を変えた\n", encoding="utf-8")
    assert p.main(["verify", str(plan), str(lock)]) == 1
    assert "書き換わっている" in capsys.readouterr().out


def test_probe_plan_lint_failures(tmp_path, capsys):
    p = load("実験の設計", "probe_plan")
    plan = tmp_path / "bad.md"
    plan.write_text("見積もりは 3 日。期日に間に合うよう測る\n", encoding="utf-8")
    assert p.main(["lint", str(plan)]) == 1
    out = capsys.readouterr().out
    assert "遮断語の混入" in out and "必須項目が無い" in out
    assert p.main(["freeze", str(plan), "--out", str(tmp_path / "x.lock")]) == 1
    assert not (tmp_path / "x.lock").exists()


def test_probe_plan_classify(tmp_path, capsys):
    p = load("実験の設計", "probe_plan")
    r = tmp_path / "r.md"
    r.write_text("結果: 原理的にできない。\n", encoding="utf-8")
    assert p.main(["classify", str(r)]) == 1
    r.write_text("メモリ上限 8GiB を超えるため原理的にできない。\n反証: 1GiB で足りると示されたら覆る\n", encoding="utf-8")
    assert p.main(["classify", str(r)]) == 0


# ---- 不可能性の論証
def test_bound_check(tmp_path, capsys):
    b = load("不可能性の論証", "bound_check")
    spec = {"claim": "全件メモリ展開は不可", "limit": {"name": "メモリ", "value": 8, "unit": "GiB"},
            "demand": "n*size/2**30", "vars": {"n": 2e9, "size": 16}, "best_case": {"size": 8},
            "falsifier": "n が 1e9 未満なら覆る"}
    assert b.check(spec)["verdict"] == "IMPOSSIBLE_BY_SYSTEM"  # 2e9*8/2^30=14.9 > 8
    r = b.check(spec)
    assert r["flip_thresholds_at_best_case"]["n"] == pytest.approx(8 * 2**30 / 8, rel=1e-6)
    spec2 = {**spec, "best_case": {"size": 2, "n": 1e9}}
    assert b.check(spec2)["verdict"] == "NOT_PROVEN"
    spec3 = {**spec, "vars": {"n": 1e6, "size": 16}, "best_case": {}}
    assert b.check(spec3)["verdict"] == "FEASIBLE"
    inc = {k: v for k, v in spec.items() if k not in ("falsifier", "best_case")}
    assert b.check(inc)["verdict"] == "INCOMPLETE"
    f = tmp_path / "c.json"
    f.write_text(json.dumps(spec2), encoding="utf-8")
    assert b.main([str(f)]) == 1
    assert "できなかった" in capsys.readouterr().out


def test_bound_check_rejects_unsafe_expr():
    b = load("不可能性の論証", "bound_check")
    with pytest.raises(ValueError):
        b.evaluate("__import__('os').system('x')", {})
    with pytest.raises(ValueError):
        b.evaluate("a+1", {})

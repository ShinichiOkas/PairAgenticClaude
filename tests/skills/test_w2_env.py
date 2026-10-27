"""検査実行環境の扱い / 受入検査の隔離規約 の武器スクリプトのテスト。"""
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "skills" / "scripts"


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


td = load("検査実行環境の扱い/tree_diff.py", "w2_td")
rw = load("検査実行環境の扱い/run_in_workspace.py", "w2_rw")
ci = load("受入検査の隔離規約/check_isolation.py", "w2_ci")


def make_src(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "m.py").write_text("print('hi')\n", encoding="utf-8")
    (src / "sub").mkdir()
    (src / "sub" / "a.txt").write_text("a", encoding="utf-8")
    return src


# ------------------------------------------------------------ tree_diff

def test_snapshot_diff_added_changed_removed(tmp_path, capsys):
    src = make_src(tmp_path)
    snap = tmp_path / "before.json"
    assert td.main(["snapshot", str(src), "-o", str(snap)]) == 0
    assert td.main(["diff", str(snap), str(src)]) == 0
    (src / "m.py").write_text("print('changed')\n", encoding="utf-8")
    (src / "sub" / "a.txt").unlink()
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "m.cpython-313.pyc").write_bytes(b"x")
    capsys.readouterr()
    assert td.main(["diff", str(snap), str(src), "--json"]) == 1
    d = json.loads(capsys.readouterr().out)
    assert d == {"added": ["__pycache__/m.cpython-313.pyc", "sub/"], "changed": ["m.py"], "removed": ["sub/a.txt"]}
    assert td.main(["diff", str(snap), str(src)]) == 1
    assert "[実行の副産物]" in capsys.readouterr().out


def test_snapshot_never_overwrites(tmp_path):
    src = make_src(tmp_path)
    out = tmp_path / "s.json"
    out.write_text("keep", encoding="utf-8")
    assert td.main(["snapshot", str(src), "-o", str(out)]) == 2
    assert out.read_text(encoding="utf-8") == "keep"


def test_diff_bad_input(tmp_path):
    assert td.main(["diff", str(tmp_path / "no.json"), str(tmp_path)]) == 2


# ------------------------------------------------------------ run_in_workspace

def test_dry_run_does_nothing(tmp_path, capsys):
    src = make_src(tmp_path)
    wd = tmp_path / "ws"
    assert rw.main([str(src), "--workdir", str(wd), "--", sys.executable, "m.py"]) == 0
    assert not wd.exists()
    assert "下見" in capsys.readouterr().out


def test_apply_runs_in_copy_and_leaves_source_untouched(tmp_path, capsys):
    src = make_src(tmp_path)
    (src / "w.py").write_text("open('made.log','w').write('x')\n", encoding="utf-8")
    wd = tmp_path / "ws"
    rc = rw.main([str(src), "--apply", "--workdir", str(wd), "--json", "--", sys.executable, "w.py"])
    rep = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert (wd / "made.log").exists() and not (src / "made.log").exists()
    assert rep["作業空間の差分"]["added"] == ["made.log"]
    assert rep["成果物の場所の差分"] == {"added": [], "changed": [], "removed": []}
    assert rep["実施条件"]["exit_code"] == 0 and rep["実施条件"]["workspace"] == str(wd)


def test_apply_reports_command_failure_without_restoring(tmp_path, capsys):
    src = make_src(tmp_path)
    (src / "bad.py").write_text("import sys; sys.exit(3)\n", encoding="utf-8")
    wd = tmp_path / "ws"
    rc = rw.main([str(src), "--apply", "--workdir", str(wd), "--json", "--", sys.executable, "bad.py"])
    assert rc == 0  # 成果物の場所は無傷。コマンドの失敗は報告に載る
    assert json.loads(capsys.readouterr().out)["実施条件"]["exit_code"] == 3


def test_apply_detects_write_to_source_location(tmp_path, capsys):
    src = make_src(tmp_path)
    (src / "evil.py").write_text(f"open({str(src / 'leak.txt')!r},'w').write('x')\n", encoding="utf-8")
    wd = tmp_path / "ws"
    rc = rw.main([str(src), "--apply", "--workdir", str(wd), "--json", "--", sys.executable, "evil.py"])
    rep = json.loads(capsys.readouterr().out)
    assert rc == 1 and rep["成果物の場所の差分"]["added"] == ["leak.txt"]
    assert (src / "leak.txt").exists()  # 復元しない


def test_workdir_must_be_empty_and_not_nested(tmp_path, capsys):
    src = make_src(tmp_path)
    full = tmp_path / "full"
    full.mkdir()
    (full / "x").write_text("x", encoding="utf-8")
    assert rw.main([str(src), "--apply", "--workdir", str(full), "--", sys.executable, "m.py"]) == 2
    assert rw.main([str(src), "--apply", "--workdir", str(src / "inner"), "--", sys.executable, "m.py"]) == 2
    assert (full / "x").read_text(encoding="utf-8") == "x"


def test_missing_command_and_timeout(tmp_path, capsys):
    src = make_src(tmp_path)
    assert rw.main([str(src), "--apply"]) == 2
    (src / "sl.py").write_text("import time; time.sleep(5)\n", encoding="utf-8")
    rc = rw.main([str(src), "--apply", "--workdir", str(tmp_path / "w"), "--timeout", "1", "--json", "--", sys.executable, "sl.py"])
    assert rc == 0 and json.loads(capsys.readouterr().out)["実施条件"]["timed_out"] is True


# ------------------------------------------------------------ check_isolation

GOOD_MK = """実装物_v(n) : 仕様
#   role : 構築者
#   blocks : 受入検査仕様
仕様 : 要求
実行可能物 : 実装物_v(n)
#   by : machine
受入検査仕様 : 仕様
#   blocks : 実装物, 実行可能物
設計保証 : 実装物_v(n), 仕様
#   blocks : 受入検査仕様
受入検査報告書 : 実行可能物, 受入検査仕様, 設計保証
#   blocks : 実装物
"""


def mk(tmp_path, text, name="x.mk"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def run(tmp_path, text, *extra):
    rc = ci.main([mk(tmp_path, text), "--json", *extra])
    return rc


def kinds(capsys):
    d = json.loads(capsys.readouterr().out)
    return {(x["target"], x["kind"]) for v in d.values() for x in v}


def test_isolation_good_model(tmp_path, capsys):
    assert run(tmp_path, GOOD_MK) == 0
    assert kinds(capsys) == set()


def test_isolation_impl_as_dep_and_missing_block(tmp_path, capsys):
    bad = GOOD_MK.replace("受入検査報告書 : 実行可能物,", "受入検査報告書 : 実装物_v(n), 実行可能物,").replace(
        "受入検査報告書 : 実装物_v(n), 実行可能物, 受入検査仕様, 設計保証\n#   blocks : 実装物", "受入検査報告書 : 実装物_v(n), 実行可能物, 受入検査仕様, 設計保証\n#   blocks : 仕様")
    assert run(tmp_path, bad) == 1
    ks = kinds(capsys)
    assert ("受入検査報告書", "実装物が dep") in ks and ("受入検査報告書", "遮断の欠落") in ks


def test_isolation_spec_must_block_executable_too(tmp_path, capsys):
    bad = GOOD_MK.replace("#   blocks : 実装物, 実行可能物", "#   blocks : 実装物")
    assert run(tmp_path, bad) == 1
    assert ("受入検査仕様", "遮断の欠落") in kinds(capsys)


def test_isolation_assurance_passthrough_and_missing(tmp_path, capsys):
    bad = GOOD_MK.replace("設計保証 : 実装物_v(n), 仕様\n#   blocks : 受入検査仕様", "設計保証 : 実装物_v(n), 仕様")
    assert run(tmp_path, bad) == 1
    assert ("設計保証", "設計保証が素通し") in kinds(capsys)
    gone = GOOD_MK.replace("設計保証 : 実装物_v(n), 仕様\n#   blocks : 受入検査仕様\n", "")
    assert run(tmp_path, gone) == 1
    assert ("受入検査報告書", "設計保証が無い") in kinds(capsys)


def test_isolation_detour_through_agent_relay(tmp_path, capsys):
    bad = GOOD_MK.replace("受入検査報告書 : 実行可能物,", "受入検査報告書 : 中継, 実行可能物,") + "中継 : 実装物_v(n)\n#   role : 誰か\n"
    assert run(tmp_path, bad) == 1
    assert ("受入検査報告書", "迂回路") in kinds(capsys)


def test_isolation_executable_must_be_machine_and_pure(tmp_path, capsys):
    bad = GOOD_MK.replace("実行可能物 : 実装物_v(n)\n#   by : machine", "実行可能物 : 実装物_v(n), 仕様\n#   by : agent")
    assert run(tmp_path, bad) == 1
    assert ("実行可能物", "切り出しが機械でない") in kinds(capsys)


def test_isolation_posture_smell(tmp_path, capsys):
    bad = GOOD_MK.replace("受入検査報告書 : 実行可能物, 受入検査仕様, 設計保証\n#   blocks : 実装物",
                          "受入検査報告書 : 実行可能物, 受入検査仕様, 設計保証\n#   post : ソースは見ないようにする")
    assert run(tmp_path, bad) == 1
    ks = kinds(capsys)
    assert ("受入検査報告書", "姿勢の疑い") in ks and ("受入検査報告書", "遮断の欠落") in ks


def test_isolation_impl_option_for_other_vocabulary(tmp_path, capsys):
    text = "調査結果 : 仕様\n受入検査報告書 : 提出版\n#   blocks : 調査結果\n受入検査仕様 : 仕様\n#   blocks : 調査結果\n"
    assert run(tmp_path, text) == 1
    capsys.readouterr()
    assert run(tmp_path, text, "--impl", "調査結果") == 0


def test_isolation_origin_target_skipped_and_bad_input(tmp_path, capsys):
    assert run(tmp_path, "受入検査報告書 :\n") == 0
    assert ci.main([str(tmp_path / "none.mk")]) == 2
    assert ci.main([mk(tmp_path, "# コメントだけ\n", "e.mk")]) == 2


def test_isolation_real_models_have_no_findings_except_inquiry_vocabulary(capsys):
    models = sorted((REPO / "models").glob("*.mk"))
    assert models
    for m in models:
        ci.main([str(m), "--json"])
        d = json.loads(capsys.readouterr().out)
        found = [x for v in d.values() for x in v]
        if m.name == "inquiry-small.mk":
            continue  # 実装物ではなく 調査結果 を遮断する語彙（--impl 調査結果 で検める）
        assert found == [], (m.name, found)

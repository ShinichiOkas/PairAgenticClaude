"""w8b のテスト共通: 入口（skills/scripts/<名前>/<script>.py）と中核（tools/design_graph.py）を読み込み、入口を走らせる。

入口の約束（探し方・読むだけ・終了コード 2）の検査もここに置き、入口ごとのテストから呼ぶ。
"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "tools" / "design_graph.py"
ENV = "PAIR_AGENT_DESIGN_GRAPH"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load(skill: str, script: str):
    return _load("w8b_" + script, ROOT / "skills" / "scripts" / skill / (script + ".py"))


dg = _load("w8b_design_graph", CORE)


def graph(tmp_path: Path, actor: str = "ai"):
    """試し打ちの DB（一時ディレクトリ）。"""
    return dg.DesignGraph(tmp_path / "graph.jsonl", actor=actor, clock=lambda: "2026-10-28T00:00:00Z")


def run(m, capsys, *argv):
    code = m.main([str(a) for a in argv])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def check_locator(m, tmp_path: Path, capsys, monkeypatch, db: Path) -> None:
    """探す順: 環境変数 → この場所から上の tools/ → install 先 2 か所。見つからない・古い中核は終了コード 2。"""
    monkeypatch.setenv(ENV, str(CORE))
    cands = m.core_candidates()
    assert ENV in cands[0][0] and cands[0][1] == CORE
    assert CORE in [p for _, p in cands[1:-2]]  # リポジトリ内では上へ辿って見つかる
    home = Path.home()
    assert [p for _, p in cands[-2:]] == [home / ".claude" / "pair-agent" / "tools" / "design_graph.py",
                                         home / ".gemini" / "config" / "pair-agent" / "tools" / "design_graph.py"]
    # 環境変数の指す先が無ければ、黙らずに注意を出して次を探す
    monkeypatch.setenv(ENV, str(tmp_path / "nowhere.py"))
    code, _, err = run(m, capsys, "--db", db)
    assert code in (0, 1) and "指す先が無い" in err
    monkeypatch.delenv(ENV)
    # どこにも無い → 探した場所を出して 2
    missing = tmp_path / "missing" / "design_graph.py"
    monkeypatch.setattr(m, "core_candidates", lambda: [("試し", missing)])
    code, out, err = run(m, capsys, "--db", db)
    assert code == 2 and out == "" and "探した場所" in err and str(missing) in err
    # 古い中核（API が無い）→ 2
    old = tmp_path / "old" / "design_graph.py"
    old.parent.mkdir()
    old.write_text("class DesignGraph:\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(m, "core_candidates", lambda: [("試し", old)])
    code, _, err = run(m, capsys, "--db", db)
    assert code == 2 and "古い" in err


def check_read_only(m, tmp_path: Path, capsys, db: Path) -> None:
    """読むだけ: DB を書き換えない・無い DB を作らない。壊れた DB は 2。"""
    before = db.read_bytes()
    run(m, capsys, "--db", db)
    run(m, capsys, "--db", db, "--json")
    assert db.read_bytes() == before
    none = tmp_path / "none" / "graph.sqlite"
    code, out, _ = run(m, capsys, "--db", none)
    assert code == 0 and "seq 0" in out and not none.parent.exists()
    broken = tmp_path / "broken.jsonl"
    broken.write_text("{broken\n", encoding="utf-8")
    code, _, err = run(m, capsys, "--db", broken)
    assert code == 2 and "エラー" in err

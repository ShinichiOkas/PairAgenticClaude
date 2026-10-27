"""w8a2 のテスト共通: 入口スクリプトの読み込み・設計 DB の作成・全入口に共通の確認。"""
import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = ROOT / "tools" / "design_graph.py"


def load(skill: str, script: str):
    p = ROOT / "skills" / "scripts" / skill / script
    spec = importlib.util.spec_from_file_location("w8a2_" + p.stem, p)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def core():
    spec = importlib.util.spec_from_file_location("w8a2_core", CORE_PATH)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def graph(tmp_path: Path, name: str = "g.jsonl", actor: str = "ai"):
    """(DesignGraph, DB のパス)。actor=human で決断・確定ができる。"""
    c = core()
    db = tmp_path / name
    return c.DesignGraph(db, None, actor), db


def reopen(db: Path, actor: str = "ai"):
    return core().DesignGraph(db, None, actor)


def run(m, capsys, *argv):
    rc = m.main([str(a) for a in argv])
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def run_json(m, capsys, *argv):
    rc, out, _ = run(m, capsys, *argv, "--json")
    return rc, json.loads(out)


def common_checks(m, db: Path, capsys, monkeypatch, tmp_path: Path, *extra) -> None:
    """全入口に共通: DB が無ければ 2／中核が無ければ 2／JSON が読める／SQLite でも同じ／DB を書き換えない／環境変数で中核を指せる。"""
    before = db.read_bytes()
    rc, out, err = run(m, capsys, "--db", db, *extra)
    rc_json, data = run_json(m, capsys, "--db", db, *extra)
    assert rc == rc_json and rc in (0, 1)
    assert "findings" in data
    assert db.read_bytes() == before, "入口が DB に書いた"

    rc2, _, err2 = run(m, capsys, "--db", tmp_path / "nothing.jsonl", *extra)
    assert rc2 == 2 and "DB が無い" in err2

    sq = tmp_path / "copy.sqlite"
    reopen(db).convert(sq)
    rc3, out3, _ = run(m, capsys, "--db", sq, *extra)
    assert (rc3, out3) == (rc, out), "SQLite でも同じ結果になる"

    other = tmp_path / "elsewhere" / "design_graph.py"
    other.parent.mkdir()
    shutil.copy(CORE_PATH, other)
    monkeypatch.setenv("PAIR_AGENT_DESIGN_GRAPH", str(other))
    rc4, out4, _ = run(m, capsys, "--db", db, *extra)
    assert (rc4, out4) == (rc, out)
    monkeypatch.delenv("PAIR_AGENT_DESIGN_GRAPH")

    monkeypatch.setattr(m, "core_candidates", lambda: [tmp_path / "ここには無い" / "design_graph.py"])
    rc5, _, err5 = run(m, capsys, "--db", db, *extra)
    assert rc5 == 2 and "探した場所" in err5 and "ここには無い" in err5

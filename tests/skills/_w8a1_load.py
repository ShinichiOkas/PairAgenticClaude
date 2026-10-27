"""w8a1 のテスト共通: 武器スクリプトの読み込みと、設計の因果 DB（tools/design_graph.py）の試料の作成。

DB は pytest の tmp_path にだけ作る。武器は DB を読むだけなので、各テストは「同じ DB を武器にかけても DB が変わらない」ことも確かめる。
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))
import design_graph as dg  # type: ignore[import-not-found]  # noqa: E402


def load(skill: str, script: str):
    p = ROOT / "skills" / "scripts" / skill / script
    spec = importlib.util.spec_from_file_location("w8a1_" + p.stem, p)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def clock() -> str:
    return "2026-10-28T00:00:00Z"


def db_path(tmp_path: Path, backend: str = "json") -> Path:
    return tmp_path / ("graph.jsonl" if backend == "json" else "graph.sqlite")


def graph(tmp_path: Path, actor: str = "ai", backend: str = "json") -> "dg.DesignGraph":
    return dg.DesignGraph(db_path(tmp_path, backend), backend=backend, actor=actor, clock=clock)


def chain(g: "dg.DesignGraph") -> dict:
    """関心事 → 課題 → 決定点 → 案 → 要求 → 要素 の鎖を AI が仮説で張る。"""
    g.actor = "ai"
    sh = g.add("stakeholder", "利用者")
    cn = g.add("concern", "炊き上がりまでの待ち時間", {"weight": 5})
    g.link("source", cn, sh)
    is_ = g.add("issue", "加熱が遅い")
    g.link("affects", is_, cn)
    d = g.add("decision_point", "加熱方式")
    g.link("anchors", d, is_)
    a = g.add("option", "IH", {"viewpoint": "構造"}, parent=d)
    b = g.add("option", "圧力", {"viewpoint": "制御"}, parent=d)
    c = g.add("option", "予熱", {"viewpoint": "条件"}, parent=d)
    rq = g.add("requirement", "40 分以内に炊き上がる")
    g.link("derives", a, rq)
    lc = g.add("component", "加熱")
    g.link("allocates", rq, lc)
    return {"sh": sh, "cn": cn, "is": is_, "d": d, "a": a, "b": b, "c": c, "rq": rq, "lc": lc}


def run(mod, capsys, tmp_path: Path, *args: str, backend: str = "json", as_json: bool = False):
    """武器を DB に対して走らせ、(終了コード, 標準出力（--json なら解釈済み）, 標準エラー) を返す。"""
    argv = ["--db", str(db_path(tmp_path, backend)), *args]
    if as_json:
        argv.append("--json")
    rc = mod.main(argv)
    cap = capsys.readouterr()
    return rc, (json.loads(cap.out) if as_json else cap.out), cap.err


def snapshot(tmp_path: Path, backend: str = "json") -> bytes:
    return db_path(tmp_path, backend).read_bytes()

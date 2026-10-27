import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run, run_json

m = load("課題の閉じ方", "issue_closure.py")


def build(tmp_path):
    g, db = graph(tmp_path)
    for t in ("遅い", "壊れる", "高い", "古い"):
        g.add("issue", t)
    g.add("risk", "停電")
    g.add("record", "顧客が納期遅れを受けた記録")
    return db


def test_closure_incomplete_cases(tmp_path, capsys):
    db = build(tmp_path)
    h = reopen(db, "human")
    h.close("IS1", "accepted", reason="受ける")  # 根拠なし
    h.close("IS2", "dismissed")  # reopen_if なし
    h.close("IS3", "deferred")  # resume_if なし
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1
    assert {f["target"] for f in data["findings"]} == {"IS1", "IS2", "IS3"}
    assert data["tally"]["受容"] == 1 and data["tally"]["未解決"] == 2


def test_complete_closures_are_clean_and_shown(tmp_path, capsys):
    db = build(tmp_path)
    h = reopen(db, "human")
    h.close("IS1", "accepted", evidence=["NT1"], reason="顧客が受けた")
    h.close("IS2", "dismissed", reopen_if="負荷が倍になったら")
    h.close("IS3", "deferred", resume_if="部品が入荷したら")
    h.close("IS4", "resolved")
    rc, out, _ = run(m, capsys, "--db", db)
    assert rc == 0
    assert "受けた記録: NT1" in out and "開き直す条件: 負荷が倍になったら" in out and "再開の条件: 部品が入荷したら" in out
    assert "RK1" in out


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path)
    reopen(db, "human").close("IS1", "accepted")
    common_checks(m, db, capsys, monkeypatch, tmp_path)

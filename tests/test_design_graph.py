"""tools/design_graph.py のテスト。一時ディレクトリだけに書く。

追加・結線・権限・要再確認・辿り・検出・ID の非再利用を、JSON と SQLite の両方で確かめ、
同じ操作列から **両方で同じ結果**（検出・辿り・要再確認・状況・書き出し・イベント列）になることを確かめる。
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import design_graph as dg  # noqa: E402  # pyright: ignore[reportMissingImports]

BACKENDS = ["json", "sqlite"]


def clock() -> str:
    return "2026-10-27T00:00:00Z"


def db_path(tmp_path: Path, backend: str) -> Path:
    return tmp_path / ("graph.jsonl" if backend == "json" else "graph.sqlite")


def open_graph(tmp_path: Path, backend: str, actor: str = "ai") -> dg.DesignGraph:
    return dg.DesignGraph(db_path(tmp_path, backend), backend=backend, actor=actor, clock=clock)


@pytest.fixture(params=BACKENDS)
def backend(request):
    return request.param


def ids(findings):
    return {f["id"] for f in findings}


def chain(g: dg.DesignGraph) -> dict:
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


# ---------------------------------------------------------------- ID

def test_ids_are_prefix_and_sequence(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    assert (x["sh"], x["cn"], x["is"], x["d"], x["rq"], x["lc"]) == ("SH1", "CN1", "IS1", "D1", "RQ1", "LC1")
    assert (x["a"], x["b"], x["c"]) == ("D1-A", "D1-B", "D1-C")
    assert g.add("requirement", "二つ目") == "RQ2"
    assert g.add("decision_point", "二つ目") == "D2"
    assert g.add("option", "D2 の案", parent="D2") == "D2-A"


def test_ids_are_never_reused(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    g.actor = "human"
    g.set_state(x["rq"], "retired")
    g.set_state(x["c"], "rejected")
    lid = g.link("derives", x["b"], x["lc"])
    g.set_state(lid, "retired")
    assert g.add("requirement", "次") == "RQ2"
    assert g.add("option", "次の案", parent=x["d"]) == "D1-D"
    # 開き直しても数え直さない
    g2 = open_graph(tmp_path, backend, "human")
    assert g2.add("requirement", "その次") == "RQ3"
    assert g2.add("option", "その次の案", parent=x["d"]) == "D1-E"
    new_link = g2.link("derives", x["b"], x["lc"])
    assert dg.natkey(new_link) > dg.natkey(lid) and new_link != lid
    # 廃止・却下は消さない（状態で表す）
    assert g2.get(x["rq"])["state"] == "retired" and g2.get(x["c"])["state"] == "rejected"


def test_letters_and_natural_order():
    assert [dg._letters(n) for n in (1, 26, 27, 52, 53)] == ["A", "Z", "AA", "AZ", "BA"]
    assert sorted(["RQ10", "RQ9", "RQ1"], key=dg.natkey) == ["RQ1", "RQ9", "RQ10"]


# ---------------------------------------------------------------- 権限

def test_ai_writes_only_hypotheses(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    g.actor = "human"
    nt = g.add("record", "議事録")
    g.set_state(x["is"], "confirmed")
    g.actor = "ai"
    before = g.last_seq
    denied = [
        lambda: g.add("requirement", "確定で作る", state="confirmed"),
        lambda: g.add("requirement", "根拠つきで作る", evidence=[nt]),
        lambda: g.set_state(x["rq"], "confirmed"),
        lambda: g.set_state(x["rq"], "retired"),
        lambda: g.decide(x["d"], x["a"]),
        lambda: g.close(x["is"], "resolved"),
        lambda: g.link("evidence", x["rq"], nt),
        lambda: g.link("derives", x["b"], x["rq"], state="confirmed"),
        lambda: g.update(x["is"], title="確定を AI が直す"),
        lambda: g.waive("unallocated:RQ1", "理由"),
        lambda: g.triage("L1", "ok"),
    ]
    for f in denied:
        with pytest.raises(dg.PermissionDenied):
            f()
    assert g.last_seq == before  # 拒んだ書き込みは何も残さない
    assert open_graph(tmp_path, backend).last_seq == before
    # 仮説は直せる・確定にも注記はできる（版は上がらない）
    assert g.update(x["rq"], title="40 分以内に炊ける") == 2
    g.annotate(x["is"], "AI の見立て: 原因は予熱の不足かもしれない")
    assert g.get(x["is"])["version"] == 1 and g.get(x["is"])["notes"][0]["actor"] == "ai"


def test_human_can_confirm_with_evidence(tmp_path, backend):
    g = open_graph(tmp_path, backend, "human")
    nt = g.add("record", "要求元への問い合わせ")
    rq = g.add("requirement", "確定で作る", state="confirmed", evidence=[nt])
    assert g.get(rq)["state"] == "confirmed"
    assert g.evidence_of(rq, confirmed_only=True) == [nt]
    dn = g.add("note", "自由メモ")
    with pytest.raises(dg.DesignGraphError, match="自由メモ"):
        g.set_state(rq, "confirmed", evidence=[dn])


# ---------------------------------------------------------------- 結線

def test_link_validation_and_idempotence(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    with pytest.raises(dg.DesignGraphError, match="知らないリンク"):
        g.link("causes", x["rq"], x["lc"])
    with pytest.raises(dg.NotFound):
        g.link("derives", x["rq"], "LC99")
    with pytest.raises(dg.DesignGraphError, match="自分自身"):
        g.link("derives", x["rq"], x["rq"])
    with pytest.raises(dg.DesignGraphError, match="ステークホルダ"):
        g.link("source", x["cn"], x["rq"])
    with pytest.raises(dg.DesignGraphError, match="parent"):
        g.add("option", "親なしの案")
    # 同じリンクは張り直さない（同じ ID を返し、イベントを足さない）
    seq = g.last_seq
    first = next(l["id"] for l in g.links.values() if l["kind"] == "derives")
    assert g.link("derives", x["a"], x["rq"]) == first
    assert g.last_seq == seq
    # 関連には述語。要求は関連（リンク）にも割り付けられる
    lc2 = g.add("component", "計測")
    rel = g.link("relation", x["lc"], lc2, predicate="温度を知らせる")
    rq2 = g.add("requirement", "温度を知らせる")
    g.link("allocates", rq2, rel)
    assert "unallocated:" + rq2 not in ids(g.check())
    assert {r["id"] for r in g.why(lc2)} >= {lc2, rel, rq2}


def test_option_parent_is_a_causal_link(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    contains = [l for l in g.links.values() if l["kind"] == "contains"]
    assert {(l["src"], l["dst"]) for l in contains} == {(x["d"], x["a"]), (x["d"], x["b"]), (x["d"], x["c"])}


# ---------------------------------------------------------------- 要再確認・仕分け

def test_recheck_is_one_step_only(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    assert g.recheck() == []
    g.update(x["cn"], attrs={"weight": 4})
    marks = g.recheck()
    assert [(m["upstream"], m["downstream"], m["seen"], m["current"]) for m in marks] == [(x["cn"], x["is"], 1, 2)]
    # 印は保存しない: 開き直しても同じ計算になる
    assert open_graph(tmp_path, backend).recheck() == marks
    g.update(x["d"], title="加熱の方式")
    downs = sorted(m["downstream"] for m in g.recheck())
    assert downs == sorted([x["is"], x["a"], x["b"], x["c"]])  # 決定点の一段先（案）まで。要求・要素には付かない


def test_triage_ok_and_issue(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    g.update(x["cn"], attrs={"weight": 4})
    g.update(x["a"], attrs={"cost": "高い"})
    m_cn, m_a = sorted(g.recheck(), key=lambda m: m["upstream"])
    with pytest.raises(dg.PermissionDenied):
        g.triage(m_cn["link"], "ok")
    g.actor = "human"
    with pytest.raises(dg.DesignGraphError, match="印は無い"):
        g.triage("L1", "ok")
    assert g.triage(m_cn["link"], "ok", note="重みが下がっても課題は残る") is None
    issue = g.triage(m_a["link"], "issue", "IH のコストが要求を揺らす")
    assert issue == "IS2"
    assert g.recheck() == []
    n = g.get(issue)
    assert n["state"] == "hypothesis" and n["attrs"]["origin"] == "triage" and n["attrs"]["downstream"] == x["rq"]
    assert [t["outcome"] for t in g.triages] == ["ok", "issue"]
    assert issue in g.status()["open_issues"]
    # 仕分けは記録に残り、開き直しても印は戻らない
    g2 = open_graph(tmp_path, backend)
    assert g2.recheck() == [] and len(g2.triages) == 2
    # 上流がまた変われば、また一段先だけに印
    g.update(x["cn"], attrs={"weight": 3})
    assert [m["downstream"] for m in g.recheck()] == [x["is"]]


def test_evidence_change_marks_the_confirmed_node(tmp_path, backend):
    g = open_graph(tmp_path, backend, "human")
    nt = g.add("record", "議事録 第 1 回")
    rq = g.add("requirement", "要求", state="confirmed", evidence=[nt])
    g.update(nt, attrs={"corrected": "議事録の訂正"})
    assert [(m["kind"], m["downstream"]) for m in g.recheck()] == [("evidence", rq)]


# ---------------------------------------------------------------- 辿り

def test_why_walks_upstream_with_evidence(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    g.actor = "human"
    nt = g.add("record", "設計会議の議事録")
    g.decide(x["d"], x["a"], evidence=[nt], conditions=["家庭用 100V"])
    rows = g.why(x["lc"])
    assert [r["id"] for r in rows] == [x["lc"], x["rq"], x["a"], x["d"], x["is"], x["cn"]]
    assert [r["depth"] for r in rows] == [0, 1, 2, 3, 4, 5]
    assert [r["via"] for r in rows] == [None, "allocates", "derives", "contains", "anchors", "affects"]
    assert next(r for r in rows if r["id"] == x["d"])["evidence"] == [nt]
    assert [r["id"] for r in g.why(x["lc"], depth=2)] == [x["lc"], x["rq"], x["a"]]


def test_impact_walks_downstream(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    rows = g.impact(x["cn"])
    assert [r["id"] for r in rows] == [x["cn"], x["is"], x["d"], x["a"], x["rq"], x["lc"], x["b"], x["c"]]
    assert [r["id"] for r in g.impact(x["rq"])] == [x["rq"], x["lc"]]
    with pytest.raises(dg.NotFound):
        g.impact("RQ99")


# ---------------------------------------------------------------- 検出

def test_check_rules_fire_and_clear(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    cn2 = g.add("concern", "電力量")                                    # no_source・no_weight
    qs = g.add("qas", "炊飯の区間", {"source": "利用者", "stimulus": "炊飯開始", "environment": "室温 10℃",
                                    "artifact": "炊飯器", "response": "炊き上がる"})  # measure 欠け
    rq2 = g.add("requirement", "保温できる")                            # unallocated
    lc2 = g.add("component", "孤児")                                     # orphan
    lc3 = g.add("component", "電源スイッチ", {"obvious": True})          # 自明は免除
    rel = g.link("relation", x["lc"], lc2)                               # no_predicate
    d2 = g.add("decision_point", "保温の方式")                           # orphan・few_options・undecided
    g.add("option", "保温しない", {"cons": ["冷める"]}, parent=d2)       # cons_no_origin
    rqb = g.add("requirement", "圧力に耐える")
    g.link("derives", x["b"], rqb)
    g.link("allocates", rqb, x["lc"])
    f = ids(g.check())
    for want in ("no_source:" + cn2, "no_weight:" + cn2, "qas_incomplete:" + qs, "unallocated:" + rq2,
                 "orphan:" + lc2, "no_predicate:" + rel, "orphan:" + d2, "few_options:" + d2, "undecided:" + d2,
                 "undecided:" + x["d"], "cons_no_origin:" + d2 + "-A"):
        assert want in f, want
    assert "orphan:" + lc3 not in f and "few_options:" + x["d"] not in f
    # 人が決める: 確定・決断・閉じ方
    g.actor = "human"
    nt = g.add("record", "設計会議の議事録")
    g.decide(x["d"], x["a"])                                             # 根拠・背景事情・must・検証なし
    g.set_state(x["rq"], "confirmed")                                    # 根拠なし
    rqh = g.add("requirement", "電力量を測れる")
    g.link("derives", cn2, rqh)
    g.link("allocates", rqh, x["lc"])
    g.set_state(rqh, "confirmed", evidence=[nt])                         # 上流 CN2 は仮説
    rk = g.add("risk", "部品調達")
    g.close(rk, "deferred")
    is3 = g.add("issue", "受容する課題")
    g.close(is3, "accepted")
    is4 = g.add("issue", "退ける課題")
    g.close(is4, "dismissed")
    f = ids(g.check())
    for want in ("no_evidence:" + x["d"], "no_conditions:" + x["d"], "no_must:" + x["a"], "no_verification:" + x["a"],
                 "no_evidence:" + x["rq"], "hyp_dep:" + x["d"], "hyp_dep:" + rqh, "on_dead:" + rqb,
                 "closure_incomplete:" + rk, "closure_incomplete:" + is3, "closure_incomplete:" + is4):
        assert want in f, want
    assert "undecided:" + x["d"] not in f
    # 直すと消える
    g.decide(x["d"], x["a"], evidence=[nt], conditions=["家庭用 100V"])
    g.update(x["a"], attrs={"must_not": ["圧力釜の機構を混ぜない"], "verification": {"how": "試作で計測", "when": "試作後"}})
    g.set_state(x["rq"], "confirmed", evidence=[nt])
    g.set_state(x["is"], "confirmed")
    g.set_state(x["cn"], "confirmed", evidence=[nt])
    g.set_state(rqb, "retired")
    g.close(rk, "deferred", resume_if="調達先が 2 社になったら")
    g.close(is3, "accepted", evidence=[nt])
    g.close(is4, "dismissed", reopen_if="販売地域に 200V が入ったら")
    g.update(lc2, attrs={"obvious": True})
    g.update(rel, predicate="電力を渡す")
    f = ids(g.check())
    for gone in ("no_evidence:" + x["d"], "no_conditions:" + x["d"], "no_must:" + x["a"], "no_verification:" + x["a"],
                 "no_evidence:" + x["rq"], "hyp_dep:" + x["d"], "on_dead:" + rqb, "closure_incomplete:" + rk,
                 "closure_incomplete:" + is3, "closure_incomplete:" + is4, "orphan:" + lc2, "no_predicate:" + rel):
        assert gone not in f, gone
    assert "hyp_dep:" + rqh in f  # CN2 は仮説のまま
    st = g.status()
    assert st["deferred"] == [rk] and st["accepted"] == [is3]


def test_check_ids_are_stable_and_sorted(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    chain(g)
    g.add("requirement", "割り付かない 9")
    g.add("requirement", "割り付かない 10")
    a = g.check()
    assert a == g.check() == open_graph(tmp_path, backend).check()
    rules = [f["rule"] for f in a]
    assert rules == sorted(rules, key=lambda r: dg.RULE_ORDER[r])
    unalloc = [f["target"] for f in a if f["rule"] == "unallocated"]
    assert unalloc == sorted(unalloc, key=dg.natkey)
    assert all(f["id"] == f"{f['rule']}:{f['target']}" for f in a)


def test_recommended_option_needs_verification(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    g.update(x["c"], attrs={"recommended": True})
    assert "no_verification:" + x["c"] in ids(g.check())
    g.update(x["c"], attrs={"verification": "机上で電力量を見積もる"})
    assert "no_verification:" + x["c"] not in ids(g.check())


def test_excluded_options_cannot_both_be_adopted(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    d2 = g.add("decision_point", "保温の方式")
    k = g.add("option", "常時保温", parent=d2)
    g.add("option", "保温しない", parent=d2)
    ex = g.link("excludes", x["a"], k)
    g.actor = "human"
    g.decide(x["d"], x["a"])
    assert "excluded_both:" + ex not in ids(g.check())
    g.decide(d2, k)
    assert "excluded_both:" + ex in ids(g.check())


def test_qas_needs_six_elements(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    six = {"source": "利用者", "stimulus": "炊飯開始", "environment": "室温 10℃", "artifact": "炊飯器",
           "response": "炊き上がる", "response_measure": "40 分"}
    ok = g.add("qas", "そろっている", six)
    alias = g.add("qas", "measure でもよい", {**{k: v for k, v in six.items() if k != "response_measure"},
                                               "measure": "40 分"})
    bad = g.add("qas", "Source が無い", {k: v for k, v in six.items() if k != "source"})
    f = {x["id"]: x for x in g.check()}
    assert "qas_incomplete:" + ok not in f and "qas_incomplete:" + alias not in f
    assert f["qas_incomplete:" + bad]["missing"] == ["source"]


def test_few_options_counts_distinct_viewpoints(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    d = g.add("decision_point", "方式")
    for t in ("案 1", "案 2", "案 3"):
        g.add("option", t, {"viewpoint": "構造"}, parent=d)
    f = next(f for f in g.check() if f["id"] == "few_options:" + d)
    assert (f["options"], f["viewpoints"]) == (3, 1)


def test_waive_lapses_when_target_changes(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    rq = g.add("requirement", "割り付け先がまだ無い")
    fid = "unallocated:" + rq
    g.actor = "human"
    with pytest.raises(dg.DesignGraphError, match="理由"):
        g.waive(fid, " ")
    with pytest.raises(dg.DesignGraphError, match="いま出ていない"):
        g.waive("orphan:LC9", "無い")
    g.waive(fid, "二週目で割り付ける")
    assert fid not in ids(g.check())
    assert next(f for f in g.check(include_waived=True) if f["id"] == fid)["waived"] is True
    g.update(rq, title="割り付け先がまだ無い（直した）")
    assert fid in ids(g.check())


# ---------------------------------------------------------------- 決断

def test_decide_keeps_rejected_options_and_can_switch(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    g.actor = "human"
    g.decide(x["d"], x["a"])
    assert [g.get(o)["state"] for o in (x["a"], x["b"], x["c"])] == ["confirmed", "rejected", "rejected"]
    assert g.get(x["d"])["decision"]["option"] == x["a"] and g.get(x["d"])["state"] == "confirmed"
    with pytest.raises(dg.DesignGraphError, match="decide"):
        g.set_state(x["b"], "confirmed")
    g.decide(x["d"], x["b"])
    assert [g.get(o)["state"] for o in (x["a"], x["b"], x["c"])] == ["rejected", "confirmed", "rejected"]
    assert len(g.find("option")) == 3  # 却下した案も消さない（判例として残る）
    with pytest.raises(dg.DesignGraphError, match="案ではない"):
        g.decide(x["d"], "D9-A")


# ---------------------------------------------------------------- 保存と同値性

def scenario(g: dg.DesignGraph) -> dict:
    x = chain(g)
    cn2 = g.add("concern", "電力量")
    g.add("qas", "炊飯の区間", {"source": "利用者", "stimulus": "炊飯開始", "artifact": "炊飯器"})
    lc2 = g.add("component", "計測")
    g.link("relation", x["lc"], lc2, predicate="温度を知らせる")
    g.add("note", "思いつき: 予熱は電力を食う")
    g.actor = "human"
    nt = g.add("record", "設計会議 議事録 第 1 回", {"type": "議事録"})
    g.set_state(x["is"], "confirmed")
    g.set_state(x["cn"], "confirmed", evidence=[nt])
    g.decide(x["d"], x["a"], evidence=[nt], conditions=["家庭用 100V"])
    g.update(x["a"], attrs={"must": ["加熱は LC1 だけが行う"]}, append=[("must_not", "圧力の機構を混ぜない")])
    g.set_state(x["rq"], "confirmed")
    g.update(x["is"], title="加熱が遅く待たせる")
    g.annotate(x["rq"], "要求元に未確認")
    rk = g.add("risk", "IH の部品調達")
    g.close(rk, "deferred")
    g.actor = "ai"
    g.update(cn2, attrs={"weight": 3})
    return x


def projection(g: dg.DesignGraph, x: dict) -> dict:
    return {"check": g.check(include_waived=True), "recheck": g.recheck(),
            "status": {k: v for k, v in g.status().items() if k != "backend"},
            "why": g.why(x["lc"]), "impact": g.impact(x["cn"]), "export": g.export_markdown(),
            "nodes": g.find(), "links": [g.get(i) for i in sorted(g.links, key=dg.natkey)], "last_seq": g.last_seq}


def test_json_and_sqlite_give_the_same_results(tmp_path):
    out = {}
    for b in BACKENDS:
        d = tmp_path / b
        d.mkdir()
        g = open_graph(d, b)
        x = scenario(g)
        live = projection(g, x)
        assert projection(open_graph(d, b), x) == live  # 再生しても同じ
        out[b] = (live, g.log.read())
    assert out["json"][0] == out["sqlite"][0]
    assert out["json"][1] == out["sqlite"][1]  # イベント列そのものも同じ
    # SQLite は同じイベントを表に持つ
    with sqlite3.connect(str(db_path(tmp_path / "sqlite", "sqlite"))) as con:
        rows = con.execute("SELECT seq, op, actor, body FROM events ORDER BY seq").fetchall()
    con.close()
    assert [json.loads(r[3]) for r in rows] == out["json"][1]
    assert [(r[0], r[1], r[2]) for r in rows] == [(e["seq"], e["op"], e["actor"]) for e in out["json"][1]]


def test_convert_json_to_sqlite_and_back(tmp_path):
    g = open_graph(tmp_path, "json")
    x = scenario(g)
    want = projection(g, x)
    b, p = g.convert(tmp_path / "copy.sqlite")
    assert b == "sqlite"
    s = dg.DesignGraph(p, clock=clock)
    assert s.backend == "sqlite" and projection(s, x) == want
    s.convert(tmp_path / "back.jsonl")
    assert projection(dg.DesignGraph(tmp_path / "back.jsonl", clock=clock), x) == want
    with pytest.raises(dg.DesignGraphError, match="空ではない"):
        g.convert(tmp_path / "copy.sqlite")


def test_reading_a_missing_db_creates_nothing(tmp_path, backend):
    p = tmp_path / "none" / ("g.jsonl" if backend == "json" else "g.sqlite")
    g = dg.DesignGraph(p, backend=backend)
    assert g.status()["last_seq"] == 0 and g.check() == [] and g.recheck() == []
    assert not p.exists() and not p.parent.exists()
    g.init()
    assert p.exists() and dg.DesignGraph(p, backend=backend).last_seq == 1


def test_stale_writer_is_refused(tmp_path, backend):
    g1 = open_graph(tmp_path, backend)
    g2 = open_graph(tmp_path, backend)
    g1.add("requirement", "先に書く")
    with pytest.raises(dg.DesignGraphError, match="別の書き手"):
        g2.add("requirement", "後から書く")
    assert open_graph(tmp_path, backend).add("requirement", "読み直して書く") == "RQ2"


def test_broken_jsonl_line_is_reported(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text('{"seq": 1, "op": "meta", "actor": "ai"}\n{broken\n', encoding="utf-8")
    with pytest.raises(dg.DesignGraphError, match="2 行目"):
        dg.DesignGraph(p)


def test_jsonl_uses_lf_and_utf8(tmp_path):
    g = open_graph(tmp_path, "json")
    g.add("requirement", "炊き上がる")
    raw = db_path(tmp_path, "json").read_bytes()
    assert b"\r\n" not in raw and "炊き上がる".encode("utf-8") in raw


def test_export_is_deterministic_and_marked_generated(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    scenario(g)
    md = g.export_markdown()
    assert md.splitlines()[0].startswith("<!-- 生成物。手で直さない")
    assert "生成物。手で直さない" in md.splitlines()[1]
    assert md == g.export_markdown() == open_graph(tmp_path, backend).export_markdown()
    assert "[仮説]" in md and "## 未決（推測で埋めないこと）" in md
    assert "LC1 —温度を知らせる→ LC2" in md
    assert "must_not: 圧力の機構を混ぜない" in md
    assert str(tmp_path) not in md  # 置き場所に依らない


# ---------------------------------------------------------------- W8b: 予算・括り・状態・ビュー・代償

def test_new_kinds_and_their_link_rules(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    lc = g.add("component", "保持")
    lc2 = g.add("component", "加熱")
    assert (g.add("world_state", "炊いていない"), g.add("system_state", "待機"), g.add("part", "マイコン"),
            g.add("model", "論理の図")) == ("WS1", "SS1", "PT1", "MO1")
    with pytest.raises(dg.DesignGraphError, match="論理コンポーネント"):
        g.add("component_state", "親なし")
    with pytest.raises(dg.DesignGraphError, match="論理コンポーネント"):
        g.add("component_state", "親が要素でない", parent="WS1")
    cs1 = g.add("component_state", "空", parent=lc)
    cs2 = g.add("component_state", "保持中", parent=lc)
    cs3 = g.add("component_state", "停止", parent=lc2)
    assert (cs1, cs2, cs3) == ("CS1", "CS2", "CS3")
    assert g.link("transitions", cs1, cs2)
    with pytest.raises(dg.DesignGraphError, match="同じ部品"):
        g.link("transitions", cs2, cs3)
    with pytest.raises(dg.DesignGraphError, match="同じ種類"):
        g.link("transitions", "WS1", "SS1")
    with pytest.raises(dg.DesignGraphError, match="同じ種類"):
        g.link("transitions", lc, lc2)
    with pytest.raises(dg.DesignGraphError, match="src はモデル"):
        g.link("shows", lc, "PT1")
    with pytest.raises(dg.DesignGraphError, match="モデルにモデル"):
        g.link("shows", "MO1", g.add("model", "別の図"))
    assert g.link("shows", "MO1", lc)


def test_budget_over_fires_only_when_the_sum_exceeds_the_target(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    qs = g.add("qas", "炊飯の区間", {"target": 60, "unit": "分"})
    steps = [g.add("component", t) for t in ("浸水", "昇温", "沸騰の維持", "蒸らし")]
    links = [g.link("allocates", qs, lc, attrs={"budget": b, "unit": "分", "basis": "仮説"})
             for lc, b in zip(steps, (30, 15, 5, 10))]
    assert "budget_over:" + qs not in ids(g.check())  # 60 ちょうどは超えていない（境目）
    b = g.budgets()[0]
    assert (b["total"], b["over"], b["remaining"], b["excess"]) == (60, False, 0, None)
    g.update(links[1], attrs={"budget": 20})
    f = {x["id"]: x for x in g.check()}
    assert f["budget_over:" + qs]["excess"] == 5 and "65" in f["budget_over:" + qs]["message"]
    # 十進で足す（0.1 + 0.2 は 0.3 を超えない）
    rq = g.add("requirement", "待機電力", {"target": 0.3})
    a1, a2 = g.add("component", "電源"), g.add("component", "表示")
    g.link("allocates", rq, a1, attrs={"budget": 0.1})
    g.link("allocates", rq, a2, attrs={"budget": 0.2})
    assert "budget_over:" + rq not in ids(g.check())


def test_budget_unreadable_is_not_silently_dropped(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    qs = g.add("qas", "区間", {"target": 60, "unit": "分"})
    lcs = [g.add("component", t) for t in ("A", "B", "C", "D")]
    ok = g.link("allocates", qs, lcs[0], attrs={"budget": 50})
    words = g.link("allocates", qs, lcs[1], attrs={"budget": "十分"})                 # 数でない
    kwh = g.link("allocates", qs, lcs[2], attrs={"budget": 30, "unit": "Wh"})         # 単位が違う（混ぜない）
    g.link("allocates", qs, lcs[3])                                                   # 予算なしは検出しない
    rq = g.add("requirement", "目標の無い要求")
    lc = g.add("component", "E")
    g.link("allocates", rq, lc, attrs={"budget": 3})
    bad = g.add("qas", "目標が文字", {"target": "60 分"})
    f = ids(g.check())
    for want in ("budget_unreadable:" + words, "budget_unreadable:" + kwh, "budget_unreadable:" + rq,
                 "budget_unreadable:" + bad):
        assert want in f, want
    assert "budget_unreadable:" + ok not in f and "budget_over:" + qs not in f  # 単位違いの 30 は合計に入れない
    row = next(b for b in g.budgets() if b["id"] == qs)
    assert row["total"] == 50 and [i["problem"] for i in row["items"]] == [None, "not_number", "unit", "no_budget"]


def test_coupling_counts_are_a_table_not_a_finding(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    lcs = [g.add("component", f"要素 {i}") for i in range(6)]
    for i, a in enumerate(lcs):
        for b in lcs[i + 1:]:
            g.link("relation", a, b, predicate="知らせる")
    g.link("relation", lcs[0], lcs[1], predicate="電力を渡す")  # 同じ組の 2 つ目の述語は 1 つと数える
    c = g.coupling()
    assert (c["elements"], c["couplings"], c["max_pairs"], c["sqrt_n"]) == (6, 15, 15, 2.45)
    assert not [f for f in g.check() if f["rule"] == "coupling_over"]  # 上限を宣言していなければ、多くても出さない


def test_coupling_over_fires_only_on_a_declared_limit(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    grp = g.add("component", "括り")
    kids = [g.add("component", f"子 {i}", parent=grp) for i in range(3)]
    g.add("component_state", "停止", parent=kids[0])  # 部品の状態は括りの中身に数えない
    out = [g.add("component", f"外 {i}") for i in range(2)]
    g.link("relation", kids[0], kids[1], predicate="渡す")
    g.link("relation", kids[0], out[0], predicate="渡す")
    g.link("relation", kids[2], out[1], predicate="渡す")
    ac = g.add("actor", "利用者")
    g.link("relation", ac, out[0], predicate="操作する")
    row = next(r for r in g.coupling()["groups"] if r["id"] == grp)
    assert (row["children"], row["elements"], row["internal"], row["external"]) == (3, 3, 1, 2)
    assert row["max_coupling"] is None and "coupling_over:" + grp not in ids(g.check())
    g.update(grp, attrs={"max_coupling": 2})
    assert "coupling_over:" + grp not in ids(g.check())  # 上限ちょうどは超えていない
    g.update(grp, attrs={"max_coupling": 1})
    f = {x["id"]: x for x in g.check()}
    assert f["coupling_over:" + grp]["external"] == 2 and "宣言した上限 1" in f["coupling_over:" + grp]["message"]
    g.update(grp, attrs={"max_coupling": "少なめ"})
    assert "0 以上の整数でない" in {x["id"]: x for x in g.check()}["coupling_over:" + grp]["message"]
    whole = g.coupling()
    assert (whole["elements"], whole["couplings"], whole["external"]) == (6, 3, 1)  # 外部はアクターとの組


def rice_states(g: dg.DesignGraph) -> dict:
    """炊飯器の部品の状態（2 × 2 × 2 = 8 通り）。"""
    hold, heat, ctl = g.add("component", "保持"), g.add("component", "加熱"), g.add("component", "制御")
    s = {name: g.add("component_state", name, parent=p) for name, p in
         (("空", hold), ("保持中", hold), ("停止", heat), ("通電中", heat), ("待機", ctl), ("実行中", ctl))}
    return {"hold": hold, "heat": heat, "ctl": ctl, **s}


def test_state_gap_overlap_and_dont_care(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    s = rice_states(g)
    assert not [f for f in g.check() if f["rule"].startswith("state_")]  # 第 3 段を始めるまでは何も出さない
    wait = g.add("system_state", "待機", {"of": [s["停止"], s["待機"]]})                       # 保持はどちらでもよい
    cook = g.add("system_state", "炊飯中", {"of": [s["保持中"], s["通電中"], s["実行中"]]})
    g.add("system_state", "空焚き", {"of": [s["空"], s["通電中"]], "forbidden": True, "reason": "空焚きになる"})
    sp = g.state_space()
    assert sp["size"] == 8 and sp["enumerated"] and len(sp["gaps"]) == 3 and sp["overlaps"] == []
    f = {x["id"]: x for x in g.check()}
    assert f["state_gap:system_state"]["count"] == 3
    assert f["state_dont_care:" + wait]["level"] == "info" and f["state_dont_care:" + wait]["components"] == [s["hold"]]
    assert "state_dont_care:" + cook not in f and "state_overlap:system_state" not in f
    keep = g.add("system_state", "保温", {"of": [s["保持中"], s["通電中"]]})  # 炊飯中と重なる
    sp = g.state_space()
    assert len(sp["gaps"]) == 2 and sp["overlaps"] == [{"states": [s["保持中"], s["通電中"], s["実行中"]], "by": [cook, keep]}]
    assert {x["id"]: x for x in g.check()}["state_overlap:system_state"]["count"] == 1
    # 「どちらでもよい」は課題に載せると消える
    is_ = g.add("issue", "待機のとき保持はどちらでもよいか（待機電力が決める）")
    g.link("about", is_, wait)
    assert "state_dont_care:" + wait not in ids(g.check())
    # 全部当てれば網羅漏れは消える
    g.add("system_state", "準備中", {"of": [s["停止"], s["実行中"]]})
    g.update(keep, attrs={"of": [s["保持中"], s["通電中"], s["待機"]]})
    f = ids(g.check())
    assert "state_gap:system_state" not in f and "state_overlap:system_state" not in f


def test_state_undefined(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    s = rice_states(g)
    two = g.add("system_state", "矛盾", {"of": [s["空"], s["保持中"]]})
    empty = g.add("system_state", "空の定義")
    wrong = g.add("system_state", "要素を指す", {"of": [s["hold"]]})
    why_not = g.add("system_state", "理由なしの禁止", {"of": [s["空"], s["通電中"]], "forbidden": True})
    f = {x["id"]: x for x in g.check()}
    assert "2 つ指している" in f["state_undefined:" + two]["message"]
    assert "attrs.of" in f["state_undefined:" + empty]["message"]
    assert "CS" in f["state_undefined:" + wrong]["message"]
    assert "理由" in f["state_undefined:" + why_not]["message"]
    # 定義の誤った状態は網羅の数え上げに使わない（理由なしの禁止は使う）
    assert [d["id"] for d in g.state_space()["definitions"] if d["valid"]] == [why_not]


def test_state_gap_is_not_enumerated_beyond_the_limit(tmp_path, backend, monkeypatch):
    monkeypatch.setattr(dg, "STATE_PRODUCT_LIMIT", 4)
    g = open_graph(tmp_path, backend)
    s = rice_states(g)
    g.add("system_state", "全部", {"of": [s["空"], s["停止"], s["待機"]]})
    sp = g.state_space()
    assert sp["size"] == 8 and not sp["enumerated"] and sp["gaps"] == []
    f = {x["id"]: x for x in g.check()}
    assert "網羅の検査をしていない" in f["state_gap:system_state"]["message"]


def test_state_flow_reachability(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    w = [g.add("world_state", t, a) for t, a in (
        ("米と水がある", {"mark": "initial"}), ("炊いている", {}), ("取り出した", {"mark": "目的達成"}),
        ("どこからも来ない", {}), ("輪 1", {}), ("輪 2", {}), ("停電", {"mark": ["external"]}))]
    for a, b in ((0, 1), (1, 2), (3, 1), (4, 5), (5, 4), (6, 1)):
        g.link("transitions", w[a], w[b], attrs={"event": "e"})
    flows = g.state_space()["flows"]
    assert [f["group"] for f in flows] == ["world_state"]  # 遷移の無い段は見ない
    assert flows[0]["problems"] == {w[3]: ["no_source"], w[4]: ["unreachable"], w[5]: ["unreachable"]}
    f = ids(g.check())
    assert {"state_flow:" + w[i] for i in (3, 4, 5)} <= f
    assert not {"state_flow:" + w[i] for i in (0, 1, 2, 6)} & f
    g.update(w[2], attrs={"mark": None})
    assert "行き止まり" in {x["id"]: x for x in g.check()}["state_flow:" + w[2]]["message"]


def test_views_need_three_basic_viewpoints_once_models_exist(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    lc1, lc2 = g.add("component", "加熱", {"obvious": True}), g.add("component", "計測", {"obvious": True})
    pt = g.add("part", "マイコン")
    f = ids(g.check())
    assert not {x for x in f if x.split(":")[0] in ("view_missing", "no_view", "mixed_kinds")}  # 図が無いあいだは出さない
    assert "orphan:" + pt in f  # 部品はあるが役割が無い
    g.link("allocates", lc1, pt)
    assert "orphan:" + pt not in ids(g.check())
    mo1 = g.add("model", "論理の図", {"viewpoint": "論理"})
    g.link("shows", mo1, lc1)
    f = ids(g.check())
    assert {"view_missing:view:implementation", "view_missing:view:allocation", "no_view:" + lc2} <= f
    assert "view_missing:view:logical" not in f and "no_view:" + pt not in f  # 実装ビューが無いうちは部品を問わない
    mo2 = g.add("model", "実装の図", {"viewpoint": "implementation"})
    g.link("shows", mo2, pt)
    g.link("shows", mo2, lc2)
    mo3 = g.add("model", "割り付けの図", {"viewpoint": "割り付け"})
    g.link("shows", mo3, lc1)
    g.link("shows", mo3, pt)
    f = {x["id"]: x for x in g.check()}
    assert not [x for x in f if x.startswith(("view_missing", "no_view"))]
    assert f["mixed_kinds:" + mo2]["kinds"] == ["component", "part"] and "mixed_kinds:" + mo3 not in f
    g.update(mo2, attrs={"whiteboard": True})
    assert "mixed_kinds:" + mo2 not in ids(g.check())
    # 要素の種類はステレオタイプで見る
    who = g.add("component", "利用者の手順", {"obvious": True, "stereotype": "人"})
    g.link("shows", mo1, who)
    assert {x["id"]: x for x in g.check()}["mixed_kinds:" + mo1]["kinds"] == ["component", "人"]
    # 要素が変わると、載せたモデルに要再確認の印が付く
    g.update(lc1, title="加熱する")
    assert {m["downstream"] for m in g.recheck() if m["kind"] == "shows"} == {mo1, mo3}


def test_view_missing_waiver_on_a_pseudo_target_holds(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    g.add("model", "論理の図", {"viewpoint": "logical"})
    g.actor = "human"
    g.waive("view_missing:view:allocation", "割り付けは二週目で描く")
    f = ids(g.check())
    assert "view_missing:view:allocation" not in f and "view_missing:view:implementation" in f


def test_no_cons_and_tradeoffs(tmp_path, backend):
    g = open_graph(tmp_path, backend)
    x = chain(g)
    d2 = g.add("decision_point", "保温の方式")
    k = g.add("option", "常時保温", parent=d2)
    g.add("option", "保温しない", parent=d2)
    g.link("conflicts", x["a"], k)
    g.link("synergy", x["b"], k)
    g.update(x["b"], attrs={"cons": [{"text": "部品が増える", "origin": "means"}]})
    g.actor = "human"
    g.decide(x["d"], x["a"], conditions=["家庭用 100V"])
    assert "no_cons:" + x["a"] in ids(g.check())
    assert "no_cons:" + x["b"] not in ids(g.check())  # 採用していない案には問わない
    g.update(x["a"], attrs={"cons": [{"text": "電力を食う", "origin": "essential", "measure": "1.2 kW"}, "高い"]})
    assert "no_cons:" + x["a"] not in ids(g.check())
    rows = g.tradeoffs()
    assert [r["dp"] for r in rows] == [x["d"]]  # 未決の D2 はまだ何も捨てていない
    r = rows[0]
    assert r["adopted"]["cons"] == [{"text": "電力を食う", "origin": "essential", "measure": "1.2 kW"}, {"text": "高い"}]
    assert [o["id"] for o in r["rejected"]] == [x["b"], x["c"]] and r["rejected"][0]["cons"][0]["origin"] == "means"
    assert [(rel["kind"], rel["other"], rel["other_adopted"]) for rel in r["relations"]] == [("conflicts", k, False)]
    assert r["concerns"] == [x["cn"]] and r["conditions"] == ["家庭用 100V"]
    g.decide(d2, k)
    assert g.tradeoffs()[0]["relations"][0]["other_adopted"] is True


def w8b_scenario(g: dg.DesignGraph) -> None:
    x = chain(g)
    qs = g.add("qas", "区間", {"target": 10})
    g.link("allocates", qs, x["lc"], attrs={"budget": 7.5})
    g.add("component", "子", {"max_coupling": 0}, parent=x["lc"])
    s = rice_states(g)
    g.add("system_state", "待機", {"of": [s["停止"]]})
    mo = g.add("model", "図", {"viewpoint": "logical"})
    g.link("shows", mo, x["lc"])
    g.actor = "human"
    g.decide(x["d"], x["a"])


def test_w8b_tables_are_the_same_on_json_and_sqlite(tmp_path):
    out = {}
    for b in BACKENDS:
        d = tmp_path / b
        d.mkdir()
        g = open_graph(d, b)
        w8b_scenario(g)
        g2 = open_graph(d, b)
        out[b] = {"budgets": g2.budgets(), "coupling": g2.coupling(), "states": g2.state_space(), "views": g2.views(),
                  "tradeoffs": g2.tradeoffs(), "check": g2.check(include_waived=True)}
        assert out[b]["check"] == g.check(include_waived=True)
    assert out["json"] == out["sqlite"]
    json.dumps(out["json"], ensure_ascii=False)  # 入口の --json で出せる


def test_kinds_lists_the_w8b_rules(capsys):
    code = dg.main(["kinds", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    for r in ("budget_over", "coupling_over", "state_gap", "state_overlap", "view_missing", "mixed_kinds", "no_cons"):
        assert r in data["rules"]
    assert data["rules"]["state_dont_care"]["level"] == "info"
    assert {"part", "model", "world_state", "system_state", "component_state"} <= set(data["kinds"])
    assert data["links"]["shows"]["upstream"] == "dst" and data["links"]["transitions"]["upstream"] is None
    assert list(dg.RULES)[-1] == "undecided"


# ---------------------------------------------------------------- CLI

def run(capsys, *argv):
    code = dg.main([str(a) for a in argv])
    cap = capsys.readouterr()
    return code, cap.out.strip(), cap.err.strip()


def test_cli_end_to_end(tmp_path, capsys, backend):
    db = db_path(tmp_path, backend)
    common = ["--db", db]
    code, cn, _ = run(capsys, "add", "concern", "待ち時間", "--attr", "weight=5", *common)
    assert (code, cn) == (0, "CN1")
    assert dg.DesignGraph(db).get("CN1")["attrs"]["weight"] == 5  # 値は JSON として読む
    _, d, _ = run(capsys, *common, "add", "decision_point", "加熱方式")  # 共通の引数は前にも置ける
    _, a, _ = run(capsys, "add", "option", "IH", "--parent", d, *common)
    assert a == "D1-A"
    code, out, err = run(capsys, "decide", d, a, *common)
    assert code == 2 and "人" in err
    code, out, _ = run(capsys, "check", *common, "--json")
    rows = json.loads(out)
    assert code == 1 and "few_options:D1" in {r["id"] for r in rows}
    code, out, _ = run(capsys, "decide", d, a, "--actor", "human", "--condition", "家庭用 100V", *common)
    assert code == 0
    code, out, _ = run(capsys, "update", a, "--append", "must=加熱は LC1 だけ", "--actor", "human", *common)
    assert (code, out) == (0, "D1-A v2")
    code, out, _ = run(capsys, "status", "--json", *common)
    st = json.loads(out)
    assert st["undecided"] == [] and st["drivers"] == ["CN1"]
    code, out, _ = run(capsys, "why", a, *common)
    assert code == 0 and "contains" in out and "D1" in out
    code, out, _ = run(capsys, "recheck", *common)
    assert out == "要再確認なし"
    md = tmp_path / "out" / "graph.md"
    code, out, _ = run(capsys, "export", "--out", md, *common)
    assert code == 0 and md.read_text(encoding="utf-8").startswith("<!-- 生成物。手で直さない")
    code, out, _ = run(capsys, "show", a, *common)
    assert code == 0 and "履歴" in out
    code, out, _ = run(capsys, "kinds")
    assert code == 0 and "no_evidence" in out
    code, out, err = run(capsys, "show", "RQ99", *common)
    assert code == 2 and "RQ99" in err


def test_cli_infers_backend_from_suffix(tmp_path, capsys):
    db = tmp_path / "graph.sqlite"
    code, out, _ = run(capsys, "add", "requirement", "要求", "--db", db)
    assert (code, out) == (0, "RQ1")
    with sqlite3.connect(str(db)) as con:
        assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2  # meta と create
    con.close()
    code, out, _ = run(capsys, "convert", "--to", tmp_path / "graph.jsonl", "--db", db)
    assert code == 0 and (tmp_path / "graph.jsonl").exists()


def test_cli_export_json_and_kinds_without_db(tmp_path, capsys):
    db = tmp_path / "g.jsonl"
    run(capsys, "add", "requirement", "要求", "--db", db)
    code, out, _ = run(capsys, "export", "--json", "--db", db)
    assert code == 0 and json.loads(out)["markdown"].startswith("<!-- 生成物。手で直さない")
    broken = tmp_path / "broken.jsonl"
    broken.write_text("{broken\n", encoding="utf-8")
    code, out, _ = run(capsys, "kinds", "--json", "--db", broken)  # kinds は DB を読まない
    assert code == 0 and "contains" in json.loads(out)["links"]


def test_cli_relation_without_predicate_warns(tmp_path, capsys):
    db = tmp_path / "g.jsonl"
    run(capsys, "add", "component", "A", "--db", db)
    run(capsys, "add", "component", "B", "--db", db)
    code, out, err = run(capsys, "link", "relation", "LC1", "LC2", "--db", db)
    assert code == 0 and out == "L1" and "述語" in err
    code, out, _ = run(capsys, "check", "--db", db)
    assert code == 1 and "no_predicate:L1" in out

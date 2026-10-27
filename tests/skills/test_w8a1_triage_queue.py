"""上流変更の仕分け の武器 triage_queue.py のテスト。"""
from _w8a1_load import chain, graph, load, run, snapshot

m = load("上流変更の仕分け", "triage_queue.py")


def test_no_change_means_empty_queue(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    rc, text, _ = run(m, capsys, tmp_path)
    assert rc == 0 and "仕分け待ちなし" in text


def test_upstream_change_marks_only_the_next_step(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    g.update(x["a"], title="IH 炊飯")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1
    assert [(q["upstream"], q["downstream"]) for q in out["queue"]] == [(x["a"], x["rq"])]
    q = out["queue"][0]
    assert q["ready"] is True and q["next"] == [x["lc"]] and q["seen"] == 1 and q["current"] == 2


def test_rows_whose_upstream_is_itself_waiting_come_later(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    g.update(x["d"], title="加熱の方式")
    g.update(x["a"], title="IH 炊飯")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    ready = [(q["upstream"], q["downstream"], q["ready"]) for q in out["queue"]]
    # 決定点の変更は案 3 つ（D1-A〜C）に印を付け、D1-A の変更はその先の RQ1 に印を付ける。RQ1 は D1-A が仕分け待ちなので後
    assert ready == [(x["d"], x["a"], True), (x["d"], x["b"], True), (x["d"], x["c"], True), (x["a"], x["rq"], False)]
    rc, text, _ = run(m, capsys, tmp_path)
    assert "後で" in text and "先に" in text


def test_triage_removes_the_row_and_counts_in_history(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    g.update(x["a"], title="IH 炊飯")
    link = g.recheck()[0]["link"]
    g.actor = "human"
    g.triage(link, "ok")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0 and out["queue"] == []


def test_rejected_upstream_is_reported_as_on_dead(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    nt = g.add("record", "議事録")
    g.actor = "human"
    g.decide(x["d"], x["b"], evidence=[nt], conditions=["圧力鍋の設置"])
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1 and any(f["rule"] == "on_dead" and f["target"] == x["rq"] for f in out["on_dead"])


def test_read_only(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    g.update(x["a"], title="IH 炊飯")
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before

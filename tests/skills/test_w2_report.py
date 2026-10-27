"""未カバー領域の言語化 / 残留リスクの書き方 / 保留の判定 / 保証の受理 の武器スクリプトのテスト。"""
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2] / "skills" / "scripts"


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cg = load("未カバー領域の言語化/coverage_gaps.py", "w2_cg")
rr = load("残留リスクの書き方/lint_residual_risk.py", "w2_rr")
hl = load("保留の判定/hold_lint.py", "w2_hl")
al = load("保証の受理/assurance_ledger.py", "w2_al")


def w(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def kinds(capsys, mod, *args):
    rc = mod.main([*args, "--json"])
    data = json.loads(capsys.readouterr().out)
    return rc, data


# ------------------------------------------------------------ coverage_gaps

SPEC = "T-01 a\nT-02 b\nT-03 c\n"


def test_gaps_all_passed_without_uncovered_section(tmp_path, capsys):
    rep = "# 報告\n全部通った。\n| T-01 | 合格 |\n| T-02 | ✅ |\n"
    rc, probs = kinds(capsys, cg, w(tmp_path, "r.md", rep), "--spec", w(tmp_path, "s.md", SPEC))
    ks = {(p["kind"]) for p in probs}
    assert rc == 1
    assert {"結果なし", "未カバー節なし", "全部通った止まり", "取りこぼし未記載"} <= ks
    assert any("T-03" in p["message"] for p in probs if p["kind"] == "結果なし")


def test_gaps_good_report_is_clean(tmp_path, capsys):
    rep = """# 報告
- T-01 合格。一部: 空入力は判定できない（仕様 2.1 の後半）
- T-02 合格。判定できない箇所: なし
- T-03 合格。取りこぼし: 並行実行は見ていない
## 未カバー領域
- 非UTF-8 入力は試していない。理由: 用意できるデータが無いため
"""
    rc, probs = kinds(capsys, cg, w(tmp_path, "r.md", rep), "--spec", w(tmp_path, "s.md", SPEC))
    assert (rc, probs) == (0, [])


def test_gaps_empty_section_and_reasonless(tmp_path, capsys):
    rc, probs = kinds(capsys, cg, w(tmp_path, "r.md", "T-01 合格 判定できない: なし\n## 未カバー領域\nなし\n"))
    assert any(p["kind"] == "未カバー節が空" for p in probs)
    rc, probs = kinds(capsys, cg, w(tmp_path, "r2.md", "T-01 合格 判定できない: なし\n## 未カバー領域\n- 文字コードの扱い\n"))
    assert any(p["kind"] == "未カバー節が空" and "理由" in p["message"] for p in probs)


def test_gaps_unknown_item_in_report(tmp_path, capsys):
    rc, probs = kinds(capsys, cg, w(tmp_path, "r.md", "T-09 合格 一部\n## 未カバー\n- x: データが無いため\n"), "--spec", w(tmp_path, "s.md", SPEC))
    assert any(p["kind"] == "仕様外" and "T-09" in p["message"] for p in probs)


def test_gaps_bad_input(tmp_path, capsys):
    assert cg.main([str(tmp_path / "nope.md")]) == 2
    assert cg.main([w(tmp_path, "r.md", "x"), "--id-pattern", "("]) == 2


# ------------------------------------------------------------ lint_residual_risk

def test_risk_two_lines_ok(tmp_path, capsys):
    rep = """## 残留リスク
- 文字化け
  - ① 文字コード違いで化ける
  - ② 非UTF-8の入力は試していない
- 競合
  - ① 並行実行で壊れうる
  - ② 同時 2 プロセスでの実行は確かめていない
"""
    rc, probs = kinds(capsys, rr, w(tmp_path, "r.md", rep))
    assert (rc, probs) == (0, [])


def test_risk_missing_second_and_unverified_in_first(tmp_path, capsys):
    rep = "## 残留リスク\n- 遅い\n  - ① 大きな入力で遅くなる可能性。未測定\n"
    rc, probs = kinds(capsys, rr, w(tmp_path, "r.md", rep))
    ks = [p["kind"] for p in probs]
    assert rc == 1 and "②なし" in ks and "①に②の中身" in ks


def test_risk_empty_second_and_vague(tmp_path, capsys):
    rep = "## 残留リスク\n- 競合\n  - ① たぶん大丈夫だが壊れうる\n  - ② なし\n"
    rc, probs = kinds(capsys, rr, w(tmp_path, "r.md", rep))
    ks = {p["kind"] for p in probs}
    assert {"②が空", "たぶん大丈夫"} <= ks


def test_risk_only_section_scanned(tmp_path, capsys):
    rep = "## 概要\n- 関係ない箇条書き\n## 残留リスク\n- a\n  - ① x\n  - ② y\n## 次\n- もっと関係ない\n"
    rc, probs = kinds(capsys, rr, w(tmp_path, "r.md", rep))
    assert (rc, probs) == (0, [])


def test_risk_verbatim_carry_from_upstream(tmp_path, capsys):
    body = "## 残留リスク\n- 競合\n  - ① 壊れうる\n  - ② 並行実行は試していない\n"
    up = w(tmp_path, "up.md", body)
    rc, probs = kinds(capsys, rr, w(tmp_path, "r.md", body), "--upstream", up)
    assert any(p["kind"] == "無印の転記" for p in probs)
    reduced = body.replace("壊れうる", "壊れうる（2 プロセスまでは確認済み）")
    rc, probs = kinds(capsys, rr, w(tmp_path, "r2.md", reduced), "--upstream", up)
    assert not any(p["kind"] == "無印の転記" for p in probs)


def test_risk_no_items(tmp_path, capsys):
    rc, probs = kinds(capsys, rr, w(tmp_path, "r.md", "## 残留リスク\nなし\n"))
    assert rc == 1 and probs[0]["kind"] == "項目なし"


# ------------------------------------------------------------ hold_lint

TABLE = """| 項目 | 判定 | 理由 | 解除条件 |
|---|---|---|---|
| T-01 | 合格 | たぶん動く | |
| T-02 | 保留 | 本番データが無い | |
| T-03 | 保留 | 環境が無い | いつか様子を見て |
| T-04 | 保留 | 期間が要る | 7日分のログが溜まったら再判定 |
| T-05 | 不合格 | | |
"""


def test_hold_table(tmp_path, capsys):
    data = kinds(capsys, hl, w(tmp_path, "r.md", TABLE))
    rc, out = data
    assert rc == 1 and out["tally"] == {"合格": 1, "不合格": 1, "保留": 3}
    got = {(p["item"], p["kind"]) for p in out["problems"]}
    assert got == {("T-01", "たぶんで合格"), ("T-02", "解除条件なし"), ("T-03", "解除条件が曖昧")}


def test_hold_bullets_and_missing_reason(tmp_path, capsys):
    rep = "- T-05 保留\n  理由: 検証機が無い 解除条件: 検証機が届いたら実行\n- T-06 保留\n"
    rc, out = kinds(capsys, hl, w(tmp_path, "r.md", rep))
    got = {(p["item"], p["kind"]) for p in out["problems"]}
    assert ("T-06 保留", "理由なし") in got and ("T-06 保留", "解除条件なし") in got
    assert not any(i.startswith("T-05") for i, _ in got)


def test_hold_binary_policy_forbids_hold(tmp_path, capsys):
    rc, out = kinds(capsys, hl, w(tmp_path, "r.md", TABLE), "--policy", "binary")
    assert sum(p["kind"] == "方針違反" for p in out["problems"]) == 3


def test_hold_clean_and_unreadable(tmp_path, capsys):
    ok = "| 項目 | 判定 | 理由 | 解除条件 |\n|---|---|---|---|\n| T-01 | 合格 | | |\n| T-02 | 保留 | 期間が要る | 7 日経過したら再測定 |\n"
    assert hl.main([w(tmp_path, "ok.md", ok)]) == 0
    assert hl.main([w(tmp_path, "no.md", "判定なし\n")]) == 2
    assert hl.main([str(tmp_path / "none.md")]) == 2


# ------------------------------------------------------------ assurance_ledger

ASSURE = """| 項目 | 主張 | エビデンス |
|---|---|---|
| 標準ライブラリのみ | 標準ライブラリのみ使用 | `python -c "import ast"` の import 一覧の機械出力 |
| 層構造 | 層構造に違反していない | レビュー済み |
| 縮退経路 | 縮退経路 4 件すべてにログ | 3 件の実行ログ。メモリ不足は未実装 |
| 件数 | 4 件すべてにログ | 3 件のログ `grep -c` |
| 空 | なにか | |
| 他 | 何か | 設計書の 3 章に記載 |
"""


def rows(capsys, text, tmp_path, *extra):
    rc = al.main([w(tmp_path, "a.md", text), "--json", *extra])
    d = json.loads(capsys.readouterr().out)
    return rc, {r["item"]: r["verdict"] for r in d["rows"]}, d


def test_assurance_verdicts(tmp_path, capsys):
    rc, v, _ = rows(capsys, ASSURE, tmp_path)
    assert rc == 1
    assert v == {"標準ライブラリのみ": "受理候補", "層構造": "不受理①", "縮退経路": "不受理②",
                 "件数": "不受理②", "空": "不受理①", "他": "要判断"}


def test_assurance_never_rejects_for_disagreement(tmp_path, capsys):
    # 内容に納得できなくても、材料があれば不受理にしない
    rc, v, _ = rows(capsys, "| 項目 | 主張 | エビデンス |\n|---|---|---|\n| X | 速い | `time python x.py` の実行結果 0.01s |\n", tmp_path)
    assert v == {"X": "受理候補"} and rc == 0


def test_assurance_not_in_assurance_items(tmp_path, capsys):
    spec = w(tmp_path, "si.txt", "# 内部項目\n標準ライブラリのみ\nスレッド安全\n")
    rc, v, d = rows(capsys, ASSURE, tmp_path, "--spec-items", spec)
    assert d["not_in_assurance"] == ["スレッド安全"]


def test_assurance_section_format_and_residual_template(tmp_path, capsys):
    text = "### 標準ライブラリのみ\n主張: import は標準のみ\nエビデンス: 次の出力\n```\nimport os\n```\n"
    assert al.main([w(tmp_path, "a.md", text)]) == 0
    out = capsys.readouterr().out
    assert "受理候補" in out and "② 確かめていない" in out


def test_assurance_unreadable(tmp_path, capsys):
    assert al.main([w(tmp_path, "a.md", "何もない\n")]) == 2

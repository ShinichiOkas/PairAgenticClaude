"""process 系 Skill の武器スクリプト（記録系: correction-record / skill-learning / vocabulary-capture / vision-record / retrospect）のテスト。"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2] / "home-claude" / "skills"


def load(skill, name):
    spec = importlib.util.spec_from_file_location(f"w6_{name}", ROOT / skill / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "pair-agent"
    for d in ("corrections", "skills", "vision"):
        (h / d).mkdir(parents=True)
    return h


# ------------------------------------------------------------ correction-record
def test_record_correction_preview_then_apply_then_no_overwrite(home, capsys):
    m = load("correction-record", "record_correction")
    args = ["--home", str(home), "--trigger", "scope_violation", "--severity", "high",
            "--quote", "勝手なことするな", "--action", "頼まれていない修正", "--learning", "範囲外は票にする",
            "--domains", "scope,git", "--slug", "no-fix", "--date", "2026-10-27"]
    assert m.main(args) == 0  # 下見
    assert not list((home / "corrections").glob("*.md"))
    assert m.main(args + ["--apply"]) == 0
    f = home / "corrections" / "2026-10-27-no-fix.md"
    t = f.read_text(encoding="utf-8")
    assert "「勝手なことするな」" in t and "trigger: scope_violation" in t
    assert "related_domains: [scope, git]" in t and "proposed_skill_id: null" in t
    assert m.main(args + ["--apply"]) == 3  # 上書きしない
    assert f.read_text(encoding="utf-8") == t


def test_record_correction_rejects_unknown_trigger(home):
    m = load("correction-record", "record_correction")
    with pytest.raises(SystemExit):
        m.main(["--home", str(home), "--trigger", "nope", "--severity", "low", "--quote", "x",
                "--action", "a", "--learning", "l"])


def test_scan_corrections_roundtrip(home, capsys):
    rec = load("correction-record", "record_correction")
    scan = load("correction-record", "scan_corrections")
    base = ["--home", str(home), "--action", "a", "--learning", "l"]
    rec.main(base + ["--trigger", "scope_violation", "--severity", "high", "--quote", "触るな",
                     "--domains", "git", "--slug", "a", "--date", "2026-10-01", "--apply"])
    rec.main(base + ["--trigger", "overengineering", "--severity", "low", "--quote", "やりすぎ",
                     "--domains", "design", "--slug", "b", "--date", "2026-10-02", "--apply"])
    rec.main(base + ["--trigger", "overengineering", "--severity", "low", "--quote", "また過剰",
                     "--domains", "design", "--slug", "c", "--date", "2026-10-03", "--apply"])
    rec.main(base + ["--trigger", "wrong_assumption", "--severity", "low", "--quote", "違う",
                     "--slug", "d", "--date", "2026-10-04", "--apply"])
    capsys.readouterr()
    assert scan.main(["--home", str(home), "stats"]) == 0
    out = capsys.readouterr().out
    assert "記録 4 件" in out and "overengineering: 2" in out
    scan.main(["--home", str(home), "search", "--domain", "git"])
    out = capsys.readouterr().out
    assert "以前『触るな』と教わっています" in out
    scan.main(["--home", str(home), "unlinked"])
    out = capsys.readouterr().out
    # high 1 件 + 同 trigger low 2 件 は候補、単発の low(wrong_assumption) は候補にしない
    assert "昇格候補 3 件" in out and "hard_boundary" in out and "wrong_assumption" not in out


def test_scan_corrections_tolerates_legacy_formats(home, capsys):
    scan = load("correction-record", "scan_corrections")
    (home / "corrections" / "2026-05-08-old.md").write_text(
        "---\ndate: 2026-05-08\nseverity: low-medium\n---\n\n## 師匠の言葉\n\n> 確認が多い\n", encoding="utf-8")
    assert scan.main(["--home", str(home), "unlinked"]) == 0
    out = capsys.readouterr().out
    assert "[medium]" in out and "2026-05-08" in out


# ------------------------------------------------------------ skill-learning
def test_skill_write_new_and_promote_rules(home, capsys):
    w = load("skill-learning", "skill_write")
    # confirmed の新規は原文が要る
    assert w.main(["--home", str(home), "new", "--name", "r1", "--category", "process", "--maturity", "confirmed",
                   "--body", "b"]) == 2
    assert w.main(["--home", str(home), "--now", "2026-10-27 10:00", "new", "--name", "r1", "--category", "process",
                   "--maturity", "draft", "--tags", "git", "--body", "実装前に仕様書", "--apply"]) == 0
    f = home / "skills" / "r1.md"
    assert "maturity: draft" in f.read_text(encoding="utf-8")
    assert w.main(["--home", str(home), "new", "--name", "r1", "--category", "process", "--body", "x", "--apply"]) == 3
    # draft -> confirmed は原文なしでは不可
    assert w.main(["promote", str(f), "--to", "confirmed", "--by", "師匠"]) == 2
    assert w.main(["--now", "2026-10-28 09:00", "promote", str(f), "--to", "forming", "--apply"]) == 0
    assert w.main(["--now", "2026-10-29 09:00", "promote", str(f), "--to", "confirmed", "--by", "師匠",
                   "--quote", "これで行こう", "--apply"]) == 0
    t = f.read_text(encoding="utf-8")
    assert "maturity: confirmed" in t and "confirmed_by: 師匠" in t and "updated_at: 2026-10-29 09:00" in t
    assert "draft -> forming" in t and "forming -> confirmed" in t and "これで行こう" in t
    assert t.count("name: r1") == 1
    # 降格は --demote が要る
    assert w.main(["promote", str(f), "--to", "forming", "--apply"]) == 2
    assert w.main(["promote", str(f), "--to", "forming", "--demote", "--apply"]) == 0
    assert "confirmed_by: null" in f.read_text(encoding="utf-8")


def test_skill_lint_and_depth(home, capsys):
    w = load("skill-learning", "skill_write")
    lint = load("skill-learning", "skill_lint")
    for name, cat, mat in (("p1", "process", "confirmed"), ("d1", "domain", "confirmed"),
                           ("d2", "domain", "confirmed"), ("d3", "domain", "forming")):
        w.main(["--home", str(home), "new", "--name", name, "--category", cat, "--maturity", mat,
                "--tags", "git" if name != "d3" else "ui", "--body", "b", "--quote", "q", "--apply"])
    assert lint.main(["--home", str(home), "lint"]) == 0
    capsys.readouterr()
    lint.main(["--home", str(home), "depth", "--tags", "git"])
    assert capsys.readouterr().out.startswith("follow")  # confirmed process が最優先
    lint.main(["--home", str(home), "depth", "--tags", "ui"])
    assert capsys.readouterr().out.startswith("thorough")  # forming だけ
    # process を外すと domain 2 件 -> skip
    (home / "skills" / "p1.md").unlink()
    lint.main(["--home", str(home), "depth", "--tags", "git"])
    assert capsys.readouterr().out.startswith("skip")
    (home / "skills" / "d2.md").unlink()
    lint.main(["--home", str(home), "depth", "--tags", "git"])
    assert capsys.readouterr().out.startswith("light")


def test_skill_lint_detects_problems(home, capsys):
    lint = load("skill-learning", "skill_lint")
    (home / "skills" / "a.md").write_text("---\nname: x\nmaturity: weird\n---\n", encoding="utf-8")
    (home / "skills" / "b.md").write_text("---\nname: x\nmaturity: draft\ncategory: process\n---\n", encoding="utf-8")
    (home / "skills" / "c.md").write_text("no frontmatter\n", encoding="utf-8")
    assert lint.main(["--home", str(home), "lint"]) == 1
    out = capsys.readouterr().out
    assert "maturity が不正" in out and "重複" in out and "フロントマターが無い" in out


# ------------------------------------------------------------ vocabulary-capture
def test_vocab_add_find_scan(home, capsys):
    v = load("vocabulary-capture", "vocab_ops")
    base = ["--home", str(home), "--now", "2026-10-27 10:00"]
    # 含まないものが無ければ拒否
    assert v.main(base + ["add", "--term", "シンプル", "--include", "外部依存なし"]) == 2
    assert v.main(base + ["add", "--term", "シンプル", "--include", "外部依存なし", "--exclude", "機能が少ない",
                          "--example", "標準ライブラリだけ", "--apply"]) == 0
    f = home / "skills" / "vocab-シンプル.md"
    t = f.read_text(encoding="utf-8")
    assert "含むもの:" in t and "含まないもの:" in t and "# 「シンプル」の定義" in t
    assert v.main(base + ["add", "--term", "シンプル", "--include", "x", "--exclude", "y", "--apply"]) == 3
    assert f.read_text(encoding="utf-8") == t
    assert v.main(base + ["add", "--term", "シンプル", "--include", "依存最小", "--exclude", "雑", "--update", "--apply"]) == 0
    t2 = f.read_text(encoding="utf-8")
    assert "依存最小" in t2 and "改訂履歴" in t2 and "created_at: 2026-10-27 10:00" in t2
    capsys.readouterr()
    assert v.main(base + ["find", "シンプ"]) == 0
    assert v.main(base + ["find", "未知語"]) == 1
    note = home / "n.txt"
    note.write_text("このAPIはシンプルにしたい", encoding="utf-8")
    v.main(base + ["scan", "--file", str(note)])
    assert "既知: 「シンプル」" in capsys.readouterr().out


# ------------------------------------------------------------ vision-record
def test_vision_add_search_patterns(home, capsys):
    v = load("vision-record", "vision_ops")
    base = ["--home", str(home), "--now", "2026-10-27T10:00:00+09:00"]
    # 師匠の言葉が空なら記録しない
    assert v.main(base + ["add", "--sprint-id", "S0", "--goal", "g", "--said", "  "]) == 2
    for sid, goal in (("S1", "認証の刷新"), ("S2", "ログ基盤")):
        assert v.main(base + ["add", "--sprint-id", sid, "--goal", goal, "--said", f"{goal}は外部依存なしで",
                              "--match", "a.py: 想定どおり", "--learn", "auth: 外部依存を嫌う",
                              "--learn", f"{sid}only: x", "--apply"]) == 0
    assert v.main(base + ["add", "--sprint-id", "S1", "--goal", "g", "--said", "x", "--apply"]) == 3
    capsys.readouterr()
    v.main(base + ["search", "--keyword", "認証"])
    out = capsys.readouterr().out
    assert "S1.md" in out and "S2.md" not in out and "1 件" in out
    v.main(base + ["patterns", "--min", "2"])
    out = capsys.readouterr().out
    assert "auth: 2 回" in out and "s1only" not in out


# ------------------------------------------------------------ retrospect
def test_retro_collect_and_report(home, tmp_path, capsys):
    rec = load("correction-record", "record_correction")
    w = load("skill-learning", "skill_write")
    r = load("retrospect", "retro_collect")
    rec.main(["--home", str(home), "--trigger", "scope_violation", "--severity", "high", "--quote", "触るな",
              "--action", "a", "--learning", "l", "--domains", "git", "--slug", "x", "--date", "2026-10-20", "--apply"])
    rec.main(["--home", str(home), "--trigger", "scope_violation", "--severity", "high", "--quote", "古い",
              "--action", "a", "--learning", "l", "--slug", "old", "--date", "2026-09-01", "--apply"])
    w.main(["--home", str(home), "--now", "2026-10-21 10:00", "new", "--name", "git-rule", "--category", "process",
            "--maturity", "forming", "--tags", "git", "--body", "b", "--apply"])
    proj = tmp_path / "proj"
    (proj / ".pair-agent" / "agreements").mkdir(parents=True)
    (proj / ".pair-agent" / "sprints").mkdir(parents=True)
    (proj / ".pair-agent" / "agreements" / "a.md").write_text(
        "# g\n\n## 修正・叱られ記録\n\n> [t] severity: high\n> 人間: 「やめろ」\n", encoding="utf-8")
    (proj / ".pair-agent" / "sprints" / "S.json").write_text(
        json.dumps({"経過": [{"at": "2026-10-22T10:00", "status": "executing -> retrospecting", "note": "n"}]}), encoding="utf-8")
    assert r.main(["--home", str(home), "collect", "--since", "2026-10-15", "--project", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "叱られ記録 1 件" in out and "触るな" in out and "古い" not in out
    assert "既存 Skill の更新候補（同ドメイン）: git-rule" in out  # 重複登録を防ぐ手がかり
    assert "[新規] git-rule" in out
    assert "a.md / 修正・叱られ記録" in out and "executing -> retrospecting" in out
    assert r.main(["--home", str(home), "collect", "--since", "bad"]) == 2
    jf = tmp_path / "reg.json"
    jf.write_text(json.dumps([{"id": "s1", "kind": "新規", "maturity": "confirmed", "line": "L",
                               "evidence": "「原文」", "where": "ペア固有"}], ensure_ascii=False), encoding="utf-8")
    capsys.readouterr()
    assert r.main(["report", "--json", str(jf)]) == 0
    out = capsys.readouterr().out
    assert "■ 登録した Skill" in out and "[s1・新規・confirmed] L" in out and "■ 取り消すとき" in out
    jf.write_text("[]", encoding="utf-8")
    r.main(["report", "--json", str(jf)])
    assert "今回は Skill にする候補はありません" in capsys.readouterr().out
    jf.write_text(json.dumps([{"id": "s1"}]), encoding="utf-8")
    assert r.main(["report", "--json", str(jf)]) == 2

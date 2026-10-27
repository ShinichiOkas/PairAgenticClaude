"""process 系 Skill の武器スクリプト（進行系: sprint-lifecycle / agreement-document / slice-size-management / subagent-cost-management / project-init / project-start-existing）のテスト。"""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "home-claude" / "skills"


def load(skill, name):
    spec = importlib.util.spec_from_file_location(f"w6_{name}", ROOT / skill / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------ sprint-lifecycle
@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "work" / "myproj"
    (p / ".pair-agent" / "agreements").mkdir(parents=True)
    return p


def sargs(proj, *rest):
    return ["--project", str(proj), "--host", "HOST", "--toplevel", "/top/myproj", "--now", "2026-10-27T10:00:00+09:00", *rest]


def test_sprint_key_is_sha1_of_host_plus_toplevel(proj, capsys):
    s = load("sprint-lifecycle", "sprint_ops")
    assert s.main(sargs(proj, "key")) == 0
    expect = hashlib.sha1(b"HOST/top/myproj").hexdigest()[:8]
    out = capsys.readouterr().out
    assert f"key={expect}" in out and f"{expect}-myproj.json" in out


def test_sprint_start_transition_status(proj, capsys):
    s = load("sprint-lifecycle", "sprint_ops")
    assert s.main(sargs(proj, "start", "--goal", "login fix", "--sprint-id", "S1")) == 0  # 下見
    assert not (proj / ".pair-agent" / "sprints").exists()
    assert s.main(sargs(proj, "start", "--goal", "login fix", "--sprint-id", "S1", "--apply")) == 0
    j = proj / ".pair-agent" / "sprints" / "S1.json"
    assert json.loads(j.read_text(encoding="utf-8"))["status"] == "deliberating"
    assert s.main(sargs(proj, "start", "--goal", "login fix", "--sprint-id", "S1", "--apply")) == 3  # 上書きしない
    # 合意ドキュメント（journal の agreement_path）の status も追従する
    ag = proj / ".pair-agent" / "agreements" / "login-fix.md"
    ag.write_text("---\nsprint_id: S1\nstatus: drafting\nupdated_at: old\n---\n# g\n", encoding="utf-8")
    assert s.main(sargs(proj, "transition", "--to", "completed", "--apply")) == 3  # 飛び越しは拒否
    assert s.main(sargs(proj, "transition", "--to", "executing", "--note", "go", "--apply")) == 0
    assert "status: executing" in ag.read_text(encoding="utf-8")
    jj = json.loads(j.read_text(encoding="utf-8"))
    assert jj["status"] == "executing" and jj["経過"][0]["status"] == "deliberating -> executing"
    capsys.readouterr()
    assert s.main(sargs(proj, "status")) == 0
    assert "OK: 一致" in capsys.readouterr().out
    # ポインタだけ壊す -> 食い違い検出 -> 遷移でジャーナルを正として両方直る
    ptr = next((proj / ".pair-agent" / "current").glob("*.json"))
    d = json.loads(ptr.read_text(encoding="utf-8"))
    d["status"] = "agreed"
    ptr.write_text(json.dumps(d), encoding="utf-8")
    assert s.main(sargs(proj, "status")) == 3
    assert "MISMATCH" in capsys.readouterr().out
    assert s.main(sargs(proj, "transition", "--to", "retrospecting", "--apply")) == 0
    assert s.main(sargs(proj, "status")) == 0
    assert s.main(sargs(proj, "transition", "--to", "completed", "--apply")) == 0
    assert s.main(sargs(proj, "transition", "--to", "executing", "--apply")) == 3  # 完了からは戻れない


def test_sprint_migrate_legacy_and_closed_guard(proj, capsys):
    s = load("sprint-lifecycle", "sprint_ops")
    legacy = proj / ".pair-agent" / "current-sprint.json"
    legacy.write_text(json.dumps({"sprint_id": "OLD", "status": "executing", "goal": "g"}), encoding="utf-8")
    assert s.main(sargs(proj, "migrate")) == 0  # 下見は書かない
    assert json.loads(legacy.read_text(encoding="utf-8"))["status"] == "executing"
    assert s.main(sargs(proj, "migrate", "--apply")) == 0
    assert json.loads(legacy.read_text(encoding="utf-8"))["status"] == "moved"
    jr = json.loads((proj / ".pair-agent" / "sprints" / "OLD.json").read_text(encoding="utf-8"))
    assert jr["goal"] == "g"
    ptr = next((proj / ".pair-agent" / "current").glob("*.json"))
    assert json.loads(ptr.read_text(encoding="utf-8"))["journal"].endswith("OLD.json")
    assert s.main(sargs(proj, "migrate", "--apply")) == 0  # 二重実行は何もしない
    # 閉じたスプリントを指す旧ファイルは写さない（ジャーナルが既にある）
    p2 = proj.parent / "p2"
    (p2 / ".pair-agent" / "sprints").mkdir(parents=True)
    (p2 / ".pair-agent" / "sprints" / "CLOSED.json").write_text(json.dumps({"status": "completed", "keep": 1}), encoding="utf-8")
    (p2 / ".pair-agent" / "current-sprint.json").write_text(json.dumps({"sprint_id": "CLOSED", "status": "executing"}), encoding="utf-8")
    capsys.readouterr()
    assert s.main(sargs(p2, "migrate", "--apply")) == 4
    assert "NEEDS-DECISION" in capsys.readouterr().out
    assert json.loads((p2 / ".pair-agent" / "sprints" / "CLOSED.json").read_text(encoding="utf-8"))["keep"] == 1


def test_sprint_key_rule_case_sensitive_no_separator_trimmed(proj, capsys):
    s = load("sprint-lifecycle", "sprint_ops")
    assert s.worktree_key("ANCIENT", "S:/work/x") == hashlib.sha1(b"ANCIENTS:/work/x").hexdigest()[:8]
    assert s.worktree_key("ANCIENT", "S:/work/x\n") == s.worktree_key("ANCIENT", "S:/work/x")  # 前後の空白は除く
    assert s.worktree_key("ancient", "S:/work/x") != s.worktree_key("ANCIENT", "S:/work/x")  # 大文字小文字は区別


def _put_ptr(proj, name, **body):
    d = proj / ".pair-agent" / "current"
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text(json.dumps(body), encoding="utf-8")
    return f


def test_sprint_status_reports_foreign_key_pointers(proj, capsys):
    s = load("sprint-lifecycle", "sprint_ops")
    canon = hashlib.sha1(b"HOST/top/myproj").hexdigest()[:8]
    lower_pipe = hashlib.sha1(b"host|/top/myproj").hexdigest()[:8]
    _put_ptr(proj, f"{lower_pipe}-myproj.json", sprint_id="S-OLD", status="executing", journal="j")
    _put_ptr(proj, "b665f4f8-other.json", sprint_id="S-ALIEN", status="agreed")
    capsys.readouterr()
    rc = s.main(sargs(proj, "status"))
    out = capsys.readouterr().out
    assert rc == 1  # 正本のポインタは無い
    assert f"規則の違う鍵: {lower_pipe}-myproj.json" in out and "sprint_id=S-OLD" in out and "migrate で移せる" in out
    assert "b665f4f8-other.json" in out and "別 PC 由来" in out and "sprint_id=S-ALIEN" in out
    # 正本のポインタが正常なら、規則の違う鍵が有るだけで 5
    assert s.main(sargs(proj, "start", "--goal", "g", "--sprint-id", "S1", "--apply")) == 0
    assert (proj / ".pair-agent" / "current" / f"{canon}-myproj.json").is_file()
    assert s.main(sargs(proj, "status")) == 5
    capsys.readouterr()
    for f in (proj / ".pair-agent" / "current").glob("*.json"):
        if not f.name.startswith(canon):
            f.unlink()
    assert s.main(sargs(proj, "status")) == 0


def test_sprint_migrate_rekeys_pointer(proj, capsys):
    s = load("sprint-lifecycle", "sprint_ops")
    canon = hashlib.sha1(b"HOST/top/myproj").hexdigest()[:8]
    old = hashlib.sha1(b"host|/top/myproj").hexdigest()[:8]
    cur = proj / ".pair-agent" / "current"
    f = _put_ptr(proj, f"{old}-myproj.json", sprint_id="S9", status="executing", journal="j",
                 workcopy={"host": "HOST", "path": "/top/myproj", "key": old})
    alien = _put_ptr(proj, "b665f4f8-other.json", sprint_id="A")
    assert s.main(sargs(proj, "migrate")) == 0  # 下見は動かさない
    assert f.is_file() and "[下見]" in capsys.readouterr().out
    assert s.main(sargs(proj, "migrate", "--apply")) == 0
    assert not f.exists() and alien.is_file()  # 別 PC 由来は移さない
    new = cur / f"{canon}-myproj.json"
    d = json.loads(new.read_text(encoding="utf-8"))
    assert d["sprint_id"] == "S9" and d["workcopy"]["key"] == canon
    # 移す先が既に有れば止める（どちらも触らない）
    f2 = _put_ptr(proj, f"{old}-myproj.json", sprint_id="S10")
    capsys.readouterr()
    assert s.main(sargs(proj, "migrate", "--apply")) == 4
    assert "NEEDS-DECISION" in capsys.readouterr().out
    assert f2.is_file() and json.loads(new.read_text(encoding="utf-8"))["sprint_id"] == "S9"


# ------------------------------------------------------------ agreement-document
def test_agreement_new_bump_append_check(tmp_path, capsys):
    a = load("agreement-document", "agreement_ops")
    d = tmp_path / "agreements"
    base = ["--now", "2026-10-27T10:00:00+09:00"]
    new = base + ["new", "--slug", "login-fix", "--sprint-id", "S1", "--goal", "ログイン修正", "--dir", str(d),
                  "--task", "原因調査:AI", "--task", "修正:AI", "--done", "テストが通る"]
    assert a.main(new) == 0 and not d.exists()  # 下見
    assert a.main(new + ["--apply"]) == 0
    f = d / "login-fix.md"
    assert a.main(new + ["--apply"]) == 3
    assert "- [ ] 原因調査（担当: AI）" in f.read_text(encoding="utf-8")
    assert a.main(["check", str(f)]) == 0
    assert a.main(base + ["bump", str(f), "--reason", "前提が違った", "--kind", "premise", "--status", "deliberating", "--apply"]) == 0
    a.main(base + ["append", str(f), "--section", "concern", "--text", "リスク大", "--severity", "high", "--apply"])
    a.main(base + ["append", str(f), "--section", "scold", "--text", "触るな", "--action", "修正した", "--learning", "聞く", "--apply"])
    # 追記セクションが変更ログの後ろにあっても、変更ログの行は変更ログ節に入る
    assert a.main(base + ["bump", str(f), "--reason", "改善", "--kind", "improvement", "--apply"]) == 0
    t = f.read_text(encoding="utf-8")
    assert "version: 3" in t and "change_count_premise: 1" in t and "change_count_improvement: 1" in t
    assert "status: deliberating" in t
    log = t.split("## 変更ログ")[1].split("## ")[0]
    assert "v2" in log and "v3" in log and "v1" in log
    assert "## AIの懸念" in t and "> 人間: 「触るな」" in t
    capsys.readouterr()
    assert a.main(["check", str(f)]) == 0


def test_agreement_check_finds_problems(tmp_path, capsys):
    a = load("agreement-document", "agreement_ops")
    f = tmp_path / "bad.md"
    f.write_text("---\nsprint_id: S\nversion: 1\nstatus: bogus\n---\n\n# スプリントゴール\n\ng\n\n## スコープ\n\n"
                 "src/a.py と src/b.py と lib/c.py を直す\n", encoding="utf-8")
    assert a.main(["check", str(f)]) == 1
    out = capsys.readouterr().out
    assert "created_at" in out and "status 'bogus'" in out and "必須の節 'タスク'" in out and "ファイルパスが 3 個" in out
    f.write_text("---\nsprint_id: S\nversion: 1\nstatus: completed\ncreated_at: x\nupdated_at: x\n---\n# スプリントゴール\n## タスク\n- [ ] t\n"
                 "## スコープ\n## 完了条件\n## 前提\n## 既知リスク\n## 変更ログ\n", encoding="utf-8")
    capsys.readouterr()
    assert a.main(["check", str(f)]) == 1
    assert "completed なのに未完了タスク" in capsys.readouterr().out


# ------------------------------------------------------------ slice-size-management
def test_slice_roster_suggest_record(tmp_path, capsys):
    s = load("slice-size-management", "slice_ops")
    s.main(["roster", "--size", "S"])
    assert "構築者 -> 非回帰 -> 受入検査実施者 -> 同期担当" in capsys.readouterr().out
    s.main(["suggest", "--current", "S", "--files", "2"])
    assert "据え置き" in capsys.readouterr().out
    s.main(["suggest", "--current", "S", "--files", "4", "--rejections", "1"])
    out = capsys.readouterr().out
    assert "S -> M" in out and "4 ファイル" in out and "差し戻し" in out
    s.main(["suggest", "--current", "XS", "--external-dependency"])
    assert "XS -> L" in capsys.readouterr().out
    s.main(["suggest", "--current", "L", "--premise-collapse"])
    assert "据え置き" in capsys.readouterr().out  # L は上限
    f = tmp_path / "a.md"
    f.write_text("# ゴール\n\nスライス: S（おまかせ）\n\n本文\n", encoding="utf-8")
    assert s.main(["record", str(f), "--to", "M", "--reason", "前提崩壊", "--date", "2026-10-27"]) == 0
    assert "S（おまかせ）\n" in f.read_text(encoding="utf-8")  # 下見は書かない
    assert s.main(["record", str(f), "--to", "M", "--reason", "前提崩壊", "--date", "2026-10-27", "--apply"]) == 0
    t = f.read_text(encoding="utf-8")
    assert "スライス: S（おまかせ） / S → M（2026-10-27・前提崩壊）" in t
    assert s.main(["record", str(f), "--to", "S", "--reason", "x", "--apply"]) == 2  # 下げない
    assert s.main(["record", str(f), "--to", "M", "--reason", "x", "--apply"]) == 0  # 変更なし
    assert f.read_text(encoding="utf-8") == t
    g = tmp_path / "b.md"
    g.write_text("# 題\n\n本文\n", encoding="utf-8")
    s.main(["record", str(g), "--to", "M", "--reason", "r", "--date", "2026-10-27", "--apply"])
    assert "スライス: M（2026-10-27・r）" in g.read_text(encoding="utf-8")


def test_slice_suggest_counts_git_range(tmp_path, capsys):
    s = load("slice-size-management", "slice_ops")
    r = tmp_path / "repo"
    r.mkdir()
    g = lambda *a: subprocess.run(["git", "-C", str(r), *a], check=True, capture_output=True)
    g("init", "-q")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (r / "a.txt").write_text("1", encoding="utf-8")
    g("add", ".")
    g("commit", "-qm", "c1")
    for n in "bcde":
        (r / f"{n}.txt").write_text("x", encoding="utf-8")
    g("add", ".")
    g("commit", "-qm", "c2")
    s.main(["suggest", "--current", "S", "--git-range", "HEAD~1..HEAD", "--project", str(r)])
    out = capsys.readouterr().out
    assert "S -> M" in out and "4 ファイル" in out


# ------------------------------------------------------------ subagent-cost-management
def agent_md(name, model, turns):
    return f"---\nname: {name}\ndescription: d\nmodel: {model}\nmaxTurns: {turns}\n---\nbody\n"


def test_cost_audit_lookup_estimate(tmp_path, capsys):
    c = load("subagent-cost-management", "cost_ops")
    tools = REPO / "tools"
    ag = tmp_path / "agents"
    ag.mkdir()
    (ag / "x-build.md").write_text(agent_md("x-build", "sonnet", 600), encoding="utf-8")
    (ag / "x-run-regression.md").write_text(agent_md("x-run-regression", "haiku", 200), encoding="utf-8")
    (ag / "handmade.md").write_text("---\nname: handmade\ndescription: d\n---\n", encoding="utf-8")  # 役割ではない -> 検査外
    assert c.main(["--tools-dir", str(tools), "audit", "--agents", str(ag)]) == 0
    (ag / "x-sync-repository.md").write_text(agent_md("x-sync-repository", "opus", 50), encoding="utf-8")
    capsys.readouterr()
    assert c.main(["--tools-dir", str(tools), "audit", "--agents", str(ag)]) == 1
    out = capsys.readouterr().out
    assert "x-sync-repository.md" in out and "低すぎる" in out and "機械役" in out and "x-build.md" not in out
    c.main(["--tools-dir", str(tools), "lookup", "foo-build"])
    assert "tier 2 / maxTurns 600" in capsys.readouterr().out
    c.main(["estimate", "--calls", "100", "--context-tokens", "500000", "--model", "sonnet", "--split", "5"])
    out = capsys.readouterr().out
    assert "50,000,000" in out and "$10.00" in out and "$2.00" in out
    assert c.main(["estimate", "--calls", "1", "--context-tokens", "1", "--model", "gpt"]) == 2
    assert c.main(["--tools-dir", str(tmp_path / "none"), "lookup", "build"]) == 2


# ------------------------------------------------------------ project-init
def make_template(home):
    t = home / "template"
    for d in ("agreements", "sprints", "acceptance", "assurance", "skills", "current"):
        (t / d).mkdir(parents=True)
        (t / d / ".gitkeep").write_text("", encoding="utf-8")
    return t


def test_project_init_flow(tmp_path, capsys):
    i = load("project-init", "init_project")
    home = tmp_path / "home"
    p = tmp_path / "proj"
    p.mkdir()
    base = ["--project", str(p), "--home", str(home), "--host", "H", "--toplevel", "/t/proj", "--now", "2026-10-27T10:00:00+09:00"]
    assert i.main(base) == 1  # 空ディレクトリは管轄外
    (p / "main.py").write_text("x", encoding="utf-8")
    (p / "CLAUDE.md").write_text("rules", encoding="utf-8")
    assert i.main(base + ["--apply"]) == 2  # テンプレート無し
    make_template(home)
    assert i.main(base) == 0
    assert not (p / ".pair-agent").exists()  # 下見
    assert i.main(base + ["--apply"]) == 0
    pa = p / ".pair-agent"
    for d in ("agreements", "sprints", "acceptance", "assurance", "skills", "current"):
        assert (pa / d / ".gitkeep").is_file()
    assert (p / "GEMINI.md").read_text(encoding="utf-8") == "rules"
    for d in (".agents/skills", ".agents/agents", ".agents/workflows"):
        assert (p / d).is_dir()
    key = hashlib.sha1(b"H/t/proj").hexdigest()[:8]
    ptr = json.loads((pa / "current" / f"{key}-proj.json").read_text(encoding="utf-8"))
    assert ptr["status"] == "idle" and ptr["workcopy"]["key"] == key
    assert i.main(base + ["--apply"]) == 1  # 既に初期化済み


def test_project_init_does_not_overwrite_gemini(tmp_path):
    i = load("project-init", "init_project")
    home = tmp_path / "home"
    make_template(home)
    p = tmp_path / "proj"
    p.mkdir()
    (p / "CLAUDE.md").write_text("A", encoding="utf-8")
    (p / "GEMINI.md").write_text("B", encoding="utf-8")
    assert i.main(["--project", str(p), "--home", str(home), "--host", "H", "--toplevel", "/t", "--apply"]) == 0
    assert (p / "GEMINI.md").read_text(encoding="utf-8") == "B"


# ------------------------------------------------------------ project-start-existing
def test_survey_project(tmp_path, capsys):
    sv = load("project-start-existing", "survey_project")
    p = tmp_path / "proj"
    p.mkdir()
    assert sv.main(["--project", str(p)]) == 0
    assert "project-start-empty" in capsys.readouterr().out
    (p / "README.md").write_text("# Title\n\nA tool for things.\n", encoding="utf-8")
    (p / "pyproject.toml").write_text("[x]", encoding="utf-8")
    (p / "tests").mkdir()
    (p / "src").mkdir()
    (p / "src" / "big.py").write_text("x" * 5000, encoding="utf-8")
    (p / "node_modules").mkdir()
    (p / "node_modules" / "skip.js").write_text("y" * 99999, encoding="utf-8")
    subprocess.run(["git", "-C", str(p), "init", "-q"], check=True, capture_output=True)
    capsys.readouterr()
    s = sv.survey(p)
    assert s["verdict"] == "needs-init" and s["files"] == 3  # node_modules は数えない
    assert s["build"] == ["Python"] and s["tests"] == ["tests"] and s["readme"] == "README.md"
    assert s["biggest"][0]["path"] == "src/big.py" and s["git"]["is_repo"] and s["git"]["dirty_files"] >= 1
    assert sv.main(["--project", str(p)]) == 0
    assert "project-init を展開" in capsys.readouterr().out
    (p / ".pair-agent").mkdir()
    assert sv.survey(p)["verdict"] == "initialized"
    sv.main(["--project", str(p), "--json"])
    assert json.loads(capsys.readouterr().out)["verdict"] == "initialized"
    assert sv.main(["--project", str(p / "nope")]) == 2

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def load(skill, name):
    p = ROOT / "skills" / "scripts" / skill / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"w5_{name}", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


cc = load("分担境界の切り方", "co_change")

LOG = """@@COMMIT@@c1
ui/a.py
core/x.py

@@COMMIT@@c2
ui/b.py

@@COMMIT@@c3
core/y.py
core/z.py

@@COMMIT@@c4
ui/a.py
core/x.py
docs/readme.md
"""


def test_parse_log():
    cs = cc.parse_log(LOG)
    assert [c["id"] for c in cs] == ["c1", "c2", "c3", "c4"]
    assert cs[0]["files"] == ["ui/a.py", "core/x.py"]


def test_cross_ratio_and_solo_ratio_by_depth():
    r = cc.analyze(cc.parse_log(LOG), depth=1)
    assert (r["commits_used"], r["cross_boundary_commits"], r["cross_ratio"]) == (4, 2, 0.5)
    g = {x["group"]: x for x in r["groups"]}
    assert (g["ui"]["commits"], g["ui"]["solo_commits"]) == (3, 1)
    assert (g["core"]["commits"], g["core"]["solo_commits"]) == (3, 1)


def test_pair_jaccard():
    r = cc.analyze(cc.parse_log(LOG), depth=1)
    p = next(x for x in r["pairs"] if (x["a"], x["b"]) == ("core", "ui"))
    assert (p["co_commits"], p["jaccard"]) == (2, round(2 / (3 + 3 - 2), 3))


def test_named_groups_exclude_unmatched_files():
    r = cc.analyze(cc.parse_log(LOG), groups=[("ui", "ui/*"), ("core", "core/*")])
    assert r["cross_boundary_commits"] == 2
    assert {g["group"] for g in r["groups"]} == {"ui", "core"}


def test_large_commits_are_excluded_and_counted():
    r = cc.analyze(cc.parse_log(LOG), depth=1, max_files=2)
    assert r["excluded_large"] == 1 and r["commits_used"] == 3


def test_cli_suggest_and_json(tmp_path, capsys):
    p = tmp_path / "h.txt"
    p.write_text(LOG, encoding="utf-8")
    assert cc.main(["--log", str(p), "--suggest", "0.4", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["suggest_move_boundary"][0]["a"] == "core"


def test_cli_rejects_unparsable_log_and_bad_group(tmp_path):
    p = tmp_path / "h.txt"
    p.write_text("nothing here", encoding="utf-8")
    assert cc.main(["--log", str(p)]) == 2
    p.write_text(LOG, encoding="utf-8")
    assert cc.main(["--log", str(p), "--group", "noequals"]) == 2


def test_reads_a_real_git_repo(tmp_path, capsys):
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "ui").mkdir()
    (tmp_path / "core").mkdir()
    (tmp_path / "ui" / "a.py").write_text("1", encoding="utf-8")
    (tmp_path / "core" / "b.py").write_text("1", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "one")
    (tmp_path / "ui" / "a.py").write_text("2", encoding="utf-8")
    git("commit", "-qam", "two")
    assert cc.main(["--repo", str(tmp_path), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["commits_used"] == 2 and out["cross_boundary_commits"] == 1

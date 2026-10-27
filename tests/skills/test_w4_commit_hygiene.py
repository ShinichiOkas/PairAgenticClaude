import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _w4_load import load

m = load("バージョン管理の作法", "commit_hygiene.py")


def test_parse_states_and_quoted_japanese():
    text = ' M a.py\nM  b.py\nMM c.py\n?? "skills/\\343\\203\\220.md"\nR  old.py -> new.py\nUU x.py\n'
    es = m.parse_porcelain(text)
    assert [e["state"] for e in es] == ["unstaged", "staged", "staged+unstaged", "untracked", "staged", "conflict"]
    assert es[3]["path"] == "skills/バ.md"
    assert es[4]["path"] == "new.py"


def test_clean_and_untracked_only_is_not_clean():
    assert m.analyze([])["clean"] is True
    r = m.analyze(m.parse_porcelain("?? new.txt\n"))
    assert r["clean"] is False and any("未追跡" in p for p in r["problems"])


def test_group_limit_boundary():
    four = m.parse_porcelain(" M a/1\n M b/1\n M c/1\n M d/1\n")
    three = m.parse_porcelain(" M a/1\n M b/1\n M c/1\n")
    assert any("4 群" in p for p in m.analyze(four, 3)["problems"])
    assert not any("群" in p for p in m.analyze(three, 3)["problems"])


def test_generated_pair_and_marker():
    es = m.parse_porcelain(" M docs/gen.md\n")
    r = m.analyze(es, gen_map={"docs/gen.md": "models/src.mk"})
    assert any("生成物 docs/gen.md だけ" in p for p in r["problems"])
    es = m.parse_porcelain(" M models/src.mk\n")
    r = m.analyze(es, gen_map={"docs/gen.md": "models/src.mk"})
    assert any("再生成" in p for p in r["problems"])
    es = m.parse_porcelain(" M models/src.mk\n M docs/gen.md\n")
    assert m.analyze(es, gen_map={"docs/gen.md": "models/src.mk"})["problems"] == []
    r = m.analyze([], generated_check={"g.md": "# title\n", "h.md": "手で編集しない\n", "i.md": None})
    assert len(r["problems"]) == 2


@pytest.mark.skipif(shutil.which("git") is None, reason="git が無い")
def test_cli_with_real_repo(tmp_path):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    git("init", "-q")
    assert m.main(["--repo", str(tmp_path)]) == 0
    (tmp_path / "日本語.md").write_text("x", encoding="utf-8")
    assert m.main(["--repo", str(tmp_path), "--json"]) == 1
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "m")
    assert m.main(["--repo", str(tmp_path)]) == 0


def test_cli_stdin_file(tmp_path):
    s = tmp_path / "s.txt"
    s.write_text(" M a/x\n", encoding="utf-8")
    g = tmp_path / "g.json"
    g.write_text(json.dumps({}), encoding="utf-8")
    assert m.main(["--status-file", str(s), "--gen-map", str(g)]) == 1

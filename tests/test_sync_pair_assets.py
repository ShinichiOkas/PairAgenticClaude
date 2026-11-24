"""ペア固有の資産（Skill・叱責記録・ビジョン）が、install で全 PC へ届くこと。

確かめること:
  - skills/・corrections/・vision/ の *.md と GOVERNANCE.md が Claude／Antigravity の両方の pair-agent/ へ写る（archive/ などは写らない）
  - 写し先の既存ファイルは消えない・減らない（ローカルにだけある物・その PC で直した物は触らない）
  - 上流の古い写しだけは新しい版へ更新される（失うものが無い）
  - 2 回目は変化なし
  - install.sh・install.bat が submodule を取得して写す（一時のホーム・一時のリポジトリで実走。本物のホームには書かない）
  - submodule が取れず中身も無いと、install は終了コード 1
  - manager/pamgr/mapping.py の配布対応が install と同じ置き場
"""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sync_pair_assets", ROOT / "tools" / "sync_pair_assets.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]


def git(cwd: Path, *args: str, env: dict | None = None) -> str:
    r = subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout


def rm_tree(p: Path) -> None:
    """git の object は Windows で読み取り専用。権限を外して消す。"""
    def _ow(func, path, _exc):
        os.chmod(path, 0o700)
        func(path)
    if p.exists():
        shutil.rmtree(p, onerror=_ow)


def put(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))


@pytest.fixture
def upstream(tmp_path: Path) -> Path:
    """pair-agent-skills の形の上流。skills/a.md は 2 つの版（v1 → v2）を持つ。"""
    up = tmp_path / "upstream"
    up.mkdir()
    git(up, "init", "-q", "-b", "main")
    put(up / "GOVERNANCE.md", "# governance\n")
    put(up / "skills" / "a.md", "a v1\n")
    put(up / "skills" / "b.md", "b\n")
    put(up / "skills" / "build.ps1", "not markdown\n")
    put(up / "corrections" / "c.md", "c\n")
    put(up / "vision" / "v.md", "v\n")
    put(up / "archive" / "old.md", "archived\n")
    put(up / "tools" / "t.md", "tool\n")
    git(up, "add", "-A")
    git(up, "commit", "-q", "-m", "v1")
    put(up / "skills" / "a.md", "a v2\n")
    git(up, "add", "-A")
    git(up, "commit", "-q", "-m", "v2")
    return up


def snapshot(home: Path) -> dict[str, tuple[bytes, int]]:
    base = home / "pair-agent"
    return {
        p.relative_to(base).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for sub in ("skills", "corrections", "vision")
        for p in (base / sub).rglob("*") if p.is_file()
    }


def test_copies_the_three_areas_and_governance_to_both_homes(upstream: Path, tmp_path: Path):
    h1, h2 = tmp_path / "claude", tmp_path / "gemini"
    assert mod.main(["--src", str(upstream), "--home", str(h1), "--home", str(h2)]) == 0
    for h in (h1, h2):
        b = h / "pair-agent"
        assert (b / "skills" / "a.md").read_text(encoding="utf-8") == "a v2\n"
        assert (b / "skills" / "b.md").is_file()
        assert (b / "corrections" / "c.md").is_file()
        assert (b / "vision" / "v.md").is_file()
        assert (b / "GOVERNANCE.md").is_file()
        assert not (b / "skills" / "build.ps1").exists()
        assert not (b / "archive").exists() and not (b / "tools").exists()


def test_second_run_changes_nothing(upstream: Path, tmp_path: Path):
    h = tmp_path / "claude"
    mod.main(["--src", str(upstream), "--home", str(h)])
    before = snapshot(h)
    assert mod.main(["--src", str(upstream), "--home", str(h)]) == 0
    assert snapshot(h) == before


def test_never_loses_local_files_and_updates_only_old_upstream_copies(upstream: Path, tmp_path: Path, capsys):
    h = tmp_path / "claude"
    b = h / "pair-agent"
    put(b / "skills" / "local-only.md", "only on this PC\n")                 # ローカルにだけある
    put(b / "skills" / "b.md", "b edited on this PC\n")                      # その PC で直した（上流の過去の版ではない）
    put(b / "skills" / "a.md", "a v1\n")                                     # 上流の古い写し
    put(b / "corrections" / "c.md", "c\r\n")                                 # 改行だけの違い
    assert mod.main(["--src", str(upstream), "--home", str(h)]) == 0
    assert (b / "skills" / "local-only.md").read_text(encoding="utf-8") == "only on this PC\n"
    assert (b / "skills" / "b.md").read_text(encoding="utf-8") == "b edited on this PC\n"
    assert (b / "skills" / "a.md").read_text(encoding="utf-8") == "a v2\n"
    assert (b / "corrections" / "c.md").read_bytes() == b"c\r\n"
    out = capsys.readouterr().out
    assert "skills/b.md" in out and "kept-local-different 1" in out and "updated 1" in out


def test_crlf_copy_of_an_old_upstream_version_is_still_recognised(upstream: Path, tmp_path: Path):
    h = tmp_path / "claude"
    put(h / "pair-agent" / "skills" / "a.md", "a v1\r\n")
    mod.main(["--src", str(upstream), "--home", str(h)])
    assert (h / "pair-agent" / "skills" / "a.md").read_text(encoding="utf-8") == "a v2\n"


def test_empty_or_missing_source_is_an_error(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    assert mod.main(["--src", str(tmp_path / "empty"), "--home", str(tmp_path / "h")]) == 1
    assert mod.main(["--src", str(tmp_path / "nope"), "--home", str(tmp_path / "h")]) == 1
    assert not (tmp_path / "h").exists()


def test_mapping_uses_the_same_destinations_as_install(upstream: Path, tmp_path: Path):
    sys.path.insert(0, str(ROOT / "manager"))
    try:
        from pamgr import mapping
    finally:
        sys.path.remove(str(ROOT / "manager"))
    master = tmp_path / "master"
    shutil.copytree(upstream, master / "external" / "pair-agent-skills", ignore=shutil.ignore_patterns(".git"))
    from_mapping = {rel for e in mapping.ENTRIES if e.scope == "user" for _src, rel in mapping.expand(e, master)}
    from_install = {f"pair-agent/{rel}" for _p, rel in mod.plan_items(master / "external" / "pair-agent-skills")}
    assert from_mapping == from_install
    assert "pair-agent/skills/a.md" in from_mapping and "pair-agent/GOVERNANCE.md" in from_mapping


# ---- install.sh / install.bat の実走（一時のリポジトリ・一時のホーム） -------------------------------------

def _make_repo(tmp_path: Path, upstream: Path, url: str | None = None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for f in ("install.sh", "install.bat"):
        shutil.copy2(ROOT / f, repo / f)
    for d in ("tools", "home-claude"):
        shutil.copytree(ROOT / d, repo / d, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    env = _env(tmp_path / "unused")
    git(repo, "submodule", "add", "-q", str(upstream), "external/pair-agent-skills", env=env)
    if url is not None:
        gm = ['[submodule "external/pair-agent-skills"]', "\tpath = external/pair-agent-skills", "\turl = " + url, ""]
        (repo / ".gitmodules").write_text("\n".join(gm))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add submodule")
    # 作業ツリーは「clone 直後で submodule が空」の状態にして、install が取得するところから確かめる
    rm_tree(repo / "external" / "pair-agent-skills")
    (repo / "external" / "pair-agent-skills").mkdir()
    rm_tree(repo / ".git" / "modules")
    git(repo, "config", "--remove-section", "submodule.external/pair-agent-skills")
    return repo


def _env(home: Path) -> dict:
    env = dict(os.environ)
    env.update(HOME=str(home), USERPROFILE=str(home), HOMEDRIVE="", GIT_TERMINAL_PROMPT="0",
               GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="protocol.file.allow", GIT_CONFIG_VALUE_0="always")
    return env


def _bash() -> str | None:
    if os.name != "nt":
        return shutil.which("bash")
    git_exe = shutil.which("git")
    if not git_exe:
        return None
    for cand in (Path(git_exe).parent.parent / "bin" / "bash.exe", Path(git_exe).parent.parent.parent / "bin" / "bash.exe"):
        if cand.is_file():
            return str(cand)
    return None


def _run_install(kind: str, repo: Path, home: Path) -> subprocess.CompletedProcess:
    if kind == "sh":
        bash = _bash()
        if not bash:
            pytest.skip("bash が無い")
        cmd = [bash, "install.sh"]
    else:
        if os.name != "nt":
            pytest.skip("install.bat は Windows だけ")
        cmd = ["cmd", "/c", str(repo / "install.bat")]
    return subprocess.run(cmd, cwd=repo, env=_env(home), capture_output=True, text=True, errors="replace", timeout=300)


@pytest.mark.parametrize("kind", ["sh", "bat"])
def test_install_fetches_submodule_and_distributes_without_losing_local_files(kind: str, upstream: Path, tmp_path: Path):
    repo = _make_repo(tmp_path, upstream)
    home = tmp_path / "home"
    local = home / ".claude" / "pair-agent" / "skills" / "local-only.md"
    put(local, "only on this PC\n")
    edited = home / ".gemini" / "config" / "pair-agent" / "skills" / "b.md"
    put(edited, "b edited on this PC\n")

    r = _run_install(kind, repo, home)
    assert r.returncode == 0, r.stdout + r.stderr
    for base in (home / ".claude" / "pair-agent", home / ".gemini" / "config" / "pair-agent"):
        assert (base / "skills" / "a.md").read_text(encoding="utf-8").replace("\r\n", "\n") == "a v2\n"
        assert (base / "corrections" / "c.md").is_file()
        assert (base / "vision" / "v.md").is_file()
        assert (base / "GOVERNANCE.md").is_file()
        assert not (base / "archive").exists()
    assert local.read_text(encoding="utf-8") == "only on this PC\n"
    assert edited.read_text(encoding="utf-8") == "b edited on this PC\n"

    claude_before = snapshot(home / ".claude")
    gemini_before = snapshot(home / ".gemini" / "config")
    r2 = _run_install(kind, repo, home)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert snapshot(home / ".claude") == claude_before
    assert snapshot(home / ".gemini" / "config") == gemini_before


@pytest.mark.parametrize("kind", ["sh", "bat"])
def test_install_fails_with_exit_1_when_the_submodule_cannot_be_fetched(kind: str, upstream: Path, tmp_path: Path):
    repo = _make_repo(tmp_path, upstream, url=str(tmp_path / "does-not-exist"))
    home = tmp_path / "home"
    r = _run_install(kind, repo, home)
    assert r.returncode == 1, r.stdout + r.stderr
    # 周辺の手順は進んでいる（規範・ルールは入る）。Skill が届かなかったことは終了コードで分かる
    assert (home / ".claude" / "rules" / "pair-agent-core.md").is_file()
    assert not list((home / ".claude" / "pair-agent" / "skills").glob("*.md"))

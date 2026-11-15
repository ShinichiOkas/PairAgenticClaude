"""GitHub 経由の同期（UC4）。マスターの git を、ほかの PC と揃える。

- ツールが触るのは TOOL_PATHS だけ（stage・commit の対象）。それ以外の変更・stage 済みの物には触らない
- pull は fast-forward のみ。衝突（diverged）は直さず報告する（節ごとのマージ・J4 は呼び出し側）
- force push・rebase・reset はしない。git が失敗しても例外にせず ok False と stderr を返す
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import paths

TOOL_PATHS = ("home-claude", "situations")

_SHORT = 60
_LONG = 180


def _root() -> Path:
    return paths.master_root()


def _git(root: Path, *args: str, timeout: int = _SHORT) -> tuple[int, str, str]:
    """git を 1 回走らせる。(終了コード, stdout, stderr)。失敗しても例外にしない（git 無し・タイムアウトは 127・124）。"""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    cmd = ["git", "-C", str(root), "-c", "core.quotepath=false", *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return 127, "", "git が見つからない"
    except subprocess.TimeoutExpired:
        return 124, "", f"git がタイムアウトした: {' '.join(args[:2])}"
    except OSError as e:
        return 127, "", str(e)
    return p.returncode, p.stdout, p.stderr.strip()


def _err(r: tuple[int, str, str], fallback: str) -> str:
    return r[2] or r[1].strip() or fallback


def _upstream(root: Path) -> dict | None:
    """現在のブランチの upstream。無ければ None。{"ref": "origin/main", "remote": "origin", "branch": "main"}"""
    rc, out, _ = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ref = out.strip()
    if rc != 0 or not ref:
        return None
    rc, out, _ = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
    cur = out.strip() if rc == 0 else ""
    remote = ""
    branch = ref
    if cur:
        _, o, _ = _git(root, "config", f"branch.{cur}.remote")
        remote = o.strip()
        _, o, _ = _git(root, "config", f"branch.{cur}.merge")
        merge = o.strip()
        if merge.startswith("refs/heads/"):
            branch = merge[len("refs/heads/"):]
    if not remote:
        remote, _, branch = ref.partition("/")
    return {"ref": ref, "remote": remote, "branch": branch}


def _dirty(root: Path) -> list[str]:
    """TOOL_PATHS の下で未コミットの変更があるファイル（リポジトリ相対の posix パス）。"""
    rc, out, _ = _git(root, "status", "--porcelain", "-z", "-uall", "--", *TOOL_PATHS)
    if rc != 0:
        return []
    res: list[str] = []
    parts = out.split("\0")
    i = 0
    while i < len(parts):
        ent = parts[i]
        i += 1
        if len(ent) < 4:
            continue
        xy, path = ent[:2], ent[3:]
        if "R" in xy or "C" in xy:  # 改名・複製は元の名前が次の欄に続く
            i += 1
        res.append(path.replace("\\", "/"))
    return sorted(set(res))


def status(fetch: bool = False) -> dict:
    """マスターの git の状態。fetch=True なら先に git fetch する。"""
    root = _root()
    res: dict = {"ok": False, "root": str(root), "branch": None, "head": None, "remote": None,
                 "ahead": 0, "behind": 0, "dirty": []}
    rc, out, err = _git(root, "rev-parse", "--is-inside-work-tree")
    if rc != 0 or out.strip() != "true":
        res["error"] = f"git のリポジトリではない: {err or root}"
        return res
    if fetch:
        r = _git(root, "fetch", timeout=_LONG)
        if r[0] != 0:
            res["fetch_error"] = _err(r, "git fetch に失敗")
    rc, out, _ = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
    res["branch"] = out.strip() or None if rc == 0 else None
    rc, out, _ = _git(root, "rev-parse", "HEAD")
    res["head"] = out.strip() if rc == 0 and out.strip() else None
    up = _upstream(root)
    if up:
        _, url, _ = _git(root, "remote", "get-url", up["remote"])
        res["remote"] = url.strip() or up["remote"]
        rc, out, _ = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}")
        if rc == 0:
            a, _, b = out.strip().partition("\t") if "\t" in out else out.strip().partition(" ")
            try:
                res["ahead"], res["behind"] = int(a), int(b)
            except ValueError:
                pass
    res["dirty"] = _dirty(root)
    res["ok"] = True
    return res


def _foreign_commits(root: Path, old: str, new: str) -> list[dict]:
    """old..new のコミットのうち、作者のメールが自分（git config user.email）と違うもの。files は TOOL_PATHS の下だけ。"""
    _, me, _ = _git(root, "config", "user.email")
    me = me.strip().lower()
    rc, out, _ = _git(root, "log", f"{old}..{new}", "--reverse", "--format=%H%x1f%an%x1f%ae%x1f%s")
    if rc != 0:
        return []
    res: list[dict] = []
    for line in out.splitlines():
        f = line.split("\x1f")
        if len(f) < 4:
            continue
        sha, author, email, subject = f[0], f[1], f[2], f[3]
        if email.strip().lower() == me:
            continue
        rc, fo, _ = _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-m", "--root", sha, "--", *TOOL_PATHS)
        files = sorted({x.strip() for x in fo.splitlines() if x.strip()}) if rc == 0 else []
        res.append({"sha": sha, "author": author, "email": email, "subject": subject, "files": files})
    return res


def pull() -> dict:
    """git fetch のあと fast-forward だけで取り込む。衝突したら diverged True で報告する（何も壊さない）。"""
    root = _root()
    res: dict = {"ok": False, "old_head": None, "new_head": None, "changed": [], "foreign": [], "diverged": False}
    rc, out, err = _git(root, "rev-parse", "--is-inside-work-tree")
    if rc != 0 or out.strip() != "true":
        res["error"] = f"git のリポジトリではない: {err or root}"
        return res
    if not _upstream(root):
        res["error"] = "upstream（追跡する遠隔ブランチ）が設定されていない"
        return res
    rc, out, _ = _git(root, "rev-parse", "HEAD")
    if rc != 0 or not out.strip():
        res["error"] = "まだコミットが無い"
        return res
    old = out.strip()
    res["old_head"] = res["new_head"] = old
    r = _git(root, "fetch", timeout=_LONG)
    if r[0] != 0:
        res["error"] = _err(r, "git fetch に失敗")
        return res
    r = _git(root, "merge", "--ff-only", "@{u}", timeout=_LONG)
    if r[0] != 0:
        res["error"] = _err(r, "git merge --ff-only に失敗")
        rc, out, _ = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}")
        if rc == 0:
            a, b = (out.split() + ["0", "0"])[:2]
            res["diverged"] = a.isdigit() and b.isdigit() and int(a) > 0 and int(b) > 0
        return res
    rc, out, _ = _git(root, "rev-parse", "HEAD")
    new = out.strip() if rc == 0 and out.strip() else old
    res["new_head"] = new
    res["ok"] = True
    if new != old:
        rc, out, _ = _git(root, "diff", "--name-only", old, new)
        res["changed"] = [x.strip() for x in out.splitlines() if x.strip()] if rc == 0 else []
        res["foreign"] = _foreign_commits(root, old, new)
    return res


def _tool_paths(root: Path) -> list[str]:
    """TOOL_PATHS のうち、作業ツリーにあるか git が知っているもの（無いパスを git add に渡すと失敗するため）。"""
    res = []
    for p in TOOL_PATHS:
        if (root / p).exists():
            res.append(p)
            continue
        rc, out, _ = _git(root, "ls-files", "--", p)
        if rc == 0 and out.strip():
            res.append(p)
    return res


def publish(message: str) -> dict:
    """TOOL_PATHS だけを stage・commit し、upstream があれば push する（force しない）。"""
    root = _root()
    res: dict = {"ok": False, "commit": None, "pushed": False, "files": []}
    rc, out, err = _git(root, "rev-parse", "--is-inside-work-tree")
    if rc != 0 or out.strip() != "true":
        res["error"] = f"git のリポジトリではない: {err or root}"
        return res
    if not (message or "").strip():
        res["error"] = "コミットメッセージが空"
        return res
    tp = _tool_paths(root)
    if not tp:
        res["ok"] = True
        return res
    r = _git(root, "add", "-A", "--", *tp)
    if r[0] != 0:
        res["error"] = _err(r, "git add に失敗")
        return res
    rc, out, _ = _git(root, "diff", "--cached", "--name-only", "--", *tp)
    files = [x.strip() for x in out.splitlines() if x.strip()] if rc == 0 else []
    if not files:
        res["ok"] = True
        return res
    res["files"] = files
    r = _git(root, "commit", "-m", message, "--", *tp, timeout=_LONG)
    if r[0] != 0:
        res["error"] = _err(r, "git commit に失敗")
        return res
    rc, out, _ = _git(root, "rev-parse", "HEAD")
    res["commit"] = out.strip() if rc == 0 else None
    up = _upstream(root)
    if not up:
        res["ok"] = True
        return res
    r = _git(root, "push", up["remote"], f"HEAD:refs/heads/{up['branch']}", timeout=_LONG)
    if r[0] != 0:
        res["error"] = _err(r, "git push に失敗")
        return res
    res["pushed"] = True
    res["ok"] = True
    return res

"""tools/skill_library_ops.py のテスト。一時ディレクトリに小さな skill-library を作って各サブコマンドを確かめる。"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import skill_library_ops as ops  # noqa: E402


def fm(**kw):
    return "---\n" + "\n".join(f"{k}: {v}" for k, v in kw.items()) + "\n---\n"


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "pair-agent"
    for d in ("skill-library/pending", "skill-library/approved", "skills"):
        (h / d).mkdir(parents=True)
    return h


def run(home, *args):
    return ops.main(["--home", str(home), *map(str, args)])


def make_source(tmp_path, name="src.md", text="判断は師匠が下す。確認してから進める。"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def make_approved(home, name, src, body, date="2026-10-27", extra=""):
    t = fm(name=name, description="説明", source_project="proj", source_path=f'"{src}"',
           survey_date="2026-10-20", generalization_score="0.9", status="approved", approved_date=date)
    if extra:
        t = t.replace("\n---\n", "\n" + extra + "---\n", 1)
    t += body
    (home / "skill-library/approved" / f"{name}.md").write_text(t, encoding="utf-8")


# ------------------------------------------------------------ verify

def test_verify_ok_and_quote_normalization(home, tmp_path, capsys):
    src = make_source(tmp_path)
    make_approved(home, "ok", src, "> 「判断は 師匠が下す」\n本文\n")
    assert run(home, "verify") == 0
    assert "with problems: 0" in capsys.readouterr().out


def test_verify_detects_quote_missing_and_placeholder(home, tmp_path, capsys):
    src = make_source(tmp_path)
    make_approved(home, "bad", src, "> 元に無い引用の行です、ほんとうに\n{PROJECT_NAME} を使う\n")
    assert run(home, "verify") == 1
    out = capsys.readouterr().out
    assert "quote-not-in-source" in out and "placeholders: {PROJECT_NAME}" in out


def test_verify_ignores_placeholders_in_code(home, tmp_path):
    src = make_source(tmp_path)
    body = "```python\nx = f'{SCHEMA_VERSION}'\n```\nインライン `{OTHER_NAME}` も除外\n"
    make_approved(home, "code", src, body)
    assert run(home, "verify") == 0
    assert ops.find_placeholders("{REAL_ONE} と `{CODE_ONE}`") == ["{REAL_ONE}"]


def test_verify_frontmatter_and_source_missing(home, tmp_path, capsys):
    (home / "skill-library/approved/nofm.md").write_text("本文だけ\n", encoding="utf-8")
    make_approved(home, "nosrc", tmp_path / "無い.md", "x\n")
    assert run(home, "verify", "--json-out", tmp_path / "r.json") == 1
    out = capsys.readouterr().out
    assert "frontmatter-open" in out and "source-missing" in out
    assert "nofm.md" in json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))


def test_verify_date_filter(home, tmp_path, capsys):
    src = make_source(tmp_path)
    make_approved(home, "old", src, "{BAD_ONE}\n", date="2026-01-01")
    assert run(home, "verify", "--approved-date", "2026-10-27") == 0
    assert "checked: 0" in capsys.readouterr().out


# ------------------------------------------------------------ waves

def make_pending(home, n):
    for i in range(n):
        (home / f"skill-library/pending/s{i:02d}.md").write_text("x", encoding="utf-8")


def test_waves_dry_run_writes_nothing(home, tmp_path, capsys):
    make_pending(home, 5)
    work = tmp_path / "w"
    assert run(home, "waves", "--size", 2, "--work-dir", work) == 0
    assert not work.exists()
    assert "下見" in capsys.readouterr().out


def test_waves_apply_numbers_and_no_overwrite(home, tmp_path, capsys):
    make_pending(home, 5)
    work = tmp_path / "w"
    assert run(home, "waves", "--size", 2, "--work-dir", work, "--apply") == 0
    r = work / "review"
    assert (r / "groupG1.txt").read_text(encoding="utf-8").split() == ["s00.md", "s01.md"]
    assert (r / "groupG2.txt").exists() and not (r / "groupG3.txt").exists()
    # 2 回目: 端数 s04 は割り当てず残る。pending を増やすと端数と合わせて 2 件になり、番号は続きから
    make_pending(home, 7)
    first = (r / "groupG1.txt").read_text(encoding="utf-8")
    assert run(home, "waves", "--size", 2, "--work-dir", work, "--apply") == 0
    assert (r / "groupG3.txt").exists()
    assert (r / "groupG1.txt").read_text(encoding="utf-8") == first


def test_waves_number_survives_gaps(home, tmp_path):
    """欠番があっても件数ではなく最大番号の次を使い、既存を上書きしない。"""
    make_pending(home, 4)
    work = tmp_path / "w"
    (work / "review").mkdir(parents=True)
    (work / "review/groupG5.txt").write_text("keep\n", encoding="utf-8")
    assert run(home, "waves", "--size", 2, "--work-dir", work, "--apply") == 0
    assert (work / "review/groupG5.txt").read_text(encoding="utf-8") == "keep\n"
    assert (work / "review/groupG6.txt").exists() and (work / "review/groupG7.txt").exists()


def test_waves_include_remainder(home, tmp_path):
    make_pending(home, 3)
    work = tmp_path / "w"
    assert run(home, "waves", "--size", 2, "--work-dir", work, "--include-remainder", "--apply") == 0
    assert (work / "review/groupG2.txt").read_text(encoding="utf-8").split() == ["s02.md"]


# ------------------------------------------------------------ index

INDEX = (
    "# index\n"
    "| name | score | status | note |\n"
    "| [A](pending/a.md) | 0.9 | pending | n |\n"
    "| [B](pending/b.md) | 0.8 | pending | n |\n"
    "| [C](pending/c.md) | 0.7 | pending | n |\n"
)


def test_index_preview_then_apply(home, capsys):
    lib = home / "skill-library"
    (lib / "index.md").write_text(INDEX, encoding="utf-8")
    (lib / "approved/a.md").write_text("x", encoding="utf-8")
    (lib / "pending/c.md").write_text("x", encoding="utf-8")
    assert run(home, "index") == 0
    assert (lib / "index.md").read_text(encoding="utf-8") == INDEX
    assert "approved: 1 rejected: 1" in capsys.readouterr().out
    assert run(home, "index", "--apply") == 0
    new = (lib / "index.md").read_text(encoding="utf-8").splitlines()
    assert len(new) == len(INDEX.splitlines())
    assert "| [A](approved/a.md) | 0.9 | approved | n |" in new
    assert "| B | 0.8 | rejected | n |" in new
    assert "| [C](pending/c.md) | 0.7 | pending | n |" in new


# ------------------------------------------------------------ promote

def test_promote_preview_apply_and_no_overwrite(home, tmp_path):
    src_dir = tmp_path / "proj"
    src_dir.mkdir()
    s1 = make_source(src_dir, "alpha.md")
    s2 = make_source(src_dir, "beta.md")
    make_approved(home, "alpha", s1, "本文A\n", extra="provenance: 元\n")
    make_approved(home, "beta", s2, "本文B\n")
    (home / "skills/beta.md").write_text("既存", encoding="utf-8")
    lst = tmp_path / "list.txt"
    lst.write_text("alpha.md\nbeta.md\n無い…\n", encoding="utf-8")
    assert run(home, "promote", "--list", lst, "--approved-date", "2026-10-27") == 0
    assert not (home / "skills/alpha.md").exists()
    assert run(home, "promote", "--list", lst, "--approved-date", "2026-10-27", "--apply") == 0
    out = (home / "skills/alpha.md").read_text(encoding="utf-8")
    assert "source_path" not in out and "status:" not in out and "approved_date" not in out
    assert "provenance: 元／skill-library サーベイ 2026-10-27" in out
    assert out.endswith("本文A\n")
    assert (home / "skills/beta.md").read_text(encoding="utf-8") == "既存"


def test_promote_adds_provenance_when_absent(home, tmp_path):
    s = make_source(tmp_path, "gamma.md")
    make_approved(home, "gamma", s, "本文\n")
    lst = tmp_path / "l.txt"
    lst.write_text("gamma\n", encoding="utf-8")
    assert run(home, "promote", "--list", lst, "--apply") == 0
    assert "provenance: skill-library サーベイ" in (home / "skills/gamma.md").read_text(encoding="utf-8")


# ------------------------------------------------------------ dedupe-candidates

def make_dup_set(home):
    long = "確認してから進める。判断基準は師匠が決める。勝手に範囲を広げない。" * 3
    for d, name, kind in (("skill-library/approved", "p", "approved"), ("skills", "q", "global")):
        (home / d / f"{name}.md").write_text(fm(name=name, description=long) + long + "\n", encoding="utf-8")
    (home / "skills/z.md").write_text(fm(name="z", description="全然別") + "recipe for soup and bread baking\n", encoding="utf-8")


def test_dedupe_candidates_without_judge_never_calls_network(home, tmp_path, monkeypatch):
    make_dup_set(home)
    monkeypatch.setattr(ops.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network"))
    out = tmp_path / "c.jsonl"
    assert run(home, "dedupe-candidates", "--out", out) == 0
    recs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert recs and recs[0]["sim"] > 0.5 and {recs[0]["a"], recs[0]["b"]} == {"approved/p.md", "global/q.md"}
    assert all("rel" not in r for r in recs)


def test_dedupe_candidates_with_judge_uses_local_ollama(home, tmp_path):
    make_dup_set(home)

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            body = json.dumps({"response": json.dumps({"rel": "同一", "why": "t"})}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        out = tmp_path / "j.jsonl"
        url = f"http://127.0.0.1:{srv.server_port}"
        assert run(home, "dedupe-candidates", "--judge-model", "m", "--ollama-url", url, "--out", out) == 0
    finally:
        srv.shutdown()
    recs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert recs and all(r["rel"] == "同一" for r in recs)

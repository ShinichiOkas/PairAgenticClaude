import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w4_load import load

m = load("差分の追跡", "trace_changes.py")


def test_trace_matches_unmatched(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("実装は src/core/engine.py にある。parser.py も参照。", encoding="utf-8")
    (docs / "b.md").write_text("無関係", encoding="utf-8")
    changes = m.read_changes("src/core/engine.py\nsrc/util/parser.py\nsrc/lonely.py\n\nsrc/core/engine.py\n")
    assert changes == ["src/core/engine.py", "src/util/parser.py", "src/lonely.py"]
    res = m.trace(changes, m.collect_docs([str(docs)]))
    byc = {r["change"]: r for r in res["changes"]}
    assert byc["src/core/engine.py"]["docs"][0]["match"] == "path"
    assert byc["src/util/parser.py"]["docs"][0]["match"] == "name"
    assert res["unmatched"] == ["src/lonely.py"]
    assert res["counts"] == {"changes": 3, "matched": 2, "unmatched": 1, "docs_scanned": 2}


def test_name_match_is_not_substring(tmp_path):
    d = tmp_path / "x.md"
    d.write_text("see myparser.py.bak", encoding="utf-8")
    res = m.trace(["lib/parser.py"], [d])
    assert res["unmatched"] == ["lib/parser.py"]


def test_cli_exit_codes_and_mtime(tmp_path, capsys):
    src = tmp_path / "src.py"
    src.write_text("x", encoding="utf-8")
    doc = tmp_path / "d.md"
    doc.write_text("uses src.py", encoding="utf-8")
    os.utime(doc, (1000, 1000))
    ch = tmp_path / "c.txt"
    ch.write_text("src.py\n", encoding="utf-8")
    rc = m.main(["--changes", str(ch), "--docs", str(doc), "--repo-root", str(tmp_path), "--with-mtime", "--json"])
    assert rc == 0
    assert '"doc_older_than_source": true' in capsys.readouterr().out
    ch.write_text("nothing.py\n", encoding="utf-8")
    assert m.main(["--changes", str(ch), "--docs", str(doc)]) == 1

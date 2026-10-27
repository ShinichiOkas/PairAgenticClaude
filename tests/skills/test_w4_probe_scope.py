import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w4_load import load

m = load("使い捨ての規律", "probe_scope.py")


def setup(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("v1", encoding="utf-8")
    (root / ".probe").mkdir()
    snap = tmp_path / "before.json"
    assert m.main(["snapshot", "--root", str(root), "--out", str(snap)]) == 0
    return root, snap


def test_snapshot_refuses_overwrite_and_inside_root(tmp_path):
    root, snap = setup(tmp_path)
    assert m.main(["snapshot", "--root", str(root), "--out", str(snap)]) == 2
    assert m.main(["snapshot", "--root", str(root), "--out", str(root / "s.json")]) == 2


def test_check_clean_then_probe_artifacts_are_side_effects(tmp_path):
    root, snap = setup(tmp_path)
    assert m.main(["check", "--root", str(root), "--snapshot", str(snap), "--workspace", ".probe"]) == 0
    (root / ".probe" / "log.txt").write_text("t", encoding="utf-8")
    assert m.main(["check", "--root", str(root), "--snapshot", str(snap), "--workspace", ".probe"]) == 0


def test_writing_to_deliverable_or_outside_workspace_is_violation(tmp_path):
    root, snap = setup(tmp_path)
    (root / "src" / "app.py").write_text("v2", encoding="utf-8")
    assert m.main(["check", "--root", str(root), "--snapshot", str(snap), "--workspace", ".probe", "--protect", "src"]) == 1
    (root / "src" / "app.py").write_text("v1", encoding="utf-8")
    (root / "stray.txt").write_text("t", encoding="utf-8")
    assert m.main(["check", "--root", str(root), "--snapshot", str(snap), "--workspace", ".probe"]) == 1
    # workspace 指定なしなら外側の新規は違反にしない
    assert m.main(["check", "--root", str(root), "--snapshot", str(snap)]) == 0


def test_protect_prefix_is_not_substring(tmp_path):
    root, snap = setup(tmp_path)
    (root / "src2").mkdir()
    (root / "src2" / "x").write_text("t", encoding="utf-8")
    assert m.main(["check", "--root", str(root), "--snapshot", str(snap), "--protect", "src"]) == 0


def test_discard_dry_run_then_apply_only_touches_new_in_workspace(tmp_path):
    root, snap = setup(tmp_path)
    (root / ".probe" / "sub").mkdir()
    (root / ".probe" / "sub" / "a.log").write_text("t", encoding="utf-8")
    (root / "src" / "app.py").write_text("v2", encoding="utf-8")
    (root / "outside.txt").write_text("t", encoding="utf-8")
    assert m.main(["discard", "--root", str(root), "--snapshot", str(snap), "--workspace", ".probe"]) == 0
    assert (root / ".probe" / "sub" / "a.log").exists()
    assert m.main(["discard", "--root", str(root), "--snapshot", str(snap), "--workspace", ".probe", "--apply"]) == 0
    assert not (root / ".probe" / "sub").exists()
    assert (root / ".probe").is_dir()
    assert (root / "src" / "app.py").read_text(encoding="utf-8") == "v2"
    assert (root / "outside.txt").exists()


def test_discard_refuses_root_and_escape(tmp_path):
    root, snap = setup(tmp_path)
    assert m.main(["discard", "--root", str(root), "--snapshot", str(snap), "--workspace", ".", "--apply"]) == 2
    assert m.main(["discard", "--root", str(root), "--snapshot", str(snap), "--workspace", "..", "--apply"]) == 2

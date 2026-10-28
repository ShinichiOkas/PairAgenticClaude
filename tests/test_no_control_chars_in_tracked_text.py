"""追跡しているテキストに制御文字（タブ・改行を除く C0）が入っていないことを確かめる。

2026-10-28、エージェントが書いた票の `\\.gemini\\antigravity` の `\\a` が BEL（0x07）に潰れて
パスが壊れたまま commit された。書いた側からは見えないので、機械で止める。
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = ["*.md", "*.bat", "*.sh", "*.py", "*.json", "*.mk", "*.js"]
ALLOWED = {"\t", "\n", "\r"}


def _tracked_files():
    # -z と core.quotepath=false: 日本語のパスを引用符・8 進エスケープ無しで受け取る
    out = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z", *PATTERNS],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    return [ROOT / name for name in out.split("\0") if name]


def test_tracked_text_has_no_control_chars():
    bad = {}
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # UTF-8 でないファイルは対象外（読めないのを黙って通すのはこの 1 種だけ）
        found = sorted({hex(ord(c)) for c in text if ord(c) < 32 and c not in ALLOWED})
        if found:
            bad[str(path.relative_to(ROOT))] = found
    assert not bad, f"制御文字が入っている（バックスラッシュの潰れを疑う）: {bad}"

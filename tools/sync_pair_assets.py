#!/usr/bin/env python3
"""ペア固有の資産（Skill・叱責記録・ビジョン）を、external/pair-agent-skills から各ホームへ「足す」。

配るもの（--src の中の *.md だけ。archive/・skill-library/・template/・tools/ は配らない）:
  skills/*.md       -> <home>/pair-agent/skills/
  corrections/*.md  -> <home>/pair-agent/corrections/
  vision/*.md       -> <home>/pair-agent/vision/
  GOVERNANCE.md     -> <home>/pair-agent/GOVERNANCE.md

写し先の既存ファイルは、減らさない・消さない（~/.claude/pair-agent は PC ごとのローカルの Skill を持つ git の作業ツリーでもある）:
  - 写し先に無い            -> 写す
  - 同じ内容（改行の違いは無視） -> 何もしない（2 回目以降は変化なし）
  - 内容が違う
      - 写し先の内容が、上流の履歴にある過去の版と一致する（= 上流の古い写し。失うものが無い）-> 新しい版へ更新する
      - それ以外（その PC で直した・ローカルにだけある版）-> 触らず、名前を知らせる
  - 写し先にだけあるファイルには触らない

終了コード: 0=成功（変更なしを含む）  1=--src が無い・配る物が 1 件も無い
標準ライブラリだけ。Windows・Mac・Linux で動く。
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

AREAS = ("skills", "corrections", "vision")
SHOW_MAX = 12


def _blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def _history_blobs(src: Path, rel: str) -> set[str]:
    """上流（git）で、そのパスが過去に取った中身の blob id。履歴が引けなければ空。"""
    try:
        r = subprocess.run(
            ["git", "-C", str(src), "log", "--format=", "--raw", "--no-abbrev", "--no-renames", "--", rel],
            capture_output=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if r.returncode != 0:
        return set()
    out: set[str] = set()
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        # :100644 100644 <old> <new> M\t<path>
        meta = line.split("\t", 1)[0].split()
        if len(meta) >= 5 and meta[0].startswith(":"):
            out.update(h for h in meta[2:4] if set(h) != {"0"})
    return out


def plan_items(src: Path) -> list[tuple[Path, str]]:
    """(上流のファイル, <home>/pair-agent からの相対パス)"""
    items: list[tuple[Path, str]] = []
    gov = src / "GOVERNANCE.md"
    if gov.is_file():
        items.append((gov, "GOVERNANCE.md"))
    for area in AREAS:
        d = src / area
        if d.is_dir():
            for p in sorted(d.glob("*.md")):
                if p.is_file():
                    items.append((p, f"{area}/{p.name}"))
    return items


def sync_home(src: Path, home: Path, items: list[tuple[Path, str]], dry_run: bool) -> dict:
    base = home / "pair-agent"
    res = {"home": str(home), "copied": 0, "updated": 0, "same": 0, "kept": []}
    for sp, rel in items:
        dp = base / rel
        data = sp.read_bytes()
        if not dp.is_file():
            if not dry_run:
                dp.parent.mkdir(parents=True, exist_ok=True)
                dp.write_bytes(data)
            res["copied"] += 1
            continue
        cur = dp.read_bytes()
        if cur == data or _lf(cur) == _lf(data):
            res["same"] += 1
            continue
        past = _history_blobs(src, rel)
        if _blob_id(cur) in past or _blob_id(_lf(cur)) in past:
            if not dry_run:
                dp.write_bytes(data)
            res["updated"] += 1
        else:
            res["kept"].append(rel)
    return res


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True, help="external/pair-agent-skills のフォルダ")
    ap.add_argument("--home", action="append", required=True, help="~/.claude や ~/.gemini/config（複数可）")
    ap.add_argument("--dry-run", action="store_true", help="書かずに件数だけ出す")
    a = ap.parse_args(argv)

    src = Path(a.src)
    if not src.is_dir():
        print(f"[pair-agent] ERROR: pair-agent-skills not found: {src}", file=sys.stderr)
        return 1
    items = plan_items(src)
    if not items:
        print(f"[pair-agent] ERROR: nothing to distribute in {src} (empty submodule? run: git submodule update --init external/pair-agent-skills)", file=sys.stderr)
        return 1
    for h in a.home:
        r = sync_home(src, Path(h), items, a.dry_run)
        tag = " (dry run)" if a.dry_run else ""
        print(f"[pair-agent] pair-specific assets -> {r['home']}/pair-agent{tag}: "
              f"copied {r['copied']}, updated {r['updated']}, unchanged {r['same']}, kept-local-different {len(r['kept'])}")
        if r["kept"]:
            shown = ", ".join(r["kept"][:SHOW_MAX])
            more = f" ... (+{len(r['kept']) - SHOW_MAX})" if len(r["kept"]) > SHOW_MAX else ""
            print(f"[pair-agent]   kept (differs from upstream and is not an old upstream copy; not overwritten): {shown}{more}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

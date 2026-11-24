#!/usr/bin/env python3
"""~/.claude/settings.json の hooks に、Pair Agent が配るフックの項目を「足すだけ」で入れる。

settings.json は PC ごとの許可・モデル・鍵を含むので丸ごとは写さない。
- 雛形 home-claude/settings-hooks.json の hooks を読み、各 PC の settings.json へ足す
- 同じ matcher の中に、同じ command か、同じスクリプト（*.py の名前）を呼ぶ項目が既にあれば足さない
- hooks 以外のキーには触らない（読み込んだ順序のまま書き戻す）
- JSON が壊れている・形が想定外なら書かずに知らせる（終了コード 1）
- 書き換える前に settings.json.pair-agent-backup を 1 度だけ残す
- settings.json が無ければ、hooks だけの新しいファイルを作る
- --remove: 雛形が足した項目（上と同じ一致）だけを外す

終了コード: 0=成功（変更なしを含む） 1=書けなかった（壊れている・形が想定外・雛形が読めない）
標準ライブラリだけ。Windows・Mac・Linux で動く。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

PY_NAME = re.compile(r"[\w.-]+\.py")


def _scripts(command: str) -> set[str]:
    return set(PY_NAME.findall(command or ""))


def _same_hook(a: dict, b: dict) -> bool:
    ca, cb = a.get("command"), b.get("command")
    if not isinstance(ca, str) or not isinstance(cb, str):
        return False
    return ca == cb or bool(_scripts(ca) & _scripts(cb))


def _entry_has(entry: dict, hook: dict) -> bool:
    return any(isinstance(h, dict) and _same_hook(h, hook) for h in entry.get("hooks", []))


class Refuse(Exception):
    pass


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise Refuse(f"{path} is not valid JSON ({e}). Nothing was written. Fix it and run again.")
    except UnicodeDecodeError as e:
        raise Refuse(f"{path} is not valid UTF-8 ({e}). Nothing was written.")
    if not isinstance(data, dict):
        raise Refuse(f"{path}: top level is not an object. Nothing was written.")
    return data


def _check_shape(settings: dict, path: Path) -> dict:
    hooks = settings.get("hooks")
    if hooks is None:
        return {}
    if not isinstance(hooks, dict):
        raise Refuse(f"{path}: hooks is not an object. Nothing was written.")
    for ev, entries in hooks.items():
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise Refuse(f"{path}: hooks.{ev} has an unexpected shape. Nothing was written.")
        for e in entries:
            if "hooks" in e and not isinstance(e["hooks"], list):
                raise Refuse(f"{path}: hooks.{ev}[].hooks is not a list. Nothing was written.")
    return hooks


def merge(settings: dict, template: dict, path: Path) -> list[str]:
    """settings を直接書き換え、足した項目の説明を返す（無ければ空）。"""
    _check_shape(settings, path)
    added: list[str] = []
    for ev, t_entries in template.get("hooks", {}).items():
        for t in t_entries:
            for th in t.get("hooks", []):
                entries = settings.setdefault("hooks", {}).setdefault(ev, [])
                if any(_entry_has(e, th) for e in entries):
                    continue
                same_matcher = next((e for e in entries if e.get("matcher") == t.get("matcher") and isinstance(e.get("hooks", []), list)), None)
                if same_matcher is not None:
                    same_matcher.setdefault("hooks", []).append(dict(th))
                else:
                    new = {k: v for k, v in t.items() if k != "hooks"}
                    new["hooks"] = [dict(th)]
                    entries.append(new)
                added.append(f"{ev}[{t.get('matcher', '*')}] {sorted(_scripts(th.get('command', ''))) or th.get('command')}")
    return added


def remove(settings: dict, template: dict, path: Path) -> list[str]:
    hooks = _check_shape(settings, path)
    removed: list[str] = []
    for ev, t_entries in template.get("hooks", {}).items():
        entries = hooks.get(ev)
        if not entries:
            continue
        for t in t_entries:
            for th in t.get("hooks", []):
                for e in list(entries):
                    kept = [h for h in e.get("hooks", []) if not (isinstance(h, dict) and _same_hook(h, th))]
                    if len(kept) != len(e.get("hooks", [])):
                        removed.append(f"{ev}[{e.get('matcher', '*')}]")
                        e["hooks"] = kept
                        if not kept:
                            entries.remove(e)
        if not entries:
            del hooks[ev]
    if "hooks" in settings and not settings["hooks"]:
        del settings["hooks"]
    return removed


def _indent_of(text: str) -> int | str:
    m = re.search(r"^([ \t]+)\S", text, re.M)
    if not m:
        return 2
    ws = m.group(1)
    return "\t" if ws.startswith("\t") else len(ws)


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--settings", default=str(Path.home() / ".claude" / "settings.json"))
    ap.add_argument("--template", default=str(here.parent / "home-claude" / "settings-hooks.json"))
    ap.add_argument("--remove", action="store_true", help="remove only the entries the template adds")
    ap.add_argument("--dry-run", action="store_true", help="print what would change, write nothing")
    a = ap.parse_args(argv)
    path, tpath = Path(a.settings), Path(a.template)
    try:
        if not tpath.is_file():
            raise Refuse(f"template not found: {tpath}")
        template = _load_json(tpath)
        existed = path.is_file()
        raw = path.read_text(encoding="utf-8-sig") if existed else ""
        settings = _load_json(path) if existed else {}
        if a.remove:
            if not existed:
                print(f"[merge-hooks] {path} does not exist. Nothing to remove.")
                return 0
            changed = remove(settings, template, path)
            verb = "removed"
        else:
            changed = merge(settings, template, path)
            verb = "added"
        if not changed:
            print(f"[merge-hooks] no change ({path})")
            return 0
        if a.dry_run:
            print(f"[merge-hooks] dry-run: would be {verb}: {changed}")
            return 0
        if existed:
            bak = path.with_name(path.name + ".pair-agent-backup")
            if not bak.exists():
                bak.write_bytes(path.read_bytes())
        text = json.dumps(settings, ensure_ascii=False, indent=_indent_of(raw)) + "\n"
        _write_atomic(path, text)
        print(f"[merge-hooks] {verb}: {changed} ({path})")
        return 0
    except Refuse as e:
        print(f"[merge-hooks] {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"[merge-hooks] could not write: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

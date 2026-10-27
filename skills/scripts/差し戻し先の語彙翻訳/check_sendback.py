#!/usr/bin/env python
"""差し戻し指示の本文を、受け手の deps／blocks（.mk から読む）と突き合わせ、遮断対象の語・受け手の語彙に無い成果物名・検査ケース番号・判定根拠の説明を洗い出す。

    python check_sendback.py --mk models/pair-agent-m.mk --receiver 実装物 差し戻し.md [--vocab 仕様.md ...] [--strict]

--receiver は成果物名（target）または役割名。複数の target が該当するときは成果物名で指定する。
--vocab に受け手の deps の実ファイルを渡すと、本文の「」や `` で括った語が受け手の語彙に無いかも見る。
遮断を破る誘惑（判定の根拠を説明したくなる）を機械で止める。判定は人間が行う。読むだけ。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

VERS = re.compile(r"_v\([^)]*\)")
TARGET_RE = re.compile(r"^([^\s#:][^:]*?)\s*:\s*(.*)$")
META_RE = re.compile(r"^#\s{1,}(\S+)\s*:\s*(.*)$")
CASE_ID = re.compile(r"\b(?:TC|AT|T|C|K)[-_ ]?\d+\b|テストケース|検査ケース|ケース\s*(?:No\.?\s*)?\d+|検査項目\s*\d+|テスト\s*\d+\s*番")
GROUNDS = re.compile(r"検査で|テストで|検査の結果|検査に(?:落ち|失敗)|不合格(?:だった|でした|となった)|落ちた(?:ため|ので)|検査が(?:通ら|落ち)|テストが(?:通ら|落ち|失敗)")


def clean(name: str) -> str:
    return VERS.sub("", name).replace("?", "").strip()


def parse_mk(text: str) -> dict[str, dict]:
    targets: dict[str, dict] = {}
    cur = None
    for line in text.splitlines():
        if not line.strip():
            cur = None
            continue
        if line.startswith("#"):
            m = META_RE.match(line)
            if m and cur is not None:
                cur["meta"].setdefault(m.group(1), []).append(m.group(2).strip())
            continue
        m = TARGET_RE.match(line)
        if m:
            # `A / B : deps` のように複数名の target は先頭だけを名前とする
            name = clean(m.group(1).split("/")[0])
            deps = [clean(d) for d in re.split(r"[,、]", m.group(2)) if clean(d)]
            cur = {"name": name, "deps": deps, "meta": {}}
            targets[name] = cur
    return targets


def pick(targets: dict[str, dict], receiver: str) -> tuple[dict | None, str]:
    if receiver in targets:
        return targets[receiver], ""
    by_role = [t for t in targets.values() if receiver in t["meta"].get("role", [])]
    if len(by_role) == 1:
        return by_role[0], ""
    if len(by_role) > 1:
        return None, f"役割「{receiver}」は複数の成果物（{'・'.join(t['name'] for t in by_role)}）を作る。成果物名で指定する"
    return None, f"受け手「{receiver}」が .mk に無い"


def find_names(text: str, names: list[str]) -> dict[str, int]:
    """長い名前を先に取り、取った区間を伏せる（「受入検査仕様」の中の「仕様」を数えない）。"""
    masked = text
    found: dict[str, int] = {}
    for n in sorted(set(names), key=lambda x: (-len(x), x)):
        if len(n) < 2:
            continue
        c = masked.count(n)
        if c:
            found[n] = c
            masked = masked.replace(n, "\0" * len(n))
    return found


def check(mk_text: str, receiver: str, body: str, vocab: str | None = None) -> tuple[list[str], dict]:
    targets = parse_mk(mk_text)
    t, err = pick(targets, receiver)
    if t is None:
        return [f"[受け手が決まらない] {err}"], {}
    blocks = [clean(b) for v in t["meta"].get("blocks", []) for b in re.split(r"[,、]", v) if clean(b)]
    deps = t["deps"]
    out: list[str] = []
    info = {"receiver": t["name"], "deps": deps, "blocks": blocks}
    if not body.strip():
        out.append("[本文が空] 受け手はこれだけを見て着手できなければならない")
    all_names = [n for n in targets] + blocks
    found = find_names(body, all_names)
    for n, c in sorted(found.items()):
        if n in blocks:
            out.append(f"[遮断違反] 受け手は「{n}」を読んではならない（blocks）。本文に {c} 回現れる → 受け手の語で言い直す")
        elif n not in deps and n != t["name"]:
            out.append(f"[受け手の語彙に無い成果物名] 「{n}」は受け手の deps（{'・'.join(deps) or 'なし'}）に無い（{c} 回）")
    if any("受入検査" in b for b in blocks):
        for m in sorted({m.group(0) for m in CASE_ID.finditer(body)}):
            out.append(f"[検査ケースの参照] 「{m}」: 検査ケースの内容や番号は遮断を壊す。仕様の語で「何が起きたか」を書く")
    for m in sorted({m.group(0) for m in GROUNDS.finditer(body)}):
        out.append(f"[判定根拠の説明の疑い] 「{m}」: 判定の根拠を説明したくなったら遮断を破る誘惑。起きたことを仕様の語で")
    if vocab is not None:
        for q in sorted({x for x in re.findall(r"[「`]([^」`\n]{2,30})[」`]", body)}):
            if q not in vocab and q not in found:
                out.append(f"[受け手の語彙に無い語の疑い] 「{q}」は --vocab のどのファイルにも無い")
    return out, info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sendback", type=Path, help="差し戻し指示の本文")
    ap.add_argument("--mk", required=True, type=Path, help="成果物定義 .mk")
    ap.add_argument("--receiver", required=True, help="受け手の成果物名または役割名")
    ap.add_argument("--vocab", nargs="*", type=Path, default=None, help="受け手の deps の実ファイル")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    for p in [a.sendback, a.mk] + list(a.vocab or []):
        if not p.is_file():
            print(f"エラー: ファイルが無い: {p}", file=sys.stderr)
            return 2
    vocab = None
    if a.vocab is not None:
        vocab = "\n".join(p.read_text(encoding="utf-8") for p in a.vocab)
    found, info = check(a.mk.read_text(encoding="utf-8"), a.receiver, a.sendback.read_text(encoding="utf-8"), vocab)
    if info:
        print(f"受け手: {info['receiver']} ／ deps: {'・'.join(info['deps']) or 'なし'} ／ 遮断: {'・'.join(info['blocks']) or 'なし'}")
    for f in found:
        print(f)
    if not found:
        print("指摘なし（これだけを見て着手できるかは、書いた後に人間が確かめる）")
    return 1 if (a.strict and found) or (found and not info) else 0


if __name__ == "__main__":
    sys.exit(main())

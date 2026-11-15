"""規範の文書を節（見出し ## など）に切る。切った節をつなぐと元の文書に戻る（欠けない・足さない）。

節のマージ（配布先の新しい節はマスターへ、マスターの新しい節は配布先へ）と、節の書き換え（判断の反映）に使う。
切り方は survey.split_sections と同じ（最も浅い「2 番目の深さ」で切る。コードフェンスの中の見出しは無視）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .survey import norm_text

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEAD = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
PREAMBLE = "(冒頭)"


@dataclass
class Chunk:
    anchor: str   # 見出しの文字（冒頭は "(冒頭)"）
    raw: str      # 改行を含む元の文字列
    prev: str | None = None   # 元の文書で直前にあった節の鍵（隣り合ったままなら区切りを足さない）

    @property
    def key(self) -> str:
        return anchor_key(self.anchor)

    @property
    def norm(self) -> str:
        return norm_text(self.raw)


def anchor_key(anchor: str) -> str:
    return re.sub(r"\s+", "", anchor).lower()


def parse(text: str) -> list[Chunk]:
    lines = text.splitlines(keepends=True)
    start = 0
    if lines and lines[0].startswith("---"):          # フロントマターは冒頭に含める
        for i in range(1, len(lines)):
            if lines[i].rstrip("\r\n").strip() == "---":
                start = i + 1
                break
    heads: list[tuple[int, int, str]] = []
    in_code = False
    for i in range(start, len(lines)):
        ln = lines[i].rstrip("\r\n")
        if _FENCE.match(ln):
            in_code = not in_code
            continue
        if not in_code:
            m = _HEAD.match(ln)
            if m:
                heads.append((i, len(m.group(1)), m.group(2).strip("* ").strip()))
    levels = sorted({lv for _, lv, _ in heads})
    if not levels:
        return [Chunk(PREAMBLE, text)]
    cut = levels[1] if len(levels) > 1 and levels[0] == 1 else levels[0]
    starts = [(i, t) for i, lv, t in heads if lv == cut]
    out: list[Chunk] = []
    first = starts[0][0] if starts else len(lines)
    if first > 0:
        out.append(Chunk(PREAMBLE, "".join(lines[:first])))
    for k, (i, t) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        out.append(Chunk(t, "".join(lines[i:end]), out[-1].key if out else ""))
    return out


_BLANK_END = re.compile(r"\n[ \t]*\r?\n$")


def newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def join(chunks: list[Chunk]) -> str:
    nl = "\r\n" if any("\r\n" in c.raw for c in chunks) else "\n"
    out = ""
    last: str | None = None
    for c in chunks:
        if out and not (c.prev is not None and c.prev == last):
            if not out.endswith("\n"):
                out += nl
            if c.anchor != PREAMBLE and not _BLANK_END.search(out):
                out += nl          # 新しく隣り合った節の前は空行 1 つ
        out += c.raw
        last = c.key
    return out


def with_newline(raw: str, nl: str, tail: int = 1) -> str:
    """書き換えた節の改行を文書の流儀にそろえ、末尾を改行 tail 個で終える（元の節の後ろの空行を保つ）。"""
    body = raw.replace("\r\n", "\n").rstrip("\n") + "\n" * max(1, tail)
    return body.replace("\n", nl)


def _tail(raw: str) -> int:
    return len(raw) - len(raw.rstrip("\r\n")) - raw[len(raw.rstrip("\r\n")):].count("\r")


def duplicated_anchors(chunks: list[Chunk]) -> list[str]:
    seen: set[str] = set()
    dup: list[str] = []
    for c in chunks:
        if c.key in seen and c.anchor not in dup:
            dup.append(c.anchor)
        seen.add(c.key)
    return dup


def by_key(chunks: list[Chunk]) -> dict[str, Chunk]:
    return {c.key: c for c in chunks}


def _body_hash(c: Chunk) -> str:
    from .survey import split_frontmatter, text_hash
    return text_hash(split_frontmatter(c.raw)[1] if c.anchor == PREAMBLE else c.raw)


def locate(text: str, anchor: str, text_hash: str) -> int:
    """サーベイの単位（見出し・中身のハッシュ）に当たる節の位置。中身が変わっていれば ValueError。"""
    chunks = parse(text)
    hit = [i for i, c in enumerate(chunks) if _body_hash(c) == text_hash]
    if len(hit) >= 1:
        same = [i for i in hit if chunks[i].key == anchor_key(anchor)]
        return (same or hit)[0]
    if any(c.key == anchor_key(anchor) for c in chunks):
        raise ValueError(f"節がその後に変わっています: {anchor}")
    raise ValueError(f"節が見つからない: {anchor}")


def replace_at(text: str, i: int, new_raw: str) -> str:
    """i 番目の節を差し替える（空なら消す）。冒頭の節のフロントマターは残す。"""
    chunks = parse(text)
    c = chunks[i]
    if not new_raw.strip():
        del chunks[i]
        return join(chunks)
    raw = with_newline(new_raw, newline(text), _tail(c.raw))
    if c.anchor == PREAMBLE and c.raw.startswith("---"):
        from .survey import split_frontmatter
        body = split_frontmatter(c.raw)[1]
        raw = c.raw[: len(c.raw) - len(body)] + raw
    chunks[i] = Chunk(c.anchor, raw, c.prev)
    return join(chunks)


def replace(text: str, anchor: str, expect_norm: str | None, new_raw: str) -> str:
    """節を 1 つ差し替える（new_raw が空なら節を消す）。expect_norm が今の節と合わなければ ValueError。"""
    chunks = parse(text)
    key = anchor_key(anchor)
    hit = [i for i, c in enumerate(chunks) if c.key == key]
    if len(hit) != 1:
        raise ValueError(f"節が見つからない（または重複）: {anchor}")
    i = hit[0]
    if expect_norm is not None and chunks[i].norm != expect_norm:
        raise ValueError(f"節がその後に変わっています: {anchor}")
    if new_raw.strip():
        chunks[i] = Chunk(chunks[i].anchor, with_newline(new_raw, newline(text), _tail(chunks[i].raw)), chunks[i].prev)
    else:
        del chunks[i]
    return join(chunks)

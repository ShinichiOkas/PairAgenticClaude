"""判断待ちの判断を反映する（UC1）。書き込みは changes を通す（退避・台帳・自動でやったことへの記録・取り消し）。

J1（同時に効く規則の矛盾）は 2 段: 文案（draft・LLM）→ 師匠が直して反映（decide）。
全体の規則（~/.claude の CLAUDE.md・rules）を書き換えるときは、マスターの同じ節も書き換える（正はマスター）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import changes, inbox, llm, mapping, sections, situations, sweep, targets
from .changes import Event, LedgerSet, Write, ckey, read, sha
from .paths import master_root


class NotYet(NotImplementedError):
    pass


def decide(iid: str, option: str, edits: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    it = inbox.get(iid)
    if it is None:
        raise KeyError(f"判断待ちが無い: {iid}")
    if it["status"] not in inbox.ACTIVE:
        raise ValueError("この項目はもう判断済みです")
    if option == "later":
        inbox.update(iid, status="later")
        return {"status": "later"}
    handler = HANDLERS.get(it["kind"])
    if handler is None:
        raise NotYet(f"inbox.decide.{it['kind']}")
    rec, status = handler(it, option, edits or [])
    inbox.update(iid, status=status, decision={"option": option, "event": rec["id"] if rec else None})
    return {"status": status, "event": rec}


def after_undo(refs: dict[str, Any]) -> None:
    """判断を取り消したら、その判断待ちを開き直す。"""
    iid = refs.get("item_id")
    if iid and inbox.get(iid):
        inbox.update(iid, status="open", decision=None)


# ---------------------------------------------------------------- J2: マージできない変更
def _j2(it: dict[str, Any], option: str, _edits: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    r = it["refs"]
    if r.get("git"):
        return _j2_git(it, option)
    t = targets.get_target(r["target_id"])
    if t is None:
        raise KeyError("配布先が管理下にありません")
    master = master_root()
    src, dest = master / r["src_rel"], Path(t["path"]) / r["rel"]
    mb, tb = read(src), read(dest)
    if sha(mb) != r["mh"] or sha(tb) != r["th"]:
        raise ValueError("判断待ちに上げた後で、ファイルが変わりました。点検し直してください")
    where = f"{t['name']}/{r['rel']}"
    refs = {"item_id": it["id"], "target_id": t["id"], "rel": r["rel"], "src_rel": r["src_rel"]}
    # 丸ごと置き換えで消える段落を、判断待ちに見せたものと照らす。見せていない消え方（この直しの前に上げた項目など）は止める
    if option in ("master", "target"):
        lost = sweep._lost(tb, mb) if option == "master" else sweep._lost(mb, tb)
        shown = r.get("t_lost" if option == "master" else "m_lost")
        if lost and shown != lost:
            side = "配布先" if option == "master" else "マスター"
            raise ValueError(f"この判断で{side}にだけある {len(lost)} 箇所が消えます（{sweep._few(lost)}）。"
                             "判断待ちにはそれが出ていないので、点検し直してから選んでください")
    if option == "master":
        ev = Event("decide", "判断: マスターの版にした", f"マスターの {r['src_rel']} → {where}", "師匠の判断（J2）",
                   [Write(dest, mb, r["th"])], [LedgerSet(t["id"], r["rel"], ckey(mb) or "", mb)], refs=refs)  # type: ignore[arg-type]
    elif option == "target":
        ws = [Write(src, tb, r["mh"])] + sweep._mirror_writes(r["src_rel"], mb, tb, sweep.Overlay(), master)  # type: ignore[arg-type]
        ev = Event("decide", "判断: 配布先の版をマスターへ", f"{where} → マスターの {r['src_rel']}", "師匠の判断（J2）",
                   ws, [LedgerSet(t["id"], r["rel"], ckey(tb) or "", tb)], refs=refs)  # type: ignore[arg-type]
    else:
        raise ValueError(f"選択肢が不明: {option}")
    return changes.commit(ev), "decided"


def _j2_git(it: dict[str, Any], option: str) -> tuple[dict[str, Any], str]:
    """git の衝突: 選んだ側を優先してマージし直し、push する。git のマージは自動では取り消さない（git revert で戻す）。"""
    from . import gitmerge
    r = it["refs"]
    if r.get("outside") or option not in ("ours", "theirs"):
        raise ValueError("規則の外のファイルがぶつかっているので、手で git pull して直してください" if r.get("outside") else f"選択肢が不明: {option}")
    root = Path(r["root"])
    m = gitmerge.merge_upstream(root, prefer=option)
    if not m["ok"]:
        raise ValueError(f"マージできませんでした: {m.get('error')}")
    pr = gitmerge.push_if_ahead(root)
    label = "この PC の版を優先" if option == "ours" else "GitHub の版を優先"
    return changes.record("decide", f"判断: git の衝突を{label}してマージ", it["title"],
                          "師匠の判断（J2）" + ("。push した" if pr.get("pushed") else f"。push はまだ（{pr.get('error', '')}）"),
                          refs={"item_id": it["id"], "no_undo": True}), "decided"


# ---------------------------------------------------------------- J1: 同時に効く規則の矛盾
class Draft(BaseModel):
    a_text: str = Field(default="", description="A の節の改訂版の全文（見出し行を含む Markdown）。A を変えないときは空")
    b_text: str = Field(default="", description="B の節の改訂版の全文（見出し行を含む Markdown）。B を変えない・消すときは空")
    note: str = Field(default="", description="何をどう変えたかを日本語で 2 文以内")


class DiffSummary(BaseModel):
    only_a: list[str] = Field(default_factory=list, description="A にだけある要素（短い箇条書き・各 60 字以内）")
    only_b: list[str] = Field(default_factory=list, description="B にだけある要素（短い箇条書き・各 60 字以内）")
    shared: list[str] = Field(default_factory=list, description="A と B の両方にある要素（短い箇条書き・各 60 字以内）")
    clash: list[str] = Field(default_factory=list, description="A と B でぶつかる点（短い箇条書き・各 80 字以内）")
    note: str = Field(default="", description="要約の総括を日本語で 2 文以内")


SUMMARY_SYSTEM = """あなたは、AI コーディングエージェントに与える規範文書の読み手です。2 つの節 A と B の違いを、意味で要約します。
- 文字の並びの DIFF ではなく、要素・主張・適用場面の違いを示します
- 師匠の原文の引用（> で始まる行・「」の中）に触れるときは、引用を変えずに示します
- 推測で断定せず、根拠が無ければ空のままにします"""


def summarize_diff(iid: str) -> dict[str, Any]:
    it = inbox.get(iid)
    if it is None:
        raise KeyError(f"判断待ちが無い: {iid}")
    if it["kind"] != "J1":
        raise ValueError("違いの要約は J1（同時に効く規則の矛盾）だけです")
    a, b = it["a"], it["b"]
    user = (f"## A（{a['where']}）\n{a['text']}\n\n## B（{b['where']}）\n{b['text']}\n\n"
            f"AI の見立て: {it.get('ai', '')}\n\nA と B の違いを、要素で要約してください。")
    s, model = llm.chat_structured(SUMMARY_SYSTEM, user, DiffSummary, role="judge")
    return {"summary": s.model_dump(), "model": model, "hypothesis": True}


DRAFT_SYSTEM = """あなたは、AI コーディングエージェントに与える規範文書の編集者です。師匠（人間）が決めた方針で、2 つの節 A・B の改訂案を作ります。
- 師匠の原文の引用（> で始まる行や「」の中の原文）は一字も変えない
- 変える必要のある箇所だけを変え、それ以外は元の文のまま残す。見出し行も残す
- 出力する節は全文（見出し行を含む Markdown）

状況定義:
{situations}"""

INSTRUCTION = {
    "split": "A と B の両方が正しくなるように、それぞれが効く状況を書き分けてください。各節の見出しの直後に「適用する状況: …」の 1 行を足し、"
             "ぶつかって見える文にも状況を添えてください。状況は状況定義の ID と名前を使ってください。a_text と b_text の両方を出力してください。",
    "a": "A を正とします。B の中で A とぶつかる記述を、A に沿うように直すか削ってください。A は変えません（a_text は空）。b_text を出力してください。",
    "b": "B を正とします。A の中で B とぶつかる記述を、B に沿うように直すか削ってください。B は変えません（b_text は空）。a_text を出力してください。",
    "a_plus_b": "A をベース（骨格・構成・原文の引用はそのまま）として、B にあって A に無い有益な要素だけを A に取り込んでください。"
                "A の原文（引用・見出し・既存の文）は一字も変えず、取り込みは A の末尾への追記か、該当する段落への補足として行います。"
                "A と B がぶつかる記述は取り込まず、B 側のぶつかる記述は削ります。"
                "a_text に取り込み後の A を、b_text にぶつかりを削った後の B を出力してください。"
                "取り込める要素が無いなら a_text は A の原文のまま、b_text は空にしてください。",
    "merge": "A と B を 1 つの節に統合してください。見出しは A のものを使い、両方の内容を矛盾なく残します。a_text に統合した節を出力し、b_text は空にしてください（B の節は消します）。",
}
SIDES = {"split": ("replace", "replace"), "a": ("keep", "replace"), "b": ("replace", "keep"),
         "a_plus_b": ("replace", "replace"), "merge": ("replace", "delete")}


def draft(iid: str, option: str) -> dict[str, Any]:
    it = inbox.get(iid)
    if it is None:
        raise KeyError(f"判断待ちが無い: {iid}")
    if it["kind"] != "J1" or option not in INSTRUCTION:
        raise ValueError("文案を作れるのは J1 の「状況で分ける・A を採る・B を採る・A ベースに B の要素を取り込む・統合」だけです")
    a, b = it["a"], it["b"]
    user = (f"## A（{a['where']}）\n{a['text']}\n\n## B（{b['where']}）\n{b['text']}\n\n"
            f"AI の見立て: {it.get('ai', '')}\n\n方針: {INSTRUCTION[option]}")
    note, model = "", ""
    try:
        d, model = llm.chat_structured(DRAFT_SYSTEM.format(situations=situations.as_prompt(situations.load())), user, Draft, role="rewrite")
        texts = {"a": d.a_text, "b": d.b_text}
        note = d.note
    except Exception as exc:     # LLM が使えなくても、元の文を自分で直せるように返す
        texts = {"a": a["text"], "b": b["text"]}
        note = f"AI の文案は保留（{type(exc).__name__}）。元の文を直してください"
    edits = []
    for side, action in zip(("a", "b"), SIDES[option]):
        x = it[side]
        if action == "keep":
            continue
        text = "" if action == "delete" else (texts[side].strip() or x["text"])
        edits.append({"side": side, "where": x["where"], "action": action, "before": x["text"], "text": text})
    inbox.update(iid, draft={"option": option, "edits": edits, "note": note, "model": model})
    return {"option": option, "edits": edits, "note": note, "model": model}


def _master_file(ref: dict[str, Any]) -> Path | None:
    """全体の規則（~/.claude の CLAUDE.md・rules）なら、マスターの対応するファイル。"""
    t = targets.get_target(ref["target_id"])
    if t is None or t["kind"] not in ("claude_home", "gemini_home"):
        return None
    for e in mapping.entries_for(t["kind"], "global"):
        if e.id not in sweep.RULE_ENTRIES:
            continue
        for src, rel in mapping.expand(e):
            if rel == ref["rel"]:
                return src
    return None


def _j1(it: dict[str, Any], option: str, edits: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    refs = {"item_id": it["id"], "pair": it["refs"]["pair"]}
    if option == "ok":
        rec = changes.record("decide", "判断: このままでよい", it["title"], "師匠の判断（J1）。同じ組は二度と上げない", refs=refs)
        return rec, "dismissed"
    if option not in SIDES:
        raise ValueError(f"選択肢が不明: {option}")
    if not edits:
        raise ValueError("先に文案を作ってください")
    master = master_root()
    buf: dict[str, str] = {}            # パス → 書き換え中の文
    orig: dict[str, bytes | None] = {}
    homes: dict[str, tuple[str, str, str]] = {}   # 配布先のパス → (配布先 ID, 相対パス, マスターのパス)

    def load(p: Path) -> str:
        k = str(p)
        if k not in buf:
            data = read(p)
            if data is None:
                raise ValueError(f"ファイルが無い: {p}")
            orig[k] = data
            buf[k] = data.decode("utf-8")
        return buf[k]

    for ed in edits:
        if ed.get("action") not in ("replace", "delete"):
            continue
        ref = it["refs"][ed["side"]]
        text = "" if ed["action"] == "delete" else str(ed.get("text", ""))
        targets_paths = [Path(ref["path"])]
        mf = _master_file(ref)
        if mf is not None:
            targets_paths.append(mf)
            homes[str(Path(ref["path"]))] = (ref["target_id"], ref["rel"], str(mf))
        for p in targets_paths:
            cur = load(p)
            try:
                i = sections.locate(cur, ref["anchor"], ref["hash"])
            except ValueError as exc:
                if p == mf:
                    raise ValueError(f"マスターの節が配布先と揃っていません。先に点検してください（{exc}）") from exc
                raise
            buf[str(p)] = sections.replace_at(cur, i, text)

    writes: list[Write] = []
    for k, text in buf.items():
        data = text.encode("utf-8")
        if data != orig[k]:
            writes.append(Write(Path(k), data, sha(orig[k])))
    for k, (tid, rel, mk) in homes.items():
        mrel = Path(mk).relative_to(master).as_posix()
        if mk in buf:
            writes += sweep._mirror_writes(mrel, orig[mk], buf[mk].encode("utf-8"), sweep.Overlay(), master)
    ledgers = []
    for k, (tid, rel, mk) in homes.items():
        if mk in buf and ckey(buf[k].encode("utf-8")) == ckey(buf[mk].encode("utf-8")):
            data = buf[k].encode("utf-8")
            ledgers.append(LedgerSet(tid, rel, ckey(data) or "", data))
    label = {"split": "状況で分けた", "a": "A を採った", "b": "B を採った",
             "a_plus_b": "A をベースに B の要素を取り込んだ", "merge": "統合した"}[option]
    ev = Event("decide", f"判断: {label}", it["title"], "師匠の判断（J1）", writes, ledgers, refs=refs)
    return changes.commit(ev), "decided"


# ---------------------------------------------------------------- J3: 管理に入れるか
def _j3(it: dict[str, Any], option: str, _edits: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    from . import managed
    r = it["refs"]
    refs = {"item_id": it["id"]}
    if option == "include":
        c = {"kind": "project", "path": r["path"], "name": r["name"]}
        return managed.include(c, "師匠の判断（J3）", kind="decide", what="判断: 管理に入れた", refs=refs), "decided"
    if option == "exclude":
        return managed.exclude(r["path"], "師匠の判断（J3）。二度と聞かない", kind="decide", what="判断: 外した", refs=refs), "dismissed"
    raise ValueError(f"選択肢が不明: {option}")


# ---------------------------------------------------------------- J4: ほかのユーザーの規則
def _j4(it: dict[str, Any], option: str, _edits: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    from . import gitsync
    if option == "take":
        return changes.record("decide", "判断: ほかのユーザーの変更を取り入れた", it["title"], "師匠の判断（J4）。次の点検で配る",
                              refs={"item_id": it["id"]}), "decided"
    if option == "reject":
        return gitsync.reject(it), "decided"
    raise ValueError(f"選択肢が不明: {option}")


HANDLERS = {"J1": _j1, "J2": _j2, "J3": _j3, "J4": _j4}

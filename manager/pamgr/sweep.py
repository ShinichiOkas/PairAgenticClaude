"""点検（docs/usecases.md §2〜§4）: 照合して、自動で直せるものは直し（事後報告・取り消せる）、人の判断が要るものを判断待ちに上げる。

計画（plan）と実行（apply）を分ける。予行（dry_run）は計画だけで、何も書かない。

ホーム（~/.claude・~/.gemini/config）のファイルごとに:
  一致                      台帳に記録するだけ（以後の向きの判定の基準）
  未配布・マスターが新しい   配る
  配布先だけが変わった       マスターへ取り込む（固有名が混じっていれば見送る）
  双方で変わった・向き不明   規範の文書は節ごとにマージ。マージできなければ判断待ち（J2）
                            それ以外は、配布先がマスターの過去の版なら配る／マスターが変わっていなければ取り込む／他は J2
プロジェクトへの書き込みはまだしない（各リポジトリに未コミットの変更を作るため。後の段）。
"""

from __future__ import annotations

import difflib
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import changes, conflicts, generalize, gitsync, history, inbox, managed, mapping, sections, settings, store, targets
from .changes import Event, LedgerSet, Write, ckey, sha
from .paths import master_root

FILE = "sweep.json"
HOMES = ("claude_home", "gemini_home")
RULE_ENTRIES = {"claude-md", "gemini-md", "rules"}
MIRRORS = {"home-claude/CLAUDE.md": "home-claude/GEMINI.md"}   # マスターでは同じ中身を保つ（CLAUDE.md と GEMINI.md）
RENAME_RATIO = 0.6
_RUN = threading.Lock()
_NAMES: list[str] | None = None   # 固有名の候補（点検 1 回につき 1 回だけ集める）


# ---------------------------------------------------------------- 計画のための重ね書き（予行でも連鎖を正しく見る）
class Overlay:
    def __init__(self) -> None:
        self.files: dict[str, bytes | None] = {}

    def read(self, p: Path) -> bytes | None:
        k = str(p)
        return self.files[k] if k in self.files else changes.read(p)

    def put(self, p: Path, data: bytes | None) -> None:
        self.files[str(p)] = data


@dataclass
class Planned:
    event: Event
    target: str
    rel: str


@dataclass
class Plan:
    actions: list[Planned] = field(default_factory=list)
    baselines: list[tuple[str, str, str, bytes]] = field(default_factory=list)   # (tid, rel, hash, data)
    inbox: list[dict[str, Any]] = field(default_factory=list)
    held: list[dict[str, Any]] = field(default_factory=list)                      # 見送ったもの（固有名・取り消し済み）
    notes: list[str] = field(default_factory=list)
    steps: dict[str, str] = field(default_factory=dict)


def _decode(b: bytes | None) -> str | None:
    if b is None:
        return None
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ---------------------------------------------------------------- 節のマージ
@dataclass
class MergeResult:
    text: str | None
    from_target: list[str] = field(default_factory=list)
    from_master: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def merge_sections(mtext: str, ttext: str, base: str | None, src_rel: str) -> MergeResult:
    """マスターと配布先を節ごとにマージする。基準は「最後に配った版」、無ければマスターの git 履歴で推定する。"""
    M, T = sections.parse(mtext), sections.parse(ttext)
    res = MergeResult(None)
    dup = sections.duplicated_anchors(M) + sections.duplicated_anchors(T)
    if dup:
        res.conflicts = [f"見出しの重複: {a}" for a in dup]
        return res
    Mk, Tk = sections.by_key(M), sections.by_key(T)
    Bk = sections.by_key(sections.parse(base)) if base is not None else None
    hist = None if Bk is not None else (history.section_history(src_rel) if history.versions(src_rel) else None)
    take: dict[str, sections.Chunk | None] = {}

    for key in list(Mk) + [k for k in Tk if k not in Mk]:
        m, t = Mk.get(key), Tk.get(key)
        if m and t:
            if m.norm == t.norm:
                take[key] = m
            elif Bk is not None:
                b = Bk.get(key)
                if b and t.norm == b.norm:
                    take[key] = m; res.from_master.append(m.anchor)
                elif b and m.norm == b.norm:
                    take[key] = t; res.from_target.append(t.anchor)
                else:
                    res.conflicts.append(m.anchor)
            elif hist is None:                        # 基準も履歴も無い: どちらが新しいか分からない
                res.conflicts.append(m.anchor)
            else:
                h = hist.get(key, set())
                if t.norm in h:                       # 配布先はマスターの過去の版（古い）
                    take[key] = m; res.from_master.append(m.anchor)
                elif h <= {m.norm}:                   # マスターはこの節を一度も変えていない → 配布先が書き換えた
                    take[key] = t; res.from_target.append(t.anchor)
                else:
                    res.conflicts.append(m.anchor)
        elif m:                                       # マスターにだけある
            b = Bk.get(key) if Bk is not None else None
            if Bk is not None and b is not None:
                if b.norm == m.norm:
                    take[key] = None; res.dropped.append(m.anchor)      # 配布先で消した
                else:
                    res.conflicts.append(m.anchor)
            else:
                take[key] = m
                if Bk is not None:
                    res.from_master.append(m.anchor)
                elif hist is not None and key not in hist:
                    res.from_master.append(m.anchor)
        elif t:                                       # 配布先にだけある
            if Bk is not None:
                b = Bk.get(key)
                if b is None:
                    take[key] = t; res.from_target.append(t.anchor)
                elif b.norm == t.norm:
                    take[key] = None; res.dropped.append(t.anchor)     # マスターで消した
                else:
                    res.conflicts.append(t.anchor)
            else:
                h = hist.get(key) if hist is not None else None
                if h is None:
                    take[key] = t; res.from_target.append(t.anchor)
                else:   # マスターの履歴にある節: マスターで消したのか、取り込みを取り消したのか決められない → 推測で消さない
                    res.conflicts.append(f"{t.anchor}（マスターの履歴にあり、いまのマスターに無い）")

    # 見出しの付け替え（マスターにだけある節と配布先にだけある節の本文がよく似ている）は推測しない
    m_only = [Mk[k] for k in Mk if k not in Tk]
    t_only = [Tk[k] for k in Tk if k not in Mk and take.get(k) is not None]
    for t in t_only:
        for m in m_only:
            if difflib.SequenceMatcher(None, _body(t), _body(m)).ratio() >= RENAME_RATIO:
                res.conflicts.append(f"見出しの付け替え？ {m.anchor} → {t.anchor}")
    if res.conflicts:
        return res

    out: list[sections.Chunk] = [take[c.key] for c in M if take.get(c.key) is not None]  # type: ignore[misc]
    placed = {c.key for c in out}
    for i, c in enumerate(T):
        if c.key in placed or take.get(c.key) is None:
            continue
        pos = 0
        for j in range(i - 1, -1, -1):
            prev = T[j].key
            hit = next((k for k, x in enumerate(out) if x.key == prev), None)
            if hit is not None:
                pos = hit + 1
                break
        out.insert(pos, take[c.key])  # type: ignore[arg-type]
        placed.add(c.key)
    res.text = sections.join(out)
    return res


def _body(c: sections.Chunk) -> str:
    return c.norm.split(" ", 1)[1] if " " in c.norm else c.norm


# ---------------------------------------------------------------- 1 ファイルの判定
def _novel_leaks(new_text: str, master_text: str) -> list[str]:
    """取り込もうとする中身に、マスターに無い固有の語があるか（プロジェクト名・絶対パス・ユーザー名）。"""
    names = _NAMES if _NAMES is not None else generalize.project_names()
    have = {f["term"].lower() for f in generalize.detect(master_text, names)}
    return sorted({f["term"] for f in generalize.detect(new_text, names) if f["term"].lower() not in have})


def _mirror_writes(src_rel: str, before: bytes | None, after: bytes, ov: Overlay, master: Path) -> list[Write]:
    mrel = MIRRORS.get(src_rel)
    if not mrel:
        return []
    mp = master / mrel
    cur = ov.read(mp)
    if cur is not None and before is not None and _decode(cur) is not None and \
            sections.norm_text(_decode(cur) or "") == sections.norm_text(_decode(before) or ""):
        return [Write(mp, after, sha(cur))]
    return []


def _file(t: dict[str, Any], e: mapping.Entry, src: Path, rel: str, ov: Overlay, led: dict[str, Any],
          sup: dict[str, Any], plan: Plan, master: Path) -> Planned | None:
    tid, tname = t["id"], t["name"]
    dest = Path(t["path"]) / rel
    mb, tb = ov.read(src), ov.read(dest)
    mh, th = sha(mb), sha(tb)            # バイト（書く直前の確かめ）
    mk, tk = ckey(mb), ckey(tb)          # 中身（改行・空白だけの違いは同じとみなす。PC ごとの改行の設定で揺れない）
    last = ((led.get(tid) or {}).get(rel) or {}).get("hash")
    src_rel = src.relative_to(master).as_posix()
    where = f"{tname}/{rel}"

    if mb is None:
        return None
    if mk == tk:
        if last != tk:
            plan.baselines.append((tid, rel, tk, tb))  # type: ignore[arg-type]
        return None

    def distribute(why: str, what: str = "配った") -> Planned:
        ev = Event("distribute", what, f"マスターの {src_rel} → {where}", why,
                   [Write(dest, mb, th)], [LedgerSet(tid, rel, mk, mb)], f"{tid}|{rel}|{mk}|{tk}",  # type: ignore[arg-type]
                   {"target_id": tid, "rel": rel, "src_rel": src_rel})
        return Planned(ev, tid, rel)

    def adopt(why: str) -> Planned | None:
        leaks = _novel_leaks(_decode(tb) or "", _decode(mb) or "")
        if leaks:
            plan.held.append({"what": "取り込みを見送った", "detail": where, "why": "固有の語が混じっている: " + "、".join(leaks[:8])})
            return None
        ws = [Write(src, tb, mh)] + _mirror_writes(src_rel, mb, tb, ov, master)  # type: ignore[arg-type]
        ev = Event("adopt", "マスターへ取り込んだ", f"{where} → マスターの {src_rel}", why,
                   ws, [LedgerSet(tid, rel, tk, tb)], f"{tid}|{rel}|{mk}|{tk}",  # type: ignore[arg-type]
                   {"target_id": tid, "rel": rel, "src_rel": src_rel})
        return Planned(ev, tid, rel)

    def j2(why: str, conflicts: list[str]) -> None:
        plan.inbox.append({
            "kind": "J2", "key": f"J2|{tid}|{rel}|{mk}|{tk}", "title": f"{where} — マスターと配布先の両方で変わっている",
            "what": why + (" ぶつかる箇所: " + "、".join(conflicts[:10]) if conflicts else ""),
            "applies": where, "refs": {"target_id": tid, "rel": rel, "src_rel": src_rel, "mh": mh, "th": th, "mk": mk, "tk": tk},
            "options": [{"id": "master", "label": "マスターの版にする（配布先を上書き）", "primary": True},
                        {"id": "target", "label": "配布先の版をマスターへ"}, {"id": "later", "label": "あとで"}]})

    if th is None:
        return distribute("配布先に無かった", "配った（新規）")
    state = "master-ahead" if last == tk else "target-ahead" if last == mk else "diverged" if last else "differs"
    if state == "master-ahead":
        return distribute("マスターが新しく、配布先は最後に配った版のままだった")
    if state == "target-ahead":
        return adopt("配布先だけで書き換えられた（マスターは最後に配った版のまま）")

    # 双方で変わった（台帳あり）・向き不明（台帳なし）
    mtext, ttext = _decode(mb), _decode(tb)
    base = changes.base_text(tid, rel, last) if last else None
    if ttext is not None and history.file_seen(src_rel, ttext):     # ファイル全体がマスターの過去の版そのもの → 確実に古い
        return distribute("配布先はマスターの過去の版だった")
    if e.id in RULE_ENTRIES and mtext is not None and ttext is not None:
        r = merge_sections(mtext, ttext, base, src_rel)
        if r.text is None:
            j2("同じ節が両方で書き換えられていて、自動ではマージできません。", r.conflicts)
            return None
        merged = r.text.encode("utf-8")
        if ckey(merged) == tk:      # マスターが古いだけ（配布先の新しい節を取り込めば揃う）
            return adopt("配布先の新しい節をマスターへ（節ごとに照合）: " + "、".join(r.from_target[:6]))
        if ckey(merged) == mk:      # 配布先が古いだけ
            return distribute("配布先はマスターの過去の版だった（節ごとに照合）" + (f"。古い節: {'、'.join(r.from_master[:6])}" if r.from_master else ""))
        novel = "\n".join(c.raw for c in sections.parse(r.text) if c.anchor in r.from_target)
        leaks = _novel_leaks(novel, mtext)
        if leaks:
            plan.held.append({"what": "節のマージを見送った", "detail": where, "why": "配布先の新しい節に固有の語: " + "、".join(leaks[:8])})
            return None
        ws = [Write(src, merged, mh), Write(dest, merged, th)] + _mirror_writes(src_rel, mb, merged, ov, master)
        parts = []
        if r.from_target:
            parts.append("配布先の新しい節をマスターへ: " + "、".join(r.from_target[:6]))
        if r.from_master:
            parts.append("マスターの新しい節を配布先へ: " + "、".join(r.from_master[:6]))
        if r.dropped:
            parts.append("消された節: " + "、".join(r.dropped[:6]))
        ev = Event("merge", "節ごとにマージした", f"{where} ⇄ マスターの {src_rel}", "。".join(parts) or "節ごとに照合した",
                   ws, [LedgerSet(tid, rel, ckey(merged) or "", merged)], f"{tid}|{rel}|{mk}|{tk}",
                   {"target_id": tid, "rel": rel, "src_rel": src_rel})
        return Planned(ev, tid, rel)
    if ttext is not None and history.file_seen(src_rel, ttext):
        return distribute("配布先はマスターの過去の版だった")
    if base is not None:
        if ckey(base.encode("utf-8")) == mk:
            return adopt("配布先だけで書き換えられた")
        j2("マスターと配布先の両方で書き換えられています。", [])
        return None
    hv = history.versions(src_rel)
    vers = {sections.norm_text(v) for v in hv} | {sections.norm_text(mtext or "")}
    if hv and len(vers) == 1:
        return adopt("配布先だけで書き換えられた（マスターはこのファイルを一度も変えていない）")
    j2("どちらが新しいか決められません（最後に配った記録が無く、マスターも変わっている）。", [])
    return None


def _apply_overlay(p: Planned, ov: Overlay, led: dict[str, Any]) -> None:
    for w in p.event.writes:
        ov.put(w.path, w.data)
    for l in p.event.ledgers:
        led.setdefault(l.tid, {})[l.rel] = {"hash": l.hash}


def plan_homes(plan: Plan, tlist: list[dict[str, Any]], held: set[str] | None = None) -> None:
    master = master_root()
    ov, led, sup = Overlay(), changes.ledger(), changes.suppressed()
    held = held or set()
    held_noted: set[str] = set()
    homes = [t for t in tlist if t["kind"] in HOMES]
    if not homes:
        plan.notes.append("ホーム（~/.claude・~/.gemini/config）が管理下にありません")
    user_ok = (master / "external" / "pair-agent-skills" / ".git").exists()
    if not user_ok:
        plan.notes.append("マスターの external/pair-agent-skills が空のため、ユーザー固有（ペア固有スキル）は照合していません（git submodule update --init が要る）")
    done: set[tuple[str, str]] = set()
    for _ in range(3):                     # マスターへの取り込み・マージの後、ほかのホームへ配る（連鎖）
        progressed = False
        for t in homes:
            root = Path(t["path"])
            for e in mapping.entries_for(t["kind"]):
                if e.scope == "user" and not user_ok:
                    continue
                if e.requires_dest_dir and not (root / e.dest).is_dir():
                    continue
                for src, rel in mapping.expand(e, master):
                    if (t["id"], rel) in done:
                        continue
                    src_rel = src.relative_to(master).as_posix()
                    if src_rel in held:
                        if src_rel not in held_noted:
                            plan.held.append({"what": "配るのを止めている", "detail": src_rel, "why": "ほかのユーザーの変更（J4）の判断待ち"})
                            held_noted.add(src_rel)
                        continue
                    p = _file(t, e, src, rel, ov, led, sup, plan, master)
                    if p is None:
                        continue
                    done.add((t["id"], rel))
                    if p.event.suppress_key in sup:
                        plan.held.append({"what": "見送った（取り消し済み）", "detail": p.event.detail, "why": "師匠が以前に取り消した動作"})
                        continue
                    _apply_overlay(p, ov, led)
                    plan.actions.append(p)
                    progressed = True
        if not progressed:
            break
    # 同じ J2 が連鎖の中で 2 回出ないように
    seen: set[str] = set()
    plan.inbox = [i for i in plan.inbox if not (i["key"] in seen or seen.add(i["key"]))]  # type: ignore[func-returns-value]


# ---------------------------------------------------------------- 点検の全体
def plan_all(dry_run: bool, tlist: list[dict[str, Any]] | None = None) -> Plan:
    global _NAMES
    plan = Plan()
    _NAMES = generalize.project_names()
    try:
        plan_homes(plan, targets.list_targets() if tlist is None else tlist, gitsync.held_files())
    finally:
        _NAMES = None
    plan.steps["homes"] = "済"
    plan.steps["projects"] = "未実装（プロジェクトへの書き込みは後の段）"
    return plan


def _public(p: Plan, applied: list[dict[str, Any]] | None = None, skipped: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    acts = [{"kind": a.event.kind, "what": a.event.what, "detail": a.event.detail, "why": a.event.why,
             "files": [str(w.path) for w in a.event.writes]} for a in p.actions]
    return {"actions": acts, "inbox": [{"kind": i["kind"], "title": i["title"], "what": i["what"], "status": i.get("initial_status", "open")} for i in p.inbox],
            "held": p.held,
            "notes": p.notes, "steps": p.steps, "baselines": len(p.baselines),
            "applied": applied if applied is not None else None, "skipped": skipped or []}


def _conflict_step(p: Plan, budget: float, progress: Callable[..., Any] | None,
                   tlist: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """効いている集合の中の矛盾（J1）。budget 秒まで未判定の組を LLM で判定する（0 なら判定済みの結果だけ使う）。"""
    cands, info = conflicts.candidates(tlist)
    wk: dict[str, Any] = {}
    if budget > 0 and cands:
        wk = conflicts.work(cands, budget, progress=progress)
    j1 = conflicts.items(cands)
    remaining = wk.get("remaining", len(conflicts.pending(cands)))
    p.steps["conflicts"] = f"候補 {len(cands)} 組・矛盾／状況依存 {len(j1)} 組・未判定 {remaining} 組"
    if remaining:
        p.notes.append(f"矛盾の検査: 未判定の組が {remaining} 組あります（LLM で順に判定します）" + (f"。止まった理由: {wk['stopped']}" if wk.get("stopped") else ""))
    return j1, {"candidates": len(cands), "j1": len(j1), "remaining": remaining, **info, **{k: v for k, v in wk.items() if k != "remaining"}}


def run(dry_run: bool = False, progress: Callable[..., Any] | None = None, llm_budget: float | None = None) -> dict[str, Any]:
    """点検する。dry_run は計画だけ（何も書かない・LLM も呼ばない）。同時には 1 つだけ走る。"""
    if not _RUN.acquire(blocking=False):
        raise ValueError("点検はいま走っています")
    try:
        if progress:
            progress(0, 3, "探索・照合中")
        sc = managed.scan()
        j3 = managed.j3_items(sc["ask"])
        if dry_run:
            tlist = targets.list_targets() + [{"id": targets.target_id(c["kind"], c["path"]), **c} for c in sc["register"]]
            p = plan_all(True, tlist)
            p.steps["managed"] = f"自動で入れる {len(sc['register'])}・確かめる（J3） {len(j3)}"
            p.inbox = j3 + p.inbox
            j1, cinfo = _conflict_step(p, 0, None, tlist)
            p.inbox += j1
            res = {"dry_run": True, "at": store.now_iso(), **_public(p), "conflicts": cinfo,
                   "managed": {"register": [{"name": c["name"], "path": c["path"], "kind": c["kind"]} for c in sc["register"]]}}
            store.save("preview.json", res)
            return res
        gs = settings.get()
        git_info: dict[str, Any] = {}
        j4: list[dict[str, Any]] = []
        if gs.get("git_sync"):
            git_info["pull"], j4 = gitsync.pull_step()
        regs = []
        with changes.LOCK:
            new_j4 = inbox.upsert(j4)
            for c in sc["register"]:
                why = "ホーム（全体の規則の配布先）" if c["kind"] != "project" else ".pair-agent/ を持つ（Pair Agent を導入済み）"
                regs.append(managed.include(c, why))
            new_j3 = inbox.upsert(j3)
            inbox.sync(("J3",), {i["key"] for i in j3})
        p = plan_all(False)
        p.steps["managed"] = f"自動で入れた {len(regs)}・確かめる（J3） {len(j3)}"
        p.inbox = j4 + j3 + p.inbox
        if progress:
            progress(1, 3, "反映中")
        applied, skipped = [], []
        with changes.LOCK:
            led_now = changes.ledger()
            base_rows = [changes.LedgerSet(tid, rel, h, data) for tid, rel, h, data in p.baselines
                         if ((led_now.get(tid) or {}).get(rel) or {}).get("hash") != h]
            if base_rows:
                changes.set_ledger_many(base_rows)
            for a in p.actions:
                try:
                    applied.append(changes.commit(a.event))
                except changes.Stale as exc:
                    skipped.append({"detail": a.event.detail, "why": str(exc)})
            new = new_j4 + new_j3 + inbox.upsert([i for i in p.inbox if i["kind"] == "J2"])
            inbox.sync(("J2",), {i["key"] for i in p.inbox if i["kind"] == "J2"})
        budget = float(settings.get().get("llm_budget_sec", 300)) if llm_budget is None else llm_budget
        j1, cinfo = _conflict_step(p, budget, progress)
        with changes.LOCK:
            new += inbox.upsert(j1)
            inbox.sync(("J1",), {i["key"] for i in j1})
        p.inbox += j1
        applied = regs + applied
        if gs.get("git_sync"):
            summ = "\n".join(f"- {e['what']}: {e['detail']}" for e in applied if e.get("changes"))
            git_info["publish"] = gitsync.publish_step(summ or "- 判断の反映・取り消し")
            pub = git_info["publish"]
            pl = git_info.get("pull") or {}
            pull_s = "済" if pl.get("ok") else f"失敗（{str(pl.get('error') or '')[:80]}）"
            if pub.get("pushed"):
                push_s = f"済 {len(pub.get('files') or [])} ファイル"
            elif pub.get("ok"):
                push_s = "出すものは無い" if not pub.get("commit") else "commit 済（upstream が無い）"
            else:
                push_s = f"失敗（{str(pub.get('error') or '')[:80]}）"
            p.steps["git"] = f"pull {pull_s}・push {push_s}"
        else:
            p.steps["git"] = "同期しない（設定）"
        res = {"dry_run": False, "at": store.now_iso(), **_public(p, [{"id": e["id"], "what": e["what"], "detail": e["detail"]} for e in applied], skipped),
               "new_inbox": len(new), "conflicts": cinfo, "git": git_info}
        store.save(FILE, res)
        if progress:
            progress(3, 3, "完了")
        return res
    finally:
        _RUN.release()


def last() -> dict[str, Any] | None:
    return store.load(FILE, None)


def preview() -> dict[str, Any] | None:
    return store.load("preview.json", None)


def running() -> bool:
    if _RUN.acquire(blocking=False):
        _RUN.release()
        return False
    return True


__all__ = ["run", "plan_all", "merge_sections", "last", "preview", "running", "asdict"]

#!/usr/bin/env python3
"""設計の因果 DB —— 設計の対象と、それらをつなぐ型付きの有向リンクを、追記だけのイベント列で持つ。

師匠の言葉（2026-10-27）:
  「設計とは複雑な情報の因果をもつれなくきれいにつないでいくことだ。設計する以上DBを中に持ってもいいというか
    持つべきともいえる。依存性を少なくするという観点ではJSONのグラフ構造などでもよいかもしれないが、
    環境によってはSQLiteなどを使うことも視野に入れるべき」
  「可能な限り作業は決定性のスクリプトにしろ。LLMの強さは柔軟性だがスクリプトの強さは再現性だ！」

標準ライブラリだけ（Python 3.11+）。LLM もネットワークも呼ばない。ライブラリとしても CLI としても使える。

保存（どちらも同じ API・同じ結果。`convert` で移せる）:
  json（既定）  追記だけの JSONL。1 行 1 イベント。既定の置き場 .pair-agent/design/graph.jsonl
  sqlite        同じイベントを表 events に持つ。      既定の置き場 .pair-agent/design/graph.sqlite
  --backend を省くと --db の拡張子（.sqlite / .sqlite3 / .db）で決める。状態はイベントの再生で作る。

要素（ノード）: id・kind・title・attrs・state（hypothesis／confirmed／rejected／retired）・parent・version（中身の版）
  id は種類の接頭辞＋連番（RQ1, CN2, D3）。案は決定点に続ける（D3-A）。一度振った ID は変えず、再利用しない。
  version は title・attrs（リンクは predicate も）が変わったときだけ上がる。状態の変更では上がらない。
リンク: 有向・型付き（`kinds` で一覧）。リンク自身も id（L1…）・state・version を持ち、上流の版 `seen` を覚える。
  因果の鎖（why／impact が辿る）: 関心事 →affects 課題 →anchors 決定点 →contains 案 →derives 要求 →allocates 要素
  （向きは上流 → 下流で読む。affects・anchors・requires は下流の側から張るので、辿るときに向きを直す）
  --parent で作ると親 → 子の contains を自動で張る（親の中身が変わると子に要再確認の印が付く）。
要再確認は保存しない: 上流の version とリンクの seen を比べてその都度計算する（一段先だけ）。仕分け（triage）だけを記録する。
権限: --actor ai（既定）は仮説しか書けない（作る・仮説を直す・根拠以外のリンクを張る・注記）。
      確定・却下・廃止への変更、決断（decide）、閉じ方（close）、仕分け（triage）、検出の見送り（waive）、
      根拠（evidence）のリンクは --actor human だけ。

規則が読む属性（Skill ごと。API は budgets／coupling／state_space／views／tradeoffs）:
  予算     目標を持つ要素（QS など）の attrs.target（数）・unit と、そこから出る allocates の attrs.budget（数）・unit・basis
  括り     --parent の親子（構造の要素）と relation。括りの attrs.max_coupling は外部結合の上限。
           上限を宣言した括りだけを検出する（結合の数が大きいこと自体は検出しない）
  状態     WS（世界）・SS（システム）・CS（論理コンポーネント。--parent に LC を指す）。
           SS の attrs.of=[CS…] で組合せを定義する（指さない部品は「どちらでもよい」）。attrs.forbidden=true＋reason で禁止。
           transitions（同じ種類の状態どうし）と attrs.mark（initial／goal／external）で供給元・行き止まり・到達性を見る
  ビュー   PT（実装部品）と MO（モデル＝1 枚の図。attrs.viewpoint=logical／implementation／allocation）。
           shows で要素を載せる。要素の種類は attrs.stereotype があればそれ。attrs.whiteboard=true の図は混在してよい
  代償     採用した案の attrs.cons（[{text, origin}]）。捨てたもの（却下した案・代償・案どうしの関係）は tradeoffs()

サブコマンド（共通: --db PATH --backend json|sqlite --actor ai|human --json）:
  init                       空の DB を作る
  add KIND TITLE             要素を足す（--parent --attr k=v --attrs-json --state --evidence）→ ID を出す
  update ID                  中身を直す（--title --attr --attrs-json --append k=v --unset k --predicate）→ 版が上がる
  link KIND SRC DST          リンクを張る（--predicate --attr --state）→ リンク ID を出す。同じものがあればその ID
  state ID STATE             状態を変える【人】（--evidence NT… --reason）
  decide DP OPTION           決断する【人】（--evidence --condition --reason）。他の案は却下にする（消さない）
  close ID --as KIND         課題・リスクを閉じる【人】（resolved／accepted／dismissed／deferred／open）
  triage LINK --ok|--issue T 要再確認を仕分ける【人】
  waive FINDING --reason R   検出を見送る【人】（対象の版が変わると見送りは切れる）
  annotate ID TEXT           注記を足す（版は上がらない。誤りは消さず注記する）
  show ID / list             1 件の詳細 / 一覧（--kind --state）
  why ID / impact ID         上流へ辿る（各段の根拠つき）/ 下流へ辿る（--depth）
  recheck                    要再確認の一覧（一段先だけ）
  check                      検出（規則, 対象 で安定した ID）。検出があれば終了コード 1（--all で見送りも出す）
                             対象が要素でない検出（view:…・system_state）の見送りは、版が無いので切れない
  status                     未決・要再確認・未解決・検出の件数と、完了の条件
  export                     Markdown に書き出す（決定性。「生成物。手で直さない」と書く）（--out）
  convert --to PATH          別の保存形式へ写す（--to-backend）
  kinds                      要素の種類・リンクの種類・検出の規則の一覧

終了コード: 0 正常 / 1 check に検出あり / 2 入力・権限・保存の誤り
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import sqlite3
import sys
from collections import deque
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable

sys.dont_write_bytecode = True

SCHEMA = 1
TOOL = "design_graph.py"
DEFAULT_DB = {"json": Path(".pair-agent/design/graph.jsonl"), "sqlite": Path(".pair-agent/design/graph.sqlite")}
SQLITE_SUFFIXES = {".sqlite", ".sqlite3", ".db"}

ACTORS = ("ai", "human")
STATES = ("hypothesis", "confirmed", "rejected", "retired")
ALIVE = frozenset({"hypothesis", "confirmed"})
STATE_LABEL = {"hypothesis": "仮説", "confirmed": "確定", "rejected": "却下", "retired": "廃止"}

# kind -> (接頭辞, 表示名)。並びは書き出しの順。案は親の決定点に続けて振る（D1-A）
KINDS: dict[str, tuple[str, str]] = {
    "stakeholder": ("SH", "ステークホルダ"),
    "concern": ("CN", "関心事"),
    "qas": ("QS", "品質特性シナリオ"),
    "requirement": ("RQ", "要求"),
    "actor": ("AC", "アクター"),
    "usecase": ("UC", "ユースケース"),
    "world_state": ("WS", "世界の状態"),
    "system_state": ("SS", "システムの状態"),
    "component": ("LC", "論理コンポーネント"),
    "component_state": ("CS", "論理コンポーネントの状態"),
    "part": ("PT", "実装部品"),
    "interface": ("IF", "インタフェース"),
    "model": ("MO", "モデル（1 枚の図）"),
    "constraint": ("CT", "制約"),
    "issue": ("IS", "アーキテクチャ課題"),
    "risk": ("RK", "リスク"),
    "decision_point": ("D", "決定点"),
    "option": ("", "案"),
    "record": ("NT", "設計ノート（根拠の記録）"),
    "note": ("DN", "自由メモ（根拠にならない）"),
}
LINK_PREFIX = "L"
# 確定に根拠（evidence → record）が要る種類
NEEDS_EVIDENCE = frozenset({"concern", "qas", "requirement", "usecase", "component", "interface",
                            "constraint", "decision_point", "part", "world_state", "system_state", "component_state"})
# 割り付け先（allocates）が要る種類
MUST_ALLOCATE = frozenset({"requirement"})
# 上流（決断・導出・割り付け・親）が要る種類。attrs.obvious が真なら免除（自明な要素）
#   実装部品は論理上の役割（allocates LC → PT）か親が要る（部品はあるが役割が無い、を孤児として出す）
NEEDS_UPSTREAM = frozenset({"component", "interface", "decision_point", "part"})
CLOSABLE = frozenset({"issue", "risk"})
CLOSURES = ("resolved", "accepted", "dismissed", "deferred", "open")
CLOSURE_LABEL = {"resolved": "解決", "accepted": "受容", "dismissed": "退ける", "deferred": "保留", "open": "未解決"}
QAS_FIELDS = ("source", "stimulus", "environment", "artifact", "response", "response_measure")
QAS_ALIASES = {"response_measure": ("measure",)}
CONS_ORIGINS = frozenset({"means", "essential", "手段由来", "本質的"})
# 状態の三段導出
STATE_KINDS = ("world_state", "system_state", "component_state")
STATE_MARKS = {"initial": ("initial", "初め", "初めの状態"), "goal": ("goal", "目的達成", "目的達成の状態"),
               "external": ("external", "外", "外の状態")}
STATE_PROBLEMS = {"no_source": "供給元なし", "dead_end": "行き止まり", "unreachable": "初めの状態から到達できない"}
STATE_PRODUCT_LIMIT = 4096   # 直積をこれより多く数え上げない（超えたら網羅の検査をしていないと出す）
STATE_EXAMPLES = 10          # 網羅漏れ・重複の検出に添える組合せの数（全部は state_space() にある）
# 三つの基本ビュー（viewpoint の値と別名）
VIEWPOINTS = {"logical": ("logical", "論理", "論理ビュー"),
              "implementation": ("implementation", "実装", "実装ビュー"),
              "allocation": ("allocation", "割り付け", "割り付けビュー", "配置", "配置ビュー")}
VIEW_LABEL = {"logical": "論理ビュー", "implementation": "実装ビュー", "allocation": "割り付けビュー"}
VIEW_OF_KIND = {"component": "logical", "part": "implementation"}  # どのビューに載るべき要素か
# 括り（構造の要素。括りの中身として数える）
STRUCTURE_KINDS = frozenset({"component", "part", "interface"})
COUPLING_GROUP_KINDS = frozenset({"component", "part", "interface", "option"})  # 案も構造の候補の括りになる
SOFT_RELATIONS = ("excludes", "conflicts", "synergy", "linked")

# リンクの種類 -> (上流の端 src|dst|None, 因果の鎖か, 表示)
#   上流の端があるリンクは、上流の版を seen に覚え、要再確認の対象になる
LINK_KINDS: dict[str, tuple[str | None, bool, str]] = {
    "derives": ("src", True, "導出する（src が上流）"),
    "allocates": ("src", True, "割り付ける（要求 → 要素・関連）"),
    "refines": ("src", True, "分解する（親 → 子）"),
    "affects": ("dst", True, "影響する（課題・リスク → 関心事。dst が上流）"),
    "anchors": ("dst", True, "解く（決定点 → 課題。dst が上流）"),
    "requires": ("dst", True, "前提にする（案 → 前提の案。dst が上流）"),
    "contains": ("src", True, "含む（親 → 子。add --parent で自動で張る）"),
    "evidence": ("dst", False, "根拠を指す（対象 → 設計ノート。人だけ）"),
    "source": ("dst", False, "出所を指す（関心事 → ステークホルダ）"),
    "verifies": ("dst", False, "検証する（設計ノート → 要求）"),
    "about": ("dst", False, "について書く（メモ・課題 → 対象）"),
    "relation": (None, False, "構造の関連（述語 predicate が要る）"),
    "transitions": (None, False, "遷移する（状態 → 次の状態。同じ種類の状態どうし。attrs.event）"),
    "shows": ("dst", False, "載せる（モデル → 要素。要素が変わるとモデルに要再確認）"),
    "excludes": (None, False, "排他（案どうし・硬い）"),
    "conflicts": (None, False, "衝突（案どうし・柔らかい）"),
    "synergy": (None, False, "相乗（案どうし・柔らかい）"),
    "linked": (None, False, "関係（案どうし・柔らかい）"),
}

# 規則 -> (表示, 引く Skill, 水準)。並びは出力の順
RULES: dict[str, tuple[str, str, str]] = {
    "no_evidence": ("根拠の無い確定", "確定の根拠", "warn"),
    "hyp_dep": ("確定が仮説の上に立つ", "結論の顔をした仮説", "warn"),
    "on_dead": ("却下・廃止の上に立つ", "上流変更の仕分け", "warn"),
    "unallocated": ("割り付かない要求", "要求の割り付け", "warn"),
    "orphan": ("孤児（上流の無い要素・決定点）", "要素と決断の紐付け", "warn"),
    "few_options": ("未決の決定点で案が 3 つ未満", "視点の異なる三案", "warn"),
    "no_must": ("決まった案に must／must_not が無い", "決断の禁止事項", "warn"),
    "no_verification": ("採用・推奨の案に検証方法が無い", "検証計画", "warn"),
    "no_conditions": ("決断に背景事情が無い", "決断の背景事情", "warn"),
    "excluded_both": ("排他の案が両方とも採用されている", "要の決定点", "warn"),
    "cons_no_origin": ("欠点に由来（手段由来／本質的）が無い", "欠点の由来", "warn"),
    "no_predicate": ("関連に述語が無い", "関連の述語", "warn"),
    "qas_incomplete": ("品質特性シナリオの 6 要素欠け", "区間の品質特性シナリオ", "warn"),
    "no_source": ("出所の無い関心事", "関心事の出所", "warn"),
    "no_weight": ("重み（1〜5）の無い関心事", "重みのラベル付け", "warn"),
    "closure_incomplete": ("閉じ方の記録が欠ける", "課題の閉じ方", "warn"),
    "no_cons": ("採用した案に代償（cons）が無い", "トレードオフの明示", "warn"),
    "budget_over": ("予算の合計が区間の目標を超える", "区間目標の予算配分", "warn"),
    "budget_unreadable": ("突き合わせられない予算（数でない・単位が違う・目標が無い）", "区間目標の予算配分", "warn"),
    "coupling_over": ("括りの外部結合が宣言した上限を超える", "括りと結合上限", "warn"),
    "state_flow": ("状態遷移の供給元なし・行き止まり・到達できない", "状態の三段導出", "warn"),
    "state_undefined": ("システム状態の定義が欠ける・誤る", "状態の三段導出", "warn"),
    "state_gap": ("どのシステム状態にも禁止にも当たらない組合せ（網羅漏れ）", "状態の三段導出", "warn"),
    "state_overlap": ("2 つ以上のシステム状態に当たる組合せ（重複）", "状態の三段導出", "warn"),
    "view_missing": ("三つの基本ビューの欠け", "三つの基本ビュー", "warn"),
    "no_view": ("どのビューのモデルにも載らない要素", "三つの基本ビュー", "warn"),
    "mixed_kinds": ("1 枚のモデルに要素の種類が混ざる", "一モデル一要素種", "warn"),
    "state_dont_care": ("「どちらでもよい」部品のあるシステム状態（未決事項）", "状態の三段導出", "info"),
    "undecided": ("未決の決定点", "未決の渡し方", "info"),
}
RULE_ORDER = {r: i for i, r in enumerate(RULES)}

_ID_TAIL = re.compile(r"^([A-Z]+)(\d+)$")
_OPTION_ID = re.compile(r"^(.+)-([A-Z]+)$")


class DesignGraphError(Exception):
    """入力・権限・保存の誤り（CLI では終了コード 2）。"""


class PermissionDenied(DesignGraphError):
    """--actor ai に許されていない書き込み。"""


class NotFound(DesignGraphError):
    """無い ID。"""


# ---------------------------------------------------------------- 共通

def natkey(s: str) -> tuple:
    """RQ9 < RQ10 となる並びの鍵。"""
    return tuple((0, int(t)) if t.isdigit() else (1, t) for t in re.split(r"(\d+)", s) if t)


def _letters(n: int) -> str:
    """1 → A, 26 → Z, 27 → AA（案の番号）。"""
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _letters_value(s: str) -> int:
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - 64)
    return n


def _prefix_of(ident: str) -> str | None:
    m = _ID_TAIL.match(ident)
    return m.group(1) if m else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _empty(v: Any) -> bool:
    return v is None or (isinstance(v, (str, list, dict, tuple)) and len(v) == 0) or (isinstance(v, str) and not v.strip())


def _is_number(v: Any) -> bool:
    """数（真偽値・NaN・無限大は除く）。"""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _dec(v: int | float) -> Decimal:
    """十進で足す（0.1 + 0.2 が 0.3 を超えない）。"""
    return Decimal(v) if isinstance(v, int) else Decimal(repr(v))


def _num(d: Decimal) -> int | float:
    return int(d) if d == d.to_integral_value() else float(d)


def _aliases(v: Any, table: dict[str, tuple[str, ...]]) -> set[str]:
    """値（文字列か文字列の配列）を、別名の表の鍵の集合に直す。表に無い値は落とす。"""
    vals = v if isinstance(v, list) else [v]
    out = set()
    for x in vals:
        if isinstance(x, str):
            out |= {k for k, names in table.items() if x.strip() in names}
    return out


def _viewpoint(v: Any) -> str | None:
    """attrs.viewpoint を三つの基本ビューの鍵（logical／implementation／allocation）に直す。
    それ以外の視点はそのままの文字列、無ければ None。"""
    if not isinstance(v, str) or not v.strip():
        return None
    keys = _aliases(v, VIEWPOINTS)
    return next(iter(keys)) if keys else v.strip()


def _cons_list(v: Any) -> list[dict]:
    """attrs.cons を [{text, origin, …}] に揃える（文字列だけの欠点は origin なし）。"""
    if _empty(v):
        return []
    out = []
    for c in v if isinstance(v, list) else [v]:
        if isinstance(c, dict):
            e = dict(c)
            if _empty(e.get("text")):
                e["text"] = _dumps(c)
            out.append(e)
        else:
            out.append({"text": str(c)})
    return out


def parse_value(text: str) -> Any:
    """CLI の値: JSON として読めればその値（数・真偽・配列・オブジェクト）、読めなければ文字列。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def parse_pairs(pairs: Iterable[str] | None, flag: str = "--attr") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for p in pairs or []:
        if "=" not in p:
            raise DesignGraphError(f"{flag} は key=value の形で書く: {p}")
        k, v = p.split("=", 1)
        k = k.strip()
        if not k:
            raise DesignGraphError(f"{flag} の key が空: {p}")
        out.append((k, parse_value(v)))
    return out


def resolve_backend(db: str | Path | None, backend: str | None) -> tuple[str, Path]:
    """(backend, path)。backend を省くと db の拡張子で決める。db を省くと backend の既定の置き場。"""
    if backend is not None and backend not in DEFAULT_DB:
        raise DesignGraphError(f"--backend は json か sqlite: {backend}")
    if db is None:
        b = backend or "json"
        return b, DEFAULT_DB[b]
    p = Path(db)
    if backend is None:
        backend = "sqlite" if p.suffix.lower() in SQLITE_SUFFIXES else "json"
    return backend, p


# ---------------------------------------------------------------- 保存（イベント列の読み書きだけ）

class JsonlLog:
    """追記だけの JSONL。1 行 1 イベント。"""

    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open(encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                s = line.strip()
                if not s:
                    continue
                try:
                    out.append(json.loads(s))
                except json.JSONDecodeError as e:
                    raise DesignGraphError(f"{self.path}:{i} 行目が JSON ではない: {e}") from e
        return out

    def _last_seq(self, f: Any) -> int:
        """最後の行の seq だけを末尾から読む（追記のたびに全体を読み直さない）。"""
        lines: list[bytes] = []
        end = f.seek(0, 2)
        size = 4096
        while True:
            start = max(0, end - size)
            f.seek(start)
            lines = [x for x in f.read(end - start).split(b"\n") if x.strip()]
            if len(lines) >= 2 or start == 0:
                break
            size *= 4
        if not lines:
            return 0
        try:
            return int(json.loads(lines[-1].decode("utf-8"))["seq"])
        except (ValueError, KeyError, TypeError) as e:
            raise DesignGraphError(f"{self.path} の最後の行が読めない: {e}") from e

    def append(self, events: list[dict], expect_last: int) -> None:
        if not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
        data = "".join(_dumps(e) + "\n" for e in events).encode("utf-8")  # 改行は LF に固定する
        with self.path.open("a+b") as f:  # 開くのは 1 回（確かめてから同じハンドルで追記する）
            if self._last_seq(f) != expect_last:
                raise DesignGraphError(f"{self.path} は読み込んだあとに別の書き手が追記した。読み直してやり直す")
            f.seek(0, 2)
            f.write(data)


class SqliteLog:
    """同じイベントを SQLite の表 events(seq, op, actor, body) に持つ。body はイベントの JSON そのもの。"""

    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        with closing(sqlite3.connect(str(self.path))) as con:
            has = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
            if not has:
                return []
            rows = con.execute("SELECT body FROM events ORDER BY seq").fetchall()
        return [json.loads(r[0]) for r in rows]

    def append(self, events: list[dict], expect_last: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(self.path), isolation_level=None)) as con:
            con.execute("CREATE TABLE IF NOT EXISTS events ("
                        "seq INTEGER PRIMARY KEY, op TEXT NOT NULL, actor TEXT NOT NULL, body TEXT NOT NULL)")
            con.execute("BEGIN IMMEDIATE")
            try:
                last = con.execute("SELECT COALESCE(MAX(seq), 0) FROM events").fetchone()[0]
                if last != expect_last:
                    raise DesignGraphError(f"{self.path} は読み込んだあとに別の書き手が追記した。読み直してやり直す")
                con.executemany("INSERT INTO events (seq, op, actor, body) VALUES (?, ?, ?, ?)",
                                [(e["seq"], e["op"], e["actor"], _dumps(e)) for e in events])
                con.execute("COMMIT")
            except BaseException:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise


def open_log(backend: str, path: Path) -> JsonlLog | SqliteLog:
    return SqliteLog(path) if backend == "sqlite" else JsonlLog(path)


# ---------------------------------------------------------------- グラフ（再生した状態と、書き込み・問い合わせ）

class DesignGraph:
    """設計の因果 DB。状態はイベント列の再生で作る。書き込みは検査してからイベントを追記する。

    g = DesignGraph(".pair-agent/design/graph.jsonl", actor="ai")
    cn = g.add("concern", "炊き上がりまでの待ち時間", attrs={"weight": 5})
    """

    def __init__(self, db: str | Path | None = None, backend: str | None = None, actor: str = "ai",
                 clock: Callable[[], str] | None = None):
        if actor not in ACTORS:
            raise DesignGraphError(f"--actor は ai か human: {actor}")
        self.backend, self.path = resolve_backend(db, backend)
        self.log = open_log(self.backend, self.path)
        self.actor = actor
        self.clock = clock or _utc_now
        self._reset()
        for ev in self.log.read():
            self._apply(ev)

    # ------------------------------------------------ 再生

    def _reset(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.links: dict[str, dict] = {}
        self.counters: dict[str, int] = {}
        self.option_counters: dict[str, int] = {}
        self.triages: list[dict] = []
        self.waivers: dict[str, dict] = {}
        self.history: dict[str, list[dict]] = {}
        self.last_seq = 0
        self._index: dict[str, list[dict]] = {}
        self._index_seq = -1

    def _bump(self, ident: str, kind: str, parent: str | None) -> None:
        if kind == "option":
            m = _OPTION_ID.match(ident)
            if m and parent:
                n = _letters_value(m.group(2))
                self.option_counters[parent] = max(self.option_counters.get(parent, 0), n)
            return
        m = _ID_TAIL.match(ident)
        if m:
            self.counters[m.group(1)] = max(self.counters.get(m.group(1), 0), int(m.group(2)))

    def _apply(self, ev: dict) -> None:
        op, seq = ev["op"], int(ev["seq"])
        self.last_seq = seq
        target = ev.get("id") or ev.get("dp") or ev.get("link")
        if op == "meta":
            return
        if op == "create":
            ident = ev["id"]
            self.nodes[ident] = {"id": ident, "kind": ev["kind"], "title": ev["title"],
                                 "attrs": dict(ev.get("attrs") or {}), "state": ev.get("state", "hypothesis"),
                                 "parent": ev.get("parent"), "version": 1, "decision": None, "closure": None,
                                 "notes": []}
            self._bump(ident, ev["kind"], ev.get("parent"))
        elif op == "link":
            ident = ev["id"]
            self.links[ident] = {"id": ident, "kind": ev["kind"], "src": ev["src"], "dst": ev["dst"],
                                 "predicate": ev.get("predicate"), "attrs": dict(ev.get("attrs") or {}),
                                 "state": ev.get("state", "hypothesis"), "version": 1, "seen": ev.get("seen"),
                                 "notes": []}
            self._bump(ident, "link", None)
        elif op == "update":
            e = self._entity(ev["id"])
            if "title" in ev:
                e["title"] = ev["title"]
            if "predicate" in ev:
                e["predicate"] = ev["predicate"]
            for k, v in (ev.get("set") or {}).items():
                e["attrs"][k] = v
            for k in ev.get("unset") or []:
                e["attrs"].pop(k, None)
            e["version"] += 1
        elif op == "state":
            self._entity(ev["id"])["state"] = ev["state"]
        elif op == "decide":
            self.nodes[ev["dp"]]["decision"] = {"option": ev["option"], "conditions": list(ev.get("conditions") or []),
                                                "reason": ev.get("reason"), "seq": seq}
        elif op == "close":
            self.nodes[ev["id"]]["closure"] = {"as": ev["as"], "reason": ev.get("reason"),
                                               "reopen_if": ev.get("reopen_if"), "resume_if": ev.get("resume_if"),
                                               "seq": seq}
        elif op == "triage":
            self.links[ev["link"]]["seen"] = ev["seen"]
            self.triages.append(dict(ev))
        elif op == "waive":
            self.waivers[ev["finding"]] = {"reason": ev.get("reason"), "version": ev.get("version"), "seq": seq}
            target = ev.get("target")
        elif op == "annotate":
            self._entity(ev["id"])["notes"].append({"seq": seq, "actor": ev["actor"], "text": ev["text"]})
        else:
            raise DesignGraphError(f"知らないイベント op={op}（seq {seq}）")
        if target:
            self.history.setdefault(target, []).append(
                {"seq": seq, "op": op, "actor": ev.get("actor"), "at": ev.get("at")})

    # ------------------------------------------------ 書き込みの土台

    def _commit(self, events: list[dict]) -> None:
        if not events:
            return
        out, seq = [], self.last_seq
        if seq == 0:
            events = [{"op": "meta", "schema": SCHEMA, "tool": TOOL}, *events]
        for e in events:
            seq += 1
            out.append({"seq": seq, "actor": self.actor, "at": self.clock(), **e})
        self.log.append(out, self.last_seq)
        for e in out:
            self._apply(e)

    def _require_human(self, what: str) -> None:
        if self.actor != "human":
            raise PermissionDenied(f"{what}は人（--actor human）だけができる。AI は仮説として書き、根拠を添えて人に求める")

    def _new_id(self, kind: str, parent: str | None, pending: list[dict]) -> str:
        if kind == "option":
            assert parent is not None
            n = self.option_counters.get(parent, 0) + sum(
                1 for e in pending if e.get("op") == "create" and e.get("kind") == "option" and e.get("parent") == parent)
            return f"{parent}-{_letters(n + 1)}"
        prefix = LINK_PREFIX if kind == "link" else KINDS[kind][0]
        op = "link" if kind == "link" else "create"
        n = self.counters.get(prefix, 0) + sum(
            1 for e in pending if e.get("op") == op and _prefix_of(e.get("id", "")) == prefix)
        return f"{prefix}{n + 1}"

    def _entity(self, ident: str) -> dict:
        if ident in self.nodes:
            return self.nodes[ident]
        if ident in self.links:
            return self.links[ident]
        raise NotFound(f"無い ID: {ident}")

    def _check_evidence(self, evidence: Iterable[str]) -> list[str]:
        out = []
        for r in evidence or []:
            n = self.nodes.get(r)
            if n is None:
                raise NotFound(f"根拠に指した ID が無い: {r}")
            if n["kind"] != "record":
                raise DesignGraphError(f"根拠に指せるのは設計ノート（record・NT）だけ: {r} は {n['kind']}"
                                       "（自由メモ DN は根拠にならない）")
            if r not in out:
                out.append(r)
        return out

    def _evidence_events(self, src: str, records: list[str], pending: list[dict]) -> list[dict]:
        evs = []
        for r in records:
            if self._find_link("evidence", src, r, None) is not None:
                continue
            ident = self._new_id("link", None, pending + evs)
            evs.append({"op": "link", "id": ident, "kind": "evidence", "src": src, "dst": r, "state": "confirmed",
                        "seen": self.nodes[r]["version"]})
        return evs

    def _find_link(self, kind: str, src: str, dst: str, predicate: str | None) -> str | None:
        for l in self.links.values():
            if (l["kind"], l["src"], l["dst"]) == (kind, src, dst) and l["state"] in ALIVE and \
                    (kind != "relation" or (l.get("predicate") or None) == (predicate or None)):
                return l["id"]
        return None

    # ------------------------------------------------ 書き込み（API）

    def init(self) -> None:
        """空の DB を作る（既にあれば何もしない）。"""
        if self.last_seq == 0:
            ev = {"seq": 1, "actor": self.actor, "at": self.clock(), "op": "meta", "schema": SCHEMA, "tool": TOOL}
            self.log.append([ev], 0)
            self._apply(ev)

    def add(self, kind: str, title: str, attrs: dict | None = None, parent: str | None = None,
            state: str = "hypothesis", evidence: Iterable[str] = ()) -> str:
        """要素を足して ID を返す。案（option）は parent に決定点を指す。"""
        if kind not in KINDS:
            raise DesignGraphError(f"知らない種類: {kind}（kinds で一覧）")
        if not isinstance(title, str) or not title.strip():
            raise DesignGraphError("title が空")
        if state not in ("hypothesis", "confirmed"):
            raise DesignGraphError("作るときの状態は hypothesis か confirmed だけ")
        if state != "hypothesis":
            self._require_human("確定として作ること")
        if kind == "option":
            if state == "confirmed":
                raise DesignGraphError("案の採用は decide で行う（作るときは仮説）")
            if not parent or parent not in self.nodes or self.nodes[parent]["kind"] != "decision_point":
                raise DesignGraphError("案（option）の parent には決定点（D…）を指す")
        elif parent is not None and parent not in self.nodes:
            raise NotFound(f"親が無い: {parent}")
        if kind == "component_state" and (not parent or self.nodes[parent]["kind"] != "component"):
            raise DesignGraphError("論理コンポーネントの状態（component_state）の parent には論理コンポーネント（LC…）を指す")
        if attrs is not None and not isinstance(attrs, dict):
            raise DesignGraphError("attrs はオブジェクト（dict）")
        records = self._check_evidence(evidence)
        if records:
            self._require_human("根拠（evidence）を指すこと")
        ident = self._new_id(kind, parent, [])
        ev: dict[str, Any] = {"op": "create", "id": ident, "kind": kind, "title": title.strip(),
                              "attrs": dict(attrs or {}), "state": state}
        events: list[dict] = [ev]
        if parent is not None:
            # 親子も因果の一段として扱う（親の中身が変わったら子に要再確認の印が付く）
            ev["parent"] = parent
            events.append({"op": "link", "id": self._new_id("link", None, events), "kind": "contains",
                           "src": parent, "dst": ident, "state": state, "attrs": {},
                           "seen": self.nodes[parent]["version"]})
        events += self._evidence_events(ident, records, events)
        self._commit(events)
        return ident

    def update(self, ident: str, title: str | None = None, attrs: dict | None = None, unset: Iterable[str] = (),
               append: Iterable[tuple[str, Any]] = (), predicate: str | None = None) -> int:
        """中身（title・attrs・リンクの predicate）を直す。変わったら版が上がり、新しい版を返す。"""
        e = self._entity(ident)
        if self.actor != "human" and e["state"] != "hypothesis":
            raise PermissionDenied(f"{ident} は{STATE_LABEL[e['state']]}。AI が直せるのは仮説だけ。"
                                   "直したい点は annotate で注記して人に求める")
        ev: dict[str, Any] = {"op": "update", "id": ident}
        if title is not None:
            if not title.strip():
                raise DesignGraphError("title が空")
            if title.strip() != e["title"]:
                ev["title"] = title.strip()
        if predicate is not None:
            if ident not in self.links:
                raise DesignGraphError("predicate はリンクだけが持つ")
            if predicate != (e.get("predicate") or ""):
                ev["predicate"] = predicate
        sets: dict[str, Any] = {}
        for k, v in (attrs or {}).items():
            if e["attrs"].get(k, object()) != v:
                sets[k] = v
        for k, v in append or []:
            cur = sets.get(k, e["attrs"].get(k))
            base = [] if cur is None else (list(cur) if isinstance(cur, list) else [cur])
            sets[k] = base + [v]
        unsets = sorted({k for k in unset or [] if k in e["attrs"] and k not in sets})
        if sets:
            ev["set"] = sets
        if unsets:
            ev["unset"] = unsets
        if len(ev) == 2:
            return e["version"]
        self._commit([ev])
        return self._entity(ident)["version"]

    def link(self, kind: str, src: str, dst: str, predicate: str | None = None, attrs: dict | None = None,
             state: str | None = None) -> str:
        """リンクを張って ID を返す。同じ種類・同じ両端（relation は同じ述語）の生きたリンクがあれば、その ID を返す。"""
        if kind not in LINK_KINDS:
            raise DesignGraphError(f"知らないリンクの種類: {kind}（kinds で一覧）")
        if src == dst:
            raise DesignGraphError("自分自身へのリンクは張らない")
        if src not in self.nodes:
            raise NotFound(f"src が無い（src は要素の ID）: {src}")
        if dst not in self.nodes:
            if not (kind == "allocates" and dst in self.links and self.links[dst]["kind"] == "relation"):
                raise NotFound(f"dst が無い（allocates だけは関連 relation のリンク ID も指せる）: {dst}")
        if kind == "evidence":
            self._require_human("根拠（evidence）を指すこと")
            self._check_evidence([dst])
        if kind == "source" and self.nodes[dst]["kind"] != "stakeholder":
            raise DesignGraphError(f"source の dst はステークホルダ（SH）: {dst}（規格・戦略も SH として置く）")
        if kind == "transitions":
            a, b = self.nodes[src], self.nodes[dst]
            if a["kind"] not in STATE_KINDS or a["kind"] != b["kind"]:
                raise DesignGraphError(f"遷移は同じ種類の状態どうし（WS→WS・SS→SS・CS→CS）: {src}（{a['kind']}）→ "
                                       f"{dst}（{b['kind']}）")
            if a["kind"] == "component_state" and a.get("parent") != b.get("parent"):
                raise DesignGraphError(f"論理コンポーネントの状態の遷移は同じ部品の中だけ: {src}（{a.get('parent')}）→ "
                                       f"{dst}（{b.get('parent')}）")
        if kind == "shows":
            if self.nodes[src]["kind"] != "model":
                raise DesignGraphError(f"shows の src はモデル（MO）: {src}")
            if self.nodes[dst]["kind"] == "model":
                raise DesignGraphError(f"モデルにモデルは載せない: {dst}")
        if state is None:
            state = "confirmed" if kind == "evidence" else "hypothesis"
        if state not in ("hypothesis", "confirmed"):
            raise DesignGraphError("張るときの状態は hypothesis か confirmed だけ")
        if state == "confirmed":
            self._require_human("確定のリンクを張ること")
        pred = predicate.strip() if isinstance(predicate, str) else None
        found = self._find_link(kind, src, dst, pred)
        if found is not None:
            return found
        up = LINK_KINDS[kind][0]
        ident = self._new_id("link", None, [])
        ev: dict[str, Any] = {"op": "link", "id": ident, "kind": kind, "src": src, "dst": dst, "state": state,
                              "attrs": dict(attrs or {}),
                              "seen": self._entity(src if up == "src" else dst)["version"] if up else None}
        if pred:
            ev["predicate"] = pred
        self._commit([ev])
        return ident

    def set_state(self, ident: str, state: str, evidence: Iterable[str] = (), reason: str | None = None) -> None:
        """状態を変える【人】。確定には根拠（設計ノート）を同じ行で指せる。"""
        self._require_human("状態の変更")
        if state not in STATES:
            raise DesignGraphError(f"状態は {'／'.join(STATES)} のどれか: {state}")
        e = self._entity(ident)
        if e.get("kind") == "option" and ident in self.nodes and state == "confirmed":
            raise DesignGraphError("案の採用は decide で行う")
        records = self._check_evidence(evidence)
        if records and ident not in self.nodes:
            raise DesignGraphError("根拠を指せるのは要素だけ（リンクには指さない）")
        events: list[dict] = []
        if e["state"] != state:
            ev: dict[str, Any] = {"op": "state", "id": ident, "state": state}
            if reason:
                ev["reason"] = reason
            events.append(ev)
        events += self._evidence_events(ident, records, events)
        self._commit(events)

    def decide(self, dp: str, option: str, evidence: Iterable[str] = (), conditions: Iterable[str] = (),
               reason: str | None = None) -> None:
        """決断する【人】。採用した案を確定に、同じ決定点の他の案を却下にする（消さない・判例として残る）。"""
        self._require_human("決断")
        d = self.nodes.get(dp)
        if d is None or d["kind"] != "decision_point":
            raise DesignGraphError(f"決定点（D…）ではない: {dp}")
        o = self.nodes.get(option)
        if o is None or o["kind"] != "option" or o.get("parent") != dp:
            raise DesignGraphError(f"{option} は {dp} の案ではない")
        if o["state"] == "retired":
            raise DesignGraphError(f"{option} は廃止されている")
        records = self._check_evidence(evidence)
        conds = [c.strip() for c in conditions or [] if isinstance(c, str) and c.strip()]
        ev: dict[str, Any] = {"op": "decide", "dp": dp, "option": option, "conditions": conds}
        if reason:
            ev["reason"] = reason
        events: list[dict] = [ev]
        if o["state"] != "confirmed":
            events.append({"op": "state", "id": option, "state": "confirmed", "reason": f"{dp} で採用"})
        for sib in self._options(dp):
            if sib["id"] != option and sib["state"] in ALIVE:
                events.append({"op": "state", "id": sib["id"], "state": "rejected", "reason": f"{dp} で {option} を採用"})
        if d["state"] == "hypothesis":
            events.append({"op": "state", "id": dp, "state": "confirmed", "reason": "決断した"})
        events += self._evidence_events(dp, records, events)
        self._commit(events)

    def close(self, ident: str, closure: str, evidence: Iterable[str] = (), reopen_if: str | None = None,
              resume_if: str | None = None, reason: str | None = None) -> None:
        """課題・リスクを閉じる【人】。受容は根拠、退けるは開き直す条件、保留は再開の条件を添える。open で開き直す。"""
        self._require_human("課題の閉じ方の記録")
        n = self.nodes.get(ident)
        if n is None or n["kind"] not in CLOSABLE:
            raise DesignGraphError(f"閉じられるのは課題（IS）とリスク（RK）だけ: {ident}")
        if closure not in CLOSURES:
            raise DesignGraphError(f"閉じ方は {'／'.join(CLOSURES)} のどれか: {closure}")
        records = self._check_evidence(evidence)
        ev: dict[str, Any] = {"op": "close", "id": ident, "as": closure}
        for k, v in (("reason", reason), ("reopen_if", reopen_if), ("resume_if", resume_if)):
            if v:
                ev[k] = v
        events = [ev]
        events += self._evidence_events(ident, records, events)
        self._commit(events)

    def triage(self, link_id: str, outcome: str, title: str | None = None, note: str | None = None) -> str | None:
        """要再確認を仕分ける【人】。ok＝問題なし（見た上流の版を記録）／issue＝課題にする（課題の ID を返す）。"""
        self._require_human("仕分け")
        mark = next((m for m in self.recheck() if m["link"] == link_id), None)
        if mark is None:
            raise DesignGraphError(f"{link_id} に要再確認の印は無い（recheck で一覧）")
        if outcome not in ("ok", "issue"):
            raise DesignGraphError("仕分けは ok（問題なし）か issue（課題にする）")
        events: list[dict] = []
        issue_id = None
        if outcome == "issue":
            issue_id = self._new_id("issue", None, [])
            down = mark["downstream"]
            t = (title or "").strip() or f"{mark['upstream']} の変更（v{mark['seen']}→v{mark['current']}）と {down} の不整合"
            events.append({"op": "create", "id": issue_id, "kind": "issue", "title": t, "state": "hypothesis",
                           "attrs": {"origin": "triage", "link": link_id, "upstream": mark["upstream"],
                                     "downstream": down, "seen": mark["seen"], "current": mark["current"]}})
            events.append({"op": "link", "id": self._new_id("link", None, events), "kind": "about", "src": issue_id,
                           "dst": down, "state": "hypothesis", "attrs": {},
                           "seen": self._entity(down)["version"]})
        ev: dict[str, Any] = {"op": "triage", "link": link_id, "outcome": outcome, "seen": mark["current"],
                              "from": mark["seen"]}
        if issue_id:
            ev["issue"] = issue_id
        if note:
            ev["note"] = note
        events.append(ev)
        self._commit(events)
        return issue_id

    def waive(self, finding_id: str, reason: str) -> None:
        """検出を見送る【人】。対象の版を覚え、対象の中身が変わると見送りは切れる。"""
        self._require_human("検出の見送り")
        if not reason or not reason.strip():
            raise DesignGraphError("見送りには理由が要る")
        f = next((x for x in self.check(include_waived=True) if x["id"] == finding_id), None)
        if f is None:
            raise DesignGraphError(f"いま出ていない検出: {finding_id}（check で一覧）")
        tgt = f["target"]
        ver = self._entity(tgt)["version"] if (tgt in self.nodes or tgt in self.links) else None
        self._commit([{"op": "waive", "finding": finding_id, "target": tgt, "version": ver, "reason": reason.strip()}])

    def annotate(self, ident: str, text: str) -> None:
        """注記を足す（誰でも。版は上がらない）。誤りは消さず注記する。"""
        self._entity(ident)
        if not text or not text.strip():
            raise DesignGraphError("注記が空")
        self._commit([{"op": "annotate", "id": ident, "text": text.strip()}])

    def convert(self, to_db: str | Path, to_backend: str | None = None) -> tuple[str, Path]:
        """イベント列をそのまま別の保存形式へ写す。写し先は空でなければならない。"""
        b, p = resolve_backend(to_db, to_backend)
        if p.resolve() == self.path.resolve():
            raise DesignGraphError("写し先が写し元と同じ")
        dst = open_log(b, p)
        if dst.read():
            raise DesignGraphError(f"写し先が空ではない: {p}")
        events = self.log.read()
        if events:
            dst.append(events, 0)
        return b, p

    # ------------------------------------------------ 問い合わせ

    def get(self, ident: str) -> dict:
        return json.loads(_dumps(self._entity(ident)))

    def is_link(self, ident: str) -> bool:
        return ident in self.links

    def find(self, kind: str | None = None, state: str | None = None) -> list[dict]:
        out = [n for n in self.nodes.values()
               if (kind is None or n["kind"] == kind) and (state is None or n["state"] == state)]
        return [json.loads(_dumps(n)) for n in sorted(out, key=lambda n: natkey(n["id"]))]

    def _options(self, dp: str) -> list[dict]:
        return sorted((n for n in self.nodes.values() if n["kind"] == "option" and n.get("parent") == dp),
                      key=lambda n: natkey(n["id"]))

    def _alive(self, ident: str) -> bool:
        e = self.nodes.get(ident) or self.links.get(ident)
        return e is not None and e["state"] in ALIVE

    def links_from(self, ident: str, kind: str | None = None) -> list[dict]:
        """ident から出ている生きたリンク（先も生きているものだけ）。索引は seq ごとに作り直す。"""
        if self._index_seq != self.last_seq:
            idx: dict[str, list[dict]] = {}
            for l in sorted(self.links.values(), key=lambda l: natkey(l["id"])):
                if l["state"] in ALIVE and self._alive(l["dst"]):
                    idx.setdefault(l["src"], []).append(l)
            self._index, self._index_seq = idx, self.last_seq
        return [l for l in self._index.get(ident, []) if kind is None or l["kind"] == kind]

    def evidence_of(self, ident: str, confirmed_only: bool = False) -> list[str]:
        """要素が指している根拠（生きた evidence リンクの先の設計ノート）。"""
        out = {l["dst"] for l in self.links_from(ident, "evidence") if not confirmed_only or l["state"] == "confirmed"}
        return sorted(out, key=natkey)

    def edges(self) -> list[tuple[str, str, str, str | None]]:
        """因果の辺（上流, 下流, 経路, リンク ID）。生きたリンクだけ。親子は contains のリンクで入る。
        要求が関連（relation）に割り付いているときは、要求 → 関連 → 関連の両端の要素 とつなぐ。"""
        out: list[tuple[str, str, str, str | None]] = []
        targeted: set[str] = set()
        for l in self.links.values():
            up_side, causal, _ = LINK_KINDS[l["kind"]]
            if not causal or l["state"] not in ALIVE:
                continue
            up, down = (l["src"], l["dst"]) if up_side == "src" else (l["dst"], l["src"])
            out.append((up, down, l["kind"], l["id"]))
            if l["kind"] == "allocates" and l["dst"] in self.links:
                targeted.add(l["dst"])
        for rid in targeted:
            r = self.links[rid]
            if r["state"] in ALIVE:
                out.append((rid, r["src"], "ends", rid))
                out.append((rid, r["dst"], "ends", rid))
        return sorted(out, key=lambda t: (natkey(t[0]), natkey(t[1]), t[2], natkey(t[3] or "")))

    def _adjacency(self) -> tuple[dict[str, list], dict[str, list]]:
        ups: dict[str, list] = {}
        downs: dict[str, list] = {}
        for up, down, via, lid in self.edges():
            downs.setdefault(up, []).append((down, via, lid))
            ups.setdefault(down, []).append((up, via, lid))
        return ups, downs

    def _walk(self, start: str, direction: str, depth: int | None) -> list[dict]:
        self._entity(start)
        ups, downs = self._adjacency()
        adj = ups if direction == "up" else downs
        stale = {m["link"] for m in self.recheck()}
        children: dict[str, list[tuple[str, str, str | None]]] = {}
        level = {start: 0}
        q = deque([start])
        while q:
            cur = q.popleft()
            if depth is not None and level[cur] >= depth:
                continue
            for other, via, lid in sorted(adj.get(cur, []), key=lambda t: (natkey(t[0]), t[1], natkey(t[2] or ""))):
                if other in level:
                    continue
                level[other] = level[cur] + 1
                children.setdefault(cur, []).append((other, via, lid))
                q.append(other)
        out: list[dict] = []
        stack: list[tuple[str, int, str | None, str | None, str | None]] = [(start, 0, None, None, None)]
        while stack:
            ident, d, via, lid, frm = stack.pop()
            e = self._entity(ident)
            out.append({"id": ident, "depth": d, "via": via, "link": lid, "from": frm,
                        "kind": e["kind"] if ident in self.nodes else f"link:{e['kind']}",
                        "title": e.get("title") or self._link_text(e), "state": e["state"],
                        "evidence": self.evidence_of(ident) if ident in self.nodes else [],
                        "stale": bool(lid and lid in stale)})
            for c, v, l in reversed(children.get(ident, [])):
                stack.append((c, d + 1, v, l, ident))
        return out

    def why(self, ident: str, depth: int | None = None) -> list[dict]:
        """上流へ辿る（幅優先で木を作り、木の順に並べる）。各段に根拠（設計ノート）を添える。"""
        return self._walk(ident, "up", depth)

    def impact(self, ident: str, depth: int | None = None) -> list[dict]:
        """下流へ辿る（全段）。"""
        return self._walk(ident, "down", depth)

    def recheck(self) -> list[dict]:
        """要再確認の印（保存しない・その都度計算）。上流の版がリンクの seen より進んだ、生きた下流だけ（一段先）。"""
        out = []
        for l in self.links.values():
            up_side = LINK_KINDS[l["kind"]][0]
            if up_side is None or l["state"] not in ALIVE or l.get("seen") is None:
                continue
            up, down = (l["src"], l["dst"]) if up_side == "src" else (l["dst"], l["src"])
            if not self._alive(down):
                continue
            cur = self._entity(up)["version"]
            if cur > l["seen"]:
                out.append({"link": l["id"], "kind": l["kind"], "upstream": up, "downstream": down,
                            "seen": l["seen"], "current": cur})
        return sorted(out, key=lambda m: (natkey(m["downstream"]), natkey(m["link"])))

    # ------------------------------------------------ 検出

    def _waived(self, fid: str, target: str) -> bool:
        w = self.waivers.get(fid)
        if w is None:
            return False
        ver = self._entity(target)["version"] if (target in self.nodes or target in self.links) else None
        return w.get("version") == ver

    def check(self, include_waived: bool = False) -> list[dict]:
        """検出の一覧。ID は「規則:対象」で、同じ状態からは同じ結果になる。"""
        out: list[dict] = []

        def add(rule: str, target: str, text: str, **extra: Any) -> None:
            label, skill, level = RULES[rule]
            fid = f"{rule}:{target}"
            waived = self._waived(fid, target)
            if waived and not include_waived:
                return
            out.append({"id": fid, "rule": rule, "target": target, "level": level, "label": label,
                        "skill": skill, "message": f"{label}：{text}", "waived": waived, **extra})

        ups, _ = self._adjacency()
        for n in sorted(self.nodes.values(), key=lambda n: natkey(n["id"])):
            if n["state"] not in ALIVE:
                continue
            ident, kind, a = n["id"], n["kind"], n["attrs"]
            upstream = sorted({u for u, _, _ in ups.get(ident, [])}, key=natkey)
            if n["state"] == "confirmed" and kind in NEEDS_EVIDENCE and not self.evidence_of(ident, confirmed_only=True):
                add("no_evidence", ident, f"{ident} は確定だが、根拠の設計ノート（NT）を指していない")
            hyp = [u for u in upstream if self._entity(u)["state"] == "hypothesis"]
            if n["state"] == "confirmed" and hyp:
                add("hyp_dep", ident, f"{ident}（確定）の上流に仮説がある: {', '.join(hyp)}", upstream=hyp)
            dead = [u for u in upstream if self._entity(u)["state"] not in ALIVE]
            if dead:
                add("on_dead", ident, f"{ident} の上流が却下・廃止: {', '.join(dead)}", upstream=dead)
            if kind in MUST_ALLOCATE and not self.links_from(ident, "allocates"):
                add("unallocated", ident, f"{ident} を割り付けた要素・関連が無い")
            if kind in NEEDS_UPSTREAM and not upstream and not a.get("obvious"):
                what = "課題につながっていない（anchors が無い）" if kind == "decision_point" else \
                    "決断・導出・割り付け・親のどれにもつながっていない（自明なら attrs.obvious=true）"
                add("orphan", ident, f"{ident} は{what}")
            if kind == "decision_point":
                self._check_dp(n, add)
            if kind == "option":
                self._check_option(n, add)
            if kind == "qas":
                missing = [f for f in QAS_FIELDS
                           if _empty(a.get(f)) and not any(not _empty(a.get(x)) for x in QAS_ALIASES.get(f, ()))]
                if missing:
                    add("qas_incomplete", ident, f"{ident} に欠け: {', '.join(missing)}", missing=missing)
            if kind == "concern":
                if not self.links_from(ident, "source"):
                    add("no_source", ident, f"{ident} の出所（source → SH）が無い。「みんな」で埋めず聞きに行く")
                w = a.get("weight")
                if isinstance(w, bool) or not isinstance(w, int) or not 1 <= w <= 5:
                    add("no_weight", ident, f"{ident} の重み（attrs.weight 1〜5）が無い・範囲外: {w!r}")
            if kind in CLOSABLE and n.get("closure"):
                c = n["closure"]
                if c["as"] == "accepted" and not self.evidence_of(ident, confirmed_only=True):
                    add("closure_incomplete", ident, f"{ident} は受容だが、誰が何をどの条件で受けたかの記録（NT）を指していない")
                elif c["as"] == "dismissed" and _empty(c.get("reopen_if")):
                    add("closure_incomplete", ident, f"{ident} は退けたが、開き直す条件（reopen_if）が無い")
                elif c["as"] == "deferred" and _empty(c.get("resume_if")):
                    add("closure_incomplete", ident, f"{ident} は保留だが、再開の条件（resume_if）が無い")
        for l in sorted(self.links.values(), key=lambda l: natkey(l["id"])):
            if l["state"] not in ALIVE:
                continue
            if l["kind"] == "relation" and _empty(l.get("predicate")):
                add("no_predicate", l["id"], f"{l['id']}（{l['src']} — {l['dst']}）に述語が無い")
            if l["kind"] == "excludes" and self._adopted(l["src"]) and self._adopted(l["dst"]):
                add("excluded_both", l["id"], f"{l['src']} と {l['dst']} は排他（{l['id']}）なのに両方とも採用されている")
        self._check_budgets(add)
        self._check_coupling(add)
        self._check_states(add)
        self._check_views(add)
        return sorted(out, key=lambda f: (RULE_ORDER[f["rule"]], natkey(f["target"])))

    def _check_dp(self, n: dict, add: Callable[..., None]) -> None:
        ident = n["id"]
        opts = [o for o in self._options(ident) if o["state"] != "retired"]
        dec = n.get("decision")
        if not dec:
            add("undecided", ident, f"{ident} {n['title']}（案 {len(opts)}）")
            views = {str(o["attrs"].get("viewpoint")).strip() if not _empty(o["attrs"].get("viewpoint")) else o["id"]
                     for o in opts}
            if len(views) < 3:
                add("few_options", ident, f"{ident} の案は {len(opts)}・視点は {len(views)}（視点の異なる 3 案以上）",
                    options=len(opts), viewpoints=len(views))
        elif not dec.get("conditions"):
            add("no_conditions", ident, f"{ident} の決断に背景事情（成り立つ条件）が無い（decide --condition）")

    def _adopted(self, ident: str) -> bool:
        """決断で採用された案か（決定点が生きていて、その decision が指している）。"""
        o = self.nodes.get(ident)
        if o is None or o["kind"] != "option" or o["state"] not in ALIVE:
            return False
        dp = self.nodes.get(o.get("parent") or "")
        return bool(dp and dp["state"] in ALIVE and (dp.get("decision") or {}).get("option") == ident)

    def _check_option(self, o: dict, add: Callable[..., None]) -> None:
        ident, a = o["id"], o["attrs"]
        adopted = self._adopted(ident)
        if adopted and _empty(a.get("must")) and _empty(a.get("must_not")):
            add("no_must", ident, f"{ident} は採用されたが、実装者への制約 must／must_not が無い")
        if (adopted or a.get("recommended")) and _empty(a.get("verification")):
            add("no_verification", ident, f"{ident} は{'採用' if adopted else '推奨'}だが、検証方法（verification）が無い")
        if adopted and _empty(a.get("cons")):
            add("no_cons", ident, f"{ident} は採用されたが、代償（cons）が書かれていない。"
                                  "「代償なし」は測っていないだけかもしれない")
        cons = a.get("cons")
        if not _empty(cons):
            entries = cons if isinstance(cons, list) else [cons]
            bad = sum(1 for c in entries if not (isinstance(c, dict) and c.get("origin") in CONS_ORIGINS))
            if bad:
                add("cons_no_origin", ident, f"{ident} の欠点 {bad} 件に由来（origin: means／essential）が無い", count=bad)

    def _check_budgets(self, add: Callable[..., None]) -> None:
        for b in self.budgets():
            u = f" {b['unit']}" if b["unit"] else ""
            if b["over"]:
                add("budget_over", b["id"], f"{b['id']} の目標 {b['target']}{u} に対し、配分の合計 {b['total']}{u}"
                    f"（超過 {b['excess']}{u}）。予算の取り合いを課題にする", goal=b["target"], total=b["total"],
                    excess=b["excess"])
            if b["problem"] == "no_target":
                add("budget_unreadable", b["id"], f"{b['id']} から予算を配分しているが、目標値（attrs.target の数）が無い")
            elif b["problem"] == "target_not_number":
                add("budget_unreadable", b["id"], f"{b['id']} の目標値（attrs.target）が数でない: {b['target']!r}")
            for i in b["items"]:
                if i["problem"] == "not_number":
                    add("budget_unreadable", i["link"],
                        f"{i['link']}（{b['id']} → {i['to']}）の予算（attrs.budget）が数でない: {i['budget']!r}")
                elif i["problem"] == "unit":
                    add("budget_unreadable", i["link"], f"{i['link']}（{b['id']} → {i['to']}）の予算の単位 {i['unit']} が"
                        f"目標の単位 {b['unit']} と違う（関心事ごとに別の予算表にする）")

    def _check_coupling(self, add: Callable[..., None]) -> None:
        for g in self.coupling()["groups"]:
            if g["limit_valid"] is None:  # 上限を宣言していない括りは検出しない（数の大きさは課題の種別にしない）
                continue
            if not g["limit_valid"]:
                add("coupling_over", g["id"], f"{g['id']} の上限（attrs.max_coupling）が 0 以上の整数でない: "
                    f"{g['max_coupling']!r}")
            elif g["over"]:
                add("coupling_over", g["id"], f"{g['id']} の外部結合 {g['external']} が、宣言した上限 {g['max_coupling']} を超える",
                    external=g["external"], limit=g["max_coupling"])

    def _check_states(self, add: Callable[..., None]) -> None:
        sp = self.state_space()
        for f in sp["flows"]:
            for ident, ps in f["problems"].items():
                add("state_flow", ident, f"{ident} は{'・'.join(STATE_PROBLEMS[p] for p in ps)}（{f['group']} の遷移）。"
                    "初め・目的達成・外の状態なら attrs.mark で印を付ける", problems=ps)
        for d in sp["definitions"]:
            if d["problems"]:
                add("state_undefined", d["id"], f"{d['id']}: {'／'.join(d['problems'])}", problems=d["problems"])
            if d["dont_care"] and not d["issues"]:
                add("state_dont_care", d["id"], f"{d['id']} は {', '.join(d['dont_care'])} の状態を決めていない（どちらでもよい）。"
                    f"未決事項として課題に載せる（課題 → about → {d['id']}）", components=d["dont_care"])
        if sp["active"] and not sp["enumerated"]:
            add("state_gap", "system_state", f"部品の状態の直積 {sp['size']} 通りが数え上げの上限 {sp['limit']} を超えるので、"
                "網羅の検査をしていない", count=None, examples=[])
        if sp["gaps"]:
            ex = sp["gaps"][:STATE_EXAMPLES]
            add("state_gap", "system_state", f"{len(sp['gaps'])} 通りがどのシステム状態にも禁止にも当たらない"
                f"（例: {', '.join('∧'.join(g) for g in ex)}）。状態の定義に当てるか、理由を付けて禁止にする",
                count=len(sp["gaps"]), examples=ex)
        if sp["overlaps"]:
            by: dict[tuple[str, ...], list[list[str]]] = {}
            for o in sp["overlaps"]:
                by.setdefault(tuple(o["by"]), []).append(o["states"])
            parts = [f"{'・'.join(k)}（{len(v)} 通り。例 {'∧'.join(v[0])}）" for k, v in list(by.items())[:STATE_EXAMPLES]]
            add("state_overlap", "system_state", f"{len(sp['overlaps'])} 通りが 2 つ以上の定義に当たる: {', '.join(parts)}",
                count=len(sp["overlaps"]), examples=sp["overlaps"][:STATE_EXAMPLES])

    def _check_views(self, add: Callable[..., None]) -> None:
        v = self.views()
        for vp in v["missing"]:
            add("view_missing", f"view:{vp}", f"{VIEW_LABEL[vp]}のモデルが無い（attrs.viewpoint={vp} のモデル MO を作り、"
                "shows で要素を載せる）", viewpoint=vp)
        view_of = {e["id"]: e["view"] for e in v["elements"]}
        for ident in v["unviewed"]:
            add("no_view", ident, f"{ident} はどのビューのモデルにも載っていない（{VIEW_LABEL[view_of[ident]]}のモデルに載せる）")
        for m in v["models"]:
            if m["mixed"]:
                vp = m["viewpoint"]
                kinds = "・".join(f"{k}（{', '.join(ids)}）" for k, ids in m["kinds"].items())
                add("mixed_kinds", m["id"], f"{m['id']}（{VIEW_LABEL.get(vp or '', vp or '視点なし')}）に要素の種類が "
                    f"{len(m['kinds'])} つ: {kinds}。図を分ける（議論中のホワイトボードなら attrs.whiteboard=true）",
                    kinds=list(m["kinds"]))

    # ------------------------------------------------ Skill の観点の表（規則が使い、入口が読む）

    def _alive_nodes(self, kind: str | None = None) -> list[dict]:
        return [n for n in sorted(self.nodes.values(), key=lambda n: natkey(n["id"]))
                if n["state"] in ALIVE and (kind is None or n["kind"] == kind)]

    def _title(self, ident: str) -> str:
        e = self._entity(ident)
        return e.get("title") or self._link_text(e)

    def budgets(self) -> list[dict]:
        """予算表（区間目標の予算配分）。目標値（attrs.target）か、予算（attrs.budget）つきの割り付けを持つ
        生きた要素ごとに 1 表。予算は十進で足す。数でない予算・単位が目標と違う予算は合計に入れず problem に出す。"""
        out = []
        for n in self._alive_nodes():
            a = n["attrs"]
            allocs = self.links_from(n["id"], "allocates")
            if "target" not in a and not any("budget" in l["attrs"] for l in allocs):
                continue
            unit = a["unit"].strip() if isinstance(a.get("unit"), str) and a["unit"].strip() else None
            items = []
            total = Decimal(0)
            for l in allocs:
                la = l["attrs"]
                b = la.get("budget")
                bu = la["unit"].strip() if isinstance(la.get("unit"), str) and la["unit"].strip() else None
                problem: str | None = None
                if "budget" not in la:
                    problem = "no_budget"
                elif not _is_number(b):
                    problem = "not_number"
                elif unit and bu and bu != unit:
                    problem = "unit"
                else:
                    total += _dec(b)
                items.append({"link": l["id"], "to": l["dst"], "to_title": self._title(l["dst"]), "budget": b,
                              "unit": bu, "basis": la.get("basis"), "state": l["state"], "problem": problem})
            target = a.get("target")
            row: dict[str, Any] = {"id": n["id"], "kind": n["kind"], "title": n["title"], "state": n["state"],
                                   "target": target, "unit": unit, "items": items, "total": _num(total), "over": False,
                                   "excess": None, "remaining": None, "problem": None}
            if _is_number(target):
                diff = total - _dec(target)
                row["over"] = diff > 0
                row["excess" if diff > 0 else "remaining"] = _num(abs(diff))
            else:
                row["problem"] = "no_target" if "target" not in a else "target_not_number"
            out.append(row)
        return out

    def coupling(self) -> dict:
        """括りと結合の数の表（括りと結合上限）。数は案を比べる材料。検出に使うのは上限（attrs.max_coupling）を宣言した括りだけ。
        結合は生きた relation の両端の組（同じ組に述語が 2 つあっても 1 つ）。括りの中身は --parent の親子を辿った構造の要素。"""
        alive = {n["id"]: n for n in self._alive_nodes()}
        children: dict[str, list[str]] = {}
        for n in alive.values():
            p = n.get("parent")
            if isinstance(p, str) and p in alive and n["kind"] in STRUCTURE_KINDS:
                children.setdefault(p, []).append(n["id"])
        pairs = sorted({tuple(sorted((l["src"], l["dst"]), key=natkey)) for l in self.links.values()
                        if l["kind"] == "relation" and l["state"] in ALIVE and l["src"] in alive and l["dst"] in alive})

        def inside(root: str) -> set[str]:
            seen, q = {root}, deque([root])
            while q:
                for c in children.get(q.popleft(), []):
                    if c not in seen:
                        seen.add(c)
                        q.append(c)
            return seen

        def count(members: set[str]) -> tuple[int, int]:
            return (sum(1 for a, b in pairs if a in members and b in members),
                    sum(1 for a, b in pairs if (a in members) != (b in members)))

        structure = {i for i, n in alive.items() if n["kind"] in STRUCTURE_KINDS}
        internal, external = count(structure)
        groups = []
        for ident, node in alive.items():
            declared = "max_coupling" in node["attrs"]
            if not declared and not (node["kind"] in COUPLING_GROUP_KINDS and ident in children):
                continue
            members = inside(ident)
            gi, ge = count(members)
            lim = node["attrs"].get("max_coupling")
            valid = isinstance(lim, int) and not isinstance(lim, bool) and lim >= 0
            groups.append({"id": ident, "kind": node["kind"], "title": node["title"],
                           "children": len(children.get(ident, [])), "elements": len(members) - 1,
                           "internal": gi, "external": ge, "max_coupling": lim if declared else None,
                           "limit_valid": valid if declared else None, "over": bool(declared and valid and ge > lim)})
        n_all = len(structure)
        return {"elements": n_all, "couplings": internal, "external": external, "max_pairs": n_all * (n_all - 1) // 2,
                "sqrt_n": round(math.sqrt(n_all), 2), "groups": groups}

    def state_space(self) -> dict:
        """状態の三段導出の表。第 3 段（SS の attrs.of による部品の状態の組合せ）の網羅漏れ・重複・「どちらでもよい」と、
        各段の遷移（transitions）の供給元・行き止まり・到達性。of で指さない部品は「どちらでもよい」（どの状態にも当たる）。"""
        cs_alive = {n["id"]: n for n in self._alive_nodes("component_state")
                    if self._alive(n.get("parent") or "") and self.nodes[n["parent"]]["kind"] == "component"}
        defs = []
        for s in self._alive_nodes("system_state"):
            a = s["attrs"]
            of = a.get("of")
            refs = [] if _empty(of) else (list(of) if isinstance(of, list) else [of])
            spec: dict[str, str] = {}
            problems: list[str] = []
            if not refs:
                problems.append("組合せ（attrs.of=[CS…]）が無い")
            for c in refs:
                if not isinstance(c, str) or c not in cs_alive:
                    problems.append(f"{c!r} は生きた論理コンポーネントの状態（CS）ではない")
                    continue
                lc = cs_alive[c]["parent"]
                if lc in spec and spec[lc] != c:
                    problems.append(f"{lc} の状態を 2 つ指している（{spec[lc]}・{c}）")
                else:
                    spec[lc] = c
            valid = not problems
            forbidden = bool(a.get("forbidden"))
            if forbidden and _empty(a.get("reason")):
                problems.append("禁止の理由（attrs.reason）が無い")
            defs.append({"id": s["id"], "title": s["title"], "forbidden": forbidden, "reason": a.get("reason"),
                         "of": refs, "spec": dict(sorted(spec.items(), key=lambda kv: natkey(kv[0]))), "valid": valid,
                         "problems": problems, "dont_care": [], "issues": []})
        usable = [d for d in defs if d["valid"]]
        comps = sorted({lc for d in usable for lc in d["spec"]}, key=natkey)
        states = {lc: [c for c in sorted(cs_alive, key=natkey) if cs_alive[c]["parent"] == lc] for lc in comps}
        size = math.prod(len(states[lc]) for lc in comps) if comps else 0
        about: dict[str, set[str]] = {}
        for l in self.links.values():
            if l["kind"] == "about" and l["state"] in ALIVE and self._alive(l["src"]) and \
                    self.nodes.get(l["src"], {}).get("kind") == "issue":
                about.setdefault(l["dst"], set()).add(l["src"])
        for d in usable:
            if not d["forbidden"]:
                d["dont_care"] = [lc for lc in comps if lc not in d["spec"]]
                d["issues"] = sorted(about.get(d["id"], set()), key=natkey)
        active = bool(usable)
        enumerated = active and size <= STATE_PRODUCT_LIMIT
        gaps: list[list[str]] = []
        overlaps: list[dict] = []
        if enumerated:
            idx = {lc: i for i, lc in enumerate(comps)}
            for combo in itertools.product(*(states[lc] for lc in comps)):
                hits = [d for d in usable if all(combo[idx[lc]] == c for lc, c in d["spec"].items())]
                allowed = [d for d in hits if not d["forbidden"]]
                if not hits:
                    gaps.append(list(combo))
                elif len(allowed) >= 2 or (allowed and len(allowed) < len(hits)):  # 禁止どうしの重なりは問わない
                    overlaps.append({"states": list(combo), "by": [d["id"] for d in hits]})
        groups: dict[str, list[str]] = {"world_state": [n["id"] for n in self._alive_nodes("world_state")],
                                        "system_state": [d["id"] for d in defs if not d["forbidden"]]}
        for lc in sorted({n["parent"] for n in cs_alive.values()}, key=natkey):
            groups[f"component_state:{lc}"] = [c for c in sorted(cs_alive, key=natkey) if cs_alive[c]["parent"] == lc]
        trans = [l for l in sorted(self.links.values(), key=lambda l: natkey(l["id"]))
                 if l["kind"] == "transitions" and l["state"] in ALIVE]
        flows = []
        for key, members in groups.items():
            mem = set(members)
            edges = [(l["src"], l["dst"]) for l in trans if l["src"] in mem and l["dst"] in mem]
            if not edges:  # 遷移を描いていない段は見ない
                continue
            inc = {d for s, d in edges if s != d}
            outg = {s for s, d in edges if s != d}
            marks = {m: _aliases(self.nodes[m]["attrs"].get("mark"), STATE_MARKS) for m in members}
            initial = [m for m in members if "initial" in marks[m]]
            reach: set[str] = set()
            if initial:
                adj: dict[str, list[str]] = {}
                for s, d in edges:
                    adj.setdefault(s, []).append(d)
                start = [m for m in members if marks[m] & {"initial", "external"}]
                reach, q = set(start), deque(start)
                while q:
                    for nx in adj.get(q.popleft(), []):
                        if nx not in reach:
                            reach.add(nx)
                            q.append(nx)
            problems_of: dict[str, list[str]] = {}
            for m in members:
                ps = []
                if not marks[m] & {"initial", "external"}:
                    if m not in inc:
                        ps.append("no_source")
                    elif initial and m not in reach:
                        ps.append("unreachable")
                if m not in outg and not marks[m] & {"goal", "external"}:
                    ps.append("dead_end")
                if ps:
                    problems_of[m] = ps
            flows.append({"group": key, "states": members, "transitions": len(edges), "initial": initial,
                          "problems": problems_of})
        return {"active": active, "size": size, "limit": STATE_PRODUCT_LIMIT, "enumerated": enumerated,
                "components": [{"id": lc, "title": self.nodes[lc]["title"], "states": states[lc]} for lc in comps],
                "unused_states": sorted((c for c in cs_alive if cs_alive[c]["parent"] not in states), key=natkey),
                "definitions": defs, "gaps": gaps, "overlaps": overlaps, "flows": flows}

    def views(self) -> dict:
        """三つの基本ビューの表。モデル（MO・1 枚の図）を attrs.viewpoint でビューに束ね、shows で載せた要素を数える。
        モデルが 1 枚も無いあいだは検査しない（active=False）。視点の無いモデルはどのビューにも属さない。"""
        models = []
        on: dict[str, list[str]] = {}
        present: set[str] = set()
        for m in self._alive_nodes("model"):
            a = m["attrs"]
            vp = _viewpoint(a.get("viewpoint"))
            kinds: dict[str, list[str]] = {}
            els = []
            for l in self.links_from(m["id"], "shows"):
                e = self.nodes[l["dst"]]
                els.append(e["id"])
                st = e["attrs"].get("stereotype")
                kinds.setdefault(st.strip() if isinstance(st, str) and st.strip() else e["kind"], []).append(e["id"])
                if vp is not None:
                    on.setdefault(e["id"], []).append(m["id"])
            if vp in VIEWPOINTS:
                present.add(vp)
            allowed = 2 if vp == "allocation" else 1  # 割り付けの図だけは 2 種類を許す
            whiteboard = bool(a.get("whiteboard"))
            models.append({"id": m["id"], "title": m["title"], "viewpoint": vp, "basic": vp in VIEWPOINTS,
                           "elements": els, "kinds": dict(sorted(kinds.items())), "allowed": allowed,
                           "whiteboard": whiteboard, "mixed": len(kinds) > allowed and not whiteboard})
        active = bool(models)
        elements = [{"id": n["id"], "kind": n["kind"], "title": n["title"], "view": VIEW_OF_KIND[n["kind"]],
                     "models": on.get(n["id"], [])} for n in self._alive_nodes() if n["kind"] in VIEW_OF_KIND]
        return {"active": active, "present": [vp for vp in VIEWPOINTS if vp in present],
                "missing": [vp for vp in VIEWPOINTS if vp not in present] if active else [],
                "models": models, "elements": elements,
                "unviewed": [e["id"] for e in elements if not e["models"] and e["view"] in present]}

    def tradeoffs(self) -> list[dict]:
        """決断ごとの「捨てたもの」: 採用した案とその代償（cons）、却下した案、採用した案と案どうしの関係
        （排他・衝突・相乗・関係）、決定点の上流の関心事。未決の決定点は入れない（まだ何も捨てていない）。"""
        rows = []
        for d in self._alive_nodes("decision_point"):
            dec = d.get("decision")
            if not dec or dec["option"] not in self.nodes:
                continue
            oid = dec["option"]
            o = self.nodes[oid]
            rels = []
            for l in sorted(self.links.values(), key=lambda l: natkey(l["id"])):
                if l["kind"] not in SOFT_RELATIONS or l["state"] not in ALIVE or oid not in (l["src"], l["dst"]):
                    continue
                other = l["dst"] if l["src"] == oid else l["src"]
                on = self.nodes.get(other) or {}
                rels.append({"link": l["id"], "kind": l["kind"], "other": other, "other_title": on.get("title", ""),
                             "other_state": on.get("state"), "other_adopted": self._adopted(other)})
            rejected = [{"id": s["id"], "title": s["title"], "state": s["state"], "viewpoint": s["attrs"].get("viewpoint"),
                         "cons": _cons_list(s["attrs"].get("cons"))} for s in self._options(d["id"]) if s["id"] != oid]
            oa = o["attrs"]
            rows.append({"dp": d["id"], "title": d["title"], "conditions": list(dec.get("conditions") or []),
                         "adopted": {"id": oid, "title": o["title"], "state": o["state"], "viewpoint": oa.get("viewpoint"),
                                     "cons": _cons_list(oa.get("cons")), "must": oa.get("must"),
                                     "must_not": oa.get("must_not")},
                         "rejected": rejected, "relations": rels,
                         "concerns": [r["id"] for r in self.why(d["id"]) if r["kind"] == "concern"]})
        return rows

    # ------------------------------------------------ 状況

    def status(self) -> dict:
        counts: dict[str, dict[str, int]] = {}
        for n in self.nodes.values():
            counts.setdefault(n["kind"], {}).setdefault(n["state"], 0)
            counts[n["kind"]][n["state"]] += 1
        undecided = [n["id"] for n in self.find("decision_point") if n["state"] in ALIVE and not n.get("decision")]
        open_, deferred, accepted = [], [], []
        for n in self.nodes.values():
            if n["kind"] not in CLOSABLE or n["state"] not in ALIVE:
                continue
            c = (n.get("closure") or {}).get("as", "open")
            {"open": open_, "deferred": deferred, "accepted": accepted}.get(c, []).append(n["id"])
        findings = [f for f in self.check() if f["level"] != "info"]
        rc = self.recheck()
        drivers = [n["id"] for n in self.find("concern") if n["state"] in ALIVE and n["attrs"].get("weight") == 5]
        return {"last_seq": self.last_seq, "backend": self.backend,
                "counts": {k: dict(sorted(v.items())) for k, v in sorted(counts.items(), key=lambda kv: list(KINDS).index(kv[0]))},
                "undecided": undecided, "recheck": len(rc), "open_issues": sorted(open_, key=natkey),
                "deferred": sorted(deferred, key=natkey), "accepted": sorted(accepted, key=natkey),
                "findings": len(findings), "drivers": drivers,
                "done": not undecided and not rc and not open_ and not findings}

    # ------------------------------------------------ 書き出し

    def label(self, ident: str) -> str:
        e = self._entity(ident)
        if ident in self.links:
            return f"{ident} {self._link_text(e)} [{STATE_LABEL[e['state']]}]"
        return f"{ident} [{STATE_LABEL[e['state']]}] {KINDS[e['kind']][1]}: {e['title']}"

    @staticmethod
    def _link_text(l: dict) -> str:
        verb = l.get("predicate") or l["kind"]
        return f"{l['src']} —{verb}→ {l['dst']}"

    def export_markdown(self) -> str:
        """決定性の Markdown。同じイベント列からは同じ文字列になる（保存形式・置き場所・時刻に依らない）。"""
        L: list[str] = []
        st = self.status()
        L.append("<!-- 生成物。手で直さない。直すときは生成の元（設計の因果 DB のイベント列）を直して再生成する -->")
        L.append("# 設計の因果 DB（生成物。手で直さない）")
        L.append("")
        L.append(f"- 生成の元: {TOOL} のイベント列（seq 1〜{self.last_seq}）")
        L.append("- [仮説] は未検証。確定と同じ顔で読まない。未決は推測で埋めない")
        L.append("")
        L.append("## 未決（推測で埋めないこと）")
        L.append("")
        L.append("### 未決の決定点")
        for d in st["undecided"]:
            opts = [o["id"] for o in self._options(d) if o["state"] in ALIVE]
            L.append(f"- open: {self.label(d)}（案: {', '.join(opts) or 'なし'}）")
        if not st["undecided"]:
            L.append("- なし")
        L.append("")
        L.append("### 未解決の課題・リスク")
        for i in st["open_issues"]:
            L.append(f"- open: {self.label(i)}")
        for i in st["deferred"]:
            c = self.nodes[i]["closure"]
            L.append(f"- 保留: {self.label(i)}（再開の条件: {c.get('resume_if') or '未記入'}）")
        if not st["open_issues"] and not st["deferred"]:
            L.append("- なし")
        L.append("")
        L.append("### 要再確認（仕分け待ち）")
        for m in self.recheck():
            L.append(f"- {m['link']}: {m['downstream']} ← {m['upstream']}（{m['kind']}・見た版 v{m['seen']} → いま v{m['current']}）")
        if not st["recheck"]:
            L.append("- なし")
        L.append("")
        L.append("### 検出（check）")
        fs = self.check()
        for f in fs:
            L.append(f"- [{f['rule']}] {f['message']}（→ {f['skill']}）")
        if not fs:
            L.append("- なし")
        L.append("")
        L.append("## 決断の一覧")
        L.append("")
        decided = [n for n in self.find("decision_point") if n.get("decision")]
        for d in decided:
            dec = d["decision"]
            o = self.nodes[dec["option"]]
            a = o["attrs"]
            L.append(f"### {self.label(d['id'])}")
            L.append(f"- 採用: {self.label(o['id'])}")
            L.append(f"- must: {_render(a.get('must'))}")
            L.append(f"- must_not: {_render(a.get('must_not'))}")
            L.append(f"- 背景事情: {_render(dec.get('conditions'))}")
            L.append(f"- 根拠: {', '.join(self.evidence_of(d['id'])) or 'なし'}")
            L.append(f"- 検証: {_render(a.get('verification'))}")
            L.append("")
        if not decided:
            L.append("- なし")
            L.append("")
        L.append("## 要素（種類ごと）")
        L.append("")
        for kind, (prefix, label) in KINDS.items():
            items = self.find(kind)
            if not items:
                continue
            L.append(f"### {label}（{prefix or 'D〈n〉-〈A〉'}）")
            for n in items:
                extra = []
                if n.get("parent"):
                    extra.append(f"親: {n['parent']}")
                ev = self.evidence_of(n["id"])
                if ev:
                    extra.append(f"根拠: {', '.join(ev)}")
                if kind == "concern":
                    srcs = sorted({l["dst"] for l in self.links.values()
                                   if l["kind"] == "source" and l["src"] == n["id"] and l["state"] in ALIVE}, key=natkey)
                    extra.append(f"出所: {', '.join(srcs) or 'なし'}")
                if n.get("closure"):
                    extra.append(f"閉じ方: {CLOSURE_LABEL[n['closure']['as']]}")
                L.append(f"- {self.label(n['id'])}（v{n['version']}{'・' + '・'.join(extra) if extra else ''}）")
                for k in sorted(n["attrs"]):
                    L.append(f"  - {k}: {_render(n['attrs'][k])}")
                for note in n.get("notes", []):
                    L.append(f"  - 注記（seq {note['seq']}・{note['actor']}）: {note['text']}")
            L.append("")
        rels = [l for l in self.links.values() if l["kind"] == "relation"]
        L.append("## 関連（主語—述語—目的語）")
        L.append("")
        for l in sorted(rels, key=lambda l: natkey(l["id"])):
            L.append(f"- {l['src']} —{l.get('predicate') or '（述語なし）'}→ {l['dst']}（{l['id']}・{STATE_LABEL[l['state']]}）")
        if not rels:
            L.append("- なし")
        L.append("")
        L.append("## 因果・根拠・案どうしのリンク")
        L.append("")
        others = [l for l in self.links.values() if l["kind"] != "relation"]
        for l in sorted(others, key=lambda l: natkey(l["id"])):
            L.append(f"- {l['src']} —{l['kind']}→ {l['dst']}（{l['id']}・{STATE_LABEL[l['state']]}）")
        if not others:
            L.append("- なし")
        L.append("")
        return "\n".join(L)


def _render(v: Any) -> str:
    if _empty(v):
        return "なし"
    if isinstance(v, str):
        return v
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return "／".join(v)
    return _dumps(v)


# ---------------------------------------------------------------- CLI

def _out(args: argparse.Namespace, data: Any, text: str | Iterable[str]) -> None:
    if args.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print(text if isinstance(text, str) else "\n".join(text))


def _attrs_from(args: argparse.Namespace) -> dict:
    attrs: dict[str, Any] = {}
    if getattr(args, "attrs_json", None):
        v = parse_value(args.attrs_json)
        if not isinstance(v, dict):
            raise DesignGraphError("--attrs-json はオブジェクト（{...}）")
        attrs.update(v)
    attrs.update(dict(parse_pairs(getattr(args, "attr", None))))
    return attrs


def _tree_text(g: DesignGraph, rows: list[dict], arrow: str) -> list[str]:
    out = []
    for r in rows:
        pad = "  " * r["depth"]
        head = "" if r["depth"] == 0 else f"{arrow} {r['via']}{(' ' + r['link']) if r['link'] and r['via'] != 'ends' else ''} {arrow} "
        ev = f"  根拠: {', '.join(r['evidence'])}" if r["evidence"] else ("  根拠: なし" if not r["kind"].startswith("link:") else "")
        mark = "  ⚠要再確認" if r["stale"] else ""
        out.append(f"{pad}{head}{g.label(r['id'])}{ev}{mark}")
    return out


def cmd_init(g: DesignGraph, args: argparse.Namespace) -> int:
    g.init()
    _out(args, {"db": str(g.path), "backend": g.backend, "last_seq": g.last_seq}, f"{g.backend}: {g.path}（seq {g.last_seq}）")
    return 0


def cmd_add(g: DesignGraph, args: argparse.Namespace) -> int:
    ident = g.add(args.kind, args.title, _attrs_from(args), args.parent, args.state, args.evidence or [])
    _out(args, {"id": ident}, ident)
    return 0


def cmd_update(g: DesignGraph, args: argparse.Namespace) -> int:
    ver = g.update(args.id, args.title, _attrs_from(args), args.unset or [],
                   parse_pairs(args.append, "--append"), args.predicate)
    _out(args, {"id": args.id, "version": ver}, f"{args.id} v{ver}")
    return 0


def cmd_link(g: DesignGraph, args: argparse.Namespace) -> int:
    ident = g.link(args.kind, args.src, args.dst, args.predicate, _attrs_from(args), args.state)
    if args.kind == "relation" and not args.predicate and not args.json:
        print(f"注意: {ident} に述語が無い（check の no_predicate に出る）", file=sys.stderr)
    _out(args, {"id": ident}, ident)
    return 0


def cmd_state(g: DesignGraph, args: argparse.Namespace) -> int:
    g.set_state(args.id, args.state, args.evidence or [], args.reason)
    _out(args, {"id": args.id, "state": g.get(args.id)["state"]}, g.label(args.id))
    return 0


def cmd_decide(g: DesignGraph, args: argparse.Namespace) -> int:
    g.decide(args.dp, args.option, args.evidence or [], args.condition or [], args.reason)
    _out(args, {"dp": args.dp, "option": args.option}, f"{args.dp} → {args.option}")
    return 0


def cmd_close(g: DesignGraph, args: argparse.Namespace) -> int:
    g.close(args.id, args.closure, args.evidence or [], args.reopen_if, args.resume_if, args.reason)
    _out(args, {"id": args.id, "as": args.closure}, f"{args.id}: {CLOSURE_LABEL[args.closure]}")
    return 0


def cmd_triage(g: DesignGraph, args: argparse.Namespace) -> int:
    issue = g.triage(args.link, "issue" if args.issue is not None else "ok", args.issue, args.note)
    _out(args, {"link": args.link, "issue": issue}, f"{args.link}: {'課題 ' + issue if issue else '問題なし'}")
    return 0


def cmd_waive(g: DesignGraph, args: argparse.Namespace) -> int:
    g.waive(args.finding, args.reason)
    _out(args, {"finding": args.finding}, f"見送り: {args.finding}")
    return 0


def cmd_annotate(g: DesignGraph, args: argparse.Namespace) -> int:
    g.annotate(args.id, args.text)
    _out(args, {"id": args.id}, f"注記: {args.id}")
    return 0


def cmd_show(g: DesignGraph, args: argparse.Namespace) -> int:
    e = g.get(args.id)
    outs = [l for l in g.links.values() if l["src"] == args.id]
    ins = [l for l in g.links.values() if l["dst"] == args.id]
    hist = g.history.get(args.id, [])
    data = {**e, "out": sorted((l["id"] for l in outs), key=natkey), "in": sorted((l["id"] for l in ins), key=natkey),
            "history": hist}
    lines = [f"{g.label(args.id)}（v{e['version']}）"]
    if e.get("parent"):
        lines.append(f"  親: {e['parent']}")
    for k in sorted(e["attrs"]):
        lines.append(f"  {k}: {_render(e['attrs'][k])}")
    if e.get("decision"):
        d = e["decision"]
        lines.append(f"  決断: {d['option']}（背景事情: {_render(d.get('conditions'))}）")
    if e.get("closure"):
        lines.append(f"  閉じ方: {CLOSURE_LABEL[e['closure']['as']]}")
    for title, ls, side in (("出ていくリンク", outs, "dst"), ("入ってくるリンク", ins, "src")):
        if ls:
            lines.append(f"  {title}:")
            for l in sorted(ls, key=lambda l: natkey(l["id"])):
                lines.append(f"    {g.label(l['id'])}  相手: {g.label(l[side])}")
    for n in e.get("notes", []):
        lines.append(f"  注記（seq {n['seq']}・{n['actor']}）: {n['text']}")
    lines.append("  履歴: " + "、".join(f"seq {h['seq']} {h['op']}（{h['actor']}）" for h in hist))
    _out(args, data, lines)
    return 0


def cmd_list(g: DesignGraph, args: argparse.Namespace) -> int:
    rows = g.find(args.kind, args.state)
    _out(args, rows, [g.label(n["id"]) for n in rows] or ["（なし）"])
    return 0


def cmd_why(g: DesignGraph, args: argparse.Namespace) -> int:
    rows = g.why(args.id, args.depth)
    _out(args, rows, _tree_text(g, rows, "←"))
    return 0


def cmd_impact(g: DesignGraph, args: argparse.Namespace) -> int:
    rows = g.impact(args.id, args.depth)
    _out(args, rows, _tree_text(g, rows, "→"))
    return 0


def cmd_recheck(g: DesignGraph, args: argparse.Namespace) -> int:
    rows = g.recheck()
    _out(args, rows, [f"{m['link']}: {m['downstream']} ← {m['upstream']}（{m['kind']}・見た版 v{m['seen']} → いま v{m['current']}）"
                      for m in rows] or ["要再確認なし"])
    return 0


def cmd_check(g: DesignGraph, args: argparse.Namespace) -> int:
    rows = g.check(include_waived=args.all)
    lines = [f"{'(見送り) ' if f['waived'] else ''}[{f['id']}] {f['message']}（→ {f['skill']}）" for f in rows]
    _out(args, rows, lines or ["検出なし"])
    return 1 if any(f["level"] != "info" and not f["waived"] for f in rows) else 0


def cmd_status(g: DesignGraph, args: argparse.Namespace) -> int:
    s = g.status()
    lines = [f"イベント: seq {s['last_seq']}（{s['backend']}）"]
    for kind, by in s["counts"].items():
        lines.append(f"  {KINDS[kind][1]}: " + "・".join(f"{STATE_LABEL[k]} {v}" for k, v in by.items()))
    lines.append(f"未決の決定点: {len(s['undecided'])}{' — ' + ', '.join(s['undecided']) if s['undecided'] else ''}")
    lines.append(f"要再確認（仕分け待ち）: {s['recheck']}")
    lines.append(f"未解決の課題・リスク: {len(s['open_issues'])}{' — ' + ', '.join(s['open_issues']) if s['open_issues'] else ''}")
    lines.append(f"保留: {len(s['deferred'])} ／ 受容: {len(s['accepted'])}")
    lines.append(f"検出: {s['findings']}（check で一覧）")
    lines.append(f"ドライバー（重み 5 の関心事）: {', '.join(s['drivers']) or 'なし'}")
    lines.append(f"完了の条件: {'満たす' if s['done'] else '未達'}")
    _out(args, s, lines)
    return 0


def cmd_export(g: DesignGraph, args: argparse.Namespace) -> int:
    md = g.export_markdown()
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="\n") as f:
            f.write(md)
        _out(args, {"out": str(p)}, f"書き出した: {p}")
    else:
        _out(args, {"markdown": md}, md)
    return 0


def cmd_convert(g: DesignGraph, args: argparse.Namespace) -> int:
    b, p = g.convert(args.to, args.to_backend)
    _out(args, {"backend": b, "db": str(p), "events": g.last_seq}, f"{g.backend} → {b}: {p}（seq {g.last_seq}）")
    return 0


def cmd_kinds(g: DesignGraph | None, args: argparse.Namespace) -> int:
    data = {"kinds": {k: {"prefix": p, "label": lb} for k, (p, lb) in KINDS.items()},
            "links": {k: {"upstream": u, "causal": c, "label": lb} for k, (u, c, lb) in LINK_KINDS.items()},
            "rules": {r: {"label": lb, "skill": s, "level": lv} for r, (lb, s, lv) in RULES.items()}}
    lines = ["要素の種類（kind 接頭辞 表示）:"]
    lines += [f"  {k:15} {p or 'D〈n〉-〈A〉':10} {lb}" for k, (p, lb) in KINDS.items()]
    lines.append("リンクの種類（kind 上流の端 鎖 表示）:")
    lines += [f"  {k:10} {u or '-':4} {'鎖' if c else '  '} {lb}" for k, (u, c, lb) in LINK_KINDS.items()]
    lines.append("検出の規則（rule 表示 → Skill）:")
    lines += [f"  {r:18} {lb} → {s}{'（情報）' if lv == 'info' else ''}" for r, (lb, s, lv) in RULES.items()]
    _out(args, data, lines)
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=argparse.SUPPRESS, help="DB の置き場（既定 .pair-agent/design/graph.jsonl）")
    common.add_argument("--backend", choices=list(DEFAULT_DB), default=argparse.SUPPRESS,
                        help="json（既定）か sqlite。省くと --db の拡張子で決める")
    common.add_argument("--actor", choices=list(ACTORS), default=argparse.SUPPRESS, help="ai（既定・仮説だけ）か human")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="機械向けの JSON で出す")

    p = argparse.ArgumentParser(prog="design_graph.py", parents=[common],
                                description="設計の因果 DB（追記だけのイベント列。JSONL か SQLite）",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def sp(name: str, func: Callable, help_: str) -> argparse.ArgumentParser:
        s = sub.add_parser(name, parents=[common], help=help_, description=help_)
        s.set_defaults(func=func)
        return s

    def attr_opts(s: argparse.ArgumentParser) -> None:
        s.add_argument("--attr", action="append", metavar="K=V", help="属性（値は JSON として読めれば JSON）。繰り返せる")
        s.add_argument("--attrs-json", metavar="JSON", help="属性をまとめて（JSON のオブジェクト）")

    sp("init", cmd_init, "空の DB を作る")
    s = sp("add", cmd_add, "要素を足す")
    s.add_argument("kind", choices=list(KINDS))
    s.add_argument("title")
    s.add_argument("--parent")
    s.add_argument("--state", choices=["hypothesis", "confirmed"], default="hypothesis")
    s.add_argument("--evidence", action="append", metavar="NT", help="根拠の設計ノート【人】")
    attr_opts(s)
    s = sp("update", cmd_update, "中身を直す（版が上がる）")
    s.add_argument("id")
    s.add_argument("--title")
    s.add_argument("--predicate")
    s.add_argument("--append", action="append", metavar="K=V", help="配列の属性に足す")
    s.add_argument("--unset", action="append", metavar="K")
    attr_opts(s)
    s = sp("link", cmd_link, "リンクを張る")
    s.add_argument("kind", choices=list(LINK_KINDS))
    s.add_argument("src")
    s.add_argument("dst")
    s.add_argument("--predicate")
    s.add_argument("--state", choices=["hypothesis", "confirmed"])
    attr_opts(s)
    s = sp("state", cmd_state, "状態を変える【人】")
    s.add_argument("id")
    s.add_argument("state", choices=list(STATES))
    s.add_argument("--evidence", action="append", metavar="NT")
    s.add_argument("--reason")
    s = sp("decide", cmd_decide, "決断する【人】")
    s.add_argument("dp")
    s.add_argument("option")
    s.add_argument("--evidence", action="append", metavar="NT")
    s.add_argument("--condition", action="append", metavar="TEXT", help="背景事情（成り立つ条件）。繰り返せる")
    s.add_argument("--reason")
    s = sp("close", cmd_close, "課題・リスクを閉じる【人】")
    s.add_argument("id")
    s.add_argument("--as", dest="closure", required=True, choices=list(CLOSURES))
    s.add_argument("--evidence", action="append", metavar="NT")
    s.add_argument("--reopen-if")
    s.add_argument("--resume-if")
    s.add_argument("--reason")
    s = sp("triage", cmd_triage, "要再確認を仕分ける【人】")
    s.add_argument("link")
    grp = s.add_mutually_exclusive_group(required=True)
    grp.add_argument("--ok", action="store_true", help="問題なし（見た上流の版を記録）")
    grp.add_argument("--issue", metavar="TITLE", help="課題にする（課題の題）")
    s.add_argument("--note")
    s = sp("waive", cmd_waive, "検出を見送る【人】")
    s.add_argument("finding")
    s.add_argument("--reason", required=True)
    s = sp("annotate", cmd_annotate, "注記を足す")
    s.add_argument("id")
    s.add_argument("text")
    s = sp("show", cmd_show, "1 件の詳細")
    s.add_argument("id")
    s = sp("list", cmd_list, "一覧")
    s.add_argument("--kind", choices=list(KINDS))
    s.add_argument("--state", choices=list(STATES))
    s = sp("why", cmd_why, "上流へ辿る（各段の根拠つき）")
    s.add_argument("id")
    s.add_argument("--depth", type=int)
    s = sp("impact", cmd_impact, "下流へ辿る")
    s.add_argument("id")
    s.add_argument("--depth", type=int)
    sp("recheck", cmd_recheck, "要再確認の一覧")
    s = sp("check", cmd_check, "検出")
    s.add_argument("--all", action="store_true", help="見送った検出も出す")
    sp("status", cmd_status, "状況")
    s = sp("export", cmd_export, "Markdown に書き出す")
    s.add_argument("--out")
    s = sp("convert", cmd_convert, "別の保存形式へ写す")
    s.add_argument("--to", required=True)
    s.add_argument("--to-backend", choices=list(DEFAULT_DB))
    sp("kinds", cmd_kinds, "種類・リンク・規則の一覧")
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    for k, v in (("db", None), ("backend", None), ("actor", "ai"), ("json", False)):
        if not hasattr(args, k):
            setattr(args, k, v)
    try:
        if args.func is cmd_kinds:  # DB を読まない（壊れた DB があっても一覧は出す）
            return cmd_kinds(None, args)
        g = DesignGraph(args.db, args.backend, args.actor)
        return args.func(g, args)
    except DesignGraphError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

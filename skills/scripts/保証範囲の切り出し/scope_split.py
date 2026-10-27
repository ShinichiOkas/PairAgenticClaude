#!/usr/bin/env python3
"""仕様の項目 ID と設計保証の項目 ID を突き合わせ、過剰（仕様に無い保証）・外形項目の保証・保証も残留リスクも無い項目を出す。

使い方:
  python scope_split.py --spec 仕様.md --assurance 設計保証.md [--external S-1,S-2] [--id-pattern "[A-Z]+-\\d+"]
  --external: 作成者自身が「実行可能物だけで判定できる」と判断した項目（受入検査の仕事）。保証に書かれていたら error。
項目 ID は行頭または表の第 1 列・見出しに現れる ID。設計保証の「残留リスク／保証しなかった」節に書かれた ID は保証ではなく残留リスク扱い。
分類: guaranteed / residual / excess(error: 仕様に無い) / external-guaranteed(error) / uncovered(error: 保証も残留リスクも無い) / external-only
終了コード: 0 / 1=error あり / 2=入力不備
"""
import argparse
import json
import re
import sys
from pathlib import Path

RESIDUAL_HEAD = re.compile(r"残留リスク|保証(し|でき)なかった|保証しない|未保証|確かめ(られ)?なかった")


def item_ids(text, pat, residual_split=False):
    """行頭（箇条書き記号・表の枠・見出し記号の後）に現れる ID を、(通常, 残留) に分けて返す。"""
    rx = re.compile(rf"^\s*(?:[-*]\s*|\|\s*|#{{1,6}}\s*|\[)?\*{{0,2}}\[?({pat})\]?")
    normal, residual, in_res = [], [], False
    for line in text.splitlines():
        h = re.match(r"^#{1,6}\s+(.*)$", line)
        if h:
            in_res = bool(RESIDUAL_HEAD.search(h.group(1)))
        m = rx.match(line)
        if m:
            (residual if (in_res and residual_split) else normal).append(m.group(1))
    return normal, residual


def split(spec_text, assurance_text, external=(), pat=r"[A-Z][A-Za-z]*-\d+"):
    spec, _ = item_ids(spec_text, pat)
    guaranteed, residual = item_ids(assurance_text, pat, residual_split=True)
    spec_s, g_s, r_s, ext = set(spec), set(guaranteed), set(residual), set(external)
    res = {
        "spec_items": sorted(spec_s),
        "guaranteed": sorted(g_s & spec_s - ext),
        "residual": sorted(r_s & spec_s),
        "external_only": sorted(ext & spec_s - g_s),
        "excess": sorted(g_s - spec_s),
        "external_guaranteed": sorted(g_s & ext),
        "uncovered": sorted(spec_s - g_s - r_s - ext),
        "unknown_external": sorted(ext - spec_s),
    }
    res["errors"] = len(res["excess"]) + len(res["external_guaranteed"]) + len(res["uncovered"]) + len(res["unknown_external"])
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--assurance", required=True)
    ap.add_argument("--external", default="", help="外形で検められる項目 ID（カンマ区切り）")
    ap.add_argument("--id-pattern", default=r"[A-Z][A-Za-z]*-\d+")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        spec = Path(a.spec).read_text(encoding="utf-8")
        ass = Path(a.assurance).read_text(encoding="utf-8")
        re.compile(a.id_pattern)
    except (OSError, re.error) as e:
        print(f"入力不備: {e}", file=sys.stderr)
        return 2
    ext = [x.strip() for x in a.external.split(",") if x.strip()]
    res = split(spec, ass, ext, a.id_pattern)
    if not res["spec_items"]:
        print("仕様から項目 ID が読み取れない（--id-pattern を確かめる）", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        labels = [("guaranteed", "保証した"), ("residual", "保証せず残留リスクへ"), ("external_only", "外形（受入検査の仕事）"),
                  ("excess", "ERROR 仕様に無いものを保証（過剰）"), ("external_guaranteed", "ERROR 外形で検められるものを保証"),
                  ("uncovered", "ERROR 保証も残留リスクも無い"), ("unknown_external", "ERROR --external が仕様に無い")]
        for k, lab in labels:
            if res[k]:
                print(f"{lab}: {', '.join(res[k])}")
        print(f"仕様項目 {len(res['spec_items'])} 件 / error {res['errors']} 件")
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.exit(main())

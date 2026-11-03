# BUG-20261103-04: active 本文が非 active の skill を `[[リンク]]` で指している（移動すると解決先を失う）

- 起票日: 2026-11-03
- 状態: fixed（対処 7f7fff1。移動後の再検査で見つかった未解決 77 件は BUG-20261103-05 で対処し、現在 0 件）
- 重要度: 中（移動後に active 側の参照が解決しなくなる）
- 分類: skill-governance / 参照整合
- 対象: `~/.claude/pair-agent/skills/`（active 244 件）

## 症状・実測（2026-11-03 計測。見たことだけ）

- active 244 件のうち 159 件の本文が、非 active（archive 行き・project 行き）の stem を指している。
- 組の数は 308（archive 行き 268 組・project 行き 40 組）。全組は `active-to-nonactive-refs-20261103.tsv`。
- 出現の形: `[[stem]]` の wiki リンクが 359 箇所、素の表記（コード・地の文）が 10 箇所、`[[stem|…]]` の形は 0。
- 参照が最も多い stem は `live-service-smoke-validation`（7 件の active が指す）。

## 再現手順

1. 分類表 `.pair-agent/governance/skill-classification-20261103.tsv` を読む（class 列）。
2. class=active の各 `skills/<stem>.md` の本文を読み、class≠active の stem と一致する文字列を数える（前後が英数・`-`・`_` でない箇所）。
3. 結果は `.pair-agent/governance/active-to-nonactive-refs-20261103.tsv`（308 行）と一致する。

## 影響（事実）

archive 行き・project 行き 404 件を移すと、上の 308 組の参照先は active 側に存在しなくなる。`archive/` は読み込まれない（GOVERNANCE §1）。

## 証拠

- `.pair-agent/governance/active-to-nonactive-refs-20261103.tsv`（移動前の状態・359 + 10 箇所）
- `.pair-agent/governance/skill-classification-20261103.tsv`（commit 22d50d9）

## 対処

- 日付: 2026-11-03
- 対処 commit: 7f7fff1（pair-agent・master）。`skills/` の 157 ファイルで、active 本文の非 active 宛 `[[stem]]` 359 箇所を `` `stem` `` に書き換えた。front matter は変えていない（front matter の非 active 宛リンクは 0 件）。
- 直後の再計測（`refs_tsv_20261103.py after`）: 本文の非 active 宛 wiki リンク 0・front matter のリンク 0・`[[X|...]]` の形 0。
- 残り: もともと `[[ ]]` でない素の表記 10 箇所は残す。`after` の計測では、書き換えた 359 箇所もコード表記として素の表記に数えるため、bare は 369（= 359 + 10）と出る。
- 移動後の検証（TODO 11・2026-11-03）: `tools/check_skill_links.py` で本文の `[[X]]` を再計測した。X が `skills/` に無いものは計 100 件（live の corrections/・vision/・skill-library/・ハーネスに解決先がある 23 件と、どこにも無い 77 件）。どこにも無い 77 件は BUG-20261103-05 で書き換え、現在 0 件。残りの 23 件は残す。
- 判断: 再分類ではなく機械的な書き換えで直した（`decisions-20261103.md` の節 3）。

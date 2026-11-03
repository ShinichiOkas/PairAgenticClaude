# BUG-20261103-05: live skills/ の本文に、どこにも解決しない `[[X]]` が 77 件残っている

- 起票日: 2026-11-03
- 状態: open（対処は直す役が行う。対処の commit は「## 対処」に記す）
- 重要度: 中（リンクの形をしているが辿れない参照が、active と保留の両方にある）
- 分類: skill-governance / 参照整合
- 対象: live `skills/`（`~/.claude/pair-agent/skills/`。47 ファイル: active 38・保留 9）

## 症状・実測（2026-11-03 計測。見たことだけ）

- `tools/check_skill_links.py`（読むだけ・書き換えなし）の計測: skills/*.md の本文の `[[X]]` は 629 件。内訳は in-skills 529（X の追跡ファイルが skills/ にある）・outside 23（corrections/・vision/・skill-library/ に X があるもの 19、ハーネス `~/.claude/skills/X/SKILL.md` があるもの 4）・unresolved 77（どこにも無い）。front matter の `[[X]]` は 1 件で、解決する。
- unresolved 77 件（リンク数。名前の種類は括弧内）:
  - archive/ に同名のファイルがある: 13 件（11 種）
  - ライブの削除履歴（`git log --all --diff-filter=D -- skills/`）にある: 9 件（6 種）。4bfe0d0（2026-11-02）が 6 件（4 種）、1c8373e と afe0f6f（2026-11-03・TODO 10 の移送）が 3 件（2 種）
  - archive/ にも削除履歴にも無い: 55 件（32 種）
- 7f7fff1 の後も残っていた。BUG-20261103-04 の「直後の再計測」は active 側の本文に限り、分類表の非 active の stem と突き合わせた。保留のまま live に残るファイルと、分類表に無い名前は対象外だった。

## 再現手順

1. live の作業ツリー（`C:\Users\0000950207\.claude\pair-agent`）で `python -B tools/check_skill_links.py` を実行する。修正前は `unresolved` が 77 と表示され、終了コードは 1 になる。
2. `python -B tools/check_skill_links.py --list` を実行し、cls が unresolved の行を見る。同じ 77 行が出る（file・line・class・target・region）。

## 影響（事実）

- 47 ファイルの本文に、リンク先の無い `[[X]]` が 77 件ある。
- 77 件の X は 49 種。どれも live の skills/・corrections/・vision/・skill-library/・ハーネスには無い。

## 証拠

- `.pair-agent/governance/dangling-links-20261103.tsv`（100 行。tool の cls が outside 23・unresolved 77。列: file・line・region・cls・target・where。where は outside の場合 repo／harness、unresolved の場合 archive／deleted:<commit>／none。raw は該当行）
- 削除の commit: 4bfe0d0（2026-11-02「移送した固有 skill 9 件をペア固有から削除（非固有化・案2 第一弾）」）、1c8373e（2026-11-03・TODO 10）、afe0f6f（2026-11-03・TODO 10）

## 対処

- 未対処（状態 open）。直し方は `decisions-20261103.md` §3-6 の規則に従う。

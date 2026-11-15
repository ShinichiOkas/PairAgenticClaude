---
name: 人も開発するリポジトリへ commit するツールは、自分が書いた内容そのままのファイルだけを commit する — add -A はしない
description: ツールが commit してよいのは、現在の中身が自分の事象ログに残る書いた内容とハッシュで一致するファイルだけ。人が編集中のファイルは含めない。git add -A は使わない。実測で同じ作業ツリーの開発者の commit と衝突しなかった
type: technique
maturity: draft
created_at: 2026-11-15
source: Pair Agent Manager（manager/pamgr/gitsync.py の tool_written・publish_step）。2026-11-15 の実運用で実測
proposed_by: ai
approved_by: none（AI の観測。未承認）
domain_tags: [manager, git, commit, shared-worktree, hash-check]
---

## 内容

人も同じ作業ツリーで開発するリポジトリに、ツールが commit・push するときの規律。

- commit するのは、**現在の中身が、ツールが書いた内容とちょうど同じ**ファイルだけ（自分の事象ログのハッシュと照合する）
- `git add -A` / `git add .` は使わない。パスを明示して add し、同じパス指定で commit する
- 照合が合わない（人が後から編集した）ファイルは、含めずに残す

## Why

実測（2026-11-15）。開発者が同じ作業ツリーで commit している間に、ツールが「pamgr: 点検で反映」の commit を 4 回 GitHub へ出した。衝突は起きなかった。人の編集中のファイルを巻き込まなかったためである。

`git add -A` なら、人が書きかけのファイルまで、ツールの名前の commit に入る。

## How to apply

- コードは `manager/pamgr/gitsync.py`（`tool_written`、`publish_step`）
- 事象ログに書いたときのハッシュを残す。比べるときは改行を正規化する（`normalize-line-endings-when-comparing-content`）
- push が拒否されたら force しない。pull（merge）してから出し直す（`multi-pc-master-sync-merges-by-section-never-rebases`）

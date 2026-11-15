---
name: 複数 PC のマスター同期は merge から始め、節ごとにマージし、残りは人へ — rebase・reset・force push はしない
description: 分かれたマスターは git merge。衝突したら規則文書(.md)は共通祖先(stage :1)を土台に節ごとにマージし、共有 JSON は和集合。残ったら merge --abort して J2（この PC 優先 / GitHub 優先）。選ばれたら -X ours|theirs で再マージ。merge は自動で戻せない
type: technique
maturity: draft
created_at: 2026-11-15
source: Pair Agent Manager（manager/pamgr/gitmerge.py、manager/tests/test_multi_pc.py）。2026-11-15
proposed_by: ai
approved_by: none（AI の観測。未承認）
domain_tags: [manager, multi-pc, git, merge, master]
---

## 内容

複数の PC が同じマスターを持ち、枝が分かれたときの同期の手順。

1. まず `git merge`
2. 衝突したら、自動で解く
   - 規則文書（.md）は、共通祖先（index の stage :1）を土台に**節ごと**にマージする
   - 共有の JSON は和集合でマージする
3. 解けないものが一つでも残ったら、`git merge --abort` して人の判断（J2）を出す
   - 選択肢は「この PC を優先」「GitHub を優先」
   - 選ばれたら `-X ours` / `-X theirs` で再マージする
4. rebase・reset・force push は**しない**

## Why

- 規則文書は、片方の編集を捨てると失う。節単位なら、別々の節への編集は両方残る
- 土台が無い 2 方向の比較では「どちらが新しいか」が決まらない。共通祖先があれば、各側が何を変えたかが分かる
- 途中の衝突状態を残すと、作業ツリーが壊れたまま放置される。解けないなら abort して元に戻す
- rebase・reset・force push は、他の PC の履歴を書き換える。取り返しがつかない

## How to apply

- コードは `manager/pamgr/gitmerge.py`。テストは `manager/tests/test_multi_pc.py`（一時の bare リモートを使う）
- merge の結果は自動では取り消せない。戻すなら `git revert`（`undo-restores-ledger-and-leaves-do-nothing-mark` の台帳の取り消しとは別物。ここでは台帳の undo に頼らない）
- J2 の文面は「この PC を優先 / GitHub を優先」の 2 択にし、各側の差分の要約を添える

## 関連

- `tool-commits-only-files-it-wrote-never-add-all`（この `skills/`）
- `share-through-multi-user-repo-only-already-shared-content`（この `skills/`）

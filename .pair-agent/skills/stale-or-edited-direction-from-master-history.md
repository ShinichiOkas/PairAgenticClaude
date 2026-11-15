---
name: 配布の台帳が無いときは、本元の git 履歴から向きを推す — 履歴にある古い版は配り直し、無い版は人へ
description: 配布台帳が無い対象の古さ・編集の向きは本元の git 履歴で決める。対象の全体や節が過去の本元の版に等しければ古い（配る）。本元が変えていない節は対象の編集。履歴に当たる節だけ消す推測をしない。それ以外は人（J2）
type: technique
maturity: draft
created_at: 2026-11-15
source: Pair Agent Manager（manager/pamgr/sweep.py の merge_sections・_file、history.py）。2026-11-15
proposed_by: ai
approved_by: none（AI の観測。未承認）
domain_tags: [manager, distribution, git-history, sweep, sections]
---

## 内容

配布の台帳が無いとき、対象の内容が「本元より古い」のか「対象で編集された」のかを、本元の git 履歴から推す。

- ファイル全体が**過去の本元の版のどれかに等しい** → 古い。配り直す
- そうでなければ**節ごとに比べる**
  - 対象の節が履歴に見つかる → 古い（配り直す）
  - 本元が一度も変えていない節 → 対象で編集された（触らない）
- 上のどれでもないものは、人に渡す（J2）
- **対象にだけある節が履歴にも出る場合でも、推測で消さない**

## Why

台帳（何をいつ配ったか）が無い対象では、「本元と違う」だけでは向きが決まらない。本元の履歴は台帳の代わりになる。過去の本元の版に当たれば、配った後に本元が進んだ（対象が古い）と言える。当たらなければ、対象で書き換えられたと言える。

向きを誤って配ると、対象の編集を上書きして失う。配布の向きの誤りは取り返しにくいので、確かな場合だけ自動にし、残りを人に渡す。

## How to apply

- コードは `manager/pamgr/sweep.py`（`merge_sections`、`_file`）と `manager/pamgr/history.py`
- 履歴の版の取り出しは、比較と同じ正規化（`normalize-line-endings-when-comparing-content`）を通す
- 判定の根拠（どの版に当たったか）を計画に残して、取り消しと説明に使う

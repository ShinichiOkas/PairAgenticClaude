---
name: 矛盾の判定は conflict だけを通知・計数する — context_dependent は急がない群に畳む
description: 全ペア判定の結果のうち通知・計数に使うのは conflict だけ。context_dependent は急がない群に畳む。同じ見出しのプロジェクトと global の食い違いは、矛盾ではなく古い写しのことが多い
type: technique
maturity: draft
created_at: 2026-11-15
source: Pair Agent Manager。2026-11-15 に global 325 ペアを判定した結果
proposed_by: ai
approved_by: none（AI の観測。未承認）
domain_tags: [manager, conflicts, inbox, notification]
---

## 内容

LLM の判定が返す区分のうち、受信箱に出して数えるのは `conflict` だけにする。

- `context_dependent` は、通知も件数にも入れず、急がない群に畳む
- 同じ見出しのプロジェクトと global の「矛盾」は、まず**古い写し**を疑う（判断の食い違いではない）

## Why

実測（2026-11-15）。global の 325 ペアで、LLM は conflict を 1 件、context_dependent を 62 件と判定した。context_dependent まで数えると、受信箱は 63 件になり、本物の 1 件が埋まって使えない。

同じ見出しのプロジェクトと global の「矛盾」は、llmbenchmark のプロジェクトに残った global の節の古い写しだった。判断の食い違いではなかった。配り直すか、「見送ったもの」に出す。

## How to apply

- 通知・件数・バッジは conflict だけで作る
- context_dependent は一覧で見られるが、通知しない群に置く
- 同じ見出しの食い違いは、矛盾の前に「古い写しか」を判定する（`stale-or-edited-direction-from-master-history` を参照）

## 関連

- `rule-conflicts-are-semantic-judge-all-pairs-with-llm`（この `skills/`）

---
name: 規則文書どうしの矛盾は意味で起きる — 同居する集合は全ペアを LLM で判定し、字面の類似は絞り込みにだけ使う
description: 矛盾する 2 節は字面が似ていない。同居する集合（global の CLAUDE.md とルール）は全ペアを LLM で判定して判定をペアの内容ハッシュで残す。字面の類似はプロジェクトと global の相手探しにだけ使う
type: technique
maturity: draft
created_at: 2026-11-15
source: Pair Agent Manager（manager/pamgr/conflicts.py）。2026-11-15 の実測
proposed_by: ai
approved_by: none（AI の観測。未承認）
domain_tags: [manager, conflicts, llm, similarity, rules]
---

## 内容

エージェント規則文書の矛盾は、字面ではなく意味で起きる。字面の類似度で矛盾の候補を絞らない。

- 同居する集合（global の `~/.claude/CLAUDE.md` と rules）は、**全ペアを LLM で判定する**
- 判定は「ペアの内容ハッシュの組」を鍵にして残す。内容が変わらない限り再判定しない
- 字面の類似（文字 bigram TF-IDF）は、**プロジェクトと global の相手探しを絞る用途にだけ**使う

## Why

実測（2026-11-15）。矛盾する対「運転方針 × セッションの始め」の字面の類似度は、節の単位で 0.11、文の単位で 0.0 だった（文字 bigram TF-IDF）。どんな閾値でも拾えない。

全ペア判定の費用は小さい。325 ペアが 298 秒で済んだ（gemma4:31b-cloud、1 ペアおよそ 1 秒）。鍵が内容ハッシュなので、2 回目以降は変わった節の分だけで済む。

## How to apply

- 同居が決まっている集合の矛盾検出は、類似度で足切りせず全ペアを判定する
- 字面の類似を使ってよいのは、相手が集合に入るか分からないとき（プロジェクトの節 → global の候補）だけ
- 判定の結果は、判定したモデル名と一緒に残す
- コードは `manager/pamgr/conflicts.py`

## 関連

- `conflict-verdicts-notify-only-conflict`（この `skills/`）— 判定の結果をどこまで通知するか

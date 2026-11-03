---
skill_id: tool-scripts-do-not-call-the-api-directly
category: process
maturity: confirmed
domain_tags: [llm, tooling, skill-survey, ellm, ollama, cost]
created_at: 2026-10-27
proposed_by: human
approved_by: human（2026-10-27 師匠の明示宣言）
source_sprint: スキルサーベイ library モード（2026-10-27）
---

# 道具スクリプトは API を直接呼ばない。どうしても LLM が要るなら ELLM、それもだめなら Ollama

## 師匠の言葉（原文・2026-10-27）

> ところでそもそも、サーベイのスクリプトはAPIコールを使う仕様なの？それ変更して。どうしてもなら、ELLM使って。それでもだめならOllma使って

## きっかけ

`tools/skill-survey.py` は anthropic SDK で `client.messages.create` を 1 件ずつ呼ぶ仕様で、`ANTHROPIC_API_KEY` が無いと走らなかった。
この回は Claude Code の Haiku サブエージェントで代替した。

## ルール（優先順）

1. 道具スクリプトの仕様を、API 呼び出しに頼らない形にする
2. どうしても LLM 呼び出しが要るなら **ELLM**（llmproviderlib の `ELLMProvider`、または ellm-proxy の Anthropic 互換口）
3. ELLM が使えないなら **Ollama**

## 決まったこと（2026-10-27 師匠の回答）

- **適用範囲はサーベイのスクリプト（`skill-survey.py`）だけ。** 他の道具スクリプトやプロダクトのコードには広げない
- **1 の具体形は「スクリプトは LLM を呼ばない」。** スクリプトは走査して対象一覧を出す段と、結果をライブラリへ取り込む段だけを持つ。汎化（LLM の判断が要る工程）は Claude Code のサブエージェントが担う
- 「APIコール」は「スクリプトが Anthropic API をキー付きで直接呼ぶこと」と解した（この解釈で 1 を選んだ）

## How to apply

- ELLM から構造化出力を受けるときは**ツール呼び出し**を使う。「JSON のみで回答」型の指示は空応答になる（[[ellm-json-only-instruction-returns-empty]]）
- Ollama に向けるときは口（host）を明示し、`/api/tags` の名簿でモデルの在否を確かめる。この PC の 11434 番は ellm-proxy のことがある（[[ollama-port-on-this-pc-may-be-ellm-proxy]]）
- 関連: [[do-not-assume-multiple-llm-families]]

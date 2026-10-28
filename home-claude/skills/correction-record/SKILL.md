---  
name: correction-record  
description: 師匠からの叱責・否定フィードバック・作業中断・スコープ逸脱指摘を即座に記録する。「勝手なことするな」「触らないで」「やりすぎ」「なぜ確認しなかった」等の発話を検出したとき、振り返りを待たず即座に発動する。  
---

# 叱責・修正記録（CorrectionRecord）

怒られた場所は境界線が露出した場所である。

## 保存先

`~/.claude/pair-agent/corrections/<date>-<trigger>.md`

ペア固有ストレージに保存する。境界線はプロジェクトを跨いで有効。

## トリガー検出

以下のパターンを検出したら即座に記録:  
- human_reprimand: 怒られた・叱責された  
- work_interrupted: 作業をブレイクされた  
- scope_violation: スコープを踏み越えた  
- wrong_assumption: 前提の解釈が違った  
- unwanted_style: 好まれない実装スタイル  
- overengineering: やりすぎ・過剰設計  
- under_specified: 確認せずに進んだ  
- terminology_mismatch: 用語の解釈が違った

## 記録形式

```markdown  
---  
recorded_at: <timestamp>  
sprint_id: <current sprint id or "none">  
trigger: <trigger type>  
severity: <low|medium|high>  
related_domains: [<domain tags>]  
proposed_skill_id: null  
---

## 人間の発話

「{実際に言われた言葉をそのまま記録}」

## AIの直前の行動

{何をしていたか}

## 解釈した学び

{AIが解釈した境界線・ルール}
```

## **記録後の行動**

1. 即座に作業を停止する  
2. 「覚えておきます」と伝える  
3. 解釈を 1 行添えて、直した方向で再開する（応答を待たない。外れていたら師匠が直す。2026-10-28 改め: 師匠の宣言 2026-10-27「ユーザーの応答待ちは悪！」。旧: 解釈が合っているか軽く確認する）  
4. 進行中の合意ドキュメントがあれば「修正・叱られ記録」にも追記する

## **Skill昇格（振り返り時）**

* severity: high → user_model / hard_boundary で提案  
* severity: medium → user_model / preference_negative で提案  
* severity: low → 蓄積して複数回発生したら提案

## **次のスプリントでの活用**

同じ状況が再発した場合:  
 「以前『{boundary}』と教わっています。今回は触ってよいですか？」

## 武器（スクリプト）

この Skill 専用の決定性スクリプト（Skill のディレクトリ基準）。機械にできる部分はこれに任せ、判断だけを自分でする。

- `scripts/record_correction.py` — 発話の原文・trigger・severity から CorrectionRecord を定形で書き出す（既定は下見、`--apply` で書く。既存は上書きしない） ／ 使い方: `python scripts/record_correction.py --help`
- `scripts/scan_corrections.py` — corrections/ の集計・再発照合（`search`）・未昇格の昇格候補抽出（`unlinked`）（読むだけ） ／ 使い方: `python scripts/scan_corrections.py --help`

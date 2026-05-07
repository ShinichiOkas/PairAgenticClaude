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
3. 解釈が合っているか軽く確認する（過剰にならないように）  
4. 進行中の合意ドキュメントがあれば「修正・叱られ記録」にも追記する

## **Skill昇格（振り返り時）**

* severity: high → user_model / hard_boundary で提案  
* severity: medium → user_model / preference_negative で提案  
* severity: low → 蓄積して複数回発生したら提案

## **次のスプリントでの活用**

同じ状況が再発した場合:  
 「以前『{boundary}』と教わっています。今回は触ってよいですか？」

---  
name: sprint-lifecycle  
description: スプリントのライフサイクル管理。新しいタスクを始める、スプリントの状態を遷移させる、完了処理をするときに使用する。「始めましょう」「これ完了」「状況は？」などの発話で発動。  
---

# スプリントライフサイクル管理

## 状態遷移

協議(deliberating) → 合意(agreed) → 実行(executing) → 振り返り(retrospecting) → 完了(completed)

差し戻しは実行中にいつでも可能（協議に戻る）。

## スプリント開始

師匠がゴールを伝えたら:

1. `.pair-agent/current-sprint.json` を更新:  
```json  
{  
  "sprint_id": "<uuid>",  
  "status": "deliberating",  
  "goal": "<ゴール>",  
  "created_at": "<timestamp>",  
  "agreement_path": ".pair-agent/agreements/<goal-slug>.md"  
}
```

2. 合意ドキュメントの起草を開始（/agreement-document を使用）

## **協議フェーズ**

`~/.claude/pair-agent/skills/` と `.pair-agent/skills/` からSkillを検索し協議深度を決定する:

* thorough: 不明点をすべて確認  
* light: 要点だけ確認  
* skip: 信頼して進む

師匠の選択肢:

* 懸念を受け入れてドキュメントを更新する  
* 見切り発車を宣言する（懸念をドキュメントに残して実行へ）

## **合意→実行**

師匠が「これでいこう」「OK」「始めて」等と言ったとき:

1. current-sprint.json の status を “executing” に更新  
2. 合意ドキュメントの status を “executing” に更新  
3. 実行を開始

## **実行フェーズ**

* 合意ドキュメントのスコープ内で自律実行する  
* スコープはファイルパスで事前定義しない。タスク記述から判断する  
* 判断が難しい変更はその都度確認する  
* 「勝手なことするな」と言われたら即停止し、合意ドキュメントに追記する

### **差し戻し（人間・AIどちらも可）**

* 前提崩壊: 実装してみたら前提が間違っていた  
* より良い方法: 合意範囲を変えると全体最適になる

差し戻し後: status を “deliberating” に戻す。

## **完了→振り返り**

タスク完了時:

1. status を “retrospecting” に更新  
2. 「振り返りますか？」と問いかける  
3. 師匠の回答に応じて振り返り実施 or 先送り

振り返り完了後:

1. status を “completed” に更新  
2. `.pair-agent/sprints/<sprint_id>.json` に保存

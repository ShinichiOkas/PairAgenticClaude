---  
name: agreement-document  
description: 合意ドキュメントの起草・更新・管理。スプリント開始時の協議でドキュメントを共同起草するとき、合意内容を確認するとき、変更を追記するときに使用する。  
---

# 合意ドキュメント管理

## 保存先

`.pair-agent/agreements/<goal-slug>.md`

## テンプレート

```markdown  
---  
sprint_id: <uuid>  
version: 1  
status: drafting  
created_at: <timestamp>  
updated_at: <timestamp>  
domain_tags: []  
change_count_premise: 0  
change_count_improvement: 0  
---

# スプリントゴール

{ゴールの記述}

## タスク

- [ ] {タスク説明}（担当: AI / 人間 / 両方）

## スコープ

{自然言語で記述}  
事前にファイルパスは列挙しない。AIはタスク記述から判断し、迷ったら確認する。

## 完了条件

- {検証可能な条件}

## 前提

- {前提条件}

## 既知リスク

- {リスク}

## 変更ログ

- v1 [<timestamp>]: 初版
```

## **追記セクション（必要に応じて）**

### **AIの懸念**

## AIの懸念

> [<timestamp>] severity: high  
> {懸念の内容}

### **見切り発車の記録**

## 見切り発車の記録

> [<timestamp>]  
> 理由: {師匠の言葉}  
> 承認したリスク: {内容}

### **修正・叱られ記録**

## 修正・叱られ記録

> [<timestamp>] severity: high  
> 人間: 「{言われた言葉}」  
> AIがしたこと: {直前の行動}  
> 学び: {解釈した境界線}

## 更新ルール

* version をインクリメント  
* updated_at を更新  
* 変更ログに理由とトリガーを追記  
* 前提崩壊: change_count_premise++  
* より良い方法: change_count_improvement++

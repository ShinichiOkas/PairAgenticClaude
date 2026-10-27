---  
name: vocabulary-capture  
description: 師匠の用語定義を学習する。協議中に曖昧な用語が出たとき、師匠が用語を定義したとき、用語の解釈ミスで叱られたときに発動。  
---

# 用語定義の学習

## 保存先

`~/.claude/pair-agent/skills/vocab-<term>.md`

用語定義はペア固有。師匠の語彙はプロジェクトを跨いで一貫する。

## 確認の仕方

「{用語}」とおっしゃっていましたが、具体的にはどの範囲を指していますか？

a) {候補1}  
 b) {候補2}  
 c) {候補3}  
 d) その他

## 記録形式

```markdown  
---  
name: vocab-<term>  
category: vocabulary  
maturity: confirmed  
domain_tags: [<relevant domains>]  
proposed_by: human  
confirmed_by: human  
created_at: <timestamp>  
updated_at: <timestamp>  
---

# 「{用語}」の定義

この師匠が「{用語}」と言うとき:  
- {含まれるもの}  
- {含まれないもの}

例: {具体例}
```

## ルール

* 一度学んだ用語は再確認しない  
* 定義が変わったと感じたときだけ確認する  
* domain_tags の名前自体も vocabulary で定義される

## 武器（スクリプト）

この Skill 専用の決定性スクリプト（Skill のディレクトリ基準）。機械にできる部分はこれに任せ、判断だけを自分でする。

- `scripts/vocab_ops.py` — 用語定義を vocab-<term>.md の定形で登録（`add`: 含む/含まないの両方が必須、既知は上書きせず `--update` で改訂履歴つき）・既知用語の検索（`find`）・テキスト中の既知用語の洗い出し（`scan`: 再確認を避ける）・一覧（`list`） ／ 使い方: `python scripts/vocab_ops.py --help`

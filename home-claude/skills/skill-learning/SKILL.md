---  
name: skill-learning  
description: Skillの生成・昇格・精緻化・管理。振り返りフェーズでのSkill提案、師匠のプロセス宣言の即時登録、maturity昇格判断、Skill一覧確認や編集を行う。  
---

# Skill学習・maturity管理

## 保存先

- ペア固有Skill:
  使用中のツールに合わせて以下のいずれかを選択する（両方存在する場合は、使用中のツールのパスを優先）。
  - `~/.claude/pair-agent/skills/<skill-name>.md` (Claude Code)
  - `~/.gemini/antigravity/pair-agent/skills/<skill-name>.md` (Google Antigravity)
- プロジェクト固有Skill:
  - `.pair-agent/skills/<skill-name>.md` (Claude Code)
  - `.agents/skills/<skill-name>/SKILL.md` (Google Antigravity - 必要に応じて `.pair-agent/skills/` からコピーまたはシンボリックリンク)

## Skill記録形式

```markdown  
---  
name: <識別名>  
category: <process|domain|vocabulary|user_model>  
maturity: <draft|forming|confirmed>  
domain_tags: [<tags>]  
source_sprint_ids: [<sprint ids>]  
proposed_by: <ai|human>  
confirmed_by: <human or null>  
created_at: <timestamp>  
updated_at: <timestamp>  
---

# <Skill名>

{Skill内容の自然言語記述}

## 改訂履歴

- [<timestamp>] 初版作成 (by: <ai|human>)
```

## **カテゴリ定義**

**process**: 働き方・ワークフローのルール。「実装前に仕様書を作る」等  
 **domain**: 技術ドメイン別の知見。「アーキテクチャ変更は信頼してよい」等  
 **vocabulary**: 師匠の用語定義。「シンプル＝外部依存なし」等  
 **user_model**: 師匠の傾向・境界線。CorrectionRecordから生成されることが多い

user_model の境界タイプ:

* hard_boundary: 絶対に踏むな。事前確認必須  
* preference_negative: 避けるが必要なら提案して確認  
* past_conflict: 以前揉めた。再発時は背景を説明して確認  
* style_dislike: 美意識として嫌う

## **保存先の判断**

| 内容 | 保存先 |
| ----- | ----- |
| 師匠の好み・用語・プロセスルール・境界線 | ペア固有Skillフォルダ（上記参照） |
| プロジェクト固有の技術知見（APIの仕様、DB構造等） | プロジェクト固有Skillフォルダ（上記参照） |
| 迷ったら | ペア固有側を優先 |

## **maturity昇格**

| 現在 | 条件 | 昇格後 |
| ----- | ----- | ----- |
| draft | パターン定着をAIが判断し、その場で昇格（問わない） | forming |
| forming | 師匠の原文の宣言・決定が付いた、または師匠が事後報告を受けて取り消さずに使い続けた | confirmed |
| confirmed | 師匠が内容更新 | confirmed（改訂版） |

## **人間起点の即時登録**

師匠の明示的ルール宣言 → maturity: confirmed で即時保存。draftを経由しない。

（2026-10-27 改め: 師匠の宣言「スキルの振り返りも自動にして、ユーザーの応答待ちは悪！」。昇格のたびに師匠へ伺わない。登録・昇格は AI がその場で行い、事後に報告する。師匠は事後に取り消せる。取り消しは CorrectionRecord に残す）

## **AI起点のSkill生成（振り返り時）**

振り返りは自動で走り、AI の観測だけの候補は forming で登録、師匠の原文の宣言に裏付けられた候補は confirmed で登録する（`retrospect` スキル）。

| 観測 | 生成Skill |
| ----- | ----- |
| 前提崩壊 | domain: 「次回詳しく詰める」 |
| 見切り発車→成功 | domain: 「信頼してよい」 |
| 見切り発車→失敗 | domain: 「必ず詰めること」 |
| 詰めが空振り | domain: 「詰め不要かも」 |
| ビジョンに同じ関心2回以上 | user_model: パターン記述 |

## 武器（スクリプト）

この Skill 専用の決定性スクリプト（Skill のディレクトリ基準）。機械にできる部分はこれに任せ、判断だけを自分でする。

- `scripts/skill_lint.py` — Skill 群のフロントマター検査（`lint`）・maturity x category の棚卸し（`inventory`）・confirmed の数から協議深度（follow/skip/light/thorough）を決める（`depth`）（読むだけ） ／ 使い方: `python scripts/skill_lint.py --help`
- `scripts/skill_write.py` — Skill の新規作成（`new`）と maturity の昇格・降格（`promote`。段飛ばしは原文必須、改訂履歴を自動追記）。既定は下見、`--apply` で書く。`new` は書き込み先に同じ師匠の原文（「…」15 文字以上／`> ` 引用行）を持つ既存 Skill が有れば拒否して追記を促す（外すのは `--allow-same-quote`） ／ 使い方: `python scripts/skill_write.py --help`

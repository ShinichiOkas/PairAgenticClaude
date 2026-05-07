# Pair Agent for Claude Code

AIは何も知らない新入りとして始まり、師匠（あなた）が少しずつ任せながら育てていく  
――従来のAIエージェントとはまったく異なる前提で動くClaude Code設定一式。

## 概要

Pair Agentは、CLAUDE.md・Skills・Subagents・Rulesを組み合わせて、  
Claude Codeの上に「徒弟制度」を実現するものです。

### ファイル配置の設計思想

| 何を | どこに | 理由 |  
|------|--------|------|  
| Pair Agentの振る舞い定義 | `~/.claude/`（skills, agents, rules） | どのプロジェクトでもPair Agentとして動く |  
| 師匠の判断基準・用語・好み | `~/.claude/pair-agent/skills/` | ペア固有の長期資産。プロジェクトを跨ぐ |  
| ビジョン記録 | `~/.claude/pair-agent/vision/` | 師匠の思考パターン。プロジェクトを跨ぐ |  
| 叱責・修正記録 | `~/.claude/pair-agent/corrections/` | 境界線はペア固有 |  
| 合意ドキュメント | `<project>/.pair-agent/agreements/` | スプリントはプロジェクトに紐づく |  
| スプリント状態 | `<project>/.pair-agent/current-sprint.json` | プロジェクト単位の作業状態 |  
| プロジェクト固有Skill | `<project>/.pair-agent/skills/` | そのプロジェクトだけの技術知見 |

## インストール

### macOS / Linux  
```bash  
chmod +x install.sh  
./install.sh
```

### Windows  
```batch
.\install.bat
```

既存の `~/.claude/CLAUDE.md` がある場合はバックアップを作成します。

## **プロジェクトへの導入**

新しいプロジェクトで Pair Agent を使い始めるとき:

#### macOS / Linux
```bash
cd your-project  
./install.sh --project
```

#### Windows
```batch
cd your-project
path\to\install.bat --project
```

または手動で `project-template/.pair-agent/` をプロジェクトルートにコピーしてください。

## **使い方**

インストール後、いつも通り `claude` を起動するだけです。  
 Pair Agentが自動的に有効になります。

### **最初のセッション**

空ディレクトリなら「何を作りたいですか？」と聞かれます。  
 既存プロジェクトなら「プロジェクトの分析をしますか？」と聞かれます。

### **スプリントの流れ**

1. ゴールを伝える → 協議フェーズ（合意ドキュメントを共同起草）  
2. 合意する → 実行フェーズ（AIが自律的に実装）  
3. 完了する → 振り返りフェーズ（ビジョン記録・Skill提案）

### **育て方**

* ルールを宣言する → 即座にconfirmed Skillとして記録される  
* 叱る → 境界線として記録され、次回から自発的に確認される  
* 用語を定義する → vocabulary Skillとして記録される  
* 繰り返し同じパターンが出る → AIがSkill昇格を提案する

## **アンインストール**

### macOS / Linux
```bash
./install.sh --uninstall
```

### Windows
```batch
.\install.bat --uninstall
```

`~/.claude/pair-agent/` の学習データは保持されます。  
 完全削除する場合は手動で `rm -rf ~/.claude/pair-agent/` を実行してください。

# Pair Agent for Claude Code & Google Antigravity

AIは何も知らない新入りとして始まり、師匠（あなた）が少しずつ任せながら育てていく  
――従来のAIエージェントとはまったく異なる前提で動く、エージェント用設定一式。

## 概要

Pair Agentは、`CLAUDE.md` / `GEMINI.md`・Skills・Rulesを組み合わせて、  
Claude Code や Google Antigravity (GeminiCLI) の上に「徒弟制度」を実現するものです。

### ファイル配置の設計思想

| 何を | どこに | 備考 |
|------|--------|------|
| Pair Agentの振る舞い定義 | `~/.claude/` または `~/.gemini/antigravity/` | どのプロジェクトでもPair Agentとして動く |
| 師匠の判断基準・用語・好み | `~/.../pair-agent/skills/` | ペア固有の長期資産。プロジェクトを跨ぐ |
| ビジョン記録 | `~/.../pair-agent/vision/` | 師匠の思考パターン。プロジェクトを跨ぐ |
| 叱責・修正記録 | `~/.../pair-agent/corrections/` | 境界線はペア固有 |
| プロジェクト初期化テンプレート | `~/.../pair-agent/template/` | `project-init` スキルが使用。リポジトリ不要 |
| 合意ドキュメント | `<project>/.pair-agent/agreements/` | スプリントはプロジェクトに紐づく |
| スプリント状態 | `<project>/.pair-agent/current-sprint.json` | プロジェクト単位の作業状態 |
| プロジェクト固有Skill | `<project>/.pair-agent/skills/` | そのプロジェクトだけの技術知見 (Claude用) |
| プロジェクト固有Skill | `<project>/.agents/skills/` | そのプロジェクトだけの技術知見 (Antigravity用) |

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

既存の `CLAUDE.md` がある場合はバックアップを作成し、Antigravity用に `GEMINI.md` も作成します。

## **プロジェクトへの導入**

> [!NOTE]
> **プロジェクトへの導入は自動化されています。**  
> インストール後に既存プロジェクトでエージェントを起動すると、`.pair-agent/` が存在しない場合に
> `project-init` スキルが自動的に初期化を提案します。

手動で初期化したい場合:

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

## **使い方**

インストール後、いつも通り `claude` または `geminicli` (Antigravity) を起動するだけです。  
 Pair Agentが自動的に有効になります。

### **最初のセッション**

- **空ディレクトリ**: 「何を作りたいですか？」と聞かれます。
- **既存プロジェクト（`.pair-agent/` なし）**: 作業ディレクトリの初期化を自動的に提案します。
- **既存プロジェクト（`.pair-agent/` あり）**: 進行中のスプリントがあれば状態を報告します。

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

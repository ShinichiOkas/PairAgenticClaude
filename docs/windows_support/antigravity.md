# Claude Code と Google Antigravity の対応機能まとめ

## 背景

Google Antigravity は「Agent-First IDE」として登場した開発環境で、Claude Code と同様にエージェントが自律的にコードを書き・実行・検証する設計思想を持っています。以下は、Claude Code の主要な設定ファイル機能と Antigravity の対応機能をまとめたものです。

---

## CLAUDE.md → GEMINI.md

Claude Code における `CLAUDE.md` は、プロジェクトのルートに置くことでセッションをまたいで永続的な指示を与えるファイルです。Antigravity における相当機能は **`GEMINI.md`** で、毎回の LLM 呼び出し時に自動的にコンテキストへ読み込まれます。基本的にはリネームするだけで同様に機能します。

**注意点**が3つあります。`@ファイル参照`などの Claude Code 固有構文は Antigravity では解釈されない可能性があること、サブディレクトリへの階層的な配置が同様に機能するかは未確認であること、そして `GEMINI.md` の自動読み込みは Gemini 3 モデル使用時に確認されており、Antigravity 上で他モデルを使う場合は挙動が異なる可能性があることです。

**両ツールを併用する場合**は、リネームではなくハードリンクで両ファイルを維持するのが実用的です。シンボリックリンクは Antigravity が追えないケースが報告されているため、ハードリンクが推奨されます。

```bash
ln CLAUDE.md GEMINI.md  # ハードリンク推奨（シンボリックリンクは非推奨）
```

---

## AGENTS.md について（重要な落とし穴）

`AGENTS.md` は Cursor・Windsurf など複数ツールに対応したクロスツール標準ファイルとして広まっていますが、**Antigravity は `AGENTS.md` を自動読み込みしません**。Reddit コミュニティでの実験検証により、Antigravity が自動でコンテキストに含めるのは `GEMINI.md` のみであることが確認されています。`AGENTS.md` だけ置いても機能しない点は特に注意が必要です。

---

## SKILL.md → SKILL.md（同名・同概念）

Claude Code の `SKILL.md` に相当する機能が Antigravity にも **`SKILL.md` という同じ名前で存在します**。Google の公式ドキュメントで定義されており、設計思想もほぼ同一です。会話開始時にエージェントが利用可能な Skill 一覧を確認し、タスクに関連しそうなものを自律的に読み込んで適用します。ユーザーが明示的に呼び出す必要はありません。

配置場所だけが異なります。

| スコープ | Claude Code | Google Antigravity |
|---|---|---|
| プロジェクト固有 | `.claude/skills/*/SKILL.md` | `.agents/skills/*/SKILL.md` |
| グローバル | `~/.claude/skills/*/SKILL.md` | `~/.gemini/antigravity/skills/*/SKILL.md` |

`SKILL.md` のフォーマットは YAML フロントマターで `name` と `description` を定義し、以下に Markdown で指示を記述する点も共通しています。`description` フィールドにエージェントが「いつ使うべきか」を判断するためのキーワードを盛り込むのがベストプラクティスです。

---

## 全体対応表

| 機能 | Claude Code | Google Antigravity | 互換性 |
|---|---|---|---|
| 永続指示ファイル | `CLAUDE.md` | `GEMINI.md` | ほぼ同等・リネームで概ね移行可 |
| クロスツール標準 | `AGENTS.md` | `AGENTS.md` | ⚠️ Antigravity は自動読み込みしない |
| スキル拡張 | `.claude/skills/*/SKILL.md` | `.agents/skills/*/SKILL.md` | ほぼ同等・配置場所のみ異なる |

---

## 移行時の実用的な結論

Claude Code から Antigravity へ移行・併用する場合、`CLAUDE.md` は `GEMINI.md` としてハードリンクで維持し、`SKILL.md` は `.agents/skills/` 以下に配置し直すだけで、ほとんどの設定をそのまま活用できます。ファイル名や概念レベルでは両ツールの設計が非常に近く、学習コストは低いと言えます。
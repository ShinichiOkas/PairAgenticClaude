# BUG-20261102-03: スプリント閉じ損ね・current 二重管理・bugs 二系統重複（運用衛生の欠陥）

- 起票日: 2026-11-02
- 状態: open
- 重要度: 中（個別は小さいが横断で衛生を下げている）
- 分類: sprint-lifecycle / current-pointer 移設 / bug-intake
- 対象: 上流 `sprint-lifecycle` / `retrospect` スキル、各プロジェクトの `.pair-agent/`

## 症状・実測（2026-11-02 計測。見たことだけ）

対象: `~/work/*/.pair-agent/`（31 プロジェクト）

### 1. スプリントが閉じ切れずに放置

current-sprint.json の status 分布:
- completed=7 / idle=5 / retrospecting=3 / moved=3 / executing=2 / done=1 / between_sprints=1 / accepted=1

`retrospecting` のまま放置（自動振り返りが閉じ切れていない疑い）:
- mu（最終 sprint ファイル Aug 29）
- Whisper（最終 sprint ファイル Sep 12）
- ChatlogLLMHumanRelation（updated_at 2026-09-01T18:20 のまま）

`executing` のまま放置:
- Humanity（sprints ディレクトリ空・humanlikeness-testbench-20260912）
- LLMWorkflow（最終 sprint ファイル May 18）

宣言「応答待ちは悪・閉じ待ちでスプリントを開けておかない」に反し、retrospecting/executing が月単位で残存。

### 2. current 形式の二重管理

新形式 `current/`（作業ツリーごとポインタ）を持つ 5 プロジェクト全てで旧 `current-sprint.json` が併存:
- AIdedArchitecture / AgenticWorkspace / MSTenantMCP / ellm-proxy / ray

しかも両者で status が食い違う例:
- ray: `current/*.json` の pointer は status=idle（2 ポインタ: ANCIENT S:/ と JPC20661296 C:/）だが `current-sprint.json` は status=moved

CLAUDE.md の移設手順（旧形式 → current/）が未完のまま放置され、どちらが真か曖昧。

### 3. bugs の二系統が重複混在（ellm-proxy）

`ellm-proxy/.pair-agent/bugs/` に 2 系統が同一日付で並走:
- 手書き詳細票: `BUG-20261030-01-persona-conflict-long-context.md`（症状・実測・証拠・状態+commit まで揃う）
- ログ機械生成票: `BUG-20261030-01.md` 〜 `BUG-20261030-08.md`（10 件前後、`refusals.db`/`failures_dir` 由来）

同一事象が複数票に散っている実例:
- req:e9ca68bd が `BUG-20261030-02.md` と `BUG-20261030-03.md` の両方に出現（Outcome: delivered）

機械生成票の集約／重複排除ルールが無く、ノイズ化している。

## 良い点（併記・事実）

- 回転実績: ray=31・mu=28・AgenticWorkspace=27・LogicParser=21 sprint。agreement も mu=38・ray=32・rex=27。
- 新形式 current/ はマルチ作業ツリーで実際に機能（ray が 2 ホストのポインタを保持）。
- バグ票の手書き票は症状・実測・証拠・closed+commit hash まで揃い、規律は守れている。

## 診断・解き方は書かない（直す役の仕事）

本票は症状と実測のみ。

## 追記（2026-11-03）: 二重管理の実測（読み取りのみ・事実のみ）

同名の `pair-agent-core.md` 3 本の比較（計測は 2026-11-03）:

| 場所 | バイト | 改行 | sha256（先頭 16 桁） | 絶対的規範 | 師匠 | ユーザー | 迷ったら project か archive |
|---|---|---|---|---|---|---|---|
| `home-claude/rules/` | 11185 | CRLF 85 | 91727c72af20a7f7 | 2 | 22 | 4 | 1 |
| `~/.claude/rules/` | 9520 | LF 81 | 7543244139b3d4d8 | 0 | 0 | 26 | 1 |
| `~/.gemini/config/rules/` | 9432 | LF 81 | 8a7fd66a33575771 | 0 | 22 | 4 | 1 |

- 3 本の sha256 はすべて異なる。「迷ったらペア固有」は 3 本とも 0 件。
- 「絶対的規範」の節はリポジトリ版にだけ現れる。`~/.claude` 版は「師匠」0 件・「ユーザー」26 件。
- インストール先 2 本は 2026-11-03 に保存先ルールの箇所を手で書き換えた（版管理外。リポジトリ版からの逆同期はしていない）。
- pair-agent の clone は 2 つある: `~/.claude/pair-agent`（ペア固有 Skill の読み込み元）と `external/pair-agent-skills`（サブモジュール）。2026-11-03 時点で両方とも 7531c01。
- 作業ツリー（2026-11-03 計測）: `git worktree list` は main（9128281）に加えて 2 件を示す。`.claude/worktrees/agent-a6b41bde7c7deee92`（branch `worktree-agent-a6b41bde7c7deee92`）と `.claude/worktrees/s-survey-r5`（branch `s-survey-r5`）で、どちらも HEAD は 7cad7c4。`.claude/worktrees/` は `.gitignore` の 7 行目で無視され、追跡ファイルは 0 件。

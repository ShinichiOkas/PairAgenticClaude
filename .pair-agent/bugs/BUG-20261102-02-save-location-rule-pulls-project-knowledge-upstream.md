# BUG-20261102-02: 保存先ルール『迷ったらペア固有』が固有知見をペア固有層へ吸い上げる（上流の設計欠陥）

- 起票日: 2026-11-02
- 状態: open
- 重要度: 高（BUG-20261102-01 の根本原因側）
- 分類: skill-governance / 保存先判定ルール
- 対象: 上流 `~/.claude/rules/pair-agent-core.md`「Skill保存先の判断基準」、`~/.claude/CLAUDE.md`「Skill検索の順序」、`retrospect` / `skill-survey` / `skill-learning` スキル

## 症状（見たことだけ）

`pair-agent-core.md`「Skill保存先の判断基準」末尾に **「迷ったらペア固有側に保存する」** とある。振り返りが自動（応答待ちは悪）で回るため、汎化前の固有知見がこの既定によってペア固有層へ流れ込み続ける。

## 実測・証拠

- 現行ルール本文（`pair-agent-core.md`「Skill保存先の判断基準」）:
  - 「このプロジェクト特有の技術知見 → プロジェクト固有側」
  - 「**迷ったらペア固有側に保存する**」
- 結果の実測は BUG-20261102-01 を参照（ペア固有 650 件中 427 件=66% に本文固有名漏出）。
- 昇格時に「固有名を剥いで一般化できるか」を判定するゲートが、どのスキル定義（retrospect/skill-survey/skill-learning）にも無い。

## 影響

- 「迷ったら」の既定が固有側ではなくペア固有側を向いているため、放っておくと固有知見が恒常的にペア固有へ蓄積する。
- 自動振り返り（速度優先）がこの圧力を増幅する（人手の汎化ステップが挟まらない）。

## 診断・解き方は書かない（直す役の仕事）

候補の方向（師匠の見立て）だけ記録: 既定を『迷ったらプロジェクト固有。固有名を剥いて原則化できたものだけペア固有へ』へ反転し、昇格ゲートを 1 つ足す。実装は直す役が決める。

## 追記（2026-11-03）

- 既定を反転（commit 83d5e2f）。反転後の文言は「迷ったら project か archive」。11 行目の旧文言は反転前の記録として残す。
- 反転した箇所: `home-claude/rules/pair-agent-core.md`・`Pair Agentic CLAUDE.md`（2 箇所）・`home-claude/skills/retrospect/SKILL.md`・`home-claude/skills/skill-learning/SKILL.md`。
- インストール先（`~/.claude/rules/`・`~/.gemini/config/rules/`・`~/.claude/skills/retrospect/`・`~/.claude/skills/skill-learning/`）も手で同じ箇所を書き換えた（版管理外。リポジトリ版からの逆同期はしていない）。
- 2026-11-03: `~/.gemini/config/skills/retrospect/SKILL.md`（53 行目）と `~/.gemini/config/skills/skill-learning/SKILL.md`（62 行目）に旧文言が残っていたため、その 1 行ずつを repo の文言に書き換えた（版管理外・行単位のみ）。`~/.gemini/antigravity-ide/skills/`・`~/.gemini/antigravity-backup/skills/` は 2026-05-11 時点の複製で、skill-learning 62 行目に旧文言を含むが未変更。

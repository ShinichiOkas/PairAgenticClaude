# BUG-20261102-01: ペア固有 skill の本文にプロジェクト固有名が大量漏出（昇格ゲート欠如）

- 起票日: 2026-11-02
- 状態: open
- 重要度: 高（ペア固有層の設計目的が崩れている・横断資産がノイズ化）
- 分類: skill-governance / 昇格ゲート欠如
- 対象: `~/.claude/pair-agent/skills/`（ペア固有 skill 層）、上流は `retrospect` / `skill-survey` / `skill-learning` の昇格基準

## 症状（見たことだけ）

ペア固有 skill は「師匠の判断基準・好み・用語・境界線（プロジェクト横断で有用なもの）」を置く層のはず。だが本文にプロジェクト固有名（mnemo・ray・ellm・proxy・wiseman・logicparser・AgenticWorkspace 等）を抱えた skill が過半を占める。

## 実測・証拠（2026-11-02 計測）

計測対象: `C:\Users\0000950207\.claude\pair-agent\skills\*.md`

| 区分 | 件数 | 比率 |
|---|---|---|
| ペア固有 skill 総数 | 650 | 100% |
| 固有名を含む skill | 501 | 77% |
| └ frontmatter（source_sprint 等 出所タグ）のみ=許容 | 74 | 11% |
| └ **本文に固有名が実際に漏出** | **427** | **66%** |

固有名別の本文出現ファイル数（単語境界一致）:
- mnemo: 301 / ray: 74 / ellm: 73 / logicparser: 53 / wiseman: 39 / proxy: 38 / ellm-proxy: 31 / rex: 19 / aided: 9 / whisper: 8 / lucianke: 4

ファイル名からして固有名プレフィックスの skill（ペア固有層に居るが定義上プロジェクト固有）: 16 件以上
- 例: `aided-gui-left-pane.md`, `lucianke-code-analysis.md`, `a2a-sdk-v11-implementation-notes.md`, `ellm-behavior-is-decided-by-mnemo.md`, `ellm-json-only-instruction-returns-empty.md`, `mnemo-integration-form-decision.md`

本文漏出の具体例:
- `a-check-must-not-depend-on-the-environment.md`（原則名は普遍）本文に `Mnemo / LLMProviderlib（2026-09-09・Phase LPL）:` と固有実測が複数行
- `a-capability-hidden-in-a-parameter-is-not-a-capability.md` 本文に `Mnemo の skill_script_run(skill=…, script=…)`
- `a-broken-meter-contaminates-the-rules-built-on-it.md` 本文に `agent-<id>.meta.json の agentType`・`mnemo-* の型`

計測方法（再現手順）:
```
cd ~/.claude/pair-agent/skills
PYTHONUTF8=1 python -I -c "<frontmatter と本文を分割し、本文のみ固有名一致を数える集計>"
```
（frontmatter=`---` で囲まれた領域を出所タグとして除外。本文側で固有名が単語境界一致したものを『漏出』と数えた）

## 影響

- ペア固有層を他プロジェクトでロードすると、無関係なプロジェクトの実測がノイズとして混じる。
- 「原則は普遍・根拠は固有」が 1 ファイルに同居し、原則の再利用性が落ちる。
- 650 件という母数自体、プロジェクト固有の技術知見がペア固有へ吸い上げられ続けた結果（昇格の暴走）。

## 診断・解き方は書かない（直す役の仕事）

本票は症状と実測のみ。原因の切り分け・修正方針は直す役が決める。

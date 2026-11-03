# BUG-20261103-09: active の skill の本文に固有名が残る（分類表では 244 件中 242 件）

- 起票日: 2026-11-03
- 状態: open（処置はユーザーの判断待ち・TODO 10c。判断が出てから直す役を並列で起こす）
- 重要度: 中（active は CLAUDE.md が「ペア固有 Skill（`~/.claude/pair-agent/skills/`）」として読ませる置き場。固有名が本文に入ると、原則として読まれる）
- 分類: skill-governance / 規則（GOVERNANCE.md）との対応
- 対象: `~/.claude/pair-agent/skills/`（active・244 件）。実例 1 件: `file-bug-ticket-for-unrelated-discovery.md`（maturity: confirmed・commit 26dd56b）
- 規則の文面（`~/.claude/pair-agent/GOVERNANCE.md`・commit 58af9a5）:
  - 6 行（経緯）: 「650 件まで膨らみ、本文にプロジェクト固有名が漏れた skill が過半（390 件）を占めた」
  - 17 行（§1 active の判定手続き・条件 1）: 「固有名を全部消しても、師匠の判断／普遍原則として過不足なく成立する」
  - 24 行（§1 project の判定手続き）: 「固有名を消すと中身が成立しない／別プロジェクトでは無意味」
  - 64 行（§5 項目 3）: 「固有名を本文に書いた skill を active（`skills/`）に置かない。固有実測は根拠の例として最小限に留め、核は普遍原則で書く。」
  - 「最小限」は 64 行の 1 箇所にだけ出る。その文に数値も判定の手順も無いため、どこまでの固有名が許されるかは文面から決まらない。

## 症状・実測（2026-11-03・見たことだけ）

- 分類表（`.pair-agent/governance/skill-classification-20261103.tsv`・commit 22d50d9・列 5 `proper_nouns`）の記載。列は分類の際に付けたもので、件ごとに本文と照合してはいない。
  - active は 244 件。列 5 に固有名の記載がある（空と「なし」以外）のは 242 件。空は `minimal-io-roundtrip-first` の 1 件、「なし」は `file-a-ticket-instantly-and-fix-in-parallel` の 1 件。
  - 列 5 の名前の出現数（active 内・カンマ区切りの完全一致。行数と同数）: Mnemo 130・ray 38・LogicParser 18・AgenticWorkspace 18・AIdedArchitecture 14・TDLThemeDB 12・ellm-proxy 11・rex 10・MSTenantMCP 9。
  - 列 5 には、プロジェクト名のほかに、ファイル名（例: `measure_agent_usage.py`）や Phase 名（例: `Phase OBS`）も入っている。
- 実例 `file-bug-ticket-for-unrelated-discovery.md`（計数は Grep と Bash〈grep・wc〉で行った。この票を作る作業では、この skill を Read・Edit・Write していない）:
  - 行 1〜10 は frontmatter。行 4: `maturity: confirmed`。
  - `Mnemo|Cowork|SharePoint` を含む行は 5 行（9・31・34・36・38）。出現数は Mnemo 5・Cowork 3・SharePoint 1（大文字小文字を区別）。行 40 以降に 3 語は無い（全 86 行）。
  - 行 9（frontmatter 内）と行 31（承認の文）: 「承認」と `Mnemo cowork-defects-20261022` を含む。
  - 行 14（改訂 2026-10-27）と行 26（改訂 2026-10-22）: 「この節が下の本文より優先する」を含む。3 語は行 14 には出ない。
  - 行 34・38: 「Cowork の欠陥」。行 36: 「Mnemo の `mnemo-file-defect`」「Mnemo の票 4 本」。
  - 行 38（Why 欄）: 「Mnemo の SharePoint の Cowork」の事例と「9 件」の記述。

## 再現手順

1. 分類表の固有名の欄を数える: `awk -F'\t' 'NR>1 && $2=="active" && $5!="" && $5!="なし" {n++} END {print n+0}' .pair-agent/governance/skill-classification-20261103.tsv` → 242
2. `file-bug-ticket-for-unrelated-discovery.md` を Grep（パターン `Mnemo|Cowork|SharePoint`・行番号付き・`-o`）で数える → 5 行・計 9 語（Mnemo 5・Cowork 3・SharePoint 1）

注: この skill を Read・Edit・Write で開くと、計装（PostToolUse・`tools/log_skill_ref.py`）が本番ログ `usage/skill-refs.jsonl` に記録を入れる。確認は Grep か Bash で行う。

## 影響（事実）

- 分類表の記載では、active の 242 件に固有名がある。ただし件ごとの本文照合は未了のため、242 件すべてが規則に反するかは、この票からは決められない。
- 「最小限」の線（本文に残してよい固有名の範囲）が文面で定義されていないため、規則の適用が件ごとに決まらない。
- 実例の 3 語は、frontmatter（行 9）と「改訂 2026-10-22」の節（行 26 から。終わりは未確認）の中（行 31・34・36・38）に出る。行 14（改訂 2026-10-27・原則の宣言の引用）には出ない。行 40 以降には 3 語は無い。

## 証拠

- 分類表（commit 22d50d9）の列 5。上の awk の出力（active 244・固有名あり 242・空 1・なし 1）。列 5 の区切りは `,`（例: `Mnemo,measure_agent_usage.py,audit_agent_compliance.py`）。
- Grep（`-n -o`）の出力: 3 語は行 9・31・34・36・38（Mnemo 5・Cowork 3・SharePoint 1）。「改訂 2026-10-2[27]」と「この節が下の本文より優先する」は行 14・26。「承認」は行 9・31（各 2 回）。「Cowork の欠陥」は行 34・38。「9 件」は行 38。
- `GOVERNANCE.md` の 6・17・24・64 行（上の引用。Read で確認）。「最小限」は 64 行のみ。
- 本番ログ `usage/skill-refs.jsonl` は 0 バイト（MD5 D41D8CD9…・2026-11-03 の計測）。

## 対処

- 未着手。処置の判断はユーザー（TODO 10c）。判断に要るのは次の 2 つ:
  1. 「最小限」の線: 本文に残してよい固有名の範囲。
  2. 線を超えた skill の扱い: project へ移す／本文から固有名を抜く（名前剥ぎは中止済み）／規則の文面を改める、のどれか。
- 推奨（未決の判断の材料）: 「最小限」は「根拠の 1 行にだけ固有名を置いてよい」と具体化する。原則の文は固有名を置かない。線を超えた skill は、固有名を抜くより、固有の実測ブロック（「改訂 2026-10-22」の節）を project へ移す。原則と 2026-10-27 の宣言の引用は active に残す。
- 判断が出たら、直す役を並列で起こし、件ごとに本文を照合して直す。

## 未確認

- 分類表の列 5 が本文を正しく反映しているか（件ごとの本文照合は未了）。
- 「固有名」の定義（プロジェクト名だけか、Phase 名・ファイル名も含むか）。この票では決めない。
- Mnemo・Cowork・SharePoint 以外の固有名の、`file-bug-ticket-for-unrelated-discovery.md` 内の出現数（未計数）。
- 行 30 の内容（未確認）。「改訂 2026-10-22」の節の終わり（39 行と推定・未確認）。
- `~/.gemini/config/pair-agent/skills/` 側に同じ型があるか（未確認）。

# BUG-20261124-11: ペア固有 Skill・叱責記録・ビジョンが、ほかの PC へ配られない

- 起票日: 2026-11-24
- 状態: fixed（2026-11-24。対処は末尾）
- 重要度: 高（師匠の規則は全プロジェクト・全セッション・全 PC が対象。配り道が働かず、PC ごとに持つ Skill が違う）
- 分類: 配布 / install
- 対象: `install.bat`・`install.sh`・`manager/pamgr/mapping.py` の `pair-skills` 項目

## 症状・実測（見たことだけ・2026-11-24）

- `install.bat`・`install.sh` は `~/.claude/pair-agent/skills`・`vision`・`corrections` と `~/.gemini/config/pair-agent/` の同名フォルダを `mkdir` するだけで、`git submodule update --init` も `external/pair-agent-skills` の中身の写しもしない。
- 配り道として書いてあるのは `manager/pamgr/mapping.py` の `pair-skills` 項目だけ（src `external/pair-agent-skills`・globs `*.md`・dest `pair-agent/skills`）。glob は再帰しない。
- リポジトリ `ShinichiOkas/pair-agent-skills`（pin 2858d54）の実体は、根に `GOVERNANCE.md`、フォルダ `skills/`（281 件の .md ほか）・`corrections/`（181）・`vision/`（130）・`archive/`（339）・`skill-library/`・`template/`・`tools/`。根の直下の `*.md` は `GOVERNANCE.md` の 1 件だけ。つまりこの項目が届けるのは `GOVERNANCE.md` を `pair-agent/skills/GOVERNANCE.md` へ 1 件（置き場も違う）。`skills/`・`corrections/`・`vision/` は配り道が無い。
- `manager/pamgr/survey.py`（マスターの調査）と `generalize.py`（昇格先）も `external/pair-agent-skills/*.md` を見ており、実体の `skills/` を見ていない。
- 作業ツリー `S:\work\develop\PairAgenticClaude` では `external/pair-agent-skills` が空（gitlink のみ。`git submodule status` の先頭が `-`）。
- 1 台の PC（ANCIENT）の `~/.claude/pair-agent`（remote の無い git）と上流 2858d54 を、読むだけで比べた:
  - skills: 上流 281 件。PC に無い 246・同じ 2・違う 33（うち改行だけの違い 6）。PC だけにある物を含め PC の skills は 597 件。
  - corrections: 上流 181。PC に無い 178・同じ 2・違う 1。
  - vision: 上流 130。PC に無い 130。
  - 違う 27 件は中身が違う（PC 側が新しい版・古い版の両方があり得る）。

## 再現手順

1. 空のホーム（`USERPROFILE`／`HOME` を空フォルダへ）で `install.bat`／`install.sh` を走らせる。
2. `~/.claude/pair-agent/skills`・`corrections`・`vision` は空のまま。

## 影響（事実）

- 上流に載せた Skill・叱責記録・ビジョンは、手でコピーしない限り ほかの PC に届かない。

## 対処（2026-11-24）

- `tools/sync_pair_assets.py` を新設。`install.sh`・`install.bat` が `git submodule update --init external/pair-agent-skills` のあとに呼び、`skills/*.md`・`corrections/*.md`・`vision/*.md` を両ホームの `pair-agent/` の同名フォルダへ、`GOVERNANCE.md` を `pair-agent/GOVERNANCE.md` へ写す（`archive/` ほかは配らない）。
- 写し先の既存は減らさない: 無ければ写す・同じ（改行差は無視）なら何もしない・違うときは「写し先が上流の履歴にある過去の版と一致」（上流の古い写し）のときだけ更新、それ以外は触らず名前を出す。2 回目は変化なし。
- 取得も写しも失敗したら、残りの手順を終えたうえで install が終了コード 1。
- `manager/pamgr/mapping.py` の配布対応を 4 項目（skills・corrections・vision・GOVERNANCE）に直し、`survey.py`・`generalize.py` の参照先も `skills/` へ。
- 試験: `tests/test_sync_pair_assets.py`（一時のホーム・一時のリポジトリで install.sh・install.bat を実走）。
- 実測（読むだけの dry-run・ANCIENT）: `~/.claude/pair-agent` へは 555 件写り・5 件更新・22 件は PC 側が違うため据え置き。

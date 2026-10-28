# バグ票: skillimport.bat --force を Antigravity 側だけに効かせられず、Claude 側の Skill まで上書きされる

- 起票: 2026-10-28（Antigravity 側の置き場の移行中に見た）
- 状態: open

## 見たこと（症状と実測だけ）

師匠の指示「Geminiはそれほど育ってないので丸ごと置き換えでいいです」（Antigravity 側だけの置き換え）に従い、`skillimport.bat --force` を実行した。出力:

```
[skillimport] Done.
  Claude:      imported 0 / overwrote 77 / skipped 0
  Antigravity: imported 0 / overwrote 77 / skipped 0
```

- Claude 側 `~/.claude/pair-agent/skills/` の 77 件も上書きされ、そのうち 32 件は中身が変わった（グローバル版の provenance・固有の経緯が、`examples/skills/` の汎化版で置き換わった）
- 片側だけを対象にするオプションは `skillimport.bat` の usage に無い（`--list` / `--force` / 引数なし の 3 つ）
- Claude 側は `~/.claude/pair-agent` の git から `git checkout -- skills` で戻した（戻した後 `git status` クリーン）

## 再現手順

1. `~/.claude/pair-agent/skills/` に、`examples/skills/` と同名で中身の違う Skill がある状態にする
2. Antigravity 側だけ置き換えたいので `skillimport.bat --force` を実行する
3. Claude 側の同名ファイルも上書きされる

## 壊してはならないもの

- 引数なし（未導入のものだけ・既存は保護）の既定の挙動
- `home-claude/skills/skill-survey/SKILL.md` §8 の「`--force` は師匠が育てたスキルを上書きするので、師匠が明示したときだけ」

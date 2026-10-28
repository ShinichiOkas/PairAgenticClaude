# バグ票: Antigravity 側のペア固有 Skill の置き場が、スクリプトと文書で 2 か所に割れている

- 起票: 2026-10-28（スキルサーベイの配布中に見た）
- 状態: open

## 見たこと（症状と実測だけ）

| どこ | 書いてある Antigravity 側の置き場 |
|---|---|
| `install.bat` | `ANTIGRAVITY_CONFIG=%USERPROFILE%\.gemini\config`（skills・pair-agent/tools・template をここへ配る） |
| `install.sh` 6 行目 | `ANTIGRAVITY_CONFIG="${HOME}/.gemini/config"` |
| `skillimport.bat` | `ANTIGRAVITY_DST=%USERPROFILE%\.gemini\antigravity\pair-agent\skills` |
| `home-claude/skills/skill-survey/SKILL.md` §8 | 「配布先は `~/.claude/pair-agent/skills/` と `~/.gemini/antigravity/pair-agent/skills/` の両方」 |
| `home-claude/CLAUDE.md`「学習データの場所」 | `~/.gemini/config/pair-agent/`（Google Antigravity） |

このマシンの実測（2026-10-28、`skillimport.bat` 実行後）:

- `~/.gemini/config/pair-agent/skills/` … 0 件
- `~/.gemini/antigravity/pair-agent/skills/` … 78 件（今回の skillimport で 32 件を新規に書いた）

## 再現手順

1. `skillimport.bat` を実行する
2. `~/.gemini/config/pair-agent/skills/`（CLAUDE.md が Antigravity の学習データの場所とする所）を見る → 増えていない
3. `~/.gemini/antigravity/pair-agent/skills/` を見る → こちらに入っている

## 壊してはならないもの

- 師匠のマシンの `~/.gemini/antigravity/pair-agent/skills/` にある 78 件（師匠が育てたものが同居している可能性がある）。移す・消すは師匠の判断
- `skillimport.bat` の「既存は上書きしない」既定

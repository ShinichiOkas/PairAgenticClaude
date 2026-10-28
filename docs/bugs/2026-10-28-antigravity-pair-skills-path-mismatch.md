# バグ票: Antigravity 側のペア固有 Skill の置き場が、スクリプトと文書で 2 か所に割れている

- 起票: 2026-10-28（スキルサーベイの配布中に見た）
- 状態: fixed

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

## 直した内容（2026-10-28）

- 正の置き場: `~/.gemini/config/pair-agent/skills/`（`install.bat`/`install.sh` の `ANTIGRAVITY_CONFIG` と `home-claude/CLAUDE.md`・`GEMINI.md`・`rules/pair-agent-core.md` が揃っている方）。
- 直したもの: `skillimport.bat`（`ANTIGRAVITY_DST` と usage 表示）、`home-claude/skills/skill-survey/SKILL.md` §8、`home-claude/skills/skill-learning/SKILL.md`「保存先」。
- 足したテスト: `tests/test_antigravity_pair_skills_path.py`（追跡ファイル内の Antigravity ペア Skill の置き場が 1 種類だけ・skillimport が install と同じ・CLAUDE.md と GEMINI.md が同一）。
- コミット: 本票と同じコミット。

## 移行（2026-10-28 実施済み）

師匠の判断（原文）: 「Geminiはそれほど育ってないので丸ごと置き換えでいいです」

- 旧置き場の skills 78 件・corrections 1 件を `~/.gemini/config/pair-agent/` の同名ディレクトリへ移した（移す前の新側は空）
- `skillimport.bat --force` で配布物の最新版に置き換えた（Antigravity 側 overwrote 77）
- 旧置き場 `~/.gemini/antigravity/pair-agent/` を削除した（残っていたのは古い template の 4 件だけ。新側の template は install 済みの新しい版）
- ⚠ `--force` が Claude 側の 77 件も上書きした（32 件は中身が変わった）→ `~/.claude/pair-agent` の git から戻した。片側だけにできない件は `2026-10-28-skillimport-force-cannot-target-one-side.md` に起票

## 移行手順（参考・実施前に書いたもの）

旧置き場 `%USERPROFILE%\.gemini\antigravity\pair-agent\skills\`（78 件）は何も触っていない。移すなら:

1. `%USERPROFILE%\.gemini\config\pair-agent\skills\` を作る（install 済みなら既にある）。
2. 旧置き場の `*.md` を新置き場へコピーする（`robocopy <旧> <新> *.md /XC /XN /XO` で新側の既存を上書きしない）。師匠が育てた分は同名衝突を目視してから。
3. 新側に揃ったら旧置き場を退避（リネーム）し、しばらく使って問題なければ消す。
4. `skillimport.bat --list` で新置き場に対する差分を確認する（以後の取り込みは新置き場へ入る）。

# バグ票: 上流の rules/pair-agent-core.md が pamgr の 6378f12 で別版に置き換わり、手元の規則の節が上流に無い

- 起票: 2026-11-23（師匠の宣言 2026-11-23 を上流へ入れる作業の中で見た）
- 状態: open

## 見たこと（症状と実測だけ）

- `git show 6378f12 -- home-claude/rules/pair-agent-core.md`（pamgr: 点検で反映・2026-11-17）で、上流の `home-claude/rules/pair-agent-core.md` が、それまでの版（`6a20850`）から別の版（`93154ba`）に置き換わった。コミットの本文の「配った」の行には、このファイルの名前が無い
- 置き換わった版（`93154ba`）には、次の節が無い:
  - 「絶対的規範（2026-11-01）」の IMPORTANT の塊
  - 「応答は 1 分以内・指示していないことは裏の役に（2026-11-05）」の IMPORTANT の塊（上流 `e82e524` で入れたもの）
  - 「セッションの始め（主エージェント）— 自分から始めない」（上流 `eb2946a` で入れたもの）。代わりに旧い「セッション開始時の手順（対話側）」がある
- 置き換わった版には、手元（`~/.claude/rules/pair-agent-core.md`）に無い文がある: 運転方針の「いつ終わるかを時刻で宣言し…（2026-11-09）」「進捗の報告には毎回、残りと見込みを付ける」。呼び方が「師匠」でなく「ユーザー」・「主エージェント」でなく「対話側」
- 2026-11-23 時点で、手元 `~/.claude/rules/pair-agent-core.md` と上流の差は 55 行足し・37 行消し。`~/.gemini/config/rules/pair-agent-core.md` は `6a20850` とほぼ同じ（手元との差 4 行）
- 2026-11-23 の作業では、上流の版はそのまま残し、11-05 と 11-23 の IMPORTANT の塊（手元と同じ文）だけを足した

## 再現手順

1. `git diff --no-index home-claude/rules/pair-agent-core.md ~/.claude/rules/pair-agent-core.md`
2. `git log --format='%h %s' -- home-claude/rules/pair-agent-core.md`

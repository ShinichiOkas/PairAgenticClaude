# スキル統治（方針 A）の最終報告

- 日付: 2026-11-04
- スプリント: TODO-20261103-skill-governance（進捗表: `.pair-agent/todo/TODO-20261103-skill-governance.md`）
- 方針の正本: `~/.claude/pair-agent/GOVERNANCE.md`（live の commit 58af9a5）

## 1. 結論

- 仕分けは完了した。648 件 = active 244 + project 66 + archive 338。
- project の 66 件のうち 51 件は 10 対象へ移送済み。残り 15 件は 5 対象で保留（判断待ち）。
- 止まっているのは 4 件: TODO 10・10b（保留 15 件）、10c（BUG-09 の処置）、12（観測データ待ち）。判断は (a)–(g)（§3）。
- 並列で走らせた BUG-10（検証テストを version 管理に入れる）は TODO 15 で完了した（§6）。

## 2. 数

| 区分 | 件数 | 行き先 |
|---|---|---|
| active | 244 | ペア固有 `skills/`（不変の原則だけ） |
| project | 66 | 移送 51（10 対象）・保留 15（5 対象） |
| archive | 338 | ペア固有 `archive/`（ライブは 339 .md = 338 + README.md） |
| 合計 | 648 | |

整合（2026-11-04 に実測）:
- 244 + 66 + 338 = 648
- ライブ `skills/` = 259 = active 244 + 保留 15
- 244 + 15 + 51 + 338 = 648

## 3. 判断一覧

ユーザーにしか決められない方針・設計の判断。推奨は 1 行。

- **(a) LogicParser（9 件）**: main が origin より 54 コミット先行し、未 push。推奨: 54 件の中身を確認してから push し、その後 9 件を移す。
- **(b) LLMWorkflow（1 件）**: 同名 stem の内容が 2 つある（移し先 2068 B・記録日 2026-05-15 ／ ライブ 1750 B・初版 1ba3f5a）。推奨: 移し先の 2068 B を正本とし、上書きしない（`.pair-agent/governance/decisions-20261103.md` §4）。ライブの 1750 B は移さず、捨てるかをユーザーが決める。先行 16 コミットも (a) と同じく中身を見てから push する。
- **(c) ELLM分析（1 件）**: remote が無い。推奨: remote を作って登録してから移す。それまで保留。
- **(d) TDLPortfolio（1 件）**: remote が無く、未コミット変更が 7 件ある。推奨: remote を登録し、未コミット 7 件には触れず stem だけを commit する。
- **(e) MSTenantMCP（3 件）**: 作業ブランチは feat/mikke-search（既定は main）。推奨: 移し先を main にして 1 コミット・push する（feat 側だけに置くと既定ブランチから辿れない）。
- **(f) BUG-20261103-09（TODO 10c）**: active の本文に固有名がある（244 件中 242 件が固有名入りの証拠行を持つ）。推奨: 「最小限」を「固有名を含んでよい証拠行 1 行」と定め、原則の本文は固有名なしにする。2026-10-22 のブロックは project へ移す。原則と 2026-10-27 の原文引用は active に残す。
- **(g) TODO の見出し 1 行**（`# TODO: スキル統治（方針 A）の未完了分`）: 規約「TODO 以外を書かない」に照らすと例外になる。助言を反映して残してある（前の区間の記録）。推奨: 残す（[TODO]/[DONE] の読みを妨げない）。外すなら 1 行削る。

## 4. 止まっているもの

| TODO | 状態 | 止まっている理由 | 次の一手 |
|---|---|---|---|
| 10 | [TODO] | 保留 15 件が残っている | 10b の判断後 |
| 10b | [TODO] | 判断 (a)–(e) | 判断が出たら対象ごとに移す（§7） |
| 10c | [TODO] | 判断 (f) | 判断が出たら進める |
| 12 | [TODO] | 観測データが無い。本番ログ `usage/skill-refs.jsonl` は 0 バイトのまま | 観測が貯まってから |

## 5. 移送の内訳（51 件・10 対象）

| 対象 | 件数 | 移し先の commit（remote・branch） | ライブの除去 commit |
|---|---|---|---|
| Mnemo | 32 | 338c9ddc | afe0f6f |
| ray | 5 | 0c7bd87（origin/master） | a28bf66 |
| ellm-proxy | 3 | 1b9d11e | d5e570a |
| AIdedArchitecture | 3 | 9ecedc7（origin/claude/confident-goldberg-ekdt34） | e76dd1b |
| PairAgenticClaude | 2 | 9e0a930（origin/main） | 40ee403 |
| LLMProviderlib | 2 | d6b80c4 | 1c8373e |
| AgenticWorkspace | 1 | 1440acc | a279710 |
| mu | 1 | de1cb05 | a846100 |
| InfoGather | 1 | e6e1672 | 6fc923b |
| rex | 1 | c21d84e | 6ef69bb |
| 合計 | 51 | | |

- 20 の hash（移し先 10・ライブの除去 10）は 2026-11-04 に存在を確認した。移し先のうち 3 件（0c7bd87・9ecedc7・9e0a930）は、記録した branch に含まれることも確認した。
- 未コミットの変更には触れていない: InfoGather 6 件、ellm-proxy 14 件、rex 1 件。
- ray の local master は origin/master より 4 コミット先行している（3c3693e・38d7a94・9a102c8・ce56805。作者は Shinichi.Oka）。未 push で、このスプリントは push していない。前の記録は 3 件だったが、実測は 4 件（3c3693e を含む）。

## 6. 直したもの・検証

| 件 | 内容 | 状態 | commit |
|---|---|---|---|
| BUG-04 | `skills/` の 157 ファイルで、active 本文の非 active 宛 `[[stem]]` 359 箇所を `` `stem` `` に書き換えた | fixed | 7f7fff1 |
| BUG-05 | 未解決リンク（active 38 ファイル・保留 9 ファイル）。計測ツール `tools/check_skill_links.py` を追加 | fixed | 57fbfbd・44f36f0・582a627 |
| BUG-06 | 一括読み（同じセッションで 10 秒に 10 回以上）を利用に数えない | fixed | b3a42ed・eea9462 |
| BUG-07 | `check_skills` の capabilities 欠落 | fixed | f3bc532 |
| BUG-08 | 保守の読み（同じセッションでの書き込みと読み）を利用から外す（票 fddf05b） | fixed | bdb1db9 |
| BUG-09 | active の本文に固有名（票 57de5ce） | open（TODO 10c） | — |
| BUG-10 | 検証テストが version 管理に無い（票 69ba801） | fixed（TODO 15） | 7aedb6e（live）・db5622e（main） |

検証:
- 計装 `tools/log_skill_ref.py`: 23 検査 PASS（移送前の scratchpad 版）。
- BUG-06 のサイドカー集計: ALL PASS（scratchpad 版）。scratchpad 版は本体の rollup（`skill_usage_rollup.py`）を `--log` で実行し、旧名のサイドカー（`usage/skill-refs.maintenance-20261103.jsonl`・108 行）を読んでいた。複製ではない（前の記述は誤り。§9）。version 管理版（`tools/tests/test_bug06_sidecar.py`）も本体を `--log` で実行し、合成ログを読む。
- BUG-08 の保守の読み除外: 38 検査 PASS（scratchpad 版）。
- `test_bug06.py`（古い版）: FAIL 2。本番ログを前提にしていて、移していない。
- version 管理版（live `tools/tests/`・commit 7aedb6e）: `test_skill_ref.py` TOTAL 23・FAILED 0・exit 0。`test_bug06_sidecar.py` ALL PASS・exit 0。`test_bug08.py` TOTAL 38・FAILED 0・exit 0。3 本とも 2026-11-04 に対話側が live の `tools/tests/` から再実行し、exit code を実測した。感度（壊れた実装を落とすか）は修正役の報告による。対話側では再実行していない。

## 7. 並列化について

- 並列にできるものは並列にした。BUG-10 の修正役は、この報告の作成と同時に走らせた。
- 残りは判断か観測の待ちで、並列にしても早くならない。
- 保留 15 件の移送（10b）は、対象ごとに並列にできる。5 対象はそれぞれ別の repo だから。
- 共有するのは live のサブモジュール参照と main の参照更新だけ。ここだけ 1 本ずつ（排他）にする。commit と push は対象ごとに残して、戻せる形を保つ。
- 直列に進めたのは、commit と push の順序を崩さないため。判断が出たら並列に進める。

## 8. 事後報告（取り消せる変更）

振り返り（スキル確認）の自動登録は 5 件:
- 450b429（main・新規・project・forming）`usage-count-excludes-maintenance-reads.md`。根拠は AI の観測（BUG-08）。
- 40d3481（live）: confirmed の `own-inference-is-not-measured-fact.md` に、AI の観測による追記 10 件を入れた。maturity は confirmed のまま。retrospect の規則（AI の観測だけの候補は forming）に照らすと forming へ下げるのが沿う。ここでは変えていない。下げるかどうかはユーザーが決める。取り消すなら追記を消す。
- d5568fb（live・forming）: `harness-exit-code-must-reflect-failure.md` に追記 14 件。
- 26dd56b（live・confirmed）: `file-bug-ticket-for-unrelated-discovery.md` を改訂。根拠はユーザーの宣言 2026-10-27 の原文。
- a4600d8（live）: confirmed の `verified-means-it-ran-not-that-it-ran-as-intended.md` に、AI の観測による追記 6 件を入れた。maturity は confirmed のまま（上と同じ規則に照らすと forming。扱いはユーザーが決める）。取り消すなら追記を消す。

グローバル設定 `C:\Users\0000950207\.claude\settings.json`:
- line 95（PostToolUse の matcher）: `"Read|Skill"` → `"Read|Skill|Edit|Write|MultiEdit"`。BUG-08 の計装の修正の過程で、修正役がブリーフの範囲外で変えた。ここで開示する。戻すなら line 95 だけを `"Read|Skill"` にする。
- line 81（`"model"`）: 現在は `"opus"`。scratchpad のバックアップ（`bug08\settings.json.bak`・21:47 時点）は `"claude-haiku-5-5"`。どちらが意図か、いつ誰が変えたかは未確認。ユーザーに確認してほしい。

live の `stash@{0}`（"WIP: denationalize in-place"・2026-11-02）は残した。触っていない。

## 9. 訂正の記録（このスプリントで直したこと）

- サイドカーの行数: 14 と書いたが、実測は 17。直した。
- BUG-06 の推論「skills/ の外のファイルも読まれていた」は誤り。取り下げた。
- 4bfe0d0 を TODO 10 の commit と書いたが、2026-11-02 の live commit で TODO 10 とは別。
- LLMWorkflow の「ライブの方が新しい（2026-08-06）」は git で裏付けられなかった。取り下げた（17c9694・push 済み）。
- 「M7 はライブの履歴のどこにも無い」は誤り。1ba3f5a がライブの別ファイルに M7 の本文を入れている。
- 7f7fff1・44f36f0・582a627・57fbfbd を main の commit と書いたが、ライブの commit。
- BUG-09 の初回の数え方は部分一致で膨らんでいた。完全一致で数え直して 242。
- dangling-links の TSV を読まずに cp で上書きした。再生成した（8e86893）。
- 修正役が「main リポジトリには書くな」を読み違え、BUG-07 の票を更新せずに戻った。票を更新した（a01916b）。
- 計測が skills=0 を返したのは ROOT が scratchpad を指していたため。再計測で 259。
- ray の未 push commit: 前の記録は 3 件、実測は 4 件（§5）。
- 前の区間では、スキル本文が再生された tool 結果の中に見えた。新しいスキルの Read は無く、本番ログは 0 バイトのまま。
- BUG-10 の票（13・25 行）と BUG-08 の票 62 行は、旧 `test_bug06_sidecar.py` を「本体の rollup の複製」「`-08` のサイドカーを読む」と書いていたが、誤り。原本は本体の rollup を `--log` で実行し、旧名のサイドカー（`usage/skill-refs.maintenance-20261103.jsonl`・108 行）を読んでいた。225ad0b で両票を訂正した。

## 10. 確かめていないこと

- フック入力の形式（`cwd`・`agent_type`）が実際のフック入力と一致するか（BUG-06 の票と同じ未確認）。
- BUG-07 の検証方法（票に無く、検証テストも無い）。
- settings line 81 の model の出所（§8）。
- GCM が push を拒否する原因。回避形（gh 経由）で push している。原因は未確認。
- LLMWorkflow（`skills/user-builds-workflows-ai-fixes.md`）: ライブの 1750 B 版は、初版 1ba3f5a（1752 B・2026-11-02）に BUG-05 の 1 箇所の書き換え（44f36f0・2026-11-03。`[[prefill-type-defaults-on-add]]` を `` `prefill-type-defaults-on-add` `` に）を加えたもの（差 2 B）。移し先の 2068 B 版が、いつどの作業で書かれたかは記録にない（2026-05-15 は recorded_at の値）。
- 観測データが 0 件のため、参照ベースの淘汰（TODO 12）の効き方は未検証。
- BUG-08 の限界: 保守の読みは、書き込みイベントが無いと事後に除外できない（チケット時点の読み）。票は、同じ 17 行のサイドカーで malformed が 2 → 0 に変わったことと、変わった集計行（`file-bug-ticket-for-unrelated-discovery` の read_count 2 → 0）を記録している。malformed だった 2 行が何かは票に書かれていない。この報告では説明しない。

## 11. 参照（絶対パス）

- 報告（本書）: `C:\Users\0000950207\work\PairAgenticClaude\.pair-agent\governance\report-skill-governance-20261103.md`
- 進捗表: `C:\Users\0000950207\work\PairAgenticClaude\.pair-agent\todo\TODO-20261103-skill-governance.md`
- 分類表: `C:\Users\0000950207\work\PairAgenticClaude\.pair-agent\governance\skill-classification-20261103.tsv`
- 判断記録: `C:\Users\0000950207\work\PairAgenticClaude\.pair-agent\governance\decisions-20261103.md`
- 保留表: `C:\Users\0000950207\work\PairAgenticClaude\.pair-agent\governance\todo10-held-20261103.md`
- 票: `C:\Users\0000950207\work\PairAgenticClaude\.pair-agent\bugs\BUG-20261103-08-maintenance-reads-counted-in-production.md`、`...\bugs\BUG-20261103-09-active-skill-carries-proper-nouns.md`、`...\bugs\BUG-20261103-10-verification-tests-not-versioned.md`
- 方針: `C:\Users\0000950207\.claude\pair-agent\GOVERNANCE.md`
- 本番ログ（0 バイト）: `C:\Users\0000950207\.claude\pair-agent\usage\skill-refs.jsonl`
- サイドカー（17 行）: `C:\Users\0000950207\.claude\pair-agent\usage\skill-refs.maintenance-20261103-08.jsonl`
- 設定: `C:\Users\0000950207\.claude\settings.json`
- scratchpad（検証の結果）: `C:\Users\000095~1\AppData\Local\Temp\claude\778e87595a7d3e63\0e4ebe9b-f99a-4cc5-bcdc-a7888f59db43\scratchpad\final3\`

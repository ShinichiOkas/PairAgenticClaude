# Pair Agent L 構成 — アーキテクチャ・大規模改修成果物定義
# ★ 2026-10-27 改め（師匠の宣言『エージェントは代行しないならエージェントじゃない』ほか）: H3（検収）は止めない。
#   確かめ（実機・API・GUI の撮影・操作・DOM 読み）は 受入検査実施者 が自分で通し、師匠の検収は「閉じた状態で長く使って OK を出す」。
#   台本も stopAtGate で H3 を止めない。止めるのは方針・設計の判断（H1・H2）だけ（おまかせなら推奨で進めて事後報告）。
#
# 前提:
#   - 探針（Spike）によるフィジビリティ検証とリスク低減
#   - アーキテクトによるトレードオフと構造制約の明示（Tier 1モデル）
#   - 人間ゲート H1（合意）, H2（アーキテクチャ・仕様承認）, H3（検収）
#   - 残留リスク報告の集約と整合・同期
#
# 成果物パス: 最初から .pair-agent/ 配下の隔離保護パスに完全準拠

# ══════ 起点 ══════
要望 :
#   agent.path : .pair-agent/inbox/要望.md
用語資産 :
#   agent.path : .pair-agent/inbox/用語資産.md
既存システムの制約 :
#   agent.path : .pair-agent/inbox/既存システムの制約.md
実行環境 :
#   agent.path : .pair-agent/inbox/実行環境.md
変更の履歴 :
#   agent.path : .pair-agent/inbox/変更の履歴.md

# ══════ コア成果物 ══════
合意ドキュメント : 要望, 用語資産?
#   role    : 意図取得者
#   task    : elicit_intent
#   agent.path : .pair-agent/agreements/合意ドキュメント.md
#   blocks  : 実装物
#   gate    : H1
#   writes  : 合意ドキュメント
#   out     : スプリント合意とスコープ
#   post    : 師匠との協議に基づいて合意されている

探針結果 : 合意ドキュメント, 既存システムの制約?, 実行環境
#   role    : 探針実施者
#   task    : run_probe
#   agent.path : .pair-agent/assurance/探針結果.md
#   blocks  : 受入検査仕様
#   writes  : 探針結果
#   tools   : exec
#   out     : 実験結果とフィジビリティ
#   post    : 測定条件と実測値が記載されている

# ══════ アーキテクチャ —— 決定ループの段で 4 役に割る（案 A・2026-10-28） ══════
# 段の対応（AIdedArchitecture docs/method/03-decision-loop.md・10-method.md）:
#   スコープとドライバー … §3.1 ユースケースから始める（UC・境界・事前事後状態・区間・重み・関心事の出所）
#   理解モデルと課題     … S0〜S2（ミニマル定義 → 骨格 → 要求の割り付け → 課題の検出）
#   アプローチ文書       … S3（課題ごとの案・Pros/Cons・検証計画・判例）＝ 導出根拠（P8・§5「アーキテクチャアプローチ」）
#   アーキテクチャ       … S4・S7・ディスクリプション（決断・構造制約・トレードオフ）＝ 結論（P8・§5「ディスクリプション」）
# ⚠ 規約型 skill（ID・仮説の扱い・自由メモ）は 1 役にだけ装着し、ほかの役には post で掛ける。
#   同じ skill 名を複数の task に書くと、derive_roles.py の split_by_skill が 4 役を 1 役に戻す
#   （4 つの target は分離線を持たず同じ群に入る —— 実測: 安全軸の群1）
# ⚠ 決定ループの戻り（S7 → S2）は前版 dep で張らない。張ると検出条件（P-53）が毎回発火して静止しない。
#   戻りは 差し戻し指示（H2）か、アーキテクチャ の「未決」として次の周に渡す

スコープとドライバー : 合意ドキュメント, 既存システムの制約?, 差し戻し指示_v(k-1)
#   role    : アーキテクト（枠取り）
#   task    : design_architecture_frame
#   agent.path : .pair-agent/agreements/アーキテクチャ-スコープとドライバー.md
#   blocks  : 実装物, 受入検査仕様
#   writes  : スコープとドライバー
#   out     : 本質的機能の一言・目的の優先度・ユースケースと代表シーケンス・システムバウンダリーと境界課題・事前／事後状態
#   out     : 区間の品質特性シナリオ・重みのラベル・アーキテクチャドライバー（関心事の出所つき）
#   out     : 理由 ＋ 残留リスク
#   post    : 関心事（要求・品質特性・リスク）すべてに発生源のステークホルダが付いている
#   post    : 重みと「確定」は根拠の記録（合意ドキュメントの箇所）を指している。指せないものは仮説と書いている
#   post    : 設計の対象に ID が振られている。振った ID を変えていない・再利用していない
#   post    : 思いつき・未整理の矛盾を本体に書いていない（自由メモに置いた）

理解モデルと課題 : スコープとドライバー, 既存システムの制約?, 差し戻し指示_v(k-1)
#   role    : アーキテクト（構造導出）
#   task    : design_architecture_structure
#   agent.path : .pair-agent/agreements/アーキテクチャ-理解モデルと課題.md
#   blocks  : 実装物, 受入検査仕様
#   writes  : 理解モデルと課題
#   out     : ミニマル定義・骨格（論理コンポーネント＋関連）・要求の割り付け（インタフェース・予算・状態）・状態の三段
#   out     : 三つの基本ビュー（論理・実装・割り付け）と、割り付かない要素
#   out     : アーキテクチャ課題の一覧（所在・見つけたダイナミックなモデル・関わるドライバー）
#   out     : 理由 ＋ 残留リスク
#   post    : 骨格の要素はミニマル定義の語からだけ導かれている（既知製品の部品を持ち込んでいない）
#   post    : どこにも割り付かない要素・要求が、課題として起票されている
#   post    : 自分の出力は「仮説」で記録している。「確定」は根拠の記録を指すものだけ
#   post    : 思いつき・未整理の矛盾を本体に書いていない（自由メモに置いた）

アプローチ文書 : 理解モデルと課題, スコープとドライバー, 探針結果, 既存システムの制約?, 差し戻し指示_v(k-1)
#   role    : アーキテクト（案出し）
#   task    : design_architecture_approach
#   agent.path : .pair-agent/agreements/アーキテクチャ-アプローチ文書.md
#   blocks  : 実装物, 受入検査仕様
#   writes  : アプローチ文書
#   out     : 主要な課題ごとのアプローチ文書 —— 課題・所在・視点の異なる 3 案以上（分解しない案を含めて検討）・Pros/Cons
#   out     : 欠点の由来（手段由来／本質的な矛盾）・検証計画・判例・専門家回答（決定要因）
#   out     : 理由 ＋ 残留リスク
#   post    : 主要な課題それぞれに、視点の異なる案が 3 つ以上ある
#   post    : どの案にも「何を・どの方法で・いつ」検証できるかが書かれている
#   post    : 却下した案も消さずに残している（判例）
#   post    : 対立する関心事を片方の採用で終わらせていない（融合した案を検討している）
#   post    : 設計の対象に ID が振られている。振った ID を変えていない・再利用していない
#   post    : 思いつき・未整理の矛盾を本体に書いていない（自由メモに置いた）

アーキテクチャ : アプローチ文書, 理解モデルと課題, スコープとドライバー, 合意ドキュメント, 探針結果, 既存システムの制約?, 差し戻し指示_v(k-1)
#   role    : アーキテクト（決断）
#   task    : design_architecture
#   agent.path : .pair-agent/agreements/アーキテクチャ.md
#   blocks  : 実装物, 受入検査仕様
#   writes  : アーキテクチャ
#   out     : トレードオフの明示、構造制約
#   out     : 決断の一覧（採用した案・理由・実装者への must／must_not・アプローチ文書の ID）・未決事項（open:）
#   out     : アーキテクチャが仕様に課す制約
#   out     : 理由 ＋ 残留リスク（前段 3 つの残留リスクを引き継ぐ）
#   post    : トレードオフの代償が明記されている
#   post    : 構造制約が検査可能な形で書かれている
#   post    : 決断はそれぞれアプローチ文書の ID を指している（結論と根拠を分けている）
#   post    : 仕様に課す制約を、仕様作成者が読める形で列挙している
#   post    : 前段（スコープとドライバー・理解モデルと課題・アプローチ文書）の残留リスクを落としていない
#   post    : 設計の対象に ID が振られている。振った ID を変えていない・再利用していない
#   post    : 自分の出力は「仮説」で記録している。「確定」は根拠の記録を指すものだけ

仕様 : アーキテクチャ, 合意ドキュメント, 差し戻し指示_v(m-1)
#   role    : 仕様作成者
#   task    : write_specification
#   agent.path : .pair-agent/agreements/仕様.md
#   blocks  : 実装物, 受入検査仕様
#   gate    : H2
#   writes  : 仕様
#   out     : 外部契約と振る舞い仕様
#   post    : アーキテクチャの構造制約を守っている
#   post    : 判定可能な仕様として記述されている

受入検査仕様 : 仕様, 差し戻し指示_v(j-1)
#   role    : 受入検査設計者
#   task    : design_acceptance_tests
#   agent.path : .pair-agent/acceptance/受入検査仕様.md
#   blocks  : 実装物, アーキテクチャ, スコープとドライバー, 理解モデルと課題, アプローチ文書
#   writes  : 受入検査仕様
#   out     : 外部契約に基づく判定手続き
#   post    : 実装コードを見ずに書かれている

実装物_v(n) : 仕様, アーキテクチャ, 実装物_v(n-1), 差し戻し指示_v(m-1)
#   role    : 構築者
#   task    : build
#   agent.path : src/
#   blocks  : 受入検査仕様
#   writes  : 実装物
#   tools   : exec
#   out     : 仕様とアーキテクチャを満たす実装コード
#   post    : 構造制約と外部契約に準拠している

非回帰の合否 : 実装物_v(n)
#   by      : machine
#   task    : run_regression
#   agent.path : .pair-agent/assurance/非回帰の合否.md
#   writes  : 非回帰の合否
#   tools   : exec
#   out     : 全既存テストの合否
#   post    : 決定論的である。「既知の赤」で通さない

設計保証 : 仕様, アーキテクチャ, 実装物_v(n)
#   role    : 構築者
#   task    : assure_design
#   agent.path : .pair-agent/assurance/設計保証.md
#   blocks  : 受入検査仕様
#   writes  : 設計保証
#   out     : 構造制約の遵守根拠とエビデンス
#   post    : 外部から見えない内部整合性が検証されている

受入検査報告書 : 受入検査仕様, 非回帰の合否, 設計保証, 実行環境
#   role    : 受入検査実施者
#   task    : execute_acceptance_tests
#   agent.path : .pair-agent/acceptance/受入検査報告書.md
#   blocks  : 実装物, アーキテクチャ, スコープとドライバー, 理解モデルと課題, アプローチ文書
#   gate    : H3
#   writes  : 受入検査報告書
#   tools   : exec
#   out     : 合否判定結果
#   post    : ブラックボックスで検証されている
#   post    : 合否が二値で判定されている

差し戻し指示 : 受入検査報告書?, 非回帰の合否?, 仕様?, アーキテクチャ?, 合意ドキュメント?
#   by      : human
#   task    : adjudicate_rework
#   agent.path : .pair-agent/assurance/差し戻し指示.md
#   gate    : H3
#   writes  : 差し戻し指示
#   out     : 差し戻し先と修正指示
#   post    : 受け手はこれだけを見て修正に着手できる

残留リスク報告 : 仕様, 受入検査報告書, 設計保証
#   by      : machine
#   task    : aggregate_residual_risk
#   agent.path : .pair-agent/assurance/残留リスク報告.md
#   writes  : 残留リスク報告
#   out     : 未カバー領域と残存リスクの総括
#   post    : 各成果物の残留リスクが漏れなく集約されている

整合したドキュメント : 仕様, アーキテクチャ, 受入検査報告書, 実装物_v(n), 変更の履歴
#   role    : ドキュメント整合担当
#   task    : reconcile_documents
#   agent.path : docs/
#   writes  : 整合したドキュメント
#   out     : 実装・アーキテクチャと一致したドキュメント
#   post    : 仕様と実装の乖離がない

リポジトリの状態 : 受入検査報告書, 実装物_v(n), 整合したドキュメント, 残留リスク報告
#   role    : 同期担当
#   task    : sync_repository
#   agent.path : .git
#   writes  : リポジトリの状態
#   tools   : exec
#   out     : クリーンな同期
#   post    : 作業ツリーがクリーンである

# Pair Agent L 構成 — アーキテクチャ・大規模改修成果物定義
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

アーキテクチャ : 合意ドキュメント, 探針結果, 既存システムの制約?, 差し戻し指示_v(k-1)
#   role    : アーキテクト
#   task    : design_architecture
#   agent.path : .pair-agent/agreements/アーキテクチャ.md
#   blocks  : 実装物, 受入検査仕様
#   writes  : アーキテクチャ
#   out     : トレードオフの明示、構造制約
#   post    : トレードオフの代償が明記されている
#   post    : 構造制約が検査可能な形で書かれている

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
#   blocks  : 実装物, アーキテクチャ
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
#   blocks  : 実装物, アーキテクチャ
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

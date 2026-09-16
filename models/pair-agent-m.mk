# Pair Agent M 構成 — 標準機能開発成果物定義
#
# 前提:
#   - 合意ドキュメント（人間ゲート H1）を中心に師匠と合意形成
#   - 仕様策定後、構築と受入検査設計を独立並行実施
#   - 設計保証と非回帰テストの通過をもって、ブラックボックス受入検査を実施
#   - 受入検査合格後にドキュメント整合とリポジトリ同期を行う
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
#   out     : スプリントの目的、スコープ、受け入れ条件
#   post    : 師匠との協議に基づいて合意されている

仕様 : 合意ドキュメント, 既存システムの制約?, 差し戻し指示_v(m-1)
#   role    : 仕様作成者
#   task    : write_specification
#   agent.path : .pair-agent/agreements/仕様.md
#   blocks  : 実装物, 受入検査仕様
#   writes  : 仕様
#   out     : 外部契約と振る舞い仕様
#   post    : 合意ドキュメントにない機能を追加していない
#   post    : 判定可能な仕様として記述されている

受入検査仕様 : 仕様, 差し戻し指示_v(j-1)
#   role    : 受入検査設計者
#   task    : design_acceptance_tests
#   agent.path : .pair-agent/acceptance/受入検査仕様.md
#   blocks  : 実装物
#   writes  : 受入検査仕様
#   out     : 各仕様項目に対応する判定手続き
#   post    : 実装コードを見ずに書かれている

実装物_v(n) : 仕様, 実装物_v(n-1), 差し戻し指示_v(m-1)
#   role    : 構築者
#   task    : build
#   agent.path : src/
#   blocks  : 受入検査仕様
#   writes  : 実装物
#   tools   : exec
#   out     : 仕様を満たす実装コード
#   post    : 仕様に記述された契約を満たしている

非回帰の合否 : 実装物_v(n)
#   by      : machine
#   task    : run_regression
#   agent.path : .pair-agent/assurance/非回帰の合否.md
#   writes  : 非回帰の合否
#   tools   : exec
#   out     : 既存テストの合否結果
#   post    : 決定論的である。「既知の赤」で通さない

設計保証 : 仕様, 実装物_v(n)
#   role    : 構築者
#   task    : assure_design
#   agent.path : .pair-agent/assurance/設計保証.md
#   blocks  : 受入検査仕様
#   writes  : 設計保証
#   out     : 内部不変条件と設計整合性の保証
#   post    : 受入検査から見えない内部構造が保証されている

受入検査報告書 : 受入検査仕様, 非回帰の合否, 設計保証, 実行環境
#   role    : 受入検査実施者
#   task    : execute_acceptance_tests
#   agent.path : .pair-agent/acceptance/受入検査報告書.md
#   blocks  : 実装物
#   gate    : H2
#   writes  : 受入検査報告書
#   tools   : exec
#   out     : 仕様に対する判定結果および残留リスク
#   post    : 実装内部コードを見ずに外部契約から検査した結果である
#   post    : 合否が二値で判定されている

差し戻し指示 : 受入検査報告書?, 非回帰の合否?, 仕様?, 合意ドキュメント?
#   by      : human
#   task    : adjudicate_rework
#   agent.path : .pair-agent/assurance/差し戻し指示.md
#   gate    : H2
#   writes  : 差し戻し指示
#   out     : 差し戻し先と修正指示
#   post    : 受け手はこれだけを見て修正に着手できる

整合したドキュメント : 仕様, 受入検査報告書, 実装物_v(n), 変更の履歴
#   role    : ドキュメント整合担当
#   task    : reconcile_documents
#   agent.path : docs/
#   writes  : 整合したドキュメント
#   out     : 実装と一致したドキュメント
#   post    : 仕様と実装の乖離がない

リポジトリの状態 : 受入検査報告書, 実装物_v(n), 整合したドキュメント
#   role    : 同期担当
#   task    : sync_repository
#   agent.path : .git
#   writes  : リポジトリの状態
#   tools   : exec
#   out     : クリーンなコミット
#   post    : 作業ツリーがクリーンである

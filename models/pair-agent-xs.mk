# Pair Agent XS 構成 — 最軽量・最速・最安成果物定義
#
# 前提:
#   - 親エージェント（主エージェント）が師匠と直接協議しながら実装を行う
#   - 独立した「受入検査実施者」サブエージェントのみを起動してブラックボックス検証を実施（SoDの維持）
#   - 余計なエージェントを一切立てず、最少ターン・最低コストで完了させる
#
# 成果物パス: 最初から .pair-agent/ 配下の隔離保護パスに完全準拠

# ══════ 起点 ══════
要望 :
#   agent.path : .pair-agent/inbox/要望.md
実行環境 :
#   agent.path : .pair-agent/inbox/実行環境.md

# ══════ コア成果物 ══════
受入検査仕様 : 要望
#   role    : 受入検査設計者
#   task    : design_acceptance_tests
#   agent.path : .pair-agent/acceptance/受入検査仕様.md
#   blocks  : 実装物
#   writes  : 受入検査仕様
#   out     : 要望に対応する最小限の判定手続き
#   post    : 実装コードを見ずに書かれている

実装物 : 要望
#   role    : 構築者
#   task    : build
#   agent.path : src/
#   blocks  : 受入検査仕様
#   writes  : 実装物
#   tools   : exec
#   out     : 変更コード
#   post    : 要望を満たす変更が行われている

非回帰の合否 : 実装物
#   by      : machine
#   task    : run_regression
#   agent.path : .pair-agent/assurance/非回帰の合否.md
#   writes  : 非回帰の合否
#   tools   : exec
#   out     : 既存テストの合否結果
#   post    : 全テストがパスしている

受入検査報告書 : 受入検査仕様, 非回帰の合否, 実行環境
#   role    : 受入検査実施者
#   task    : execute_acceptance_tests
#   agent.path : .pair-agent/acceptance/受入検査報告書.md
#   blocks  : 実装物
#   gate    : H1
#   writes  : 受入検査報告書
#   tools   : exec
#   out     : 受入検査仕様に基づく合否判定
#   out     : 未カバー領域・残留リスク
#   post    : 実装内部コードを見ずに外部契約から検査した結果である
#   post    : 合否が明確に判定されている

# Pair Agent S 構成 — バグ修正・小改修成果物定義
#
# 前提:
#   - バグ票または直接の要望をそのまま仕様として扱う
#   - 合意ドキュメントの起草は省略し、直線的に流して素早く完了する
#   - 構築者 → 非回帰検査 → 設計保証 → 受入検査実施者 → リポジトリ同期
#
# 成果物パス: 最初から .pair-agent/ 配下の隔離保護パスに完全準拠

# ══════ 起点 ══════
バグ票 :
#   agent.path : .pair-agent/sprints/バグ票.md
実行環境 :
#   agent.path : .pair-agent/inbox/実行環境.md

# ══════ コア成果物 ══════
受入検査仕様 : バグ票, 差し戻し指示_v(j-1)
#   role    : 受入検査設計者
#   task    : design_acceptance_tests
#   agent.path : .pair-agent/acceptance/受入検査仕様.md
#   blocks  : 実装物
#   writes  : 受入検査仕様
#   out     : バグ票の再現条件と修正判定基準
#   post    : 実装コードを見ずに書かれている
#   post    : 各判定基準が明確である

実装物_v(n) : バグ票, 実装物_v(n-1), 差し戻し指示_v(m-1)
#   role    : 構築者
#   task    : build
#   agent.path : src/
#   blocks  : 受入検査仕様
#   writes  : 実装物
#   tools   : exec
#   out     : 修正された実装コード
#   post    : バグ票の事象を解消する実装となっている

非回帰の合否 : 実装物_v(n)
#   by      : machine
#   task    : run_regression
#   agent.path : .pair-agent/assurance/非回帰の合否.md
#   writes  : 非回帰の合否
#   tools   : exec
#   out     : 既存テストの合否結果
#   post    : 決定論的である。「既知の赤」で通さない

設計保証 : バグ票, 実装物_v(n)
#   role    : 構築者
#   task    : assure_design
#   agent.path : .pair-agent/assurance/設計保証.md
#   blocks  : 受入検査仕様
#   writes  : 設計保証
#   out     : 修正箇所の説明と副作用がない根拠
#   post    : 受入検査から見えない内部整合性が保証されている

受入検査報告書 : 受入検査仕様, 非回帰の合否, 設計保証, 実行環境
#   role    : 受入検査実施者
#   task    : execute_acceptance_tests
#   agent.path : .pair-agent/acceptance/受入検査報告書.md
#   blocks  : 実装物
#   gate    : H1
#   writes  : 受入検査報告書
#   tools   : exec
#   out     : バグ修正の検証結果および合否
#   post    : 実装内部コードを見ずに外部契約から検査した結果である
#   post    : 合否が明確に判定されている

差し戻し指示 : 受入検査報告書?, 非回帰の合否?, バグ票?
#   by      : human
#   task    : adjudicate_rework
#   agent.path : .pair-agent/assurance/差し戻し指示.md
#   gate    : H1
#   writes  : 差し戻し指示
#   out     : 差し戻し先と修正指示
#   post    : 受け手はこれだけを見て修正に着手できる

リポジトリの状態 : 受入検査報告書, 実装物_v(n)
#   role    : 同期担当
#   task    : sync_repository
#   agent.path : .git
#   writes  : リポジトリの状態
#   tools   : exec
#   out     : コミットと同期
#   post    : 作業ツリーがクリーンである

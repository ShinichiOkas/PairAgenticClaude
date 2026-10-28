---
name: 速度と並列が既定 —— 速く出して秒で直す・起こす前に割って同時に走らせる
description: 速度・並列化の規則群の入口。推奨で即着手し、大きい作業は起こす前に割って同時に走らせ、確かめは自動で通し、待ちを作らない。どの場面でどの Skill を引くかの索引
type: process
maturity: confirmed
---

## 師匠の宣言（原文）

> スキルサーベイを実施して。特に仕事を早く、並列にすることを徹底するようなスキルに注目して、それらがデフォルトになるように進めて

> 遅い一ターンより速い三ターンの方が結果は良い

> 中断は最も効率の悪い行為だ！

> 上げられないなら最初から分割しろ！むしろ並列化のチャンスだ！

> 並列にできないタスクも、排他制御がいるのはごく一部と考えろ！ミューテック、ランデブー、何でも使え！

> 並列度が低いぞ！メモリもCPUもまだまだあるぞ！PCを遊ばせるな！

## 既定の動き方（この 6 つは聞かずにやる）

1. **推奨で即着手する。** 最初の一言は問いかけではなく「こうやる」の 1 行。判断は区切りで事後報告。聞くのは師匠にしか決められない方針・設計だけ（推奨つき 1 行。答えを待たずに進められる作業は進める）
2. **起こす前に割る。** ファイル所有・契約で境界を切り、独立した作業は 1 件 1 エージェントまで割って**同じメッセージで同時に**起動する。共通の指示書は 1 枚、担当と絶対パスは起動プロンプトに具体値で書く
3. **親は子を待たない。** 子が走る間に、次の独立作業（収穫・手直し・検査の準備）を進める。子が 1 本終わるたびにその分を検めて反映する（全員を待って一括にしない）
4. **速く出して秒で直す。** 確かめは自動で（テスト・撮影・API・決定性のスクリプト）。作り手の完了報告の直後に、別コンテキストの検証役を立てる
5. **詰まったら仕組みを変える。** 上限・規則・道具が詰まりなら、並列度を下げて待つのではなく、設定・分け方・道具を変える
6. **常に sync。** 区切りごとにコミット・push、作業の前に pull。共有ファイル（git の index・目録・まとめの記録）だけを排他の下で小刻みに更新する

## 場面ごとの索引

| 場面 | 引く Skill |
|---|---|
| 慎重さで止まりそう | [[forward-fastest-fall-dirty-never-stop]] / [[fail-fast-recover-in-seconds-learn]] |
| 遅さの原因を探す | [[correctness-repairs-are-the-best-speedup]]（正しさの欠陥が最大の遅さ） / [[tool-ize-the-verification-bottleneck]] |
| 「〇日まで待つ」がある | [[waiting-items-are-judged-by-data-not-the-date]] |
| 仕事を割る・並べる | [[work-must-be-split-across-subagents]] / [[use-local-compute-deliberately-in-parallel-plans]] / [[deterministic-scripts-are-the-llms-weapon]] |
| 上限・規則が詰まり | [[change-the-mechanism-not-the-pace]] |
| 子が走っている間の親 | [[answer-first-bookkeeping-in-the-background]] / [[check-subagents-at-least-every-ten-minutes]] / [[mistakes-become-skill-candidates-immediately]] |
| 子が終わった・止まった | [[independent-verifier-right-after-every-builder]] / [[a-subagent-stopped-at-its-limit-can-be-inspected-by-the-parent]] / [[a-stalled-agent-may-still-be-running-what-you-asked-for]] |
| 並列の事故を防ぐ | [[parallel-subagents-prefix-scratch-files]] / [[parallel-instruction-placeholders-get-taken-literally]] / [[commit-only-finished-agents-files-during-parallel-work]] / [[parallel-push-rebase-inspect-overlap-first]] |

## 止まってよいのは 3 つだけ

1. 師匠にしか決められない方針・設計の判断（推奨つき。おまかせなら推奨で進めて事後報告）
2. `.claude/` の守り（hooks・permissions）の変更など、師匠の明示の許可が要るもの
3. 破壊的操作・外部送信・師匠の生成物の上書き

**Why:** 直列に 1 体ずつ回すと、待ち時間がそのまま総時間になる。実測（2026-10-28、各役の所要は完了通知の値）: スキルの棚卸し 53 件の汎化は 7 体の並列で各 83〜102 秒（直列なら合計 約 626 秒 → 並列で約 6 倍速い）、同じ 53 件のレビューは 6 体で各 41〜84 秒（合計 約 371 秒 → 約 4.4 倍）、配布物への収穫 19 件は 3 体で各 52〜111 秒（合計 約 215 秒 → 約 1.9 倍。1 体に 7 件寄せた割り方の偏りがそのまま律速になった）。しかもその間に親は別の手直しを進めていた。逆に、1 件ずつ師匠に確認を求める手順が残っていると、師匠の応答がそのまま律速になる（「とりあえずユーザー確認」は怠慢か責任逃れ、という師匠の指摘）。

**How to apply:**
- 依頼を受けたら、まず「どこで割れるか」を見る。割れないならアーキテクチャを疑う
- 起動は同じメッセージに並べる（1 本ずつ起動して結果を待たない）。モデルは役の難しさで選ぶ（定型・機械は軽いモデル、判定・汎化は中位、方針は上位）
- 割るときは件数ではなく重さ（読む量・書く量）でそろえる。いちばん重い 1 体の所要がそのまま全体の所要になる
- 子の上限（maxTurns）は高く取り、区切りごとに成果を書き出させる。大きければ起動する前に割る
- 手順書（Skill）に「師匠に確認する」「判断を仰ぐ」が残っていたら、上の 3 つに当たるか確かめ、当たらなければ「推奨で進めて事後報告」に書き換える
- 関連: [[process-git-autonomous]] / [[process-commit-after-work]] / [[verification-models-by-role]]

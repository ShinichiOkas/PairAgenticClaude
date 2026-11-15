---
name: 多人数が使うリポジトリへ共有するのは、すでにそこで共有されている中身だけ — プロジェクトの規則を引く判定は PC に残す
description: 判定の結果を共有するかは、その中身がすでに共有の場にあるかで決める。global 同士の規則ペアの判定は master の situations/verdicts.json へ。プロジェクトのペアの判定はプロジェクトの規則文を引くので PC に残す
type: technique
maturity: draft
created_at: 2026-11-15
source: Pair Agent Manager。2026-11-15
proposed_by: ai
approved_by: none（AI の観測。未承認）
domain_tags: [manager, sharing, privacy, master, verdicts]
---

## 内容

多人数が使うリポジトリ（マスター）へデータを載せるのは、**その中身がすでにそこで共有されているとき**だけ。

- global 同士の規則ペアの判定 → マスターの `situations/verdicts.json` に載せる（規則そのものがマスターにある）
- プロジェクトのペアの判定 → 載せない。判定がプロジェクトの規則文を引くため、載せるとプロジェクトの中身が共有の場へ漏れる。PC に残す

## Why

判定の結果は、根拠の規則文を含む。根拠がマスターにあるものなら、結果を載せても新しい情報は出ない。プロジェクトの規則文を含むものは、別の人の PC へ届くと、その人に見せるべきでない中身を渡す。

## How to apply

- 載せる前に「この判定が引く文は、すでにマスターにあるか」を問う
- 迷ったら PC に残す。後から載せるのは簡単だが、一度載せたものは取り返せない
- 個人の層の同期は別の話で、利用者が選ぶ（pair 固有の `personal-sync-is-opt-in-per-user-and-pc`）

## 関連

- `multi-pc-master-sync-merges-by-section-never-rebases`（この `skills/`）
- `conflict-verdicts-notify-only-conflict`（この `skills/`）

---
name: Graph の新機能はスコープ要求の前に既存トークンの scp を見る
description: AAD はアクセストークンに「要求したスコープ」ではなく「そのクライアントに同意済みの全スコープ」を載せる。新スコープを名指し要求する前に、トークンキャッシュの scp を読む
type: domain
maturity: confirmed
---

Microsoft Graph で新しい機能を足すとき、**必要なスコープを MSAL に名指しで要求してはいけない**。先に**既存トークンの `scp` クレーム（キャッシュの `AccessToken[].target`）を見る**。AAD はアクセストークンに「要求したスコープ」ではなく**「そのクライアントに同意済みの全スコープ」**を載せるため、要求せずとも既に使える権限が入っていることが多い。実測では、Office first-party クライアント（`d3590ed6-52b3-4102-aeff-aad2292ab01c`）にコード上の要求 3 スコープに対し **51 スコープ**が焼かれていた。

**Why:** 実例——チャット読み取りのために `Chat.Read` を名指し要求して**3回連続でログインに失敗**（テナントがユーザー同意を閉じている／first-party クライアントは AADSTS65002）。その後キャッシュを読んだら上位の `Chat.ReadWrite` が**最初から入っており**、何も要求せず既存トークンで叩いたら 200 が返った。ユーザーに3回無駄なログインをさせた。Microsoft の preauthorization リストは「下位スコープを含まない」ことがあり、**上位が使えて下位が使えない**という直感に反する状態が起きる。

**How to apply:**
1. Graph の新機能を検討したら、まずトークンキャッシュの `AccessToken[].target` を読む。ログイン不要・コスト0
2. 必要な権限が既にあれば **`SCOPES` を一切変更せず**、silent 取得したトークンでそのまま叩く
3. 無いときだけ追加同意の話になる:
   - Office 等の first-party クライアントに**未登録スコープは足せない**（AADSTS65002）。テナント管理者に頼んでも解決しない（Microsoft 側のリスト）
   - 正規ルートは Entra ID への自前アプリ登録＋管理者同意（情シス案件）
4. 上位スコープが使えても**書き込み系を実装してよいことにはならない**。読み取りだけ実装する（[[outward-send-stays-human]]）

付随して判明した Graph の癖（該当機能を触るとき既知バグとして扱う）:
- `/me/joinedTeams` と `/teams/{id}/channels` は `$top` を受け付けない（400）
- カレンダーの `isOnlineMeeting` は `$filter` 非対応。取得後に手元で絞る
- 自分がメンバーでない private チャネルの `/messages` は 403（権限不足ではなく正常挙動）
- 会議トランスクリプトの `getAllTranscripts` は委任権限非対応。委任では「予定 → `joinUrl` → `/me/onlineMeetings?$filter=joinWebUrl` → `/transcripts`」の経路のみ

関連: [[anticipate-knowable-constraints]]（既存トークンを先に読めば1回目で分かった）/ [[probe-external-behavior-before-design]] / [[msal-device-code-default]]

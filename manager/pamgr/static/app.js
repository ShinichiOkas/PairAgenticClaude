// Pair Agent Manager — 画面。API の応答が implemented:false なら「未実装」を出す。
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(method, path, body) {
  const opt = { method, headers: {} };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch("/api" + path, opt);
  let data;
  try { data = await r.json(); } catch { data = { implemented: true, error: `HTTP ${r.status}` }; }
  if (!r.ok && !data.error) data.error = data.detail ? JSON.stringify(data.detail) : `HTTP ${r.status}`;
  return data;
}

// 応答の共通処理: 未実装・エラーなら表示して false を返す
function guard(outId, res) {
  if (res && res.implemented === false) {
    $(outId).innerHTML = `<div class="notimpl">未実装 <span class="muted">(${esc(res.feature || "")})</span></div>`;
    return false;
  }
  if (res && res.error) {
    $(outId).innerHTML = `<div class="error">${esc(res.error)}</div>`;
    return false;
  }
  return true;
}

function busy(outId, msg) { $(outId).innerHTML = `<p class="muted">${esc(msg || "実行中…")}</p>`; }

const STATE_BADGE = {
  "same": ["一致", "b-ok"], "missing": ["未配布", "b-muted"], "master-ahead": ["マスターが新しい", "b-info"],
  "target-ahead": ["配布先で改変", "b-warn"], "diverged": ["双方で変更", "b-bad"], "differs": ["差分あり（向き不明）", "b-warn"],
  "create": ["新規", "b-info"], "update": ["更新", "b-info"], "skip-same": ["一致（何もしない）", "b-ok"], "conflict": ["配布先で改変（要選択）", "b-warn"],
};
const badge = (k) => { const [t, c] = STATE_BADGE[k] || [k, "b-muted"]; return `<span class="badge ${c}">${esc(t)}</span>`; };

function renderDiff(outId, title, text) {
  const lines = String(text || "").split("\n").map((l) => {
    const cls = l.startsWith("@@") ? "hunk" : l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "del" : "";
    return cls ? `<span class="${cls}">${esc(l)}</span>` : esc(l) + "\n";
  }).join("");
  $(outId).innerHTML = `<h3>${esc(title)}</h3><pre class="diff">${lines || '<span class="muted">差分なし</span>'}</pre>`;
}

// ------------------------------------------------------------ タブ
document.querySelectorAll("#nav a").forEach((a) => a.addEventListener("click", () => showTab(a.dataset.tab)));
function showTab(name) {
  document.querySelectorAll("#nav a").forEach((x) => x.classList.toggle("active", x.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x.id === "tab-" + name));
  location.hash = name;
  const onShow = { inbox: loadInbox, activity: loadActivity, effective: fillEffectiveSelect, managed: loadManaged, targets: loadTargets, status: fillTargetSelect, situations: loadSituations, distribute: fillDistTargets, settings: loadSettings };
  if (onShow[name]) onShow[name]();
}

// ------------------------------------------------------------ ヘッダ（常駐の状態・点検）
async function loadHealth() {
  const h = await api("GET", "/health");
  $("hdr-info").textContent = h.master_root ? `マスター: ${h.master_root}` : "";
}
const fmtAt = (s) => (s ? String(s).replace("T", " ").slice(0, 19) : "");
async function loadResident() {
  const r = await api("GET", "/resident");
  let state;
  if (r.implemented === false || r.error) state = '<span class="badge b-warn">常駐: 未実装</span>';
  else {
    const res = r.resident_implemented === false
      ? '<span class="badge b-warn" title="自動の点検（常駐）はまだ未実装。いまは「今すぐ点検」だけ">常駐: 未実装</span>'
      : `<span class="badge ${r.running ? "b-ok" : "b-muted"}">${r.running ? "常駐中" : "停止"}</span>`;
    state = `${res} <span class="muted">最終点検 ${esc(fmtAt(r.last_sweep) || "まだ")}${r.next_sweep ? " ・ 次 " + esc(fmtAt(r.next_sweep)) : ""}</span>`;
    $("nav-inbox-n").textContent = r.open || "";
  }
  $("resident").innerHTML = `${state} <button id="sweep-now" class="secondary" title="照合して、自動で直せるものは直します（配る・マスターへ取り込む・節ごとのマージ）。書く前の版は退避し、「自動でやったこと」から取り消せます">今すぐ点検（自動で直す）</button><span id="sweep-out">${r.sweeping ? ' <span class="badge b-info">点検中…</span>' : ""}</span>`;
  $("sweep-now").onclick = () => runSweep(false, "sweep-out");
}
async function runSweep(dryRun, outId, done) {
  const s = await api("POST", "/sweep", { dry_run: dryRun });
  if (s.error) { $(outId).innerHTML = ` <span class="badge b-bad">${esc(s.error)}</span>`; return; }
  $(outId).innerHTML = ` <span class="badge b-info">${dryRun ? "予行中…" : "点検中…"}</span>`;
  const tick = async () => {
    const j = await api("GET", "/jobs/" + encodeURIComponent(s.job_id));
    if (j.state === "running") { setTimeout(tick, 700); return; }
    if (!dryRun) { await loadResident(); refreshCurrent(); }
    const el = $(outId);
    if (el) el.innerHTML = j.state === "done" ? ` <span class="badge b-ok">${dryRun ? "予行しました" : "点検しました"}</span>` : ` <span class="badge b-bad">${esc(j.error || "失敗")}</span>`;
    if (done) done(j);
  };
  setTimeout(tick, 500);
}
function refreshCurrent() {
  const cur = (location.hash || "#inbox").slice(1);
  if (cur === "inbox") loadInbox();
  if (cur === "activity") loadActivity();
}

// ------------------------------------------------------------ 判断待ち（UC1）
const J_LABEL = { J1: "同時に効く規則の矛盾", J2: "マージできない変更", J3: "管理に入れるか", J4: "ほかのユーザーの規則" };
function decisionCard(item, sample) {
  const dis = sample ? "disabled" : "";
  const opts = (item.options || []).map((o) => `<button ${dis} class="${o.primary ? "" : "secondary"} dc-opt" data-id="${esc(item.id)}" data-opt="${esc(o.id)}">${esc(o.label)}</button>`).join("");
  const rule = (x, k) => x ? `<div class="rule"><div class="muted">${k} ・ ${esc(x.where)} ・ ${esc(x.when || "")}</div><pre>${esc(x.text)}</pre></div>` : "";
  const diffBtn = item.kind === "J2" && item.refs ? `<button class="secondary dc-diff" data-id="${esc(item.id)}" data-t="${esc(item.refs.target_id)}" data-rel="${esc(item.refs.rel)}">差分を見る（- マスター / + 配布先）</button>` : "";
  return `<div class="card decision ${sample ? "sample" : ""}">
    ${sample ? '<div class="sample-tag">見本（この種類の判断はまだ未実装。画面の形を見るためのもの。実データから作った例）</div>' : ""}
    <div class="bar"><span class="badge b-bad">${esc(J_LABEL[item.kind] || item.kind)}</span><b>${esc(item.title)}</b>${item.status === "later" ? ' <span class="badge b-muted">あとで</span>' : ""}</div>
    <p>${esc(item.what)}</p>
    ${item.a || item.b ? `<div class="side">${rule(item.a, "規則 A")}${rule(item.b, "規則 B")}</div>` : ""}
    ${item.applies ? `<p><b>${item.kind === "J3" ? "場所" : item.kind === "J2" ? "ファイル" : "どこで同時に効くか"}:</b> ${esc(item.applies)}</p>` : ""}
    ${item.ai ? `<div class="ai"><b>AI の見立て（仮説）:</b> ${esc(item.ai)}</div>` : ""}
    <div class="bar">${opts}${diffBtn}</div><div class="dc-out" id="dc-out-${esc(item.id)}"></div></div>`;
}
const SAMPLE_INBOX = [
  { id: "sample-j1", kind: "J1", title: "運転方針 × セッションの始め",
    what: "2 つの規則が、すべてのプロジェクトのエージェントに同時に効いています。依頼が無いのに着手するのか、待つのかがぶつかって見えます。",
    a: { where: "~/.claude/CLAUDE.md › 運転方針", when: "2026-10-27 の宣言", text: "依頼を受けたら、聞き返さずに推奨を決めて着手する。最初の一言は問いかけではなく「こうやる」の 1 行。" },
    b: { where: "~/.claude/rules/pair-agent-core.md › セッションの始め", when: "2026-11-05 の宣言", text: "セッションの始めに自分から何も始めない。ツールを 1 つも走らせない。最初の発話が依頼でないなら「何を始めますか？」の 1 行だけ返して待つ。" },
    applies: "全プロジェクト（どちらも全体の規則）",
    ai: "矛盾ではなく、状況次第で両方真。A は「依頼を受けた後」、B は「セッション開始直後で依頼がまだ無い」ときに効く（状況定義 main-agent ／ session-start-no-request）。",
    options: [{ id: "split", label: "状況で分ける（AI の案を直せる）", primary: true }, { id: "a", label: "A を採る" }, { id: "b", label: "B を採る" }, { id: "merge", label: "統合した文案にする" }, { id: "later", label: "あとで" }] },
  { id: "sample-j3", kind: "J3", title: "openclaw を管理に入れるか",
    what: "CLAUDE.md を持つリポジトリが見つかりました。.pair-agent/ が無いので、他人のリポジトリかもしれません。管理に入れると、全体の規則とプロジェクトの雛形を配ります。",
    applies: "S:\\work\\develop\\openclaw（CLAUDE.md・AGENTS.md あり）",
    options: [{ id: "include", label: "管理に入れる", primary: true }, { id: "exclude", label: "外す（二度と聞かない）" }, { id: "later", label: "あとで" }] },
];
async function loadInbox() {
  busy("inbox-out");
  const r = await api("GET", "/inbox");
  if (guard("inbox-out", r)) {
    const items = r.items || [];
    const open = items.filter((i) => i.status === "open"), later = items.filter((i) => i.status === "later");
    $("nav-inbox-n").textContent = open.length || "";
    $("inbox-out").innerHTML = (open.length ? open.map((i) => decisionCard(i)).join("") : '<p class="ok-big">やることはありません。</p>') +
      (later.length ? `<h3 class="muted">あとで（${later.length}）</h3>` + later.map((i) => decisionCard(i)).join("") : "");
  }
  $("inbox-sample").innerHTML = SAMPLE_INBOX.map((i) => decisionCard(i, true)).join("");
  document.querySelectorAll(".dc-opt:not(:disabled)").forEach((b) => (b.onclick = async () => {
    const out = "dc-out-" + b.dataset.id;
    busy(out, "反映中…");
    const d = await api("POST", `/inbox/${encodeURIComponent(b.dataset.id)}/decide`, { option: b.dataset.opt });
    if (!guard(out, d)) return;
    $(out).innerHTML = `<span class="badge b-ok">${d.status === "later" ? "あとでに回しました" : "反映しました"}</span>${d.sweep_job ? ' <span class="muted">ほかの配布先へ広げています（点検）</span>' : ""}`;
    setTimeout(() => { loadInbox(); loadResident(); }, 1200);
  }));
  document.querySelectorAll(".dc-diff").forEach((b) => (b.onclick = async () => {
    const out = "dc-out-" + b.dataset.id;
    busy(out);
    const d = await api("GET", `/diff?target_id=${encodeURIComponent(b.dataset.t)}&rel=${encodeURIComponent(b.dataset.rel)}`);
    if (guard(out, d)) renderDiff(out, "差分（- マスター / + 配布先）", d.diff);
  }));
}

// ------------------------------------------------------------ 自動でやったこと（UC2）
const KIND_LABEL = { distribute: "配った", adopt: "取り込んだ", merge: "節マージ", decide: "判断", manage: "管理", undo: "取り消し" };
async function loadActivity() {
  busy("activity-out");
  const r = await api("GET", "/activity");
  if (guard("activity-out", r)) {
    const ev = r.events || [];
    let html = "";
    if ((r.held || []).length) html += `<div class="card"><h3>見送ったもの（最終点検 ${esc(fmtAt(r.last_sweep))}）</h3><table><tr><th>何を</th><th>どこ</th><th>なぜ</th></tr>` +
      r.held.map((h) => `<tr><td>${esc(h.what)}</td><td>${esc(h.detail)}</td><td>${esc(h.why)}</td></tr>`).join("") + "</table></div>";
    if ((r.notes || []).length) html += r.notes.map((n) => `<p class="muted">※ ${esc(n)}</p>`).join("");
    html += ev.length ? actTable(ev) : '<p class="muted">まだありません。</p>';
    $("activity-out").innerHTML = html;
    document.querySelectorAll(".act-undo").forEach((b) => (b.onclick = async () => {
      const d = await api("POST", `/activity/${encodeURIComponent(b.dataset.id)}/undo`);
      if (d.error) { b.insertAdjacentHTML("afterend", ` <span class="badge b-bad">${esc(d.error)}</span>`); return; }
      loadActivity(); loadResident();
    }));
    document.querySelectorAll(".act-diff").forEach((b) => (b.onclick = async () => {
      const cell = $("act-d-" + b.dataset.id);
      if (cell.dataset.open) { cell.innerHTML = ""; delete cell.dataset.open; return; }
      const d = await api("GET", `/activity/${encodeURIComponent(b.dataset.id)}/diff`);
      if (d.error) { cell.innerHTML = `<div class="error">${esc(d.error)}</div>`; return; }
      cell.dataset.open = "1";
      cell.innerHTML = (d.files || []).map((f, i) => `<div id="act-d-${esc(b.dataset.id)}-${i}"></div>`).join("");
      (d.files || []).forEach((f, i) => renderDiff(`act-d-${b.dataset.id}-${i}`, f.path, f.diff));
    }));
  }
  renderPreview();
}
function actTable(ev) {
  return `<table><tr><th>いつ</th><th>何を</th><th>どこへ</th><th>なぜ</th><th></th></tr>` +
    ev.map((e) => {
      const undoable = e.kind !== "undo" && !e.undone;
      const btns = `${(e.changes || []).length ? `<button class="secondary act-diff" data-id="${esc(e.id)}">差分</button> ` : ""}${undoable ? `<button class="secondary act-undo" data-id="${esc(e.id)}">取り消す</button>` : e.undone ? '<span class="badge b-muted">取り消し済み</span>' : ""}`;
      return `<tr><td>${esc(fmtAt(e.at))}</td><td><span class="badge b-info">${esc(KIND_LABEL[e.kind] || e.kind)}</span> ${esc(e.what)}</td><td>${esc(e.detail)}</td><td>${esc(e.why)}</td><td style="white-space:nowrap">${btns}</td></tr>` +
        `<tr><td colspan="5" id="act-d-${esc(e.id)}" style="padding:0;border:0"></td></tr>`;
    }).join("") + "</table>";
}
async function renderPreview() {
  const r = await api("GET", "/sweep");
  const p = r.preview;
  let body = '<p class="muted">点検が次に何をするかを、書かずに見ます。</p>';
  if (p) {
    body = `<p class="muted">予行 ${esc(fmtAt(p.at))} ・ 書く ${p.actions.length} 件 ・ 判断待ち ${p.inbox.length} 件 ・ 見送り ${p.held.length} 件</p>` +
      (p.actions.length ? `<table><tr><th>何を</th><th>どこへ</th><th>なぜ</th></tr>` + p.actions.map((a) => `<tr><td><span class="badge b-info">${esc(KIND_LABEL[a.kind] || a.kind)}</span> ${esc(a.what)}</td><td>${esc(a.detail)}</td><td>${esc(a.why)}</td></tr>`).join("") + "</table>" : '<p class="ok-big">書くものはありません。</p>') +
      (p.inbox.length ? `<p><b>判断待ちに上がるもの:</b></p><ul>${p.inbox.map((i) => `<li>${esc(J_LABEL[i.kind] || i.kind)}: ${esc(i.title)}</li>`).join("")}</ul>` : "") +
      (Object.keys(p.steps || {}).length ? `<p class="muted">段: ${Object.entries(p.steps).map(([k, v]) => `${esc(k)}=${esc(v)}`).join(" ・ ")}</p>` : "");
  }
  $("activity-sample").innerHTML = `<div class="card"><div class="bar"><h3 style="margin:0">予行（書かない）</h3><button id="pv-run" class="secondary">予行する</button><span id="pv-out"></span></div>${body}</div>`;
  $("pv-run").onclick = () => runSweep(true, "pv-out", () => renderPreview());
}

// ------------------------------------------------------------ 効いている規則（UC5）
async function fillEffectiveSelect() {
  const r = await api("GET", "/targets");
  $("ef-target").innerHTML = r.implemented === false ? "" : (r.targets || []).filter((t) => t.kind === "project").map((t) => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("") || '<option value="">（管理下のプロジェクトがありません）</option>';
}
$("ef-show").onclick = async () => {
  busy("ef-out");
  const r = await api("GET", "/effective/" + encodeURIComponent($("ef-target").value || "_"));
  if (!guard("ef-out", r)) return;
  $("ef-out").innerHTML = `<pre>${esc(JSON.stringify(r, null, 2))}</pre>`;
};

// ------------------------------------------------------------ 管理下（UC3）
async function loadManaged() {
  busy("managed-out");
  const r = await api("GET", "/managed");
  if (!guard("managed-out", r)) return;
  $("managed-out").innerHTML = `<pre>${esc(JSON.stringify(r, null, 2))}</pre>`;
}

// ------------------------------------------------------------ 配布先
let discovered = [];
$("disc-run").onclick = async () => {
  busy("disc-out", "探索中…");
  const roots = $("disc-roots").value.split("\n").map((s) => s.trim()).filter(Boolean);
  const r = await api("POST", "/targets/discover", { roots, depth: Number($("disc-depth").value) });
  if (!guard("disc-out", r)) return;
  discovered = r.candidates || [];
  $("disc-out").innerHTML = `<p class="muted">${discovered.length} 件</p><table><tr><th><input type="checkbox" id="disc-all"></th><th>名前</th><th>種類</th><th>目印</th><th>場所</th></tr>` +
    discovered.map((c, i) => `<tr><td><input type="checkbox" class="disc-cb" data-i="${i}" ${c.registered ? "disabled" : ""}></td><td>${esc(c.name)} ${c.registered ? '<span class="badge b-ok">登録済み</span>' : ""}</td><td>${esc(c.kind)}</td><td>${(c.markers || []).map((m) => `<code>${esc(m)}</code>`).join(" ")}</td><td class="path">${esc(c.path)}</td></tr>`).join("") + "</table>";
  $("disc-all").onchange = (e) => document.querySelectorAll(".disc-cb:not(:disabled)").forEach((cb) => (cb.checked = e.target.checked));
};
$("disc-register").onclick = async () => {
  const picked = [...document.querySelectorAll(".disc-cb:checked")].map((cb) => discovered[Number(cb.dataset.i)]);
  if (!picked.length) { $("disc-out").insertAdjacentHTML("afterbegin", '<p class="muted">登録するものを選んでください</p>'); return; }
  const r = await api("POST", "/targets", { targets: picked.map((c) => ({ path: c.path, kind: c.kind, name: c.name })) });
  if (!guard("tgt-out", r)) return;
  await loadTargets();
  $("disc-run").onclick();
};
async function loadTargets() {
  busy("tgt-out");
  const r = await api("GET", "/targets");
  if (!guard("tgt-out", r)) return;
  const ts = r.targets || [];
  $("tgt-out").innerHTML = ts.length ? `<table><tr><th>名前</th><th>種類</th><th>場所</th><th></th></tr>` +
    ts.map((t) => `<tr><td>${esc(t.name)}</td><td>${esc(t.kind)}</td><td class="path">${esc(t.path)}</td><td><button class="secondary tgt-del" data-id="${esc(t.id)}">解除</button></td></tr>`).join("") + "</table>" : '<p class="muted">登録はまだありません。上の「探索」から登録してください。</p>';
  document.querySelectorAll(".tgt-del").forEach((b) => (b.onclick = async () => { const d = await api("DELETE", "/targets/" + encodeURIComponent(b.dataset.id)); if (guard("tgt-out", d)) loadTargets(); }));
}
$("tgt-refresh").onclick = loadTargets;

// ------------------------------------------------------------ 配布状況・差分
async function fillTargetSelect() {
  const r = await api("GET", "/targets");
  const sel = $("st-target");
  if (r.implemented === false) { sel.innerHTML = '<option value="">（未実装）</option>'; return; }
  const cur = sel.value;
  sel.innerHTML = (r.targets || []).map((t) => `<option value="${esc(t.id)}">${esc(t.name)} (${esc(t.kind)})</option>`).join("");
  if (cur) sel.value = cur;
}
$("st-all").onclick = async () => {
  busy("st-out", "照合中…"); $("diff-out").innerHTML = "";
  const r = await api("GET", "/status");
  if (!guard("st-out", r)) return;
  const keys = ["same", "missing", "master-ahead", "target-ahead", "diverged", "differs"];
  $("st-out").innerHTML = `<table><tr><th>配布先</th><th>種類</th>${keys.map((k) => `<th>${badge(k)}</th>`).join("")}</tr>` +
    (r.targets || []).map((t) => `<tr class="click st-row" data-id="${esc(t.id)}"><td>${esc(t.name)}</td><td>${esc(t.kind)}</td>${keys.map((k) => `<td>${t.counts?.[k] || ""}</td>`).join("")}</tr>`).join("") + "</table>";
  document.querySelectorAll(".st-row").forEach((tr) => (tr.onclick = () => { $("st-target").value = tr.dataset.id; $("st-one").onclick(); }));
};
$("st-one").onclick = async () => {
  const id = $("st-target").value;
  busy("st-out", "照合中…"); $("diff-out").innerHTML = "";
  const r = await api("GET", "/status/" + encodeURIComponent(id || "_"));
  if (!guard("st-out", r)) return;
  const hide = $("st-hide-same").checked;
  const files = (r.files || []).filter((f) => !(hide && f.state === "same"));
  $("st-out").innerHTML = `<p class="muted">${esc(r.target?.name)} ・ ${esc(r.target?.path)} ・ 表示 ${files.length} / 全 ${(r.files || []).length}</p>` +
    `<table><tr><th>状態</th><th>区分</th><th>マスター</th><th>配布先</th></tr>` +
    files.map((f) => `<tr class="click st-file" data-rel="${esc(f.dest_rel)}" data-adopt="${["differs", "target-ahead", "diverged"].includes(f.state) && f.src_rel ? 1 : ""}"><td>${badge(f.state)}${f.newer ? `<br><span class="muted">更新時刻は${f.newer === "target" ? "配布先" : "マスター"}が新しい</span>` : ""}</td><td>${esc(f.label || f.entry)}</td><td class="path">${esc(f.src_rel)}</td><td class="path">${esc(f.dest_rel)}</td></tr>`).join("") + "</table>";
  document.querySelectorAll(".st-file").forEach((tr) => (tr.onclick = () => showDiff(id, tr.dataset.rel, "diff-out", !!tr.dataset.adopt)));
};
async function showDiff(targetId, rel, outId, canAdopt) {
  busy(outId);
  const r = await api("GET", `/diff?target_id=${encodeURIComponent(targetId)}&rel=${encodeURIComponent(rel)}`);
  if (!guard(outId, r)) return;
  renderDiff(outId, `差分: ${rel}（- マスター / + 配布先）`, r.diff);
  if (canAdopt) {
    $(outId).insertAdjacentHTML("afterbegin", `<div class="bar"><button id="adopt-btn" class="secondary">配布先の版をマスターに取り込む</button><span class="muted">マスターは git 管理なので戻せます</span></div><div id="adopt-out"></div>`);
    $("adopt-btn").onclick = async () => {
      const a = await api("POST", "/status/adopt", { target_id: targetId, rel });
      if (guard("adopt-out", a)) $("adopt-out").innerHTML = `<p><span class="badge b-ok">取り込みました</span> <code>${esc(a.written)}</code></p>`;
    };
  }
}

// ------------------------------------------------------------ サーベイ
let units = [];
function renderUnits() {
  const q = $("sv-filter").value.trim().toLowerCase(), sc = $("sv-scope").value, kd = $("sv-kind").value;
  const list = units.filter((u) => (!sc || u.scope === sc) && (!kd || u.kind === kd) && (!q || `${u.name} ${u.title} ${u.target} ${u.rel}`.toLowerCase().includes(q)));
  const head = $("sv-out").dataset.summary || "";
  $("sv-out").innerHTML = head + `<p class="muted">表示 ${Math.min(list.length, 500)} / 該当 ${list.length} / 全 ${units.length}</p><table><tr><th>スコープ</th><th>種類</th><th>名前</th><th>成熟度</th><th>場所</th><th>配布先</th></tr>` +
    list.slice(0, 500).map((u) => `<tr class="click sv-row" data-id="${esc(u.id)}"><td>${esc(u.scope)}</td><td>${esc(u.kind)}</td><td>${esc(u.name || u.title)}</td><td>${esc(u.maturity || "")}</td><td class="path">${esc(u.rel)}</td><td>${esc(u.target)}</td></tr>`).join("") + "</table>";
  document.querySelectorAll(".sv-row").forEach((tr) => (tr.onclick = () => showUnit(tr.dataset.id, "sv-unit")));
}
function setSurvey(r) {
  units = r.units || [];
  const s = r.summary || {};
  const row = (o) => Object.entries(o || {}).map(([k, v]) => `<span class="badge b-muted">${esc(k)}: ${v}</span>`).join(" ");
  $("sv-out").dataset.summary = `<div class="card"><b>合計 ${s.total ?? units.length}</b> ・ ${esc(s.surveyed_at || "")}<br>スコープ別 ${row(s.by_scope)}<br>種類別 ${row(s.by_kind)}</div>`;
  renderUnits();
}
$("sv-run").onclick = async () => { busy("sv-out", "収集中…"); const r = await api("POST", "/survey/run"); if (guard("sv-out", r)) setSurvey(r); };
$("sv-load").onclick = async () => { busy("sv-out"); const r = await api("GET", "/survey"); if (guard("sv-out", r)) setSurvey(r); };
["sv-filter", "sv-scope", "sv-kind"].forEach((id) => $(id).addEventListener("input", () => units.length && renderUnits()));
async function showUnit(id, outId) {
  busy(outId);
  const r = await api("GET", "/survey/unit/" + encodeURIComponent(id));
  if (!guard(outId, r)) return;
  const u = r.unit || {};
  $(outId).innerHTML = `<div class="card"><h3>${esc(u.name || u.title)}</h3><p class="muted">${esc(u.scope)} ・ ${esc(u.kind)} ・ ${esc(u.path)}${u.anchor ? " #" + esc(u.anchor) : ""}</p><pre>${esc(u.text)}</pre></div>`;
}

// ------------------------------------------------------------ 検査
let pollTimer = null;
$("ck-run").onclick = async () => {
  busy("ck-job", "開始中…"); $("ck-out").innerHTML = "";
  const r = await api("POST", "/checks/run", { mode: $("ck-mode").value, limit: Number($("ck-limit").value) });
  if (!guard("ck-job", r)) return;
  pollJob(r.job_id);
};
function pollJob(jobId) {
  clearInterval(pollTimer);
  const tick = async () => {
    const j = await api("GET", "/jobs/" + encodeURIComponent(jobId));
    if (!guard("ck-job", j)) { clearInterval(pollTimer); return; }
    const p = j.progress || {}, pct = p.total ? Math.round((100 * p.done) / p.total) : 0;
    $("ck-job").innerHTML = `<p>${esc(j.state)} ・ ${p.done ?? 0} / ${p.total ?? "?"} ・ ${esc(j.message || "")}</p><div class="progress"><div style="width:${pct}%"></div></div>`;
    if (j.state === "done" || j.state === "error") { clearInterval(pollTimer); if (j.state === "error") $("ck-job").insertAdjacentHTML("beforeend", `<div class="error">${esc(j.error)}</div>`); loadChecks(); }
  };
  pollTimer = setInterval(tick, 1000); tick();
}
const uref = (u) => `<b>${esc(u?.name || u?.title)}</b><br><span class="muted">${esc(u?.scope)} ・ ${esc(u?.target)}</span><br><span class="path">${esc(u?.rel)}${u?.anchor ? " #" + esc(u.anchor) : ""}</span>`;
const REL = { duplicate: ["同一", "b-bad"], subsumes: ["包含", "b-warn"], overlap: ["重複あり", "b-warn"], conflict: ["矛盾", "b-bad"], context_dependent: ["状況次第で両方真", "b-info"], unrelated: ["無関係", "b-muted"], error: ["判定失敗", "b-muted"] };
async function loadChecks() {
  busy("ck-out");
  const r = await api("GET", "/checks");
  if (!guard("ck-out", r)) return;
  let html = "";
  const red = r.redundancy;
  if (red) {
    html += `<div class="card"><h3>冗長（機械）<span class="muted"> ・ ${esc(red.checked_at || "")}</span></h3>`;
    html += `<p><b>完全一致の重複</b> ${red.exact?.length || 0} 組</p>` + (red.exact || []).slice(0, 100).map((g) => `<div class="card">${g.units.map(uref).join("<hr>")}</div>`).join("");
    html += `<p><b>同名で中身が違う（改変された写し）</b> ${red.variants?.length || 0} 組</p><table><tr><th>名前</th><th>写し</th></tr>` + (red.variants || []).slice(0, 200).map((g) => `<tr><td>${esc(g.name)}</td><td>${g.units.map((u) => `${esc(u.scope)}・${esc(u.target)} <span class="path">${esc(u.rel)}</span>`).join("<br>")}</td></tr>`).join("") + "</table>";
    html += `<p><b>よく似ている（文字の類似）</b> ${red.near?.length || 0} 組</p><table><tr><th>類似度</th><th>A</th><th>B</th></tr>` + (red.near || []).slice(0, 200).map((p) => `<tr><td>${p.score}</td><td>${uref(p.a)}</td><td>${uref(p.b)}</td></tr>`).join("") + "</table></div>";
  }
  const cf = r.conflict;
  if (cf) {
    html += `<div class="card"><h3>矛盾・状況依存（LLM・仮説）<span class="muted"> ・ ${esc(cf.model || "")} ・ ${esc(cf.checked_at || "")}</span></h3><table><tr><th>判定</th><th>A</th><th>B</th><th>状況（A／B）</th><th>理由</th></tr>` +
      (cf.pairs || []).map((p) => { const [t, c] = REL[p.relation] || [p.relation, "b-muted"]; return `<tr><td><span class="badge ${c}">${esc(t)}</span><br><span class="badge b-muted">仮説</span></td><td>${uref(p.a)}</td><td>${uref(p.b)}</td><td>${esc(p.situation_a || "")}<hr>${esc(p.situation_b || "")}${p.proposed_situation ? `<br><span class="badge b-info">新しい状況の提案</span> ${esc(p.proposed_situation)}` : ""}</td><td>${esc(p.reason || p.error || "")}</td></tr>`; }).join("") + "</table></div>";
  }
  $("ck-out").innerHTML = html || '<p class="muted">まだ結果がありません</p>';
}
$("ck-load").onclick = loadChecks;

// ------------------------------------------------------------ 状況定義
async function loadSituations() {
  busy("si-out");
  const r = await api("GET", "/situations");
  if (!guard("si-out", r)) return;
  $("si-out").innerHTML = `<table><tr><th>ID</th><th>名前</th><th>定義</th><th>手がかり</th></tr>` +
    (r.situations || []).map((s) => `<tr class="click si-row" data-id="${esc(s.id)}"><td>${esc(s.id)}</td><td>${esc(s.name)}</td><td>${esc(s.definition)}</td><td>${(s.signals || []).map(esc).join("<br>")}</td></tr>`).join("") + "</table>";
  document.querySelectorAll(".si-row").forEach((tr) => (tr.onclick = () => { const s = (r.situations || []).find((x) => x.id === tr.dataset.id); $("si-id").value = s.id; $("si-name").value = s.name; $("si-def").value = s.definition || ""; $("si-signals").value = (s.signals || []).join("\n"); }));
}
$("si-load").onclick = loadSituations;
$("si-save").onclick = async () => {
  const body = { id: $("si-id").value.trim(), name: $("si-name").value.trim(), definition: $("si-def").value.trim(), signals: $("si-signals").value.split("\n").map((s) => s.trim()).filter(Boolean) };
  const r = await api("POST", "/situations", body);
  if (guard("si-out", r)) loadSituations();
};

// ------------------------------------------------------------ 一般化
$("gn-search").onclick = async () => {
  busy("gn-list");
  if (!units.length) { const r = await api("GET", "/survey"); if (!guard("gn-list", r)) return; units = r.units || []; }
  const q = $("gn-filter").value.trim().toLowerCase();
  const list = units.filter((u) => u.kind === "skill" && (!q || `${u.name} ${u.title} ${u.target} ${u.rel}`.toLowerCase().includes(q))).slice(0, 100);
  $("gn-list").innerHTML = `<table><tr><th>スコープ</th><th>名前</th><th>配布先</th><th>場所</th><th></th></tr>` +
    list.map((u) => `<tr><td>${esc(u.scope)}</td><td>${esc(u.name || u.title)}</td><td>${esc(u.target)}</td><td class="path">${esc(u.rel)}</td><td><button class="gn-go" data-id="${esc(u.id)}">一般化</button></td></tr>`).join("") + "</table>";
  document.querySelectorAll(".gn-go").forEach((b) => (b.onclick = () => runGeneralize(b.dataset.id)));
};
async function runGeneralize(unitId) {
  busy("gn-out", "LLM で書き換え中…（数十秒かかることがあります）");
  const r = await api("POST", "/generalize", { unit_id: unitId });
  if (!guard("gn-out", r)) return;
  const u = r.unit || {};
  $("gn-out").innerHTML = `<div class="card"><h3>${esc(u.name)}</h3>
    <p>検出した固有の語: ${(r.findings || []).map((f) => `<span class="badge b-warn">${esc(f.term)}（${esc(f.kind)}×${f.count}）</span>`).join(" ") || '<span class="muted">なし</span>'}</p>
    <p>書き換え後に残った語: ${(r.remaining || []).map((t) => `<span class="badge b-bad">${esc(t)}</span>`).join(" ") || '<span class="badge b-ok">なし</span>'} <span class="muted">モデル: ${esc(r.model || "")}</span></p>
    <div class="side"><div><h3>元</h3><pre>${esc(u.text)}</pre></div><div><h3>一般化の案（編集できます）</h3><textarea id="gn-text" rows="24">${esc(r.proposal)}</textarea></div></div>
    <div class="bar"><select id="gn-scope"><option value="user">ユーザー固有（ペア固有スキル）へ</option><option value="global">全体（home-claude/skills）へ</option></select>
    <input id="gn-name" value="${esc(r.suggested_name || u.name || "")}" placeholder="ファイル名（ケバブケース）"><button id="gn-promote">マスターへ昇格</button></div><div id="gn-prom-out"></div></div>`;
  $("gn-promote").onclick = async () => {
    const p = await api("POST", "/generalize/promote", { unit_id: unitId, text: $("gn-text").value, scope: $("gn-scope").value, name: $("gn-name").value.trim() });
    if (guard("gn-prom-out", p)) $("gn-prom-out").innerHTML = `<p><span class="badge b-ok">書き込み</span> <code>${esc(p.written)}</code></p>`;
  };
}

// ------------------------------------------------------------ 再配布
let plan = null;
async function fillDistTargets() {
  const r = await api("GET", "/targets");
  if (r.implemented === false) { $("ds-targets").innerHTML = '<div class="notimpl">未実装 <span class="muted">(targets.list)</span></div>'; return; }
  $("ds-targets").innerHTML = (r.targets || []).map((t) => `<label><input type="checkbox" class="ds-t" value="${esc(t.id)}" data-kind="${esc(t.kind)}"> ${esc(t.name)} <span class="muted">(${esc(t.kind)})</span></label>`).join("") || '<p class="muted">配布先が登録されていません</p>';
}
$("ds-plan").onclick = async () => {
  busy("ds-out", "計画中…"); $("ds-diff").innerHTML = "";
  const ids = [...document.querySelectorAll(".ds-t:checked")].map((c) => c.value);
  const r = await api("POST", "/distribute/plan", { scope: $("ds-scope").value, target_ids: ids });
  if (!guard("ds-out", r)) return;
  plan = r;
  const acts = r.actions || [];
  $("ds-out").innerHTML = `<p class="muted">計画 ${esc(r.plan_id)} ・ ${acts.length} 行（一致は除外済み ${r.skipped_same || 0}）。「配布先で改変」「双方で変更」の行は既定で選ばない。</p><table><tr><th><input type="checkbox" id="ds-all"></th><th>動作</th><th>状態</th><th>配布先</th><th>マスター</th><th>書き込み先</th></tr>` +
    acts.map((a) => `<tr><td><input type="checkbox" class="ds-a" value="${esc(a.id)}" ${a.selected_default ? "checked" : ""}></td><td>${badge(a.action)}</td><td>${badge(a.state)}</td><td>${esc(a.target_name)}</td><td class="path">${esc(a.src_rel)}</td><td class="path click ds-d" data-t="${esc(a.target_id)}" data-rel="${esc(a.dest_rel)}" style="text-decoration:underline">${esc(a.dest_path)}</td></tr>`).join("") + "</table>";
  $("ds-all").onchange = (e) => document.querySelectorAll(".ds-a").forEach((cb) => (cb.checked = e.target.checked));
  document.querySelectorAll(".ds-d").forEach((td) => (td.onclick = () => showDiff(td.dataset.t, td.dataset.rel, "ds-diff")));
};
$("ds-apply").onclick = async () => {
  if (!plan) { $("ds-out").innerHTML = '<p class="muted">先に計画を作ってください</p>'; return; }
  const ids = [...document.querySelectorAll(".ds-a:checked")].map((c) => c.value);
  if (!ids.length) { $("ds-diff").innerHTML = '<p class="muted">適用する行を選んでください</p>'; return; }
  busy("ds-diff", "適用中…");
  const r = await api("POST", "/distribute/apply", { plan_id: plan.plan_id, action_ids: ids });
  if (!guard("ds-diff", r)) return;
  $("ds-diff").innerHTML = `<div class="card"><p><span class="badge b-ok">適用 ${r.applied?.length || 0} 件</span> 退避先: <code>${esc(r.backup_dir || "（退避なし）")}</code></p><pre>${esc((r.applied || []).map((a) => a.dest_path).join("\n"))}</pre></div>`;
  plan = null;
};

// ------------------------------------------------------------ GitHub
$("fl-load").onclick = async () => { busy("fl-out"); const r = await api("GET", "/fleet"); if (guard("fl-out", r)) $("fl-out").innerHTML = `<pre>${esc(JSON.stringify(r, null, 2))}</pre>`; };
$("fl-publish").onclick = async () => { busy("fl-out"); const r = await api("POST", "/fleet/publish"); if (guard("fl-out", r)) $("fl-out").innerHTML = `<pre>${esc(JSON.stringify(r, null, 2))}</pre>`; };
$("fl-pull").onclick = async () => { busy("fl-out"); const r = await api("POST", "/fleet/pull"); if (guard("fl-out", r)) $("fl-out").innerHTML = `<pre>${esc(JSON.stringify(r, null, 2))}</pre>`; };

// ------------------------------------------------------------ 設定
function fillModelSelects(models, cur) {
  for (const [id, key] of [["cf-model-judge", "model_judge"], ["cf-model-rewrite", "model_rewrite"]]) {
    const v = cur?.[key] || $(id).value;
    const names = [...new Set([...(v ? [v] : []), ...models])];
    $(id).innerHTML = names.map((m) => `<option ${m === v ? "selected" : ""}>${esc(m)}</option>`).join("");
  }
}
async function loadSettings() {
  const r = await api("GET", "/settings");
  if (!guard("cf-out", r)) return;
  const s = r.settings || {};
  $("cf-base").value = s.ollama_base_url || "";
  $("cf-roots").value = (s.scan_roots || []).join("\n");
  $("cf-depth").value = s.scan_depth || 2;
  if (!$("disc-roots").value) $("disc-roots").value = (s.scan_roots || []).join("\n");
  fillModelSelects([], s);
  $("cf-out").innerHTML = "";
}
$("cf-load").onclick = loadSettings;
$("cf-models").onclick = async () => {
  busy("cf-llm-out", "モデル一覧を取得中…");
  const r = await api("GET", "/llm/models?base_url=" + encodeURIComponent($("cf-base").value.trim()));
  if (!guard("cf-llm-out", r)) return;
  fillModelSelects(r.models || []);
  $("cf-llm-out").innerHTML = `<p class="muted">${esc(r.base_url)} ・ ${(r.models || []).length} モデル</p>`;
};
$("cf-save").onclick = async () => {
  const body = { ollama_base_url: $("cf-base").value.trim(), model_judge: $("cf-model-judge").value, model_rewrite: $("cf-model-rewrite").value, scan_roots: $("cf-roots").value.split("\n").map((s) => s.trim()).filter(Boolean), scan_depth: Number($("cf-depth").value) };
  const r = await api("PUT", "/settings", body);
  if (guard("cf-out", r)) $("cf-out").innerHTML = '<p><span class="badge b-ok">保存しました</span></p>';
};
$("cf-test").onclick = async () => {
  busy("cf-llm-out", "LLM に問い合わせ中…");
  const r = await api("POST", "/llm/test", { model: $("cf-model-judge").value, base_url: $("cf-base").value.trim() });
  if (!guard("cf-llm-out", r)) return;
  $("cf-llm-out").innerHTML = `<p><span class="badge ${r.ok ? "b-ok" : "b-bad"}">${r.ok ? "応答あり" : "失敗"}</span> ${esc(r.model)} ・ ${r.elapsed_ms ?? "-"} ms</p><pre>${esc(r.content || r.error || "")}</pre>`;
};

$("rs-save").onclick = async () => {
  const r = await api("PUT", "/resident", { autostart: $("rs-autostart").checked, notify: $("rs-notify").checked, interval_min: Number($("rs-interval").value), watch: $("rs-watch").checked });
  if (guard("rs-out", r)) $("rs-out").innerHTML = '<p><span class="badge b-ok">保存しました</span></p>';
};

// ------------------------------------------------------------ 起動
loadHealth();
loadResident();
const first = (location.hash || "#inbox").slice(1);
showTab(document.getElementById("tab-" + first) ? first : "inbox");

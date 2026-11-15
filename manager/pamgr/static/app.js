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
  const onShow = { targets: loadTargets, status: fillTargetSelect, situations: loadSituations, distribute: fillDistTargets, settings: loadSettings, dashboard: loadDashboard };
  if (onShow[name]) onShow[name]();
}

// ------------------------------------------------------------ ヘッダ・ダッシュボード
async function loadHealth() {
  const h = await api("GET", "/health");
  $("hdr-info").textContent = h.master_root ? `v${h.version} ・ マスター: ${h.master_root} ・ データ: ${h.data_home}` : "";
}
async function loadDashboard() {
  busy("dash-out");
  const r = await api("GET", "/dashboard");
  if (!guard("dash-out", r)) return;
  const s = r.stats || {};
  const card = (n, l) => `<div class="stat"><div class="n">${esc(n ?? "-")}</div><div class="l">${esc(l)}</div></div>`;
  $("dash-out").innerHTML = `<div class="stats">${card(s.targets, "登録済みの配布先")}${card(s.drift, "マスターとずれているファイル")}${card(s.units, "サーベイ済みの単位")}${card(s.findings, "検査の指摘（仮説）")}${card(s.situations, "状況定義")}</div>` +
    (r.notes || []).map((n) => `<p class="muted">${esc(n)}</p>`).join("");
}
$("dash-refresh").onclick = loadDashboard;

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

// ------------------------------------------------------------ 起動
loadHealth();
showTab((location.hash || "#dashboard").slice(1));

export const meta = {
  name: "meta",
  description: "meta の成果物 DAG を 1 巡させる（役 3 ／ 機械 3 ／ 人間ゲート 2）",
  whenToUse: "成果物定義 meta.mk に沿って、要求から受入検査まで1 パス通したいとき。args.root に作業根を渡す",
  phases: [
    { title: "第1段", detail: "実績" },
    { title: "第2段", detail: "探針結果" },
    { title: "第3段", detail: "見積もり" },
    { title: "第4段", detail: "プロジェクト方針 / 成立可否" },
    { title: "第5段", detail: "ドメインの.mk" },
  ],
}

// 自動生成。手で編集しない。正は models/meta.mk
// 生成: python tools/emit_claude.py models/meta.mk
//
// ⚠ 段ごとに parallel（バリア）を張っている。**ここでは正しい** ——
//    次の段の担い手は、前の段が**ファイルとして置いた成果物**を読む。
//    台本にファイルシステムは無いので、置かれたことは前段の完了でしか分からない。
//
// ⚠ `by: human` の rule は走らせない（P-12: A は委譲不能）。
//    最後に「人間に渡すもの」として列挙して台本を終える。

const MODEL = "meta"
const NODES = {
  "実績": {
    "target": "実績",
    "role": "機械",
    "task": "aggregate_track_record",
    "by": "machine",
    "agentType": "meta-aggregate-track-record",
    "gate": "",
    "path": "meta/実績.md",
    "deps": [
      {
        "name": "受入検査報告書?",
        "node": "受入検査報告書",
        "kind": "任意",
        "path": "inbox/受入検査報告書.md"
      },
      {
        "name": "見積もり_v(m-1)",
        "node": "見積もり",
        "kind": "前版",
        "path": "meta/見積もり.md"
      },
      {
        "name": "探針結果_v(k-1)",
        "node": "探針結果",
        "kind": "前版",
        "path": "meta/探針結果.md"
      }
    ],
    "blocks": [],
    "checks": [],
    "writes": [
      "実績"
    ],
    "post": [
      "**測定条件を伴わない数値を含まない**（値だけ残すと普遍値の顔をする）",
      "失敗した試みも含まれている（成功だけを残していない＝生存者バイアスの排除）",
      "集約であって、判断を混ぜていない"
    ],
    "out": [
      "何をどれくらいで作り、実際どうだったか —— **測定条件つきで**",
      "見積もり と 実際 の差（見積もり精度そのものが実績になる）"
    ],
    "skills": []
  },
  "探針結果": {
    "target": "探針結果",
    "role": "探針実施者",
    "task": "run_probe",
    "by": "agent",
    "agentType": "meta-run-probe",
    "gate": "",
    "path": "meta/探針結果.md",
    "deps": [
      {
        "name": "要望",
        "node": "要望",
        "kind": "必須",
        "path": "inbox/要望.md"
      },
      {
        "name": "実行環境",
        "node": "実行環境",
        "kind": "必須",
        "path": "inbox/実行環境.md"
      },
      {
        "name": "実績",
        "node": "実績",
        "kind": "必須",
        "path": "meta/実績.md"
      }
    ],
    "blocks": [
      "見積もり",
      "プロジェクト方針",
      "期日"
    ],
    "checks": [],
    "writes": [
      "探針結果"
    ],
    "post": [
      "実験の産物を成果物へ継承していない（捨てている）",
      "**実験が他人の成果物に書き込んでいない。**実行環境に残った副作用は測定条件に申告している",
      "「できなかった」と「原理的にできない」を区別して書いている",
      "上限を主張するときは、測定条件が再現できる形で書かれている"
    ],
    "out": [
      "実現可能性の判定（この要求は満たせるか／上限はどこか）",
      "測定値と、再現できる形の測定条件",
      "理由 ＋ 残留リスク"
    ],
    "skills": [
      "実験の設計",
      "測定"
    ]
  },
  "見積もり": {
    "target": "見積もり",
    "role": "見積もり者",
    "task": "estimate",
    "by": "agent",
    "agentType": "meta-estimate",
    "gate": "M1",
    "path": "meta/見積もり.md",
    "deps": [
      {
        "name": "要望",
        "node": "要望",
        "kind": "必須",
        "path": "inbox/要望.md"
      },
      {
        "name": "実績",
        "node": "実績",
        "kind": "必須",
        "path": "meta/実績.md"
      },
      {
        "name": "探針結果",
        "node": "探針結果",
        "kind": "必須",
        "path": "meta/探針結果.md"
      },
      {
        "name": "アーキテクチャ?",
        "node": "アーキテクチャ",
        "kind": "任意",
        "path": "inbox/アーキテクチャ.md"
      },
      {
        "name": "ドメインの.mk_v(p-1)",
        "node": "ドメインの.mk",
        "kind": "前版",
        "path": "meta/ドメインの.mk"
      }
    ],
    "blocks": [
      "期日",
      "資源上限",
      "プロジェクト方針"
    ],
    "checks": [],
    "writes": [
      "見積もり"
    ],
    "post": [
      "不確かさが幅で書かれている（点推定になっていない）",
      "外挿の根拠が実績のどれに紐づくか書かれている",
      "期日・資源上限に言及していない（見ていない証拠）"
    ],
    "out": [
      "規模・所要（**不確かさを幅で**。点推定にしない）",
      "外挿の根拠 —— 実績のどれに紐づくか",
      "版（v1 粗 → 探針で v2 → アーキテクチャで v3）",
      "理由 ＋ 残留リスク"
    ],
    "skills": [
      "外挿と不確かさ",
      "測定"
    ]
  },
  "プロジェクト方針": {
    "target": "プロジェクト方針",
    "role": "PjM",
    "task": "decide_policy",
    "by": "agent",
    "agentType": "meta-decide-policy",
    "gate": "M2",
    "path": "meta/プロジェクト方針.md",
    "deps": [
      {
        "name": "見積もり",
        "node": "見積もり",
        "kind": "必須",
        "path": "meta/見積もり.md"
      },
      {
        "name": "期日",
        "node": "期日",
        "kind": "必須",
        "path": "inbox/期日.md"
      },
      {
        "name": "資源上限",
        "node": "資源上限",
        "kind": "必須",
        "path": "inbox/資源上限.md"
      },
      {
        "name": "A の帯域",
        "node": "A の帯域",
        "kind": "必須",
        "path": "inbox/Aの帯域.md"
      },
      {
        "name": "要望",
        "node": "要望",
        "kind": "必須",
        "path": "inbox/要望.md"
      },
      {
        "name": "アーキテクチャ?",
        "node": "アーキテクチャ",
        "kind": "任意",
        "path": "inbox/アーキテクチャ.md"
      },
      {
        "name": ".mkカタログ?",
        "node": ".mkカタログ",
        "kind": "任意",
        "path": "models"
      }
    ],
    "blocks": [],
    "checks": [
      "見積もり"
    ],
    "writes": [
      "プロジェクト方針"
    ],
    "post": [
      "ゲートの数が A の帯域の範囲に収まっている",
      "選択の根拠が「見積もりと 期日・資源上限 の差」に紐づいている",
      "既製の `.mk` を選んだなら、どれをなぜ選んだかが書かれている",
      "**カタログが空だったなら、そう申告したうえで書いている**（P-53。空を埋めない）",
      "見積もりを書き換えていない（合わないなら要望か期日を動かす）",
      "要望を勝手に切っていない —— ドロップは範囲外。人間が `要望` の版を入れ直す（P-23）"
    ],
    "out": [
      "**ドメインの `.mk`** —— 既製カタログから選ぶ、または書く",
      "ゲート配置（**A の帯域の配分**。これが役割数を決める）",
      "「扱い」の型のうちどれを許すか（スコープ外／延期／代案／不可能・W-6）",
      "判定の値域（合否は二値か、保留を許すか・G-10）",
      "探針の要否",
      "理由（なぜその `.mk` を選んだか）＋ 残留リスク"
    ],
    "skills": [
      "プロセスモデルの選択",
      "受入検査の隔離規約",
      "帰責の設計",
      "資源配分"
    ]
  },
  "ドメインの.mk": {
    "target": "ドメインの.mk",
    "role": "機械",
    "task": "extract_process_model",
    "by": "machine",
    "agentType": "meta-extract-process-model",
    "gate": "",
    "path": "meta/ドメインの.mk",
    "deps": [
      {
        "name": "プロジェクト方針",
        "node": "プロジェクト方針",
        "kind": "必須",
        "path": "meta/プロジェクト方針.md"
      }
    ],
    "blocks": [],
    "checks": [],
    "writes": [
      "ドメインの.mk"
    ],
    "post": [
      "**選択の理由と、期日・資源上限との差を含まない**",
      "方針から決定的に取り出されている（内容を足していない）"
    ],
    "out": [
      "工程・ゲート配置・扱いの型・判定の値域（＝ドメイン層の正典）"
    ],
    "skills": []
  },
  "成立可否": {
    "target": "成立可否",
    "role": "機械",
    "task": "check_feasibility_envelope",
    "by": "machine",
    "agentType": "meta-check-feasibility-envelope",
    "gate": "",
    "path": "meta/成立可否.md",
    "deps": [
      {
        "name": "見積もり",
        "node": "見積もり",
        "kind": "必須",
        "path": "meta/見積もり.md"
      },
      {
        "name": "期日",
        "node": "期日",
        "kind": "必須",
        "path": "inbox/期日.md"
      },
      {
        "name": "資源上限",
        "node": "資源上限",
        "kind": "必須",
        "path": "inbox/資源上限.md"
      }
    ],
    "blocks": [],
    "checks": [],
    "writes": [
      "成立可否"
    ],
    "post": [
      "決定論的である。判断を混ぜない"
    ],
    "out": [
      "見積もりの幅が 期日・資源上限 の内側に収まるか（決定論的）"
    ],
    "skills": []
  }
}
const LEVELS = [
  [
    "実績"
  ],
  [
    "探針結果"
  ],
  [
    "見積もり"
  ],
  [
    "プロジェクト方針",
    "成立可否"
  ],
  [
    "ドメインの.mk"
  ]
]
const ORIGINS = [
  {
    "name": "要望",
    "path": "inbox/要望.md"
  },
  {
    "name": "期日",
    "path": "inbox/期日.md"
  },
  {
    "name": "資源上限",
    "path": "inbox/資源上限.md"
  },
  {
    "name": "A の帯域",
    "path": "inbox/Aの帯域.md"
  },
  {
    "name": "実行環境",
    "path": "inbox/実行環境.md"
  },
  {
    "name": "受入検査報告書",
    "path": "inbox/受入検査報告書.md"
  },
  {
    "name": "アーキテクチャ",
    "path": "inbox/アーキテクチャ.md"
  },
  {
    "name": ".mkカタログ",
    "path": "models"
  }
]
const HUMAN = []

// 完了報告（ブリーフの 6 項目）。schema を付けた呼び出しは検証済みで返る
const REPORT = {
  type: 'object',
  required: ['target', 'path', 'postconditions', 'readFiles', 'emptyDeps', 'broughtKnowledge', 'escalated'],
  properties: {
    target: { type: 'string' },
    path: { type: 'string' },
    postconditions: { type: 'array', items: { type: 'object',
      required: ['condition', 'met'],
      properties: { condition: { type: 'string' }, met: { type: 'boolean' }, note: { type: 'string' } } } },
    readFiles: { type: 'array', items: { type: 'string' } },
    emptyDeps: { type: 'array', items: { type: 'string' } },
    broughtKnowledge: { type: 'array', items: { type: 'string' } },
    escalated: { type: 'array', items: { type: 'string' } },
  },
}

const root = (args && args.root) || 'workspace'
const stopAtGate = !!(args && args.stopAtGate)
// args.force で検出条件を無視して全部走らせる（初回や、状態を疑うとき）
const force = !!(args && args.force)

// 遵守の申告を違反として拾わないための否定語（check_report.py の DENIAL と同じ）
const DENIAL = /読ま|読んでいない|読んでない|遮断|禁止|見ていない|参照していない|開いていない|触れていない/
const BSLASH = String.fromCharCode(92)

function at(p) { return root + '/' + p }
const chr10 = String.fromCharCode(10)
function norm0(x) { return String(x).split(BSLASH).join('/').toLowerCase() }

function briefOf(s) {
  const L = []
  L.push('作業根は ' + root + ' である。担当は ' + s.target + ' ただ一つ。')
  L.push('')
  L.push('## 読んでよいもの（deps）—— これ以外を読んではならない')
  if (!s.deps.length) L.push('- （無し。起点から始まる）')
  s.deps.forEach(function (d) {
    L.push('- ' + d.name + '（' + d.kind + '）: ' + at(d.path))
  })
  if (s.blocks.length) {
    L.push('')
    L.push('## 読んではならないもの（遮断）')
    s.blocks.forEach(function (b) { L.push('- ' + b) })
  }
  L.push('')
  L.push('## 書くもの')
  L.push('- ' + s.target + ' を ' + at(s.path) + ' に置く（単一ファイルなら .md を付けてよい。複数ならディレクトリにする）')
  L.push('- 作業空間は自由に使ってよい。他人の成果物には書き込まない')
  if (s.post.length) {
    L.push('')
    L.push('## 事後条件（これを満たさなければ完了ではない）')
    s.post.forEach(function (c, i) { L.push((i + 1) + '. ' + c) })
  }
  L.push('')
  L.push('## 返す形')
  L.push('StructuredOutput で返す。postconditions は**上の事後条件を 1 つずつ**、原文のまま condition に入れて met を付ける。')
  L.push('readFiles には**実際に読んだファイルを全部**挙げる（遮断が効いていたかを機械が検める）。')
  L.push('emptyDeps には**空だった dep**（前版・任意で存在しなかったもの）を挙げる。埋めていないことを示す。')
  L.push('broughtKnowledge には**deps に無かった知識で決めた箇所**を挙げる。遮断はファイルにしか掛かっていない —— 申告しなければ誰にも見えない。')
  return L.join('\n')
}

log('起点（外から与えられる。誰も作らない）: ' + (ORIGINS.length
  ? ORIGINS.map(function (o) { return o.name + ' → ' + at(o.path) }).join(' / ')
  : 'なし'))

// ── 起動の 2 条件（P-53）─────────────────────────────
//
// ⚠ **台本にファイルシステムは無い。** 存在と更新時刻は測れないので、
//    それだけを見る担い手を 1 体立て、**判定は台本側で決定的に行う。**
//    測らせるのは存在と時刻だけである。中身は読ませない（遮断を跨がないため）。
const PROBE = {
  type: 'object', required: ['files'],
  properties: { files: { type: 'array', items: { type: 'object',
    required: ['path', 'exists'],
    properties: { path: { type: 'string' }, exists: { type: 'boolean' },
      mtime: { type: 'number' } } } } },
}

const stat = {}
if (!force) {
  // ⚠ NODES だけでは足りない。`by: human` の成果物（差し戻し指示）は
  //    NODES に居ないので、**dep のパスも観測対象に入れる。**
  //    入れないと、差し戻しても検出できない（実測前に気づいた漏れ）
  const seen0 = {}
  const paths = []
  const addPath = function (x) {
    if (x && !seen0[x]) { seen0[x] = 1; paths.push(x) }
  }
  ORIGINS.forEach(function (o) { addPath(o.path) })
  Object.keys(NODES).forEach(function (n) {
    addPath(NODES[n].path)
    NODES[n].deps.forEach(function (d) { addPath(d.path) })
  })
  phase('検出')
  const probe = await agent(
    ['次のパスについて、**存在するかどうかと最終更新時刻だけ**を調べて返す。',
     '',
     '⚠ **中身は読まない。** 存在と時刻だけを見る。',
     '⚠ ディレクトリなら、**その中で最も新しいファイルの時刻**を返す。',
     '⚠ 存在しないものは exists=false / mtime=0 とする。',
     'mtime は**エポック秒の整数**で返す。path は渡した文字列をそのまま返す。',
     '',
     paths.map(function (t) { return '- ' + at(t) }).join(chr10)].join(chr10),
    { label: '状態の観測', phase: '検出', schema: PROBE })
  ;((probe && probe.files) || []).forEach(function (f) {
    stat[norm0(f.path)] = f.exists ? (f.mtime || 0) : null
  })
}

// パスの表記ゆれ（区切り・大小・絶対と相対）を吸収して引く
function look(p) {
  const key = norm0(at(p))
  if (key in stat) return stat[key]
  const tail = norm0(p)
  const hit = Object.keys(stat).filter(function (k)
    { return k.indexOf(tail) >= 0 })
  return hit.length ? stat[hit[0]] : null
}
const updated = {}

// **実行可能条件を先に判定し、そのうえで検出条件で起動する。**
// **片方だけでは起動条件にならない**（P-53）
function fires(n) {
  if (force) return { run: true, why: 'args.force' }
  const s = NODES[n]
  // 自分自身を指す dep（前版）は判定に使わない
  const other = s.deps.filter(function (d) { return d.node !== n })
  const missing = other.filter(function (d)
    { return d.kind === '必須' && look(d.path) === null })
  if (missing.length) return { run: false, wait: true,
    why: '必須 dep が無い: ' + missing.map(function (d)
      { return d.name }).join('/') }
  const mine = look(s.path)
  if (mine === null) return { run: true, why: 'target がまだ無い' }
  const newer = other.filter(function (d) {
    if (updated[d.node]) return true
    const t = look(d.path)
    return t !== null && t > mine
  })
  if (newer.length) return { run: true,
    why: '新しい dep: ' + newer.map(function (d)
      { return d.name }).join('/') }
  return { run: false, why: 'deps はどれも target より新しくない' }
}

const produced = []
const skipped = []
const unmet = []
const blocked = []
const outside = []
const openGates = []
let halted = null

for (let i = 0; i < LEVELS.length && !halted; i++) {
  const title = '第' + (i + 1) + '段'
  const names = []
  LEVELS[i].forEach(function (n) {
    const f = fires(n)
    if (f.run) { names.push(n); return }
    skipped.push({ target: NODES[n].target, why: f.why, wait: !!f.wait })
    log('  — ' + NODES[n].target + ' は走らせない（' + f.why + '）')
  })
  if (!names.length) continue
  phase(title)
  log(title + ': ' + names.map(function (n) { return NODES[n].target }).join(' / '))
  const reports = await parallel(names.map(function (n) {
    return function () {
      const s = NODES[n]
      return agent(briefOf(s), {
        label: s.target,
        phase: title,
        agentType: s.agentType,
        schema: REPORT,
      })
    }
  }))
  for (let k = 0; k < names.length; k++) {
    const s = NODES[names[k]]
    const rep = reports[k]
    if (!rep) {
      unmet.push({ target: s.target, condition: '(報告なし)', note: 'エージェントが結果を返さなかった' })
      continue
    }
    produced.push({ target: s.target, path: rep.path, by: s.by })
    updated[names[k]] = true
    ;(rep.postconditions || []).forEach(function (p) {
      if (!p.met) unmet.push({ target: s.target, condition: p.condition, note: p.note || '' })
    })
    // 遮断の機械検査 —— check_report.py の [遮断の疑い] と同じ位置づけ。
    // ⚠ **申告しなかった読み取りは、報告からは原理的に見えない**（P-13）
    //
    // 2 種を分けて見る:
    //   blocked … blocks に挙がった成果物名が、読んだ申告に現れる（ブラックリスト）
    //   outside … deps でも作業空間でもないパスを読んでいる（ホワイトリスト）
    //
    // ⚠ **否定の申告を違反として拾ってはならない。**
    //    「実装物は読んでいない」は違反ではなく**遵守の申告**である。
    //    実測（2026-09-06）: これで偽陽性が 6 件出た。
    //    check_report.py の DENIAL と同じ扱いにする（あちらは先に解いていた）。
    // ⚠ 申告のパスは `BSLASH` 区切りで来る（Windows）。`.mk` 由来の宣言は `/` 区切りである。
    //    揃えずに比べると**すべてが deps 外に見える**（実測 2026-09-06: 偽陽性 21 件）。
    var norm = function (x) { return String(x).split(BSLASH).join('/').toLowerCase() }
    var allowed = s.deps.map(function (d) { return norm(d.path) }).concat([norm(s.path), 'workspace'])
    ;(rep.readFiles || []).forEach(function (f) {
      var t = String(f)
      if (DENIAL.test(t)) return
      s.blocks.forEach(function (b) {
        if (t.indexOf(b) >= 0) blocked.push({ target: s.target, forbidden: b, read: t })
      })
      // パスに見えないもの（散文の申告）は、ホワイトリストでは判定しない
      if (t.indexOf('/') < 0 && t.indexOf(BSLASH) < 0) return
      var nt = norm(t)
      var ok = allowed.some(function (a) { return a && nt.indexOf(a) >= 0 })
      if (!ok) outside.push({ target: s.target, read: t })
    })
    if (s.gate) {
      openGates.push({ gate: s.gate, target: s.target, path: rep.path })
      log('⏸ 人間ゲート ' + s.gate + ': ' + s.target + ' —— A の判定が要る')
      if (stopAtGate) halted = s.gate
    }
  }
  if (halted) log('args.stopAtGate により ' + halted + ' で止めた')
}

if (HUMAN.length) {
  log('人間に渡すもの（by: human。台本は走らせない・P-12）: '
    + HUMAN.map(function (h) { return h.target }).join(' / '))
}
if (skipped.length)
  log('走らせなかった rule ' + skipped.length + ' 件（P-53 の起動条件）')
if (unmet.length) log('未達の事後条件 ' + unmet.length + ' 件')
if (blocked.length) log('⚠ 遮断の疑い ' + blocked.length + ' 件')
if (outside.length) log('⚠ deps 外の読み取りの疑い ' + outside.length + ' 件')

return {
  model: MODEL,
  root: root,
  produced: produced,
  skipped: skipped,
  unmet: unmet,
  blocked: blocked,
  outside: outside,
  openGates: openGates,
  haltedAt: halted,
  human: HUMAN,
}

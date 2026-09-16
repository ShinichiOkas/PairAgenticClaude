export const meta = {
  name: "pair-agent-s",
  description: "pair-agent-s の成果物 DAG を 1 巡させる（役 5 ／ 機械 1 ／ 人間ゲート 1）",
  whenToUse: "成果物定義 pair-agent-s.mk に沿って、要求から受入検査まで1 パス通したいとき。args.root に作業根を渡す",
  phases: [
    { title: "第1段", detail: "受入検査仕様 / 実装物_v(n)" },
    { title: "第2段", detail: "設計保証 / 非回帰の合否" },
    { title: "第3段", detail: "受入検査報告書" },
    { title: "第4段", detail: "リポジトリの状態" },
  ],
}

// 自動生成。手で編集しない。正は /Users/shinichi/work/PairAgenticClaude/models/pair-agent-s.mk
// 生成: python tools/emit_claude.py /Users/shinichi/work/PairAgenticClaude/models/pair-agent-s.mk
//
// ⚠ 段ごとに parallel（バリア）を張っている。**ここでは正しい** ——
//    次の段の担い手は、前の段が**ファイルとして置いた成果物**を読む。
//    台本にファイルシステムは無いので、置かれたことは前段の完了でしか分からない。
//
// ⚠ `by: human` の rule は走らせない（P-12: A は委譲不能）。
//    最後に「人間に渡すもの」として列挙して台本を終える。

const MODEL = "pair-agent-s"
const NODES = {
  "受入検査仕様": {
    "target": "受入検査仕様",
    "role": "受入検査設計者",
    "task": "design_acceptance_tests",
    "by": "agent",
    "agentType": "pair-agent-s-design-acceptance-tests",
    "gate": "",
    "path": ".pair-agent/acceptance/受入検査仕様.md",
    "deps": [
      {
        "name": "バグ票",
        "node": "バグ票",
        "kind": "必須",
        "path": ".pair-agent/sprints/バグ票.md"
      },
      {
        "name": "差し戻し指示_v(j-1)",
        "node": "差し戻し指示",
        "kind": "前版",
        "path": ".pair-agent/assurance/差し戻し指示.md"
      }
    ],
    "blocks": [
      "実装物"
    ],
    "checks": [],
    "writes": [
      "受入検査仕様"
    ],
    "post": [
      "実装コードを見ずに書かれている",
      "各判定基準が明確である"
    ],
    "out": [
      "バグ票の再現条件と修正判定基準"
    ],
    "skills": [
      "同値分割",
      "境界値分析"
    ]
  },
  "実装物": {
    "target": "実装物_v(n)",
    "role": "構築者",
    "task": "build",
    "by": "agent",
    "agentType": "pair-agent-s-build",
    "gate": "",
    "path": "src/",
    "deps": [
      {
        "name": "バグ票",
        "node": "バグ票",
        "kind": "必須",
        "path": ".pair-agent/sprints/バグ票.md"
      },
      {
        "name": "実装物_v(n-1)",
        "node": "実装物",
        "kind": "前版",
        "path": "src/"
      },
      {
        "name": "差し戻し指示_v(m-1)",
        "node": "差し戻し指示",
        "kind": "前版",
        "path": ".pair-agent/assurance/差し戻し指示.md"
      }
    ],
    "blocks": [
      "受入検査仕様"
    ],
    "checks": [],
    "writes": [
      "実装物"
    ],
    "post": [
      "バグ票の事象を解消する実装となっている"
    ],
    "out": [
      "修正された実装コード"
    ],
    "skills": [
      "ホワイトボックステストの書き方",
      "実装言語・基盤の知識",
      "縮退経路のログ設計"
    ]
  },
  "非回帰の合否": {
    "target": "非回帰の合否",
    "role": "機械",
    "task": "run_regression",
    "by": "machine",
    "agentType": "pair-agent-s-run-regression",
    "gate": "",
    "path": ".pair-agent/assurance/非回帰の合否.md",
    "deps": [
      {
        "name": "実装物_v(n)",
        "node": "実装物",
        "kind": "必須",
        "path": "src/"
      }
    ],
    "blocks": [],
    "checks": [],
    "writes": [
      "非回帰の合否"
    ],
    "post": [
      "決定論的である。「既知の赤」で通さない"
    ],
    "out": [
      "既存テストの合否結果"
    ],
    "skills": []
  },
  "設計保証": {
    "target": "設計保証",
    "role": "構築者",
    "task": "assure_design",
    "by": "agent",
    "agentType": "pair-agent-s-assure-design",
    "gate": "",
    "path": ".pair-agent/assurance/設計保証.md",
    "deps": [
      {
        "name": "バグ票",
        "node": "バグ票",
        "kind": "必須",
        "path": ".pair-agent/sprints/バグ票.md"
      },
      {
        "name": "実装物_v(n)",
        "node": "実装物",
        "kind": "必須",
        "path": "src/"
      }
    ],
    "blocks": [
      "受入検査仕様"
    ],
    "checks": [],
    "writes": [
      "設計保証"
    ],
    "post": [
      "受入検査から見えない内部整合性が保証されている"
    ],
    "out": [
      "修正箇所の説明と副作用がない根拠"
    ],
    "skills": [
      "エビデンスの設計",
      "保証範囲の切り出し"
    ]
  },
  "受入検査報告書": {
    "target": "受入検査報告書",
    "role": "受入検査実施者",
    "task": "execute_acceptance_tests",
    "by": "agent",
    "agentType": "pair-agent-s-execute-acceptance-tests",
    "gate": "H1",
    "path": ".pair-agent/acceptance/受入検査報告書.md",
    "deps": [
      {
        "name": "受入検査仕様",
        "node": "受入検査仕様",
        "kind": "必須",
        "path": ".pair-agent/acceptance/受入検査仕様.md"
      },
      {
        "name": "非回帰の合否",
        "node": "非回帰の合否",
        "kind": "必須",
        "path": ".pair-agent/assurance/非回帰の合否.md"
      },
      {
        "name": "設計保証",
        "node": "設計保証",
        "kind": "必須",
        "path": ".pair-agent/assurance/設計保証.md"
      },
      {
        "name": "実行環境",
        "node": "実行環境",
        "kind": "必須",
        "path": ".pair-agent/inbox/実行環境.md"
      }
    ],
    "blocks": [
      "実装物"
    ],
    "checks": [],
    "writes": [
      "受入検査報告書"
    ],
    "post": [
      "実装内部コードを見ずに外部契約から検査した結果である",
      "合否が明確に判定されている"
    ],
    "out": [
      "バグ修正の検証結果および合否"
    ],
    "skills": [
      "保証の受理",
      "未カバー領域の言語化",
      "検査実行環境の扱い",
      "残留リスクの書き方"
    ]
  },
  "リポジトリの状態": {
    "target": "リポジトリの状態",
    "role": "同期担当",
    "task": "sync_repository",
    "by": "agent",
    "agentType": "pair-agent-s-sync-repository",
    "gate": "",
    "path": ".git",
    "deps": [
      {
        "name": "受入検査報告書",
        "node": "受入検査報告書",
        "kind": "必須",
        "path": ".pair-agent/acceptance/受入検査報告書.md"
      },
      {
        "name": "実装物_v(n)",
        "node": "実装物",
        "kind": "必須",
        "path": "src/"
      }
    ],
    "blocks": [],
    "checks": [],
    "writes": [
      "リポジトリの状態"
    ],
    "post": [
      "作業ツリーがクリーンである"
    ],
    "out": [
      "コミットと同期"
    ],
    "skills": [
      "バージョン管理の作法"
    ]
  }
}
const LEVELS = [
  [
    "受入検査仕様",
    "実装物"
  ],
  [
    "設計保証",
    "非回帰の合否"
  ],
  [
    "受入検査報告書"
  ],
  [
    "リポジトリの状態"
  ]
]
const ORIGINS = [
  {
    "name": "バグ票",
    "path": ".pair-agent/sprints/バグ票.md"
  },
  {
    "name": "実行環境",
    "path": ".pair-agent/inbox/実行環境.md"
  }
]
const HUMAN = [
  {
    "target": "差し戻し指示",
    "gate": "H1",
    "path": ".pair-agent/assurance/差し戻し指示.md",
    "deps": [
      "受入検査報告書?",
      "非回帰の合否?",
      "バグ票?"
    ],
    "post": [
      "受け手はこれだけを見て修正に着手できる"
    ],
    "out": [
      "差し戻し先と修正指示"
    ]
  }
]

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

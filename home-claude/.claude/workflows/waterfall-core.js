export const meta = {
  name: "waterfall-core",
  description: "waterfall-core の成果物 DAG を 1 巡させる（役 6 ／ 機械 4 ／ 人間ゲート 3）",
  whenToUse: "成果物定義 waterfall-core.mk に沿って、要求から受入検査まで1 パス通したいとき。args.root に作業根を渡す",
  phases: [
    { title: "第1段", detail: "要求" },
    { title: "第2段", detail: "検査接点" },
    { title: "第3段", detail: "仕様" },
    { title: "第4段", detail: "受入検査仕様 / 実装物_v(n)" },
    { title: "第5段", detail: "変異試験の合否 / 実行可能物 / 設計保証 / 非回帰の合否" },
    { title: "第6段", detail: "受入検査報告書" },
    { title: "第7段", detail: "残留リスク報告" },
  ],
}

// 自動生成。手で編集しない。正は models/waterfall-core.mk
// 生成: python tools/emit_claude.py models/waterfall-core.mk
//
// ⚠ 段ごとに parallel（バリア）を張っている。**ここでは正しい** ——
//    次の段の担い手は、前の段が**ファイルとして置いた成果物**を読む。
//    台本にファイルシステムは無いので、置かれたことは前段の完了でしか分からない。
//
// ⚠ `by: human` の rule は走らせない（P-12: A は委譲不能）。
//    最後に「人間に渡すもの」として列挙して台本を終える。

const MODEL = "waterfall-core"
const NODES = {
  "要求": {
    "target": "要求",
    "role": "意図取得者",
    "task": "elicit_intent",
    "by": "agent",
    "agentType": "waterfall-core-elicit-intent",
    "gate": "H1",
    "path": "upstream/要求.md",
    "deps": [
      {
        "name": "要望",
        "node": "要望",
        "kind": "必須",
        "path": "inbox/要望.md"
      },
      {
        "name": "用語資産?",
        "node": "用語資産",
        "kind": "任意",
        "path": "inbox/用語資産.md"
      },
      {
        "name": "要求への差し戻し_v(r-1)",
        "node": "要求への差し戻し",
        "kind": "前版",
        "path": "差し戻し/要求.md"
      }
    ],
    "blocks": [
      "実装物",
      "実行可能物"
    ],
    "checks": [],
    "writes": [
      "要求"
    ],
    "post": [
      "要望に現れた曖昧な語が**すべて**定義されている（入力と突き合わせて検査できる・P-16）",
      "定義は「含むもの」と「含まないもの」の両方を書いている",
      "確定は人間の回答による。自分で定義を選んでいない（選べば「要求にないことの追加」にあたる）",
      "**問いに依存関係が付いている**（上位に答えると下位が確定するか消える）"
    ],
    "out": [
      "曖昧な語ごとの定義（含むもの／含まないものまで）",
      "確認の問い —— **疑問形であること**。平叙文は「読んでおいてください」で済むが、疑問文は答えないと先へ進めない（P-13）",
      "理由（入力に無かった知識・判断の由来）＋ 残留リスク"
    ],
    "skills": [
      "QAW",
      "復唱・確認",
      "用語定義の書き方"
    ]
  },
  "検査接点": {
    "target": "検査接点",
    "role": "仕様作成者",
    "task": "define_test_interface",
    "by": "agent",
    "agentType": "waterfall-core-define-test-interface",
    "gate": "",
    "path": "upstream/検査接点.md",
    "deps": [
      {
        "name": "要求",
        "node": "要求",
        "kind": "必須",
        "path": "upstream/要求.md"
      },
      {
        "name": "既存システムの制約?",
        "node": "既存システムの制約",
        "kind": "任意",
        "path": "inbox/既存システムの制約.md"
      },
      {
        "name": "検査接点への差し戻し_v(k-1)",
        "node": "検査接点への差し戻し",
        "kind": "前版",
        "path": "差し戻し/検査接点.md"
      }
    ],
    "blocks": [
      "実装物",
      "実行可能物",
      "受入検査仕様"
    ],
    "checks": [],
    "writes": [
      "検査接点"
    ],
    "post": [
      "**構築者が deps だけを見て実装できる**（暫定の名前や未定義の引数を含まない）",
      "**受入検査仕様の担い手が、実装物を見ずにこれだけで判定手続きを書ける**",
      "**内部構造を露出していない** —— 露出させると受入検査がブラックボックスでなくなる",
      "要求から導出できない観測点を足していない（P-23）",
      "**提供できない観測点が明示されている**（「全部観測できる」で終わらせない）"
    ],
    "out": [
      "**外から何を、どう叩けば、何が観測できるか**（呼び名・引数・戻り・出し先）",
      "要求の各項目について、それを**外形から判定するのに要る観測点**",
      "**判定に要るのに提供できない観測点**の一覧（`設計保証` が引き受ける材料になる）",
      "理由 ＋ 残留リスク"
    ],
    "skills": [
      "インタフェース設計",
      "判定可能な仕様の書き方",
      "外部契約からの計測設計"
    ]
  },
  "仕様": {
    "target": "仕様",
    "role": "仕様作成者",
    "task": "write_specification",
    "by": "agent",
    "agentType": "waterfall-core-define-test-interface",
    "gate": "H2",
    "path": "upstream/仕様.md",
    "deps": [
      {
        "name": "要求",
        "node": "要求",
        "kind": "必須",
        "path": "upstream/要求.md"
      },
      {
        "name": "検査接点",
        "node": "検査接点",
        "kind": "必須",
        "path": "upstream/検査接点.md"
      },
      {
        "name": "既存システムの制約?",
        "node": "既存システムの制約",
        "kind": "任意",
        "path": "inbox/既存システムの制約.md"
      },
      {
        "name": "仕様への差し戻し_v(m-1)",
        "node": "仕様への差し戻し",
        "kind": "前版",
        "path": "差し戻し/仕様.md"
      }
    ],
    "blocks": [
      "実装物",
      "実行可能物",
      "受入検査仕様"
    ],
    "checks": [],
    "writes": [
      "仕様"
    ],
    "post": [
      "不足なし —— 要求の項目が黙って落ちていない",
      "過剰なし —— 要求と用語定義から**導出できない**ものを足していない（P-24）",
      "各項目が判定手続きに落とせる（検査するのは 受入検査仕様 の担い手）",
      "「不可能」と判定した項目は範囲外として上げている（deps を満たす OUT が存在しないため）",
      "**暫定**として置いた項目には、**解除条件**（誰が何を答えたら差し替えるか）が付いている"
    ],
    "out": [
      "何を作るか。要求を 100% 説明する",
      "満たさない項目は**理由と扱い**（スコープ外／延期／代案／不可能／**暫定**）",
      "実装言語・対象プラットフォームの制約（P-30。役割ではなく仕様に置く）",
      "理由 ＋ 残留リスク"
    ],
    "skills": [
      "判定可能な仕様の書き方",
      "対象ドメイン知識",
      "扱いの型の使い分け"
    ]
  },
  "受入検査仕様": {
    "target": "受入検査仕様",
    "role": "受入検査設計者",
    "task": "design_acceptance_tests",
    "by": "agent",
    "agentType": "waterfall-core-design-acceptance-tests",
    "gate": "",
    "path": "acceptance/受入検査仕様.md",
    "deps": [
      {
        "name": "仕様",
        "node": "仕様",
        "kind": "必須",
        "path": "upstream/仕様.md"
      },
      {
        "name": "検査接点",
        "node": "検査接点",
        "kind": "必須",
        "path": "upstream/検査接点.md"
      },
      {
        "name": "受入検査仕様への差し戻し_v(j-1)",
        "node": "受入検査仕様への差し戻し",
        "kind": "前版",
        "path": "差し戻し/受入検査仕様.md"
      }
    ],
    "blocks": [
      "実装物",
      "実行可能物"
    ],
    "checks": [
      "仕様"
    ],
    "writes": [
      "受入検査仕様"
    ],
    "post": [
      "仕様の各項目に判定手続きが対応している（網羅）",
      "**「対応している」の定義を満たしている** —— 手続きが no を出す ⟺ 仕様項目が満たされていない。後ろ向き（満たされていないのに no を出さない）が成り立たない部分は明示されている",
      "上流の成果物が自分の事後条件を破っていたら、勝手に読み替えず「暫定」として扱い、解除条件（A が仕様を直すか、この読み替えを承認するか）を付けている",
      "判定が二値である",
      "内部構造に依存しない（ブラックボックス）"
    ],
    "out": [
      "仕様の各項目に対応する判定手続き",
      "判定手続きに落とせなかった仕様項目の一覧（空でなければ 差し戻し指示 の材料になる）",
      "**各判定手続きが、対応する仕様項目のどこを判定できないか**（部分的な取りこぼし）",
      "理由 ＋ 残留リスク"
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
    "agentType": "waterfall-core-build",
    "gate": "",
    "path": "実装物",
    "deps": [
      {
        "name": "仕様",
        "node": "仕様",
        "kind": "必須",
        "path": "upstream/仕様.md"
      },
      {
        "name": "検査接点",
        "node": "検査接点",
        "kind": "必須",
        "path": "upstream/検査接点.md"
      },
      {
        "name": "実装物_v(n-1)",
        "node": "実装物",
        "kind": "前版",
        "path": "実装物"
      },
      {
        "name": "実装物への差し戻し_v(n-1)",
        "node": "実装物への差し戻し",
        "kind": "前版",
        "path": "差し戻し/実装物.md"
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
      "仕様を満たす（不足なし・過剰なし）",
      "ホワイトボックステストを含む",
      "縮退経路にログがある"
    ],
    "out": [
      "実行可能なコード",
      "ホワイトボックステスト（**必須**。非回帰の合否の deps がこれを要求する）",
      "縮退・フォールバック経路のログ（**必須**。無いと下流のどこからも観測できない）",
      "理由 ＋ 残留リスク"
    ],
    "skills": [
      "ホワイトボックステストの書き方",
      "実装言語・基盤の知識",
      "縮退経路のログ設計"
    ]
  },
  "設計保証": {
    "target": "設計保証",
    "role": "構築者",
    "task": "assure_design",
    "by": "agent",
    "agentType": "waterfall-core-assure-design",
    "gate": "",
    "path": "upstream/設計保証",
    "deps": [
      {
        "name": "実装物_v(n)",
        "node": "実装物",
        "kind": "必須",
        "path": "実装物"
      },
      {
        "name": "仕様",
        "node": "仕様",
        "kind": "必須",
        "path": "upstream/仕様.md"
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
      "外形から検められる項目を含んでいない（受入検査の仕事を重複させない）",
      "**主張だけの項目が無い。**すべてにエビデンスが付いている",
      "**エビデンスが、実装物を読まずに検められる形になっている**",
      "仕様に無い項目を保証していない（P-23。**過剰はここに現れる** —— G-70）"
    ],
    "out": [
      "**外形からは検められない仕様項目の一覧**（なぜ検められないかつき）",
      "各項目について「どう満たしたか」の主張 ＋ **エビデンス**",
      "**保証できなかった項目** —— 残留リスクへ移す"
    ],
    "skills": [
      "エビデンスの設計",
      "保証範囲の切り出し"
    ]
  },
  "実行可能物": {
    "target": "実行可能物",
    "role": "機械",
    "task": "package",
    "by": "machine",
    "agentType": "waterfall-core-package",
    "gate": "",
    "path": "実行可能物",
    "deps": [
      {
        "name": "実装物_v(n)",
        "node": "実装物",
        "kind": "必須",
        "path": "実装物"
      }
    ],
    "blocks": [],
    "checks": [],
    "writes": [
      "実行可能物"
    ],
    "post": [
      "実装物から決定的に得られている（内容を足していない）",
      "**落とすべきものが落ちている** —— `受入検査報告書` の遮断対象が含まれていない",
      "**落としたものが列挙されている**（黙って落とさない。黙って残さない）"
    ],
    "out": [
      "動かせる形にした成果。**ホワイトボックステスト・構築者の理由・作業ログを落とす**",
      "**落としたものの一覧**（何を落としたか、なぜ落としたか）"
    ],
    "skills": []
  },
  "受入検査報告書": {
    "target": "受入検査報告書",
    "role": "受入検査実施者",
    "task": "execute_acceptance_tests",
    "by": "agent",
    "agentType": "waterfall-core-execute-acceptance-tests",
    "gate": "H3",
    "path": "acceptance/受入検査報告書.md",
    "deps": [
      {
        "name": "実行可能物",
        "node": "実行可能物",
        "kind": "必須",
        "path": "実行可能物"
      },
      {
        "name": "受入検査仕様",
        "node": "受入検査仕様",
        "kind": "必須",
        "path": "acceptance/受入検査仕様.md"
      },
      {
        "name": "検査接点",
        "node": "検査接点",
        "kind": "必須",
        "path": "upstream/検査接点.md"
      },
      {
        "name": "設計保証",
        "node": "設計保証",
        "kind": "必須",
        "path": "upstream/設計保証"
      },
      {
        "name": "実行環境",
        "node": "実行環境",
        "kind": "必須",
        "path": "inbox/実行環境.md"
      }
    ],
    "blocks": [
      "実装物"
    ],
    "checks": [
      "実装物"
    ],
    "writes": [
      "受入検査報告書"
    ],
    "post": [
      "受入検査仕様の各項目に結果が対応している",
      "合否が二値である",
      "カバーできなかった領域が明示されている（「全部通った」で終わらせない）",
      "欠陥を見つけても直していない —— 合否を no にして差分に書く。修正は 実装物 の再作成に回す",
      "**設計保証の各項目に、受理／不受理が付いている**",
      "**設計保証を読んだことで、受入検査仕様の項目を増減させていない**",
      "**受理したが自分では検証していない項目**を、残留リスクに移している",
      "**実行が他人の成果物に書き込んでいない** —— `実行可能物` を作業空間へ複製して実行する",
      "**作業領域に閉じない副作用**（実行環境の状態変化）があれば、**実施条件に申告している**"
    ],
    "out": [
      "合否（二値）",
      "差分 —— どの項目がどう外れたか",
      "実施条件 —— いつ・どの環境で・どのデータで、**そして実行が環境に何を残したか**（**入力に無い**。これがコアである理由）",
      "カバーできなかった領域（**入力に無い**。実行して初めて分かる）",
      "残留リスク（何が起こりうるか ＋ 理由として何を確かめていないか）"
    ],
    "skills": [
      "保証の受理",
      "未カバー領域の言語化",
      "検査実行環境の扱い",
      "残留リスクの書き方"
    ]
  },
  "変異試験の合否": {
    "target": "変異試験の合否",
    "role": "機械",
    "task": "run_mutation_testing",
    "by": "machine",
    "agentType": "waterfall-core-run-mutation-testing",
    "gate": "",
    "path": "checks/変異試験の合否.md",
    "deps": [
      {
        "name": "実装物_v(n)",
        "node": "実装物",
        "kind": "必須",
        "path": "実装物"
      }
    ],
    "blocks": [],
    "checks": [],
    "writes": [
      "変異試験の合否"
    ],
    "post": [
      "決定論的である",
      "検出されなかった変異が空でなければ不合格。「通った」で終わらせない"
    ],
    "out": [
      "注入した変異のうち、**検出されなかったもの**の一覧"
    ],
    "skills": []
  },
  "非回帰の合否": {
    "target": "非回帰の合否",
    "role": "機械",
    "task": "run_regression",
    "by": "machine",
    "agentType": "waterfall-core-run-regression",
    "gate": "",
    "path": "checks/非回帰の合否.md",
    "deps": [
      {
        "name": "実装物_v(n)",
        "node": "実装物",
        "kind": "必須",
        "path": "実装物"
      },
      {
        "name": "実装物_v(n-1)",
        "node": "実装物",
        "kind": "前版",
        "path": "実装物"
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
    "out": [],
    "skills": []
  },
  "残留リスク報告": {
    "target": "残留リスク報告",
    "role": "機械",
    "task": "aggregate_residual_risk",
    "by": "machine",
    "agentType": "waterfall-core-aggregate-residual-risk",
    "gate": "",
    "path": "checks/残留リスク報告.md",
    "deps": [
      {
        "name": "要求",
        "node": "要求",
        "kind": "必須",
        "path": "upstream/要求.md"
      },
      {
        "name": "仕様",
        "node": "仕様",
        "kind": "必須",
        "path": "upstream/仕様.md"
      },
      {
        "name": "受入検査仕様",
        "node": "受入検査仕様",
        "kind": "必須",
        "path": "acceptance/受入検査仕様.md"
      },
      {
        "name": "実装物_v(n)",
        "node": "実装物",
        "kind": "必須",
        "path": "実装物"
      },
      {
        "name": "受入検査報告書",
        "node": "受入検査報告書",
        "kind": "必須",
        "path": "acceptance/受入検査報告書.md"
      }
    ],
    "blocks": [],
    "checks": [],
    "writes": [
      "残留リスク報告"
    ],
    "post": [
      "各コア成果物の残留リスクが漏れなく集約されている"
    ],
    "out": [],
    "skills": []
  }
}
const LEVELS = [
  [
    "要求"
  ],
  [
    "検査接点"
  ],
  [
    "仕様"
  ],
  [
    "受入検査仕様",
    "実装物"
  ],
  [
    "変異試験の合否",
    "実行可能物",
    "設計保証",
    "非回帰の合否"
  ],
  [
    "受入検査報告書"
  ],
  [
    "残留リスク報告"
  ]
]
const ORIGINS = [
  {
    "name": "要望",
    "path": "inbox/要望.md"
  },
  {
    "name": "用語資産",
    "path": "inbox/用語資産.md"
  },
  {
    "name": "既存システムの制約",
    "path": "inbox/既存システムの制約.md"
  },
  {
    "name": "実行環境",
    "path": "inbox/実行環境.md"
  }
]
const HUMAN = [
  {
    "target": "要求への差し戻し",
    "gate": "H3",
    "path": "差し戻し/要求.md",
    "deps": [
      "受入検査報告書?",
      "変異試験の合否?",
      "非回帰の合否?",
      "仕様?",
      "要求?"
    ],
    "post": [
      "受け手は**これだけを見て**修正に着手できる",
      "受け手が読めない語彙を含まない",
      "**どのゲートで差し戻したかが書かれている**（判定の根拠＝検査ケースの内容を含まない）",
      "**宛先を本文に書いていない。** 宛先はこの文書が存在すること自体である"
    ],
    "out": [
      "なぜ差し戻されるか —— **意図取得者の deps の語彙**で、着手できる粒度で",
      "同一項目の再発回数（探針を起動すべき信号。実現不能の証明ではない）"
    ]
  },
  {
    "target": "検査接点への差し戻し",
    "gate": "H3",
    "path": "差し戻し/検査接点.md",
    "deps": [
      "受入検査報告書?",
      "変異試験の合否?",
      "非回帰の合否?",
      "仕様?",
      "要求?"
    ],
    "post": [
      "受け手は**これだけを見て**修正に着手できる",
      "受け手が読めない語彙を含まない",
      "**どのゲートで差し戻したかが書かれている**",
      "**宛先を本文に書いていない**"
    ],
    "out": [
      "なぜ差し戻されるか —— **仕様作成者の deps の語彙**で、着手できる粒度で",
      "同一項目の再発回数"
    ]
  },
  {
    "target": "仕様への差し戻し",
    "gate": "H3",
    "path": "差し戻し/仕様.md",
    "deps": [
      "受入検査報告書?",
      "変異試験の合否?",
      "非回帰の合否?",
      "仕様?",
      "要求?"
    ],
    "post": [
      "受け手は**これだけを見て**修正に着手できる",
      "受け手が読めない語彙を含まない",
      "**どのゲートで差し戻したかが書かれている**",
      "**宛先を本文に書いていない**"
    ],
    "out": [
      "なぜ差し戻されるか —— **仕様作成者の deps の語彙**で、着手できる粒度で",
      "同一項目の再発回数"
    ]
  },
  {
    "target": "受入検査仕様への差し戻し",
    "gate": "H3",
    "path": "差し戻し/受入検査仕様.md",
    "deps": [
      "受入検査報告書?",
      "変異試験の合否?",
      "非回帰の合否?",
      "仕様?",
      "要求?"
    ],
    "post": [
      "受け手は**これだけを見て**修正に着手できる",
      "受け手が読めない語彙を含まない",
      "**どのゲートで差し戻したかが書かれている**",
      "**宛先を本文に書いていない**"
    ],
    "out": [
      "なぜ差し戻されるか —— **受入検査設計者の deps の語彙**で、着手できる粒度で",
      "同一項目の再発回数"
    ]
  },
  {
    "target": "実装物への差し戻し",
    "gate": "H3",
    "path": "差し戻し/実装物.md",
    "deps": [
      "受入検査報告書?",
      "変異試験の合否?",
      "非回帰の合否?",
      "仕様?",
      "要求?"
    ],
    "post": [
      "受け手は**これだけを見て**修正に着手できる",
      "受け手が読めない語彙を含まない",
      "**どのゲートで差し戻したかが書かれている**",
      "**宛先を本文に書いていない**"
    ],
    "out": [
      "なぜ差し戻されるか —— **構築者の deps の語彙**（仕様・検査接点）で、着手できる粒度で",
      "同一項目の再発回数"
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

"""PostToolUse(Agent) フック: 裏の役を起こしたとき、主エージェントに見回りと停止の規則を知らせる。

師匠の規則（2026-11-24・全プロジェクト・全セッション）:
- 仕事が終わったサブプロセスは直ちに停止する（絶対ルール）
- サブプロセスが 1 本でも残っていたら完了と言わない
- 最低 10 分に 1 回、出力が動いているかを確かめる（CronCreate の見回り job はセッションの中にしか無い）

知らせるだけで、何も止めない・何も断らない。失敗しても黙って終わる（道具の呼び出しを妨げない）。
"""
import json
import sys

MSG = (
    "【師匠の規則・全セッション】裏の役を起こした。"
    "(1) このセッションに 10 分ごとの見回りの job が無ければ今すぐ CronCreate で作る（CronList で確かめる）。"
    "見回りでは各役の記録 ~/.claude/projects/*/*/subagents/agent-<id>.jsonl の大きさ・時刻が動いているかを見て"
    "（tasks/<id>.output は走っている間 0 バイトで目安にならない）、止まっていれば手当てする。走っている役が 0 本になったら CronDelete。"
    "(2) 役の報告（hand-back）を受けたら、同じ応答の中で TaskStop する（『waiting on N shell』も止める）。"
    "(3) サブプロセスが 1 本でも残っていたら『完了』『終わった』『走っている役はない』と言わない。ListAgents で 0 本を確かめてから言う。"
)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    if data.get("tool_name") != "Agent":
        return
    out = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": MSG}}
    # ASCII に逃がす（Windows の標準出力は cp932 になり、日本語が化ける）
    sys.stdout.write(json.dumps(out, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass

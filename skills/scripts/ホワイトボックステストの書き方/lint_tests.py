#!/usr/bin/env python3
"""pytest/unittest 形式のテストを静的に検査し、assert 無し・自明な assert・主張の詰め込み・例外経路の欠落を指摘する。

使い方:
  python lint_tests.py tests/ [--max-asserts 3] [--json]
指摘: no-assert(error) / trivial-assert(error) / many-assertions(warn, 1 テスト 1 主張) /
      no-failure-path(warn, ファイルに raises/assertRaises/例外系の語が無い)
終了コード: 0 / 1=error あり / 2=入力不備
"""
import argparse
import ast
import json
import sys
from pathlib import Path

FAIL_WORDS = ("raises", "assertRaises", "assertRaisesRegex", "warns", "assertLogs", "caplog", "capsys")


def _is_trivial(test):
    if isinstance(test, ast.Constant) and bool(test.value):
        return True
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq):
        return ast.dump(test.left) == ast.dump(test.comparators[0])
    return False


def lint_source(src, path="<src>", max_asserts=3):
    tree = ast.parse(src)
    issues = []

    def add(sev, code, line, msg):
        issues.append({"file": str(path), "line": line, "severity": sev, "code": code, "message": msg})

    n_tests = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test"):
            continue
        n_tests += 1
        asserts = 0
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assert):
                asserts += 1
                if _is_trivial(sub.test):
                    add("error", "trivial-assert", sub.lineno, f"{node.name}: 常に真の assert")
            elif isinstance(sub, ast.Call):
                fn = ast.unparse(sub.func)
                if fn.startswith("self.assert") or fn.endswith(".raises") or fn.endswith("raises") \
                        or fn.endswith(".warns") or fn.endswith("pytest.fail") or fn.endswith("self.fail"):
                    asserts += 1
        if asserts == 0:
            add("error", "no-assert", node.lineno, f"{node.name}: 主張が無い（通っても何も検めていない）")
        elif asserts > max_asserts:
            add("warn", "many-assertions", node.lineno,
                f"{node.name}: assert {asserts} 個 > {max_asserts}（1 テスト 1 主張。落ちた原因が 1 つに決まらない）")
    if n_tests and not any(w in src for w in FAIL_WORDS):
        add("warn", "no-failure-path", 1, "例外・縮退の経路を検めるテストが見当たらない（正常系だけでは変異試験に落ちる）")
    return issues, n_tests


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--max-asserts", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    files = []
    for p in map(Path, a.paths):
        files += sorted(p.rglob("test*.py")) if p.is_dir() else ([p] if p.is_file() else [])
    if not files:
        print("対象のテストファイルが無い", file=sys.stderr)
        return 2
    issues, total = [], 0
    for f in files:
        try:
            i, n = lint_source(f.read_text(encoding="utf-8"), f.as_posix(), a.max_asserts)
        except SyntaxError as e:
            i, n = [{"file": f.as_posix(), "line": e.lineno or 0, "severity": "error", "code": "syntax", "message": str(e)}], 0
        issues += i
        total += n
    errs = sum(i["severity"] == "error" for i in issues)
    if a.json:
        print(json.dumps({"tests": total, "issues": issues, "errors": errs}, ensure_ascii=False, indent=2))
    else:
        for i in issues:
            print(f"{i['severity']:5} {i['code']:16} {i['file']}:{i['line']} {i['message']}")
        print(f"テスト {total} 件 / error {errs} / warn {len(issues) - errs}")
    return 1 if errs else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

#!/usr/bin/env python3
"""Python ソースから縮退経路（握りつぶした例外・suppress・フォールバック）を洗い出し、各経路がログを出すかを数える。

使い方:
  python scan_degradation.py src/ [--json] [--fail-on silent|low-level|never]
出力の要点: 「縮退経路 N 件のうちログ(警告以上)を出すのは M 件」。設計保証のエビデンスにそのまま貼れる。
判定: 再送出(raise)する handler は縮退ではない。警告以上のログ(warning/error/exception/critical, warnings.warn,
stderr への出力)があれば logged、info/debug/print のみは low-level、何も無ければ silent。
終了コード: 0 / 1=--fail-on に該当 / 2=入力不備
"""
import argparse
import ast
import json
import sys
from pathlib import Path

HIGH = {"warning", "warn", "error", "exception", "critical", "fatal"}
LOW = {"info", "debug", "log"}
LOGGER_NAMES = {"logging", "logger", "log", "_log", "_logger", "warnings"}


def _call_kind(call):
    """Call ノードがログ呼び出しなら 'high'/'low'、そうでなければ None。"""
    f = call.func
    if isinstance(f, ast.Attribute):
        base = f.value
        bname = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else "")
        if f.attr in HIGH and (bname.lower() in LOGGER_NAMES or "log" in bname.lower()):
            return "high"
        if f.attr in LOW and "log" in bname.lower():
            return "low"
        if f.attr == "write" and isinstance(base, ast.Attribute) and base.attr == "stderr":
            return "high"
    if isinstance(f, ast.Name) and f.id == "print":
        for kw in call.keywords:
            if kw.arg == "file" and "stderr" in ast.unparse(kw.value):
                return "high"
        return "low"
    return None


def _exc_name(h):
    return "(bare)" if h.type is None else ast.unparse(h.type)


def classify_body(body):
    raises = logs = False
    level = None
    msgs = []
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Raise):
            raises = True
        if isinstance(node, ast.Call):
            k = _call_kind(node)
            if k:
                logs = True
                if k == "high" or level is None:
                    level = k if level != "high" else "high"
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    msgs.append(node.args[0].value[:80])
    return raises, level, msgs


def scan_source(src, path="<src>"):
    tree = ast.parse(src)
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            raises, level, msgs = classify_body(node.body)
            if raises:
                continue
            status = "logged" if level == "high" else ("low-level" if level == "low" else "silent")
            sites.append({"file": str(path), "line": node.lineno, "kind": "except", "exception": _exc_name(node),
                          "status": status, "messages": msgs})
        elif isinstance(node, ast.With):
            for item in node.items:
                c = item.context_expr
                if isinstance(c, ast.Call) and ast.unparse(c.func).endswith("suppress"):
                    sites.append({"file": str(path), "line": node.lineno, "kind": "suppress",
                                  "exception": ", ".join(ast.unparse(x) for x in c.args), "status": "silent",
                                  "messages": []})
    return sorted(sites, key=lambda s: (s["file"], s["line"]))


def iter_py(paths):
    for p in paths:
        p = Path(p)
        if p.is_dir():
            yield from sorted(x for x in p.rglob("*.py") if "__pycache__" not in x.parts)
        elif p.is_file():
            yield p


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on", choices=["silent", "low-level", "never"], default="silent")
    a = ap.parse_args(argv)
    files = list(iter_py(a.paths))
    if not files:
        print("対象の .py が無い", file=sys.stderr)
        return 2
    sites, errors = [], []
    for f in files:
        try:
            sites += scan_source(f.read_text(encoding="utf-8"), f.as_posix())
        except (SyntaxError, UnicodeDecodeError) as e:
            errors.append({"file": f.as_posix(), "error": str(e)})
    n = len(sites)
    logged = sum(s["status"] == "logged" for s in sites)
    summary = {"files": len(files), "degradation_paths": n, "logged": logged,
               "low_level": sum(s["status"] == "low-level" for s in sites),
               "silent": sum(s["status"] == "silent" for s in sites), "unparsable": len(errors)}
    if a.json:
        print(json.dumps({"summary": summary, "sites": sites, "errors": errors}, ensure_ascii=False, indent=2))
    else:
        for s in sites:
            print(f"{s['status']:9} {s['file']}:{s['line']} {s['kind']} {s['exception']}")
        for e in errors:
            print(f"parse-error {e['file']}: {e['error']}")
        print(f"縮退経路 {n} 件のうちログ(警告以上)を出すのは {logged} 件 "
              f"(低水準のみ {summary['low_level']} / 無音 {summary['silent']})")
    bad = summary["silent"] + (summary["low_level"] if a.fail_on == "low-level" else 0)
    return 1 if (a.fail_on != "never" and bad) or errors else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

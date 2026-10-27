"""差し戻し先の語彙翻訳 の武器（check_sendback.py）のテスト。実際の models/pair-agent-m.mk を読む。"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "skills" / "scripts" / "差し戻し先の語彙翻訳" / "check_sendback.py"
spec = importlib.util.spec_from_file_location("check_sendback", P)
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)

MK_TEXT = (ROOT / "models" / "pair-agent-m.mk").read_text(encoding="utf-8")


def chk(body, receiver="実装物", vocab=None):
    return cs.check(MK_TEXT, receiver, body, vocab)


def test_parse_real_mk():
    t = cs.parse_mk(MK_TEXT)
    assert t["実装物"]["deps"] == ["仕様", "実装物", "差し戻し指示"]
    assert t["実装物"]["meta"]["blocks"] == ["受入検査仕様"]
    assert t["受入検査報告書"]["meta"]["role"] == ["受入検査実施者"]


def test_clean_text_in_spec_vocabulary():
    f, info = chk("仕様の「重複を除去する」項目で、同一内容が 2 件出力される。")
    assert f == []
    assert info["blocks"] == ["受入検査仕様"]


def test_blocked_name_is_violation_and_longest_match_wins():
    f, _ = chk("受入検査仕様のケース3が落ちた。")
    t = "\n".join(f)
    assert "遮断違反" in t and "受入検査仕様" in t
    assert "検査ケースの参照" in t
    # 「受入検査仕様」の中の「仕様」は deps の語として数えない（誤検出しない）
    assert "受け手の語彙に無い成果物名] 「仕様」" not in t


def test_name_outside_deps_flagged():
    f, _ = chk("受入検査報告書に書かれた不具合を直す。")
    assert any("受け手の語彙に無い成果物名" in x and "受入検査報告書" in x for x in f)


def test_receiver_by_role_and_ambiguous_role():
    f, info = chk("仕様を直す。", receiver="仕様作成者")
    assert info["receiver"] == "仕様"
    f, info = chk("x", receiver="構築者")
    assert info == {} and any("受け手が決まらない" in x for x in f)
    f, info = chk("x", receiver="存在しない")
    assert info == {}


def test_case_id_patterns():
    for s in ("TC-12 が不合格", "テストケース 5 の期待値", "検査項目3"):
        assert any("検査ケースの参照" in x for x in chk(s)[0]), s


def test_grounds_explanation_flagged():
    assert any("判定根拠" in x for x in chk("検査の結果、重複が残っていた。")[0])


def test_empty_body():
    assert any("本文が空" in x for x in chk("  ")[0])


def test_vocab_check():
    f, _ = chk("仕様の「重複を除去する」と「謎の用語」を直す。", vocab="重複を除去する 仕様")
    assert any("謎の用語" in x for x in f)
    assert not any("「重複を除去する」は" in x for x in f)


def test_cli(tmp_path):
    mk = ROOT / "models" / "pair-agent-m.mk"
    s = tmp_path / "s.md"
    s.write_text("仕様の重複除去が働いていない。", encoding="utf-8")
    assert cs.main([str(s), "--mk", str(mk), "--receiver", "実装物", "--strict"]) == 0
    s.write_text("受入検査仕様に従え。", encoding="utf-8")
    assert cs.main([str(s), "--mk", str(mk), "--receiver", "実装物", "--strict"]) == 1
    assert cs.main([str(s), "--mk", str(mk), "--receiver", "ない"]) == 1
    assert cs.main([str(tmp_path / "none"), "--mk", str(mk), "--receiver", "実装物"]) == 2

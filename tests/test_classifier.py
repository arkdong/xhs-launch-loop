# -*- coding: utf-8 -*-
"""评论分类的回归测试：tests/fixtures/labeled_comments.txt 里每一行是一条带标注的评论。"""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import comment_insight as ci  # noqa: E402


def load_cases():
    cases = []
    with open(os.path.join(HERE, "fixtures", "labeled_comments.txt"), encoding="utf-8") as f:
        for no, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            parts += [""] * (3 - len(parts))
            cases.append((no, parts[0], [x for x in parts[1].split(",") if x], [x for x in parts[2].split(",") if x]))
    return cases


def problems(lex, text, intents, aspects):
    r = lex.analyse(text)
    bad = []
    for it in intents:
        if it.startswith("!"):
            if it[1:] in r["intents"]:
                bad.append("不应有意图 %s" % it[1:])
        elif it not in r["intents"]:
            bad.append("缺意图 %s" % it)
    for a in aspects:
        if a.startswith("!"):
            if a[1:] in r["aspects"]:
                bad.append("不应命中 %s（实际 %s）" % (a[1:], r["aspects"][a[1:]][0]))
            continue
        name, lab = a.split(":")
        got = r["aspects"].get(name, (None,))[0]
        if lab.startswith("!"):
            if got == lab[1:]:
                bad.append("%s 不应是 %s" % (name, lab[1:]))
        elif got != lab:
            bad.append("%s 应是 %s，实际 %s" % (name, lab, got))
    return bad, r


class ClassifierTest(unittest.TestCase):
    def test_labeled_comments(self):
        lex = ci.Lexicon()
        cases = load_cases()
        self.assertGreater(len(cases), 150)
        failed = []
        for no, text, intents, aspects in cases:
            bad, r = problems(lex, text, intents, aspects)
            if bad:
                failed.append("第 %d 行 %s → %s｜实际 %s %s" % (no, text, "；".join(bad), r["intents"], dict(r["aspects"])))
        self.assertFalse(failed, "\n" + "\n".join(failed))

    def test_spam_filter(self):
        lex = ci.Lexicon()
        spam = {"看我主页，有同款": "引流自荐", "互关互赞，有赞必回": "互关互赞", "@点点 帮我总结一下这篇笔记": "助手指令",
                "我自己也做了一个类似的小程序，欢迎大家体验": "引流自荐", "需要的姐妹私我": "引流自荐",
                "恳请平台重新审核，@薯队长 @小红书 @客服薯": "申诉灌水"}
        for text, kind in spam.items():
            self.assertEqual(lex.spam_kind(text), kind, text)
        for text in ["已关注，求链接", "求回复", "加我一个", "做副业的姐妹可以试试这个", "可以私我链接吗", "这个不违规吗", "有人转让吗"]:
            self.assertIsNone(lex.spam_kind(text), text)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""xhs-launch-loop 的回归测试。只用标准库：

    python3 -m unittest discover -s tests

按 2026-11-25 测试报告里的问题分组：粘贴内容的解析、在任意目录运行、词表、分析门槛、结论门槛、
方案检查、合规词表、文档和命令是否一致。每个用例都在临时目录里跑，不会碰技能目录。
"""
import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest
import zipfile
from datetime import datetime

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
FIX = os.path.join(HERE, "fixtures")
EX = os.path.join(ROOT, "examples")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, ROOT)
import package  # noqa: E402
import common as C  # noqa: E402
import comment_insight as ci  # noqa: E402
import content_plan as cp  # noqa: E402
import guide  # noqa: E402
import launch_log as ll  # noqa: E402
import note_check as nc  # noqa: E402
import research as rs  # noqa: E402

ALL_SCRIPTS = ["launch_log.py", "research.py", "comment_insight.py", "content_plan.py", "note_check.py", "guide.py"]
NOTE_ID = "65f0a1b2c3d4e5f6a7b8c9%02d"


def run(script, *args, cwd, stdin=None, env=None):
    """在 cwd 里运行一个脚本，返回 (退出码, 输出)。"""
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    e.pop("XHS_LAUNCH_DIR", None)
    e.update(env or {})
    p = subprocess.run([sys.executable, "-B", os.path.join(SCRIPTS, script)] + [str(a) for a in args], cwd=cwd, env=e,
                       input=stdin.encode("utf-8") if isinstance(stdin, str) else stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout.decode("utf-8", "replace")


class Work(unittest.TestCase):
    """每个用例一个临时工作目录，相当于用户自己的文件夹。"""

    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="xhs_test_")
        self.addCleanup(shutil.rmtree, self.work, True)

    def write(self, name, text, encoding="utf-8"):
        path = os.path.join(self.work, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding=encoding, newline="") as f:
            f.write(text)
        return path

    def ok(self, script, *args, **kw):
        code, out = run(script, *args, cwd=self.work, **kw)
        self.assertEqual(code, 0, out)
        return out

    def refused(self, script, *args, **kw):
        code, out = run(script, *args, cwd=self.work, **kw)
        self.assertNotEqual(code, 0, out)
        return out

    def data(self, *parts):
        with open(os.path.join(self.work, "xhs_launch", *parts), encoding="utf-8") as f:
            return json.load(f)

    def save(self, obj, *parts):
        self.write(os.path.join("xhs_launch", *parts), json.dumps(obj, ensure_ascii=False, indent=2))

    def init(self, goal="互动", identity="自己买的用户", material="产品图 3 张", **more):
        args = ["init", "--product", "白茶护手霜", "--category", "护手霜", "--audience", "敲键盘的打工人", "--selling-points", "不黏键盘,39元50g",
                "--price", "39 元 50g", "--identity", identity, "--fact", "定位=给每天敲键盘的人用的护手霜", "--fact", "使用情况=自己用了两周，每天涂三次",
                "--fact", "结果=涂完 1 分钟就能打字", "--fact", "缺点=香味半小时就散了", "--fact", "素材=" + material, "--fact", "购买方式=主页店铺"]
        if goal:
            args += ["--goal", goal]
        for k, v in more.items():
            args += ["--fact", "%s=%s" % (k, v)]
        return self.ok("launch_log.py", *args)

    def baseline(self, impressions=5000, views=600, likes=40, collects=20, comments=8):
        """登记一篇有数据的基线，返回它的编号。"""
        out = self.ok("launch_log.py", "add", "--title", "护手霜开箱", "--baseline")
        lid = re.search(r"已登记发布 (L\d+)", out).group(1)
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", impressions, "--views", views, "--likes", likes, "--collects", collects, "--comments", comments)
        return lid

    def launch(self, *extra):
        out = self.ok("launch_log.py", "add", "--title", "打字不黏键盘的护手霜", "--angle", "黏键盘痛点", "--hypothesis", "以黏键盘痛点开头，评论率高于基线", *extra)
        return re.search(r"已登记发布 (L\d+)", out).group(1)

    def comments_file(self, n=24):
        base = ["涂完打字黏键盘真的烦", "太油了，摸鼠标都打滑", "有没有不油的推荐", "吸收太慢了，要搓半天", "多少钱一支", "求链接", "味道好好闻", "包装好好看"]
        return self.write("comments.txt", "\n".join("%s %d" % (base[i % len(base)], i) for i in range(n)) + "\n")


# ---------- 1. 粘贴内容的解析：笔记 ----------

class PasteNotes(Work):
    def notes(self, text, name="in.txt", encoding="utf-8"):
        return rs.read_notes(self.write(name, text, encoding))

    def test_app_cards_keep_titles_whole(self):
        notes, info = rs.read_notes(os.path.join(FIX, "app_search_handcream.txt"))
        self.assertEqual(len(notes), 15)
        self.assertIn("卡片", info["format"])
        self.assertEqual(info["warnings"], [])
        first = notes[0]
        self.assertEqual(first["title"], "5款护手霜一周实测｜不黏键盘的只有这支")       # 开头的数字和「｜」后面的半句都要留着
        self.assertEqual((first["author"], first["likes"]), ("小鹿爱护肤", 13000))
        titles = [n["title"] for n in notes]
        self.assertIn("30支护手霜红黑榜，第7支后悔没早买", titles)
        self.assertIn("2026年护手霜年度爱用，空瓶记", titles)
        self.assertIn("护手霜正确用法，90%的人都涂错了", titles)
        self.assertEqual([n["likes"] for n in notes[:4]], [13000, 21000, 3456, 8802])

    def test_missing_numbers_are_unknown_not_zero(self):
        notes, _ = rs.read_notes(os.path.join(FIX, "app_search_handcream.txt"))
        for n in notes:
            self.assertIsNone(n["collects"])
            self.assertIsNone(n["comments"])
            self.assertIsNone(n["followers"])
        notes, _ = self.notes("只有标题的一篇笔记\n另一篇没有数字的笔记\n")
        self.assertEqual([n["likes"] for n in notes], [None, None])

    def test_cards_with_ad_video_and_date(self):
        text = "广告\n护手霜避雷｜这3支别买\n橘子汽水 3天前\n8802\n视频\n10块钱的护手霜也能很好用\n省钱小能手\n1.2万\n办公室好物分享\n打工人小何\n2026-11-02\n421\n"
        notes, info = self.notes(text)
        self.assertEqual([n["title"] for n in notes], ["护手霜避雷｜这3支别买", "10块钱的护手霜也能很好用", "办公室好物分享"])
        self.assertEqual([n["author"] for n in notes], ["橘子汽水", "省钱小能手", "打工人小何"])
        self.assertEqual([n["likes"] for n in notes], [8802, 12000, 421])
        self.assertEqual(notes[1]["type"], "视频")
        self.assertEqual(notes[2]["date"], "2026-11-02")

    def test_search_page_tabs_and_footer_are_not_cards(self):
        text = ("综合\n最新\n最热\n筛选\n全部\n图文\n视频\n用户\n敲键盘的人怎么选护手霜？7支实测\n键盘侠的工位\n3天前\n1.8万\n"
                "9块9的护手霜居然比大牌好用\n省钱小能手momo\n11-20\n5632\n干皮救星！厚涂过夜的护手霜\n北方姑娘在南方\n11-19\n赞\n- THE END -\n")
        notes, info = self.notes(text)
        self.assertEqual([(n["title"], n["author"], n["likes"]) for n in notes],
                         [("敲键盘的人怎么选护手霜？7支实测", "键盘侠的工位", 18000), ("9块9的护手霜居然比大牌好用", "省钱小能手momo", 5632), ("干皮救星！厚涂过夜的护手霜", "北方姑娘在南方", 0)])
        self.assertEqual([n["type"] for n in notes], ["", "", ""])                # 顶部的「视频」是筛选标签，不是第一篇的形式
        self.assertEqual(info["warnings"], [])                                    # 页脚不算「没复制完整的一篇」

    def test_one_or_two_cards_are_still_cards(self):
        notes, info = self.notes("敲键盘的人怎么选护手霜？7支实测\n键盘侠的工位\n3天前\n1.8万\n9块9的护手霜居然比大牌好用\n省钱小能手momo\n11-20\n5632\n")
        self.assertIn("卡片", info["format"])
        self.assertEqual([(n["title"], n["author"], n["likes"]) for n in notes],
                         [("敲键盘的人怎么选护手霜？7支实测", "键盘侠的工位", 18000), ("9块9的护手霜居然比大牌好用", "省钱小能手momo", 5632)])
        notes, info = self.notes("只贴了一篇的标题\n作者昵称\n321\n")
        self.assertEqual([(n["title"], n["author"], n["likes"]) for n in notes], [("只贴了一篇的标题", "作者昵称", 321)])

    def test_stray_number_and_date_lines_are_never_titles(self):
        text = "\n".join("护手霜笔记标题第%d篇" % i for i in range(1, 13)) + "\n3天前\n5632\n"       # 十几行标题里混进一行日期、一行数字
        notes, info = self.notes(text)
        self.assertEqual(len(notes), 12)
        self.assertFalse([n["title"] for n in notes if n["title"] in ("3天前", "5632")])
        self.assertIn("有 2 行只有数字或日期", info["warnings"][0])

    def test_like_word_without_a_number_is_zero_and_said_so(self):
        notes, info = self.notes("护手霜推荐｜打工人必备\n小鹿\n1.2万\n护手霜避雷清单\n阿宁\n赞\n冬天护手霜怎么选\n木木\n356\n")
        self.assertEqual([(n["title"], n["author"], n["likes"]) for n in notes],
                         [("护手霜推荐｜打工人必备", "小鹿", 12000), ("护手霜避雷清单", "阿宁", 0), ("冬天护手霜怎么选", "木木", 356)])
        self.assertTrue(any("有 1 篇的点赞位置只有「赞」字、没有数字" in x and "不是缺失" in x for x in info["notes"]), info)
        self.assertIsNone(notes[1]["collects"])                    # 没读到的仍然是未知
        _, plain = self.notes("护手霜推荐｜打工人必备\n小鹿\n1.2万\n冬天护手霜怎么选\n木木\n356\n")
        self.assertFalse(plain.get("notes"))

    def test_cards_with_uneven_blocks_warn(self):
        text = "标题一号笔记\n作者甲\n100\n标题二号笔记\n多出来的一行摘要\n作者乙\n200\n标题三号笔记\n作者丙\n300\n标题四号笔记\n作者丁\n400\n"
        notes, info = self.notes(text)
        self.assertEqual(len(notes), 4)
        self.assertTrue(any("行数和别的不一样" in w for w in info["warnings"]), info)

    def test_truncated_last_card_warns(self):
        text = "标题一号笔记\n作者甲\n100\n标题二号笔记\n作者乙\n200\n标题三号笔记\n作者丙\n300\n标题四号没复制完\n"
        notes, info = self.notes(text)
        self.assertEqual(len(notes), 3)
        self.assertTrue(any("没有点赞数" in w for w in info["warnings"]), info)

    def test_line_format_all_fields(self):
        url = "https://www.xiaohongshu.com/explore/" + NOTE_ID % 1
        notes, info = self.notes("5款护手霜一周实测｜打工人版 | 作者 小鹿 | 赞 1.2万 | 藏 800 | 评 56 | 粉丝 900 | 2026-11-01 | %s\n" % url)
        n = notes[0]
        self.assertEqual(n["title"], "5款护手霜一周实测｜打工人版")
        self.assertEqual((n["author"], n["likes"], n["collects"], n["comments"], n["followers"], n["date"]), ("小鹿", 12000, 800, 56, 900, "2026-11-01"))
        self.assertEqual(n["url"], url)
        self.assertEqual(n["id"], NOTE_ID % 1)

    def test_second_column_treated_as_author_when_consistent(self):
        text = "护手霜避雷这3支别买 | 橘子汽水 | 赞 8802\n十块钱的护手霜也好用 | 省钱小能手 | 赞 3456\n办公室好物分享 | 打工人小何 | 赞 421\n"
        notes, info = self.notes(text)
        self.assertEqual([n["author"] for n in notes], ["橘子汽水", "省钱小能手", "打工人小何"])
        self.assertEqual(notes[0]["title"], "护手霜避雷这3支别买")
        self.assertTrue(info["notes"], info)

    def test_stray_pipe_in_title_warns_instead_of_guessing(self):
        text = "护手霜避雷 | 第二弹 | 赞 8802\n十块钱的护手霜也好用 | 赞 3456\n办公室好物分享 | 赞 421\n冬天手干裂怎么办 | 赞 932\n"
        notes, info = self.notes(text)
        self.assertEqual(notes[0]["author"], "")
        self.assertIn("第二弹", notes[0]["title"])
        self.assertTrue(any("已整段当作标题" in w for w in info["warnings"]), info)

    def test_trailing_count_is_likes(self):
        notes, _ = self.notes("护手霜避雷这3支别买 1.5万\n十块钱的护手霜也好用 3456\n")
        self.assertEqual(notes[0]["title"], "护手霜避雷这3支别买")
        self.assertEqual(notes[0]["likes"], 15000)
        self.assertEqual(notes[1]["title"], "十块钱的护手霜也好用 3456")       # 不带单位的行尾数字可能是标题的一部分，不猜
        self.assertIsNone(notes[1]["likes"])

    def test_numbering_stripped_only_for_a_numbered_list(self):
        notes, _ = self.notes("1. 护手霜避雷这3支别买 | 赞 10\n2. 十块钱的护手霜 | 赞 20\n3. 办公室好物分享 | 赞 30\n")
        self.assertEqual([n["title"] for n in notes], ["护手霜避雷这3支别买", "十块钱的护手霜", "办公室好物分享"])
        notes, _ = self.notes("5款护手霜实测 | 赞 10\n30支护手霜红黑榜 | 赞 20\n2026年度爱用 | 赞 30\n")
        self.assertEqual([n["title"] for n in notes], ["5款护手霜实测", "30支护手霜红黑榜", "2026年度爱用"])

    def test_gbk_csv_from_excel(self):
        text = "标题,点赞,收藏,评论,粉丝,作者\r\n护手霜避雷这3支别买,8802,1200,300,1900,橘子汽水\r\n十块钱的护手霜,1.2万,,,,省钱小能手\r\n"
        notes, info = self.notes(text, "export.csv", "gbk")
        self.assertIn("GBK", info["format"])
        self.assertEqual((notes[0]["title"], notes[0]["likes"], notes[0]["followers"], notes[0]["author"]), ("护手霜避雷这3支别买", 8802, 1900, "橘子汽水"))
        self.assertEqual(notes[1]["likes"], 12000)
        self.assertIsNone(notes[1]["collects"])

    def test_markdown_table(self):
        notes, info = self.notes("| 标题 | 点赞 | 作者 |\n|---|---|---|\n| 护手霜避雷｜这3支别买 | 8802 | 橘子汽水 |\n| 十块钱的护手霜 | 3k | momo |\n")
        self.assertIn("表格", info["format"])
        self.assertEqual([(n["title"], n["likes"]) for n in notes], [("护手霜避雷｜这3支别买", 8802), ("十块钱的护手霜", 3000)])

    def test_json_account_export_carries_author_and_fans(self):
        data = {"account": {"nickname": "某账号", "fans": "8.5万", "collected_at": "2026-11-22"},
                "notes": [{"note_id": NOTE_ID % 2, "display_title": "上线：新功能来了", "interact_info": {"liked_count": "1.3万", "collected_count": 900, "comment_count": 77},
                           "time": "3天前", "type": "video", "comments": [{"content": "太好了", "like_count": 5}, "什么时候上线"]}]}
        notes, info = self.notes(json.dumps(data, ensure_ascii=False), "acc.json")
        n = notes[0]
        self.assertEqual((n["author"], n["followers"], n["likes"], n["collects"], n["comments"], n["type"]), ("某账号", 85000, 13000, 900, 77, "视频"))
        self.assertEqual(n["date"], "2026-11-19")                # 「3天前」按采集那天算，不按今天
        self.assertEqual([c["text"] for c in n["comment_list"]], ["太好了", "什么时候上线"])

    def test_note_id_from_links(self):
        nid = NOTE_ID % 3
        for url in ("https://www.xiaohongshu.com/explore/%s?xsec_token=abc" % nid, "https://www.xiaohongshu.com/discovery/item/%s" % nid,
                    "https://www.xiaohongshu.com/user/profile/5f0000000000000000000001/%s" % nid, "https://example.com/x?noteId=%s" % nid):
            self.assertEqual(rs.note_id(url), nid, url)
        self.assertEqual(rs.note_id("http://xhslink.com/a/AbCdEf12"), "xhslink:AbCdEf12")
        self.assertIsNone(rs.note_id("https://www.xiaohongshu.com/search_result?keyword=x"))

    def test_same_note_counted_once_different_notes_kept_apart(self):
        a = "护手霜避雷这3支别买 | 作者 橘子汽水 | 赞 8802 | https://www.xiaohongshu.com/explore/%s\n" % (NOTE_ID % 4)
        b = "护手霜避雷这3支别买 | 作者 另一个人 | 赞 12 | https://www.xiaohongshu.com/explore/%s\n" % (NOTE_ID % 5)
        self.ok("research.py", "add", self.write("a.txt", a), "--keyword", "护手霜 避雷")
        out = self.ok("research.py", "add", self.write("b.txt", a + b), "--keyword", "护手霜 推荐")
        self.assertIn("合并重复 1 篇", out)
        notes = self.data("research", "notes.json")["notes"]
        self.assertEqual(len(notes), 2)                          # 标题一样但编号不同：是两篇
        self.assertEqual(sorted(notes[0]["keywords"]), ["护手霜 推荐", "护手霜 避雷"])

    def test_add_echoes_what_it_read_and_warns_without_likes(self):
        out = self.ok("research.py", "add", os.path.join(FIX, "app_search_handcream.txt"), "--keyword", "护手霜")
        self.assertIn("共 **15** 篇", out)
        self.assertIn("5款护手霜一周实测｜不黏键盘的只有这支", out)
        self.assertIn("按未知处理，不当 0", out)
        self.assertIn("请核对", out)
        out = self.ok("research.py", "add", self.write("t.txt", "只有标题的一篇笔记\n另一篇没有数字的笔记\n"), "--replace")
        self.assertIn("都没有点赞数", out)

    def test_stdin_and_missing_file(self):
        out = self.ok("research.py", "add", "-", stdin="护手霜避雷这3支别买 | 赞 8802\n")
        self.assertIn("共 **1** 篇", out)
        self.assertIn("找不到文件", self.refused("research.py", "add", "nope.txt"))

    def test_dates_without_year_are_never_in_the_future(self):
        today = datetime(2026, 11, 26)
        self.assertEqual(C.parse_date("11-02", today), "2026-11-02")
        self.assertEqual(C.parse_date("编辑于 11-02 上海", today), "2026-11-02")
        self.assertEqual(C.parse_date("12-25", today), "2025-12-25")
        self.assertEqual(C.parse_date("3天前 广东", today), "2026-11-23")
        self.assertEqual(C.parse_date("昨天 21:15", today), "2026-11-25")
        self.assertEqual(C.parse_date("2026年11月1日", today), "2026-11-01")
        self.assertIsNone(C.parse_date("一杯不到4块", today))

    def test_counts(self):
        for raw, want in (("1.2万", 12000), ("3k", 3000), ("1,024", 1024), ("10万+", 100000), ("2.4w", 24000), (56, 56)):
            self.assertEqual(C.num(raw), want, raw)
        for raw in ("", None, "赞", "abc", True):
            self.assertIsNone(C.num(raw), raw)


# ---------- 2. 粘贴内容的解析：评论 ----------

class PasteComments(Work):
    def read(self, text, name="c.txt", author="", encoding="utf-8"):
        raw, info = ci.read_comments(self.write(name, text, encoding), author)
        ok, stat = ci.prepare(raw, ci.Lexicon())
        return raw, info, ok, stat

    def test_app_comment_blocks(self):
        raw, info = ci.read_comments(os.path.join(FIX, "app_comments_handcream.txt"))
        ok, stat = ci.prepare(raw, ci.Lexicon())
        self.assertIn("评论块", info["format"])
        self.assertEqual((len(raw), len(ok), len(stat["author_replies"])), (13, 10, 3))
        texts = [t for t, _ in ok]
        self.assertIn("这个真的不黏吗？我打字手心一出汗就黏键盘", texts)
        for junk in ("奶茶不加糖", "3天前 广东", "赞 8", "回复", "作者", "共 23 条评论", "展开 2 条回复", "- THE END -"):
            self.assertNotIn(junk, texts)                       # 用户名、时间、点赞数、按钮都不是评论
        self.assertEqual(dict(ok)["之前买的那支太油了，摸鼠标都打滑"], 12)       # 点赞数跟着评论走
        self.assertNotIn("39 一支 50g，主页店铺有", texts)               # 作者回复不算用户反馈

    def test_page_total_and_collapsed_replies_are_reported(self):
        # 页面自己写的总数、没展开的回复：已读到的评论照常统计，但少读了多少要说出来，差一两条就可能过不了 20 条的门槛
        _, info = ci.read_comments(os.path.join(FIX, "app_comments_handcream.txt"))
        self.assertEqual(len(info["notes"]), 2, info["notes"])
        self.assertTrue(info["notes"][0].startswith("页面上写着共 23 条评论，这里读到 13 条，少 10 条：多半是折叠的回复没有展开"), info["notes"])
        self.assertEqual(info["notes"][1], "有 1 处回复没有展开（共 2 条），这些回复没有读到。")
        block = "小熊\n多少钱一支\n3天前 广东\n赞 2\n回复\n富贵花开\n吸收有点慢\n昨天 20:02 山东\n赞 6\n回复\n阿七\n求链接\n3天前 上海\n赞\n回复\n"
        for head, want in (("共 3 条评论\n", ["页面上写着共 3 条评论，和读到的条数一致。"]), ("", [])):
            raw, info, _, _ = self.read(head + block)
            self.assertEqual((len(raw), info["notes"]), (3, want))
        _, info, _, _ = self.read("共 2 条评论\n" + block)                       # 读到的比页面写的还多：多半读错了，要对照原文
        self.assertIn("这里读到 3 条，多出 1 条", info["notes"][0])
        _, info, _, _ = self.read("共 5 条评论\n" + block + "展开 2 条回复\n")
        self.assertIn("少 2 条", info["notes"][0])
        self.assertEqual(info["notes"][1], "有 1 处回复没有展开（共 2 条），这些回复没有读到。")
        self.assertEqual(info["warnings"], [])                                   # 这是说明，不是解析存疑：不降低可信度

    def test_profile_numbers_are_checked_against_the_comment_section(self):
        # 档案写 45 小时，作者自己回复说 9 小时和 40 小时，读者也在追问：这种对不上要指出来
        claims = [("卖点", "45 小时续航"), ("事实·价格", "到手 299 元"), ("卖点", "通勤降噪")]
        replies = ["统一回复：单耳续航 9 小时，配合充电盒总共 40 小时左右，链接在主页店铺", "到手 299，暂时没有学生价"]
        readers = [("续航真有45小时吗，我朋友那副两天就没电了", 9), ("299 这个价位值了", 3), ("我 259 元买的，比你便宜", 1),
                   ("通勤一个小时刚好听完一期播客", 0), ("续航 45h 够用一周", 2), ("降噪怎么样？地铁上能压住报站声吗", 5)]
        got = ci.claim_checks(claims, replies, readers)
        self.assertEqual([(c["source"], c["claim"]) for c in got], [("卖点", "45 小时续航"), ("事实·价格", "到手 299 元")])
        hours, price = got
        self.assertEqual([x["numbers"] for x in hours["replies"]], [["9 小时", "40 小时"]])            # 作者回复里的数字和档案不一样
        self.assertEqual([(x["text"], x["numbers"]) for x in hours["readers"]], [("续航真有45小时吗，我朋友那副两天就没电了", [])])   # 读者在追问这个数字
        self.assertEqual(price["replies"], [])                                                          # 「到手 299」和档案一致
        self.assertEqual([(x["text"], x["numbers"]) for x in price["readers"]], [("我 259 元买的，比你便宜", ["259 元"])])
        # 说法一致（45h 就是 45 小时）、说的不是一回事（通勤一个小时）、没有数字的卖点：都不报
        self.assertEqual(ci.claim_checks(claims, ["续航 45 小时，充电 10 分钟"], [("续航 45h 够用一周", 2), ("通勤一个小时刚好听完一期播客", 0)]), [])
        # 整条命令：自己笔记下的评论和档案对，别人笔记下的不对
        self.ok("launch_log.py", "init", "--product", "静界 Air 耳机", "--goal", "互动", "--selling-points", "通勤降噪,45 小时续航", "--price", "到手 299 元")
        self.ok("launch_log.py", "add", "--title", "地铁通勤党的降噪耳机", "--baseline", "--published", "2026-11-19")
        rows = [("读者%d" % i, t, n) for i, (t, n) in enumerate(readers)] + [("阿澈数码", t, 0) for t in replies]
        paste = self.write("c.txt", "".join("%s\n%s\n3天前 上海\n赞 %d\n回复\n" % r for r in rows))
        out = self.ok("comment_insight.py", paste, "--id", "L1", "--author", "阿澈数码")
        self.assertIn("有效评论 **6** 条，作者回复 2 条", out)
        self.assertIn("## 说法核对", out)
        self.assertIn("- 档案（卖点）写的是「45 小时续航」", out)
        self.assertIn("  - 作者回复里是 9 小时、40 小时：“统一回复：单耳续航 9 小时", out)
        self.assertIn("  - 读者在问这个数字：“续航真有45小时吗，我朋友那副两天就没电了”（9 赞）", out)
        self.ok("launch_log.py", "verdict", "--id", "L1", "--result", "基线", "--learning", "地铁场景开头")
        nxt = self.ok("launch_log.py", "next")                                           # 下了结论以后，下一步的依据里一直带着，直到核实
        self.assertIn("## 待核实的说法", nxt)
        self.assertIn("45 小时续航", nxt)
        self.assertNotIn("说法核对", self.ok("comment_insight.py", paste, "--research", "--author", "阿澈数码"))

    def test_author_named_on_command_line(self):
        text = "小熊\n多少钱一支\n3天前 广东\n赞 2\n回复\n店主阿七\n39 一支\n3天前 上海\n赞\n回复\n富贵花开\n吸收有点慢\n昨天 20:02 山东\n赞 6\n回复\n"
        raw, info, ok, stat = self.read(text, author="店主阿七")
        self.assertEqual([t for t, _ in ok], ["多少钱一支", "吸收有点慢"])
        self.assertEqual(stat["author_replies"], ["39 一支"])

    def test_one_per_line_and_nickname_prefix(self):
        _, info, ok, _ = self.read("太油了\n多少钱一支\n求链接\n味道好好闻\n")
        self.assertEqual(info["format"], "每行一条评论")
        self.assertEqual(len(ok), 4)
        _, info, ok, _ = self.read("小熊：太油了\n阿七：多少钱一支\nmomo: 求链接\n花开：味道好好闻\n")
        self.assertIn("昵称", info["format"])
        self.assertEqual([t for t, _ in ok], ["太油了", "多少钱一支", "求链接", "味道好好闻"])

    def test_csv_gbk_and_author_column(self):
        text = "昵称,评论内容,点赞数,是否作者\r\n小熊,太油了,12,否\r\n店主,39 一支,1,是\r\nmomo,多少钱一支,5,\r\n"
        raw, info, ok, stat = self.read(text, "c.csv", encoding="gbk")
        self.assertIn("GBK", info["format"])
        self.assertEqual(ok, [("太油了", 12), ("多少钱一支", 5)])
        self.assertEqual(stat["author_replies"], ["39 一支"])

    def test_json_shapes(self):
        _, _, ok, _ = self.read(json.dumps(["太油了", "多少钱一支"], ensure_ascii=False), "a.json")
        self.assertEqual(len(ok), 2)
        nested = {"data": {"items": [{"title": "笔记标题不是评论", "desc": "笔记正文也不是评论",
                                      "comments": [{"content": "太油了", "like_count": 3, "user_info": {"nickname": "小熊"}},
                                                   {"content": "谢谢喜欢", "show_tags": ["is_author"], "sub_comments": [{"content": "求链接"}]}]}]}}
        raw, _, ok, stat = self.read(json.dumps(nested, ensure_ascii=False), "b.json")
        self.assertEqual(sorted(t for t, _ in ok), ["太油了", "求链接"])
        self.assertEqual(stat["author_replies"], ["谢谢喜欢"])

    def test_spam_and_duplicates_are_counted_separately(self):
        text = "太油了，摸鼠标都打滑\n看我主页，有同款更便宜\n互关互赞，有赞必回\n太油了，摸鼠标都打滑\n多少钱一支\n求链接\n"
        _, _, ok, stat = self.read(text)
        self.assertEqual([t for t, _ in ok], ["太油了，摸鼠标都打滑", "多少钱一支", "求链接"])
        self.assertEqual(sum(len(v) for v in stat["spam"].values()), 2)
        self.assertEqual(stat["duplicates"], 1)

    def test_blocks_split_by_like_and_reply_lines(self):
        _, info, ok, _ = self.read("太油了\n赞 3\n回复\n多少钱一支\n赞 1\n回复\n")     # 没有时间行，靠「赞 / 回复」行分块
        self.assertEqual(ok, [("太油了", 3), ("多少钱一支", 1)])
        self.assertEqual(info["warnings"], [])

    def test_one_or_two_comments_are_still_blocks(self):
        raw, info, ok, stat = self.read("奶茶不加糖\n这个真的不黏吗\n3天前 广东\n赞 8\n回复\n护手霜研究所\n作者\n不黏的，我敲了一下午代码试过\n3天前 上海\n赞\n回复\n")
        self.assertIn("评论块", info["format"])
        self.assertEqual(ok, [("这个真的不黏吗", 8)])              # 用户名不算评论
        self.assertEqual(stat["author_replies"], ["不黏的，我敲了一下午代码试过"])
        self.assertEqual(info["warnings"], [])

    def test_leftover_ui_lines_raise_a_warning(self):
        _, info, ok, _ = self.read("太油了\n昨天 14:02\n回复\n多少钱一支\n求链接\n")       # 夹着界面文字，但凑不成评论块：按每行一条读，并提醒
        self.assertEqual(info["format"], "每行一条评论")
        self.assertEqual([t for t, _ in ok], ["太油了", "多少钱一支", "求链接"])
        self.assertIn("有 2 行像是时间、点赞数或「回复」按钮", info["warnings"][0])

    def test_report_states_counts_and_thresholds(self):
        out = self.ok("comment_insight.py", os.path.join(FIX, "app_comments_handcream.txt"))
        self.assertIn("读到 13 条，其中有效评论 **10** 条，作者回复 3 条", out)
        self.assertIn("有效评论不到 20 条", out)
        self.assertIn("只能当线索", out)
        out = self.ok("comment_insight.py", os.path.join(FIX, "handcream_comments_20.txt"), "--detail")
        self.assertIn("有效评论 **20** 条", out)
        self.assertIn("| 质地与手感 |", out)
        self.assertIn("痛点", out)
        self.assertIn("## 逐条归类", out)

    def test_three_complaints_are_a_pain_only_with_enough_comments(self):
        few = [("太油了", 0), ("黏糊糊的不敢碰手机", 0), ("吸收太慢了，要搓半天", 0)]
        r = ci.analyse(few + [("多少钱一支", 0)])
        by = {a["aspect"]: a for a in r["aspects"]}
        self.assertEqual(by["质地与手感"]["complaints"], 3)
        self.assertFalse(r["pain_clusters"]["质地与手感"]["enough"])            # 3 条吐槽，但一共只有 4 条评论：线索
        self.assertEqual(by["质地与手感"]["verdict"], "线索（样本不足）")
        self.assertNotIn("| 痛点 |", ci.to_markdown(r))
        filler = [("包装好好看 %d" % i, 0) for i in range(17)]
        r = ci.analyse(few[:2] + filler + [("求链接", 0)])                      # 20 条评论，但这个维度只有 2 条吐槽
        self.assertFalse(r["pain_clusters"]["质地与手感"]["enough"])
        r = ci.analyse(few + filler)                                            # 20 条评论，3 条吐槽
        self.assertTrue(r["pain_clusters"]["质地与手感"]["enough"])
        self.assertEqual({a["aspect"]: a for a in r["aspects"]}["质地与手感"]["verdict"], "痛点")
        r = ci.analyse(few + filler, parse={"format": "x", "warnings": ["条数可能不准"]})     # 解析有疑点：同样不下判断
        self.assertEqual({a["aspect"]: a for a in r["aspects"]}["质地与手感"]["verdict"], "线索（解析存疑）")

    def test_project_lexicon_example_from_the_docs(self):
        doc = C.read_text(os.path.join(ROOT, "references", "feedback.md"))[0]
        block = re.search(r"```json\n(.*?)\n```", doc, re.S).group(1)
        self.save(json.loads(block), "lexicon.json")
        lex = ci.Lexicon([os.path.join(self.work, "xhs_launch", "lexicon.json")])
        self.assertEqual(lex.analyse("烧到一半挂壁了")["aspects"]["燃烧表现"][0], "C")
        self.assertEqual(lex.analyse("烧得均匀，没有隧道")["aspects"]["燃烧表现"][0], "P")
        self.assertEqual(lex.analyse("烛芯要剪吗")["aspects"]["燃烧表现"][0], "Q")
        self.assertIn("购买意向", lex.analyse("求团购")["intents"])
        self.assertEqual(lex.spam_kind("同款代购看这里"), "自定义")
        self.assertNotIn("痛点吐槽", lex.analyse("土耳其可以发货吗")["intents"])
        out = self.ok("comment_insight.py", self.write("c.txt", "烧到一半挂壁了\n有隧道\n炸芯了吓我一跳\n烛芯要剪吗\n"))
        self.assertIn("已加载项目词表", out)                                    # 数据目录里的词表自动加载
        self.assertIn("| 燃烧表现 | 3 | 1 |", out)

    def test_bad_lexicon_is_reported_not_crashed(self):
        self.write("xhs_launch/lexicon.json", "{ not json")
        self.assertIn("不是合法的 JSON", self.refused("comment_insight.py", self.write("c.txt", "太油了\n")))


# ---------- 3. 在用户自己的目录运行 ----------

class AnyFolder(Work):
    def tree(self):
        out = []
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
            out += [os.path.relpath(os.path.join(base, f), ROOT) for f in files]
        return sorted(out)

    def test_every_script_runs_from_another_folder(self):
        for s in ALL_SCRIPTS:
            code, out = run(s, "-h", cwd=self.work)
            self.assertEqual(code, 0, s + out)
            self.assertIn("usage", out)

    def test_data_lands_in_the_users_folder_not_the_skill(self):
        before = self.tree()
        self.init()
        self.ok("research.py", "add", os.path.join(EX, "sample_notes.json"))
        self.ok("comment_insight.py", os.path.join(EX, "sample_comments.txt"), "--research")
        self.ok("research.py", "analyze", "--days", "0")
        self.assertEqual(self.tree(), before)
        for f in ("launch_log.json", "research/notes.json", "research/insight.json", "research/analysis.json", "research/brief.md"):
            self.assertTrue(os.path.exists(os.path.join(self.work, "xhs_launch", f)), f)

    def test_next_step_hints_are_copy_paste_ready(self):
        outs = [self.init(), self.ok("launch_log.py", "status"), self.ok("research.py", "keywords", "--category", "护手霜"),
                self.ok("research.py", "add", os.path.join(EX, "sample_notes.json")), self.ok("guide.py"), self.ok("guide.py", "commands")]
        for out in outs:
            self.assertNotRegex(out, r"python3?\s+scripts/")                    # 相对路径在用户目录里一定跑不通
            for m in re.finditer(r"(\S+)\s+(\S*?(?:%s))" % "|".join(re.escape(s) for s in ALL_SCRIPTS), out):
                if m.group(1) in ("python3", "python", "py"):
                    self.assertTrue(os.path.isabs(m.group(2)) and os.path.exists(m.group(2)), m.group(0))
        hint = re.search(r"调研再写新笔记：(.+)", outs[0]).group(1)
        code = subprocess.run(hint, shell=True, cwd=self.work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(code.returncode, 0, code.stdout.decode("utf-8", "replace"))      # 提示里的命令原样粘贴就能跑

    def test_missing_log_tells_how_to_start(self):
        out = self.refused("launch_log.py", "add", "--title", "x", "--hypothesis", "y 高于 z")
        self.assertIn("请先建档", out)
        self.assertIn(os.path.join(SCRIPTS, "launch_log.py"), out)
        self.assertIn("尚未建立发布日志", self.ok("launch_log.py", "status"))

    def test_status_without_a_profile_lists_what_to_ask(self):
        # 还没有档案时，status 给出建档前要问的问题：按用户要做的事分两组，每组一轮问完，命令照着填就能跑
        out = self.ok("launch_log.py", "status")
        review, write = out.split("## 二、")
        self.assertIn("## 一、只想看一篇已经发出去的笔记", review)
        self.assertIn("问 4 样", review)
        self.assertIn("调研前问 7 样", write)
        for k in ll.LATER:
            self.assertNotIn("%s：" % k, review)                    # 复盘用不到的事实不问
            self.assertIn("- %s：%s" % (k, ll.FACTS[k]), write)      # 写笔记要的事实留到第二轮，事先说明
        self.assertEqual(sorted(ll.LATER + ("价格", "身份")), sorted(ll.FACTS))       # 七样必填的事实，要么在第一轮问，要么在第二轮问
        self.assertIn("不要填「无」", out)
        self.assertIn("缺点和身份不能填「无」", out)
        cmds = re.findall(r"(?m)^python3 .+$", out)
        self.assertEqual(len(cmds), 3)
        self.assertNotIn("--fact", "".join(cmds))                   # 第一轮的建档命令里没有第二轮才问的事实
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        for c in cmds[:2]:                                          # 复盘那一组：两条命令原样粘贴就能跑通
            p = subprocess.run(c, shell=True, cwd=self.work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(p.returncode, 0, p.stdout.decode("utf-8", "replace"))
        log = self.data("launch_log.json")
        self.assertEqual((log["product"]["facts"], log["launches"][0]["baseline"], log["launches"][0]["published_at"][:10]), ({}, True, "2026-11-20"))
        self.assertIn("已存在", self.refused("launch_log.py", *cmds[2].split("launch_log.py ")[1].replace('"', "").split()))

    def test_tone_is_recorded_like_a_fact(self):
        self.ok("launch_log.py", "init", "--product", "白茶护手霜", "--goal", "互动", "--fact", "语气=朋友聊天")
        self.assertEqual(self.data("launch_log.json")["product"]["tone"], "朋友聊天")
        self.assertNotIn("语气", self.data("launch_log.json")["product"]["facts"])
        self.assertIn("语气 = 像同事安利", self.ok("launch_log.py", "fact", "语气=像同事安利", "外观=白色软管"))
        p = self.data("launch_log.json")["product"]
        self.assertEqual((p["tone"], p["facts"]["外观"]), ("像同事安利", "白色软管"))
        self.refused("launch_log.py", "fact", "语气=无")             # 「无」不是一种语气，原来的不动
        self.assertEqual(self.data("launch_log.json")["product"]["tone"], "像同事安利")

    def test_dir_flag_keeps_products_apart_and_is_carried_in_hints(self):
        out = self.ok("launch_log.py", "--dir", "candle", "init", "--product", "雪松蜡烛", "--category", "香薰蜡烛")
        self.assertIn("--dir candle", out)
        self.assertTrue(os.path.exists(os.path.join(self.work, "candle", "launch_log.json")))
        self.assertFalse(os.path.exists(os.path.join(self.work, "xhs_launch")))
        self.assertIn("雪松蜡烛", self.ok("launch_log.py", "status", "--dir", "candle"))
        self.assertIn("雪松蜡烛", self.ok("launch_log.py", "status", env={"XHS_LAUNCH_DIR": os.path.join(self.work, "candle")}))

    def test_running_inside_the_skill_folder_warns(self):
        skill = os.path.join(self.work, "skill")
        shutil.copytree(ROOT, skill, ignore=shutil.ignore_patterns(".git", "__pycache__", "tests"))
        p = subprocess.run([sys.executable, "-B", os.path.join(skill, "scripts", "launch_log.py"), "init", "--product", "x"], cwd=skill,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertIn("当前目录在技能目录里", p.stdout.decode("utf-8", "replace"))

    def test_output_cut_by_head_still_saves_files(self):
        self.init()
        cmd = "%s -B %s add %s | head -1" % (C.quote(sys.executable), C.quote(os.path.join(SCRIPTS, "research.py")), C.quote(os.path.join(EX, "sample_notes.json")))
        p = subprocess.run(cmd, shell=True, cwd=self.work, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(p.stderr.decode("utf-8", "replace").strip(), "")
        self.assertEqual(len(self.data("research", "notes.json")["notes"]), 24)

    def test_demo_runs_end_to_end_and_cleans_up(self):
        before = self.tree()
        out = self.ok("guide.py", "demo")
        self.assertIn("演示完成", out)
        for stage in ("① 调研", "② 发布", "③ 反馈", "④ 迭代"):
            self.assertIn(stage, out)
        self.assertEqual(os.listdir(self.work), [])
        self.assertEqual(self.tree(), before)
        self.assertIn("临时目录已经删除", out)                        # 输出里的路径演示完就不在了，要说一声
        keep = os.path.join(self.work, "keep")
        kept = self.ok("guide.py", "demo", "--out", keep)
        self.assertNotIn("临时目录", kept)
        self.assertIn("产出文件保留在：" + os.path.join(keep, "xhs_launch"), kept)
        log = C.read_json(os.path.join(keep, "xhs_launch", "launch_log.json"))
        self.assertEqual([(l["id"], l["verdict"]["result"]) for l in log["launches"]], [("L1", "基线"), ("L2", "成立")])
        self.assertIn("已有 xhs_launch", run("guide.py", "demo", "--out", keep, cwd=self.work)[1])      # 不覆盖已有数据

    def test_demo_follows_its_own_analysis(self):
        # 演示登记的假设，就是它自己的分析给出的第一条候选；结论里的数字和诊断算出来的一致
        keep = os.path.join(self.work, "keep")
        out = self.ok("guide.py", "demo", "--full", "--out", keep)
        first = C.read_json(os.path.join(keep, "xhs_launch", "research", "analysis.json"))["hypotheses"][0]
        l1, l2 = C.read_json(os.path.join(keep, "xhs_launch", "launch_log.json"))["launches"]
        self.assertEqual(first["basis"], "需求缺口")
        self.assertIn(first["evidence"], l2["evidence"])
        self.assertEqual(first["metric"], l2["main_metric"])
        self.assertIn("「价格」", first["hypothesis"])
        self.assertIn("价格", l2["hypothesis"])
        rate = lambda l: "%.1f%%" % (100.0 * l["metrics"][-1]["raw"]["comments"] / l["metrics"][-1]["raw"]["views"])
        self.assertIn("评论率 %s" % rate(l1), l1["verdict"]["learning"])
        self.assertIn("评论率 %s，是基线 %s" % (rate(l2), rate(l1)), l2["verdict"]["learning"])
        self.assertIn("对比 L1：评论率 %s → %s" % (rate(l1), rate(l2)), out)

    def test_demo_shows_key_lines_whole(self):
        # 默认的演示只列要点：每条命令都有要点，每一行都是完整输出里原样的整行，不会把命令从中间切开
        a, b = os.path.join(self.work, "a"), os.path.join(self.work, "b")
        brief = self.ok("guide.py", "demo", "--out", a).replace(a, "DIR")
        full = self.ok("guide.py", "demo", "--full", "--out", b).replace(b, "DIR")
        self.assertLess(len(brief), len(full) / 2)
        self.assertNotIn("以上是要点", full)
        whole = set(full.splitlines())
        cmds = [c for _, group in guide.demo_steps() for c in group if c != "COPY_PLAN"]
        blocks = [x.splitlines() for x in brief.split("\n$ ")[1:]]
        self.assertEqual(len(blocks), len(cmds))
        for block in blocks:
            shown = [l for l in block[1:] if l.startswith("  ") and not l.startswith("  （以上是要点")]
            self.assertTrue(shown, block[0])
            for l in shown:
                self.assertIn(l, whole, "要点里的这一行不是完整输出里的原样整行")
        for fact in ("有效评论 **21** 条", "| 价格 | 3 | 6 | 0 |", "🎯 缺口", "依据：21 条评论里有 9 条在吐槽或追问它，但 32 篇笔记里只有 3 篇在标题回应", "结论：通过（错误 0，警告 0）",
                     "读者在问这个数字", "（+158%）", "→ 成立", "## 待核实的说法"):
            self.assertIn(fact, brief)
        # 每一组要点规则都对得上真实输出；输出改了写法，这里会先报出来
        used = {}
        for cmd, block in zip(cmds, [x.splitlines() for x in full.split("\n$ ")[1:]]):
            lines = [l[2:] for l in block[1:] if l.startswith("  ")]
            key = guide.digest_key(cmd)
            self.assertTrue(guide.digest(key, lines)[1], "演示的要点规则对不上 %s 的输出" % key)
            used.setdefault(key, set()).update(p for p, _ in guide.DIGEST[key] if any(re.match(r"\s*(?:%s)" % p, l) for l in lines))
        for key, rules in guide.DIGEST.items():
            self.assertEqual(used.get(key), set(p for p, _ in rules), "要点规则里有对不上任何输出的写法：" + key)
        self.assertEqual(guide.digest("没有这种命令", ["a", "b"]), (["a", "b"], False))

    def test_same_input_same_output(self):
        ties = "太油了还很黏，而且闷\n有点黏还油，闷手\n又闷又油又黏\n" * 1 + "包装漏了，盖子还裂了，压泵也坏了\n盖子裂了，压泵坏了，包装还漏\n价格多少，味道怎么样，包装好看吗\n"
        outs = set()
        for seed in ("0", "1", "2", "3", "4", "5"):
            d = tempfile.mkdtemp(prefix="xhs_seed_")
            self.addCleanup(shutil.rmtree, d, True)
            with open(os.path.join(d, "ties.txt"), "w", encoding="utf-8") as f:
                f.write(ties)                                      # 同一个维度里几个词次数一样：顺序不能看运气
            got = []
            for args in (["research.py", "add", os.path.join(EX, "sample_notes.json")], ["comment_insight.py", os.path.join(EX, "sample_comments.txt"), "--research"],
                         ["research.py", "analyze", "--days", "0"], ["comment_insight.py", os.path.join(FIX, "handcream_comments_20.txt")], ["comment_insight.py", "ties.txt"]):
                code, out = run(*args, cwd=d, env={"PYTHONHASHSEED": seed})
                self.assertEqual(code, 0, out)
                got.append(out.replace(d, "WORK"))
            outs.add("\n".join(got))
        self.assertEqual(len(outs), 1)


# ---------- 4. 分析的门槛 ----------

def note(title, likes, author="", followers=None, collects=None, comments=None, desc="", typ="图文"):
    return {"id": None, "title": title, "desc": desc, "likes": likes, "collects": collects, "comments": comments, "shares": None, "author": author,
            "followers": followers, "date": None, "url": "", "type": typ, "comment_list": [], "keywords": []}


class ResearchGuards(Work):
    def test_small_sample_gives_no_hypothesis(self):
        notes = [note("护手霜测评第%d篇！" % i, 100 * (i + 1), "作者%d" % i, 1000) for i in range(12)]
        R = rs.analyze(notes, days=0)
        self.assertFalse(R["sample_sufficient"])
        self.assertEqual(R["hypotheses"], [])
        self.assertTrue(any("不到 20 篇" in w for w in R["no_hypothesis_reasons"]), R["no_hypothesis_reasons"])
        self.assertFalse(any(h["solid"] for h in R["hooks"]))
        self.assertIn("不到 20 篇", rs.to_markdown(R, "护手霜"))

    def test_big_account_does_not_make_a_hook_look_good(self):
        # 一个大号每篇都用感叹号、互动很高；小号不用。直接比互动数会把感叹号算成好写法。
        notes = [note("大号的日常分享%d！" % i, 20000 + i * 100, "大号", 5000000) for i in range(10)]
        notes += [note("小号的认真测评%d" % i, 200 + i * 10, "小号%d" % (i % 10), 1000 + i * 37) for i in range(20)]
        R = rs.analyze(notes, days=0)
        hook = next(h for h in R["hooks"] if h["hook"] == "感叹号")
        self.assertEqual(R["adjust"], "按粉丝量校正")
        self.assertFalse(hook["solid"])
        self.assertNotIn("感叹号", json.dumps(R["hypotheses"], ensure_ascii=False))
        raw = rs.median([n["likes"] for n in notes[:10]]) / rs.median([n["likes"] for n in notes[10:]])
        self.assertLess(hook["lift"], raw / 5)                    # 校正后的倍数远小于直接相除

    def test_within_account_comparison_when_notes_come_from_few_accounts(self):
        notes = []
        for a, base in (("甲", 10000), ("乙", 100)):
            notes += [note("%s上线：新功能%d" % (a, i), base * 3, a, None) for i in range(6)]
            notes += [note("%s的日常记录%d" % (a, i), base, a, None) for i in range(8)]
        R = rs.analyze(notes, days=0)
        self.assertEqual(R["adjust"], "账号内相对值")
        hook = next(h for h in R["hooks"] if h["hook"] == "新闻动词")
        self.assertEqual(hook["lift"], 3.0)
        self.assertEqual(hook["by_author"], {"甲": 3.0, "乙": 3.0})
        self.assertTrue(hook["solid"])

    def test_no_fan_counts_is_flagged(self):
        notes = [note("护手霜笔记%d" % i, 100 + i, "作者%d" % i) for i in range(25)]
        R = rs.analyze(notes, days=0)
        self.assertIsNone(R["adjust"])
        self.assertIn("⚠️", R["adjust_note"])
        self.assertFalse(any(h["basis"] in ("标题钩子", "角度机会", "内容形式") for h in R["hypotheses"]))

    def test_finding_from_one_or_two_accounts_is_not_a_conclusion(self):
        def corpus(title, accounts):
            notes = [note("护手霜笔记%d" % i, 100 + i, "作者%d" % i, 1000) for i in range(25)]
            return notes + [note(title % i, 5000, "大号%d" % (i % accounts), 1000) for i in range(6)]

        for accounts, usable in ((2, False), (6, True)):            # 同样 6 篇高互动笔记：出自 2 个账号不算结论，出自 6 个账号才算
            R = rs.analyze(corpus("这支太绝了！%d", accounts), days=0)
            hook = next(h for h in R["hooks"] if h["hook"] == "感叹号")
            self.assertEqual((hook["used"], hook["authors"], hook["solid"]), (6, accounts, usable))
            self.assertGreater(hook["lift"], 10)
            self.assertEqual(any(h["basis"] == "标题钩子" and "感叹号" in h["hypothesis"] for h in R["hypotheses"]), usable)
            R = rs.analyze(corpus("护手霜避雷清单%d", accounts), days=0)
            angle = next(a for a in R["angles"] if a["angle"] == "避雷踩坑")
            self.assertEqual((angle["count"], angle["authors"], angle["opportunity"]), (6, accounts, usable))
            self.assertEqual(any(h["basis"] == "角度机会" for h in R["hypotheses"]), usable)

    def test_other_bucket_is_never_the_baseline_or_an_opportunity(self):
        notes = [note("随便写写%d" % i, 5000, "作者%d" % i, 1000) for i in range(6)]         # 篇数够、占比低、互动高、作者分散：换成别的角度就是「机会」
        notes += [note("护手霜合集推荐%d" % i, 100, "作者%d" % (i + 10), 1000) for i in range(26)]
        R = rs.analyze(notes, days=0)
        other = next(a for a in R["angles"] if a["angle"] == "其他")
        self.assertEqual((other["count"], other["share"]), (6, 0.188))
        self.assertGreaterEqual(other["vs_overall"], 1.2)
        self.assertFalse(other["opportunity"])
        self.assertEqual(R["angles"][-1]["angle"], "其他")
        md = rs.to_markdown(R, "护手霜")
        self.assertRegex(md, r"\| 其他 \| 6 \| 19% \| — \| 5000 \| 6 \| — \|")
        self.assertNotIn("「其他」角度", json.dumps(R["hypotheses"], ensure_ascii=False))

    def test_selling_point_synonyms(self):
        terms = rs.selling_terms(["一杯不到4块"], ["一杯不到4块=多少钱/每杯", "3秒冷萃＝3秒／秒冲"])
        self.assertIn("多少钱", terms["一杯不到4块"])
        self.assertEqual(terms["3秒冷萃"], ["3秒冷萃", "3秒", "秒冲"])
        notes = [note("冷萃咖啡液一杯到底多少钱？", 3000, "甲", 1000), note("打工人早八咖啡｜3秒冲好", 12000, "乙", 1000)]
        notes += [note("咖啡液推荐第%d篇" % i, 100, "作者%d" % i, 1000) for i in range(20)]
        R = rs.analyze(notes, days=0, selling=terms)
        by = {s["selling_point"]: s for s in R["same_selling_point"]}
        self.assertEqual((by["一杯不到4块"]["notes"], by["一杯不到4块"]["top"][0]["matched"]), (1, "多少钱"))
        self.assertEqual(by["3秒冷萃"]["top"][0]["title"], "打工人早八咖啡｜3秒冲好")
        wide = rs.analyze(notes, days=0, selling=rs.selling_terms(["冷萃"], ["冷萃=咖啡"]))["same_selling_point"][0]
        self.assertEqual(wide["ignored_terms"], ["咖啡"])                       # 一半以上笔记都有的说法分不出谁在讲这个卖点
        none = rs.to_markdown(rs.analyze(notes, days=0, selling=rs.selling_terms(["零添加"])), "咖啡液")
        self.assertIn("可能是空白，也可能只是说法不同", none)

    def test_gap_needs_three_concerns_and_enough_comments(self):
        notes = [note("护手霜合集推荐%d" % i, 100 + i, "作者%d" % i, 1000) for i in range(22)]
        few = ci.analyse([("太油了", 0), ("黏糊糊的", 0), ("多少钱一支", 0)])
        R = rs.analyze(notes, days=0, insight=few)
        self.assertFalse(any(g["gap"] for g in R["gaps"]))
        self.assertFalse(R["demand_sufficient"])
        many = ci.analyse([("太油了%d" % i, 0) for i in range(12)] + [("味道好好闻%d" % i, 0) for i in range(10)])
        R = rs.analyze(notes, days=0, insight=many)
        gap = next(g for g in R["gaps"] if g["aspect"] == "质地与手感")
        self.assertTrue(gap["gap"])
        self.assertTrue(any(h["basis"] == "需求缺口" for h in R["hypotheses"]))
        covered = notes + [note("不油不黏的护手霜%d" % i, 100, "作者%d" % (i + 50), 1000) for i in range(5)]
        R = rs.analyze(covered, days=0, insight=many)
        self.assertFalse(next(g for g in R["gaps"] if g["aspect"] == "质地与手感")["gap"])      # 已经有不少笔记在标题回应，就不算缺口

    def test_likes_only_basis_when_collects_are_missing(self):
        notes = [note("笔记%d" % i, 100 + i, "作者%d" % i, 1000) for i in range(20)]
        self.assertEqual(rs.analyze(notes, days=0)["basis"], "仅点赞")
        full = [note("笔记%d" % i, 100 + i, "作者%d" % i, 1000, 10, 5) for i in range(20)]
        self.assertEqual(rs.analyze(full, days=0)["basis"], "赞 + 2×藏 + 3×评")

    def test_price_and_spec_points_are_not_cut_into_other_prices(self):
        terms = rs.selling_terms(["39 元 50g", "一杯4.5元", "45小时续航", "一杯不到4块", "不黏键盘"])
        self.assertEqual(terms["39元50g"], ["39元50g"])                       # 「9元50」会把 19 元、99 元也算成撞卖点
        self.assertEqual(terms["一杯4.5元"], ["一杯4.5元"])                    # 小数点不能丢：4.5 元不是 45 元
        self.assertEqual(terms["45小时续航"], ["45小时续航", "45小时", "小时续航"])
        self.assertEqual(terms["一杯不到4块"], ["一杯不到4块", "一杯不到", "杯不到4", "不到4块"])
        notes = [note("99元50g的大牌护手霜值不值", 900, "甲", 1000), note("19元50g学生党护手霜", 800, "乙", 1000), note("这支 39 元 50G，够用一冬天", 700, "丙", 1000),
                 note("不粘键盘的护手霜，打字党看", 600, "丁", 1000)]
        notes += [note("护手霜推荐第%d篇" % i, 100, "作者%d" % i, 1000) for i in range(20)]
        R = rs.analyze(notes, days=0, selling=terms)
        by = {s["selling_point"]: s for s in R["same_selling_point"]}
        self.assertEqual([n["title"] for n in by["39元50g"]["top"]], ["这支 39 元 50G，够用一冬天"])      # 不管空格和大小写，但别的价格不算
        self.assertEqual((by["不黏键盘"]["notes"], by["不黏键盘"]["in_title"]), (1, 1))                  # 「黏」「粘」两种写法是同一个卖点
        md = rs.to_markdown(R, "护手霜")
        self.assertIn("查的说法：「39元50g」）", md)
        self.assertIn("查的说法：「45小时续航」，以及原文的 2 个片段）", md)

    def test_keywords_come_from_the_profile(self):
        self.assertIn("还不知道品类", self.refused("research.py", "keywords"))
        self.ok("launch_log.py", "init", "--product", "白茶护手霜", "--category", "护手霜", "--audience", "每天敲键盘的打工人", "--selling-points", "39元50g,不黏键盘")
        out = self.ok("research.py", "keywords")
        self.assertIn("品类、卖点、人群取自产品档案", out)
        self.assertIn("护手霜 不黏键盘", out)
        self.assertIn("打工人 护手霜", out)                                    # 人群描述太长时只取人群词
        both = out + self.ok("research.py", "keywords", "--full")
        self.assertNotRegex(both, r"(?m)^\d+\. .*39元")                         # 只有价格和规格的卖点搜不出同类笔记
        self.assertIn("卖点「39元50g」只有价格或规格，搜不出同类笔记，没有拿来搜", out)   # 并且说出来，不是悄悄丢掉
        self.assertIn("咖啡液 3秒冷萃", self.ok("research.py", "keywords", "--category", "咖啡液", "--selling-points", "59元20条,3秒冷萃"))      # 命令行写了就用命令行的
        self.assertNotIn("取自产品档案", self.ok("research.py", "keywords", "--category", "咖啡液", "--selling-points", "3秒冷萃", "--audience", "打工人"))

    def test_labeled_titles_get_their_angle(self):
        cases, wrong = 0, []
        with open(os.path.join(FIX, "labeled_titles.txt"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                title, want = [x.strip() for x in line.rsplit("|", 1)]
                got = rs.angle_of(title)
                cases += 1
                if (got == want[1:]) if want.startswith("!") else (got != want):
                    wrong.append("%s：应为 %s，实际 %s" % (title, want, got))
        self.assertGreater(cases, 60)
        self.assertEqual(wrong, [])

    def test_angle_words_in_the_body_only_count_when_unambiguous(self):
        self.assertEqual(rs.angle_of("白茶护手霜", "这次写一篇保姆级教程，手把手教你"), "教程攻略")
        self.assertEqual(rs.angle_of("白茶护手霜", "我的同事推荐给我的，用了两周，终于不干了"), "其他")     # 「我的」「推荐」「用了」在正文里太常见
        self.assertEqual(rs.angle_of("护手霜征集｜说说你的小方法", ""), "征集互动")                        # 「征集」是明确的说法，「方法」不太确定：明确的优先
        self.assertEqual(set(a[0] for a in rs.ANGLES) - set(cp.T), {"单品种草"})                           # 其余角度都有同名模板
        self.assertEqual(cp.pick_template("单品种草", None, "互动", False)[0], "发布体")

    def test_title_hooks_read_what_the_title_means(self):
        hook = dict(rs.HOOKS)
        on = lambda name, title: bool(re.search(hook[name], title))
        for title in ("护手霜怎么选", "这支到底值不值", "学生党买哪支", "30块的护手霜好用吗", "为什么越涂越干"):
            self.assertTrue(on("疑问句", title), title)
        for title in ("哪怕再贵也要回购", "没什么用的护手霜别买", "动不动就干裂的手有救了", "时不时涂一下"):
            self.assertFalse(on("疑问句", title), title)
        for title in ("护手霜避雷清单", "护手霜红黑榜", "踩雷了，这支别买", "买完就后悔的3支", "不推荐这几支"):
            self.assertTrue(on("负面/避雷", title), title)
        for title in ("平价不踩雷的护手霜", "闭眼入不会踩雷", "后悔没早买的护手霜", "再也不怕踩坑"):
            self.assertFalse(on("负面/避雷", title), title)
        for title in ("打工人护手霜", "学生党平价清单", "敏感肌也能用", "干皮救星", "程序员的桌面好物", "每天敲键盘的人看过来"):
            self.assertTrue(on("点名人群", title), title)
        for title in ("护手霜里的人气单品", "护手霜推荐"):
            self.assertFalse(on("点名人群", title), title)

    def test_multipliers_without_fan_counts_are_leads(self):
        # 手动搜回来的卡片没有粉丝数，笔记又分散在很多账号：倍数分不清是写法还是账号的功劳，只当线索
        notes = [note("这支太绝了！第%s篇" % "一二三四五六七八九十"[i], 5000 + i, "甲%d" % i) for i in range(10)]
        notes += [note("护手霜笔记%s" % "abcdefghijklmno"[i], 100 + i, "乙%d" % i) for i in range(15)]
        R = rs.analyze(notes, days=0)
        hook = next(h for h in R["hooks"] if h["hook"] == "感叹号")
        self.assertGreater(hook["lift"], 10)
        self.assertFalse(hook["solid"])
        self.assertEqual(R["hypotheses"], [])
        self.assertTrue(any("粉丝数不全" in w for w in R["no_hypothesis_reasons"]), R["no_hypothesis_reasons"])
        lead = next(x for x in R["leads"] if x["basis"] == "标题钩子")
        self.assertIn("粉丝数不全", lead["short_of"])
        md = rs.to_markdown(R, "护手霜")
        self.assertRegex(md, r"\| 感叹号 \| 10 \| 40% \| [\d.]+ 倍（线索） \| 10 \| — \|  \|")
        self.assertIn("**线索候选**", md)
        self.assertIn("还差什么：粉丝数不全", md)
        with_fans = rs.analyze([dict(n, followers=1000) for n in notes], days=0)       # 同样的笔记，有粉丝数就是正式候选
        self.assertTrue(any(h["basis"] == "标题钩子" for h in with_fans["hypotheses"]))
        self.assertEqual(with_fans["leads"], [])
        self.assertNotIn("（线索）", rs.to_markdown(with_fans, "护手霜"))
        self.assertIn("能按账号大小校正的篇数", rs.to_markdown(with_fans, "护手霜"))
        self.assertIn("「可比篇数」是有互动数据的篇数，倍数用它们算。这一批的倍数没有按账号大小校正。", md)

    def test_both_shortfalls_are_named_at_once(self):
        # 篇数不够、粉丝数也没有：两样一起说。只说篇数的话，用户补到 20 篇才发现倍数还是线索，白跑一趟
        notes = [note("这支太绝了！第%s篇" % "一二三四五六七八九十"[i], 5000 + i, "甲%d" % i) for i in range(8)]
        notes += [note("护手霜笔记%s" % "abcdefghijklmno"[i], 100 + i, "乙%d" % i) for i in range(10)]
        R = rs.analyze(notes, days=0)
        self.assertEqual(R["hypotheses"], [])
        self.assertEqual(R["no_hypothesis_reasons"], [
            "没有评论数据，无法判断需求缺口。",
            "有互动数据的笔记只有 18 篇，不到 20 篇：角度、钩子、形式的比较不出假设。",
            "粉丝数也不全：就算补够篇数，倍数没法按账号大小校正，角度、钩子、形式的比较仍然只当线索。"])
        lead = next(x for x in R["leads"] if x["basis"] == "标题钩子")
        self.assertEqual(lead["short_of"], "有互动数据的笔记只有 18 篇，不到 20 篇；粉丝数不全，分不清是写法的功劳还是账号大")
        with_fans = rs.analyze([dict(n, followers=1000) for n in notes], days=0)       # 有粉丝数时只差篇数
        lead = next(x for x in with_fans["leads"] if x["basis"] == "标题钩子")
        self.assertEqual(lead["short_of"], "有互动数据的笔记只有 18 篇，不到 20 篇")
        self.assertFalse(any("粉丝数" in w for w in with_fans["no_hypothesis_reasons"]))

    def test_leads_say_what_is_missing(self):
        notes = [note("护手霜合集推荐%d" % i, 100 + i, "作者%d" % i) for i in range(18)]
        few = ci.analyse([("太油了%d" % i, 0) for i in range(5)] + [("味道好好闻%d" % i, 0) for i in range(14)])       # 19 条，差 1 条
        R = rs.analyze(notes, days=0, insight=few)
        self.assertEqual(R["hypotheses"], [])
        lead = R["leads"][0]
        self.assertEqual((lead["basis"], lead["metric"]), ("需求缺口", "评论率"))
        self.assertIn("「质地与手感」", lead["hypothesis"])
        self.assertEqual(lead["evidence"], "19 条评论里有 5 条在吐槽或追问它，18 篇笔记里只有 0 篇在标题回应")
        self.assertEqual(lead["short_of"], "评论只有 19 条，不到 20 条")
        md = rs.to_markdown(R, "护手霜")
        self.assertIn("数据没有给出达到标准的假设", md)
        self.assertIn("1. **需求缺口（线索）**", md)
        self.assertIn("缺口（线索）", md)
        # 读者最在意的点已经有不少笔记在写：不是缺口，照实说，仍然可以当线索
        covered = notes + [note("不油不黏的护手霜%d" % i, 100, "作者%d" % (i + 50)) for i in range(5)]
        R = rs.analyze(covered, days=0, insight=few)
        lead = R["leads"][0]
        self.assertEqual(lead["basis"], "最受关注的点")
        self.assertIn("不是缺口：已经有 5 篇笔记在标题回应", lead["short_of"])

    def test_first_post_is_told_it_has_nothing_to_compare_with(self):
        self.init()
        self.ok("research.py", "add", os.path.join(EX, "sample_notes.json"))
        out = self.ok("research.py", "analyze", "--days", "0")
        self.assertIn("还没有一篇有数据的发布可以比", out)
        self.assertIn("发布后的结论先记「证据不足」", out)
        self.assertRegex(out, r"`python3 \S+launch_log\.py add --title \"那一篇的标题\" --baseline --published 发布日期`")
        self.baseline()
        self.assertNotIn("还没有一篇有数据的发布可以比", self.ok("research.py", "analyze", "--days", "0"))

    def test_keywords_say_what_was_left_out(self):
        out = self.ok("research.py", "keywords", "--category", "香薰蜡烛", "--selling-points", "雨后森林的味道不甜腻,燃烧没有黑烟,大豆蜡", "--audience", "租房独居的上班族",
                      "--pains", "黑烟,太甜腻,烧出坑,贵", "--competitors", "观夏,野兽派")
        terms = re.findall(r"(?m)^\d+\. (.+)$", out)
        self.assertEqual(terms[:4], ["香薰蜡烛 推荐", "香薰蜡烛 测评", "香薰蜡烛 避雷", "香薰蜡烛 雨后森林"])       # 长卖点只取核心的几个字
        for term in ("香薰蜡烛 燃烧没有黑烟", "香薰蜡烛 烧出坑", "上班族 香薰蜡烛", "租房 香薰蜡烛", "观夏 测评"):
            self.assertIn(term, terms)                                    # 第二条卖点、第三个痛点、更细的人群词都排得进去
        self.assertIn("没有排进去的：卖点「大豆蜡」；痛点「贵」；人群「独居」；竞品「野兽派」", out)       # 排不进去的说出来，不悄悄丢掉
        self.assertNotIn("提示：补充", out)

    def test_keywords_use_optional_facts_from_the_profile(self):
        self.ok("launch_log.py", "init", "--product", "白茶护手霜", "--category", "护手霜", "--audience", "敲键盘的打工人", "--selling-points", "不黏键盘", "--goal", "互动",
                "--fact", "常见吐槽=油,黏", "--fact", "竞品=欧舒丹")
        out = self.ok("research.py", "keywords")
        self.assertIn("品类、卖点、人群、痛点、竞品取自产品档案", out)
        for term in ("护手霜 油", "护手霜 黏", "欧舒丹 测评"):
            self.assertIn(term, out)
        self.ok("launch_log.py", "fact", "竞品=无")                      # 用户说不知道竞品：不拿「无」去搜
        self.assertNotIn("无 测评", self.ok("research.py", "keywords"))

    def test_add_points_to_the_comments_step_until_it_is_done(self):
        self.init()
        hint = 'comment_insight.py 评论文件 --research --author "作者昵称"'
        first = self.ok("research.py", "add", os.path.join(EX, "sample_search_paste.txt"))
        self.assertIn("笔记还差 12 篇到 20 篇", first)
        self.assertIn(hint, first)
        self.ok("comment_insight.py", os.path.join(EX, "sample_comments_paste.txt"), "--research", "--author", "示例作者")
        second = self.ok("research.py", "add", os.path.join(EX, "sample_notes.json"))
        self.assertNotIn(hint, second)
        self.assertNotIn("笔记还差", second)
        self.assertIn("research.py analyze", second)

    def test_light_keywords_by_default(self):
        out = self.ok("research.py", "keywords", "--category", "护手霜", "--selling-points", "不黏键盘", "--audience", "打工人", "--pains", "油,黏")
        n = len(re.findall(r"^\d+\. ", out, re.M))
        self.assertTrue(4 <= n <= 8, out)
        self.assertIn("## 必搜（4 个）", out)
        self.assertIn("必搜的 4 个词，每个看「综合」排序的前 8 篇，一共 30 篇左右，最少 20 篇", out)      # 工作量只有一个说法，而且算得上
        self.assertIn("手机 App：搜索结果页一般选不了字，截图发过来", out)
        self.assertIn("没有粉丝数，所以认不出低粉爆款", out)                  # 手动搜回来的数据能看出什么、看不出什么，事先说清
        self.assertIn(os.path.join(self.work, "xhs_launch", "inbox"), out)    # 粘贴的内容由助手存成文件，放在哪也说了
        self.assertIn("还要评论", out)
        full = self.ok("research.py", "keywords", "--category", "护手霜", "--selling-points", "不黏键盘", "--audience", "打工人", "--pains", "油,黏", "--full")
        self.assertGreater(len(re.findall(r"^\d+\. ", full, re.M)), n)


# ---------- 5. 结论的门槛 ----------

class Verdicts(Work):
    def test_init_takes_all_facts_in_one_go(self):
        out = self.init()
        self.assertNotIn("还需要这些事实", out)
        status = self.ok("launch_log.py", "status")
        self.assertIn("互动（主指标：评论率）", status)
        self.assertNotIn("还缺", status)
        self.assertEqual(self.data("launch_log.json")["product"]["facts"]["价格"], "39 元 50g")

    def test_missing_facts_are_listed_once(self):
        out = self.ok("launch_log.py", "init", "--product", "白茶护手霜", "--category", "护手霜")
        for k in ll.FACTS:
            self.assertIn("- %s：" % k, out)
        self.assertIn("还没定发布目标", out)
        self.assertIn("写笔记需要的事实已齐", self.ok("launch_log.py", "fact", *["%s=有" % k for k in ll.FACTS]))

    def test_hypothesis_or_baseline_is_required(self):
        self.init()
        self.assertIn("--baseline", self.refused("launch_log.py", "add", "--title", "随手发的"))
        self.assertIn("--baseline", self.refused("launch_log.py", "add", "--title", "随手发的", "--hypothesis", "待定"))
        self.assertIn("只能选一个", self.refused("launch_log.py", "add", "--title", "x", "--baseline", "--hypothesis", "评论率更高"))
        self.assertIn("基线，没有假设", self.ok("launch_log.py", "add", "--title", "以前发的开箱", "--baseline"))

    def test_baseline_only_takes_the_baseline_result(self):
        self.init()
        lid = self.baseline()
        self.assertIn("是基线", self.refused("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "x"))
        self.ok("launch_log.py", "verdict", "--id", lid, "--result", "基线", "--learning", "评论率 1.3%")
        l2 = self.launch()
        self.assertIn("带了假设", self.refused("launch_log.py", "verdict", "--id", l2, "--result", "基线", "--learning", "x"))

    def test_low_impressions_refused(self):
        self.init()
        self.baseline()
        lid = self.launch()
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 600, "--views", 90, "--likes", 9, "--collects", 3, "--comments", 30)
        out = self.refused("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "x")
        self.assertIn("曝光 600，不到 1000", out)
        self.assertIn("证据不足", out)
        self.assertIsNone(self.data("launch_log.json")["launches"][1]["verdict"])
        self.ok("launch_log.py", "verdict", "--id", lid, "--result", "证据不足", "--learning", "曝光还不到 1000")

    def test_few_comments_refused_for_interaction_goal(self):
        self.init()
        self.baseline()
        lid = self.launch()
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 9000, "--views", 1200, "--likes", 80, "--collects", 30, "--comments", 12)
        self.assertIn("评论 12 条，不到 20 条", self.refused("launch_log.py", "verdict", "--id", lid, "--result", "不成立", "--learning", "x"))
        self.ok("comment_insight.py", self.comments_file(10), "--id", lid)
        self.assertIn("有效评论 10 条，不到 20 条", self.refused("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "x"))

    def test_no_comparison_refused_then_baseline_unlocks(self):
        self.init()
        lid = self.launch()
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 9000, "--views", 1200, "--likes", 80, "--collects", 30, "--comments", 40)
        self.ok("comment_insight.py", self.comments_file(24), "--id", lid)
        out = self.refused("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "x")
        self.assertIn("没有另一篇有数据的发布可以对比", out)
        self.assertIn("add --baseline", out)
        self.baseline()                                          # 后补登记的旧笔记也能当对照
        out = self.ok("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "痛点开头评论率 3.3%")
        self.assertIn("对比 L2", out)

    def test_main_metric_must_exist_on_both_sides(self):
        self.init()
        base = self.ok("launch_log.py", "add", "--title", "旧笔记", "--baseline")
        self.ok("launch_log.py", "metrics", "--id", "L1", "--likes", 40, "--comments", 8)          # 基线没有观看数，算不出评论率
        lid = self.launch()
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 9000, "--views", 1200, "--likes", 80, "--collects", 30, "--comments", 40)
        self.ok("comment_insight.py", self.comments_file(24), "--id", lid)
        self.assertIn("主指标「评论率」在 L1 上算不出来", self.refused("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "x"))
        self.assertTrue(base)

    def test_unverified_parse_warning_blocks_until_checked(self):
        self.init()
        self.baseline()
        lid = self.launch()
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 9000, "--views", 1200, "--likes", 80, "--collects", 30, "--comments", 40)
        messy = self.write("messy.txt", "".join("小熊%d\n第%d条：太油了，摸鼠标都打滑\n11-%02d 上海\n赞 %d\n回复\n" % (i, i, i, i) for i in range(1, 25))
                           + "最后一条复制的时候被截断了\n")             # 24 条完整的评论，末尾多出半条
        raw, info = ci.read_comments(messy)
        self.assertEqual(len(raw), 24)
        self.assertIn("末尾有 1 行后面没有时间行", info["warnings"][0])
        out = self.ok("comment_insight.py", messy, "--id", lid)
        self.assertIn("--checked", out)
        self.assertIn("评论解析有疑点", self.refused("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "x"))
        self.ok("comment_insight.py", messy, "--id", lid, "--checked")
        self.ok("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "评论率更高")

    def test_collect_goal_needs_likes_not_comments(self):
        self.init(goal="收藏")
        self.baseline()
        lid = self.launch()
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 9000, "--views", 1200, "--likes", 12, "--collects", 30, "--comments", 2)
        self.assertIn("点赞 12 个，不到 20 个", self.refused("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "x"))
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 9000, "--views", 1200, "--likes", 60, "--collects", 90, "--comments", 2)
        out = self.ok("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "教程体收藏点赞比 1.5")
        self.assertIn("收藏点赞比", out)

    def test_reach_goal_has_no_comment_gate(self):
        self.init(goal="触达")
        self.baseline()
        lid = self.launch()
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 9000, "--views", 1500, "--likes", 60, "--collects", 9, "--comments", 0)
        self.assertIn("点击率", self.ok("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "新闻式标题点击率 16.7%"))

    def test_force_records_the_reason(self):
        self.init()
        lid = self.launch()
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 600, "--views", 90, "--likes", 9, "--comments", 3)
        out = self.ok("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "私信里有 40 人问价格", "--force", "私信反馈 40 条")
        self.assertIn("强制登记", out)
        v = self.data("launch_log.json")["launches"][0]["verdict"]
        self.assertEqual(v["forced"], "私信反馈 40 条")
        self.assertTrue(v["unmet"])
        self.assertIn("证据未达标，强制登记", self.ok("launch_log.py", "next"))
        self.assertIn("强制登记的理由：私信反馈 40 条", self.ok("launch_log.py", "report"))

    def test_partial_metrics_are_accepted_and_explained(self):
        self.init()
        lid = self.launch()
        out = self.ok("launch_log.py", "metrics", "--id", lid, "--likes", 50, "--collects", 20)
        self.assertIn("没有观看数", out)
        self.assertIn("| 点击率 | 未知 |", out)
        self.assertIn("没有收到任何数字", self.refused("launch_log.py", "metrics", "--id", lid))

    def test_metrics_compare_with_the_previous_launch(self):
        self.init()
        self.baseline(views=600, comments=6)
        lid = self.launch()
        out = self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 9000, "--views", 1200, "--likes", 80, "--collects", 30, "--comments", 36)
        self.assertRegex(out, r"对比 L1：评论率 1\.0% → 3\.0%（\+200%），这是这一篇的主指标")

    def test_verdict_that_contradicts_the_numbers_gets_a_notice(self):
        self.init()
        self.baseline(views=600, comments=30)                    # 基线评论率 5%
        lid = self.launch()
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 9000, "--views", 1200, "--likes", 80, "--collects", 30, "--comments", 24)   # 2%
        self.ok("comment_insight.py", self.comments_file(24), "--id", lid)
        out = self.ok("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "x")
        self.assertIn("没有高于 L1", out)
        out = self.ok("launch_log.py", "verdict", "--id", lid, "--result", "不成立", "--learning", "痛点开头评论率反而更低")
        self.assertNotIn("注意：", out)

    def test_next_needs_three_complaints_across_launches(self):
        self.init()
        self.baseline()
        lid = self.launch()
        self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 9000, "--views", 1200, "--likes", 80, "--collects", 30, "--comments", 40)
        self.ok("comment_insight.py", self.comments_file(24), "--id", lid)
        self.ok("launch_log.py", "verdict", "--id", lid, "--result", "成立", "--learning", "痛点开头评论率 3.3%")
        out = self.ok("launch_log.py", "next")
        self.assertRegex(out, r"\*\*质地与手感\*\*：吐槽 \d+ 条，疑问 \d+ 条（痛点）")
        self.assertIn("累计有效评论 24 条（%s 24 条）" % lid, out)
        self.assertIn("登记为下一篇的假设", out)
        self.assertIn("先看原话是不是同一个问题", out)
        self.assertIn("一次只改一个变量", out)
        self.assertIn("## 基线", out)

    def test_complaints_are_a_lead_until_three_of_them_and_twenty_comments(self):
        self.init()
        a = self.launch()
        self.ok("comment_insight.py", self.write("few.txt", "太油了，摸鼠标都打滑\n涂完打字黏键盘真的烦\n油不油啊\n多少钱一支\n味道好好闻\n"), "--id", a)
        self.ok("launch_log.py", "verdict", "--id", a, "--result", "证据不足", "--learning", "评论太少")
        out = self.ok("launch_log.py", "next")
        self.assertIn("**质地与手感**：吐槽 2 条，疑问 1 条（线索）", out)
        self.assertIn("还没有哪个维度累计到 3 条吐槽", out)
        self.assertIn("⚠️ 样本不足：累计有效评论不到 20 条", out)
        self.assertNotIn("登记为下一篇的假设", out)
        b = self.launch()
        self.ok("comment_insight.py", self.write("one.txt", "吸收太慢了，要搓半天\n包装好好看\n"), "--id", b)
        self.ok("launch_log.py", "verdict", "--id", b, "--result", "证据不足", "--learning", "评论太少")
        out = self.ok("launch_log.py", "next")
        self.assertIn("**质地与手感**：吐槽 3 条，疑问 1 条（线索）", out)        # 吐槽满 3 条了，但两次一共才 7 条有效评论：还是线索
        self.assertIn("「质地与手感」累计 3 条吐槽，但累计有效评论只有 7 条", out)
        self.assertNotIn("登记为下一篇的假设", out)
        self.assertIn("（%s）" % a, out)                                          # 原话带出处
        report = self.ok("launch_log.py", "report")                              # 导出的报告同样带着样本不足的标记
        self.assertIn("评论：有效 5 条（⚠️ 不到 20 条，评论里的发现只是线索）", report)
        self.assertIn("⚠️ 样本不足：累计有效评论不到 20 条", report)
        c = self.launch()
        self.ok("comment_insight.py", self.write("more.txt", "\n".join("包装好好看，第 %d 次回购" % i for i in range(13)) + "\n"), "--id", c)
        self.ok("launch_log.py", "verdict", "--id", c, "--result", "证据不足", "--learning", "没有可比的")
        out = self.ok("launch_log.py", "next")
        self.assertIn("累计有效评论 20 条", out)
        self.assertIn("**质地与手感**：吐槽 3 条，疑问 1 条（痛点）", out)        # 三次加起来 20 条评论、3 条吐槽：才算痛点
        self.assertIn("「质地与手感」累计 3 条吐槽：先看原话是不是同一个问题", out)
        self.assertNotIn("⚠️ 样本不足", out)


# ---------- 6. 方案检查 ----------

class Plans(Work):
    def new_plan(self, *add, goal="互动", identity="店主", material="产品图 3 张", new=()):
        self.init(goal=goal, identity=identity, material=material)
        out = self.ok("launch_log.py", "add", *(add or ("--title", "打字不黏键盘的护手霜", "--angle", "黏键盘痛点", "--hypothesis", "以黏键盘痛点开头，评论率高于基线")))
        lid = re.search(r"已登记发布 (L\d+)", out).group(1)
        return lid, self.ok("content_plan.py", "new", "--id", lid, *new)

    def fill(self, lid="L1", **over):
        p = self.data("plans", lid + ".json")
        p["titles"] = ["打字不黏键盘？我用了两周", "39元的护手霜值不值", "敲键盘的人怎么选护手霜"]
        for g in p["pages"]:
            g.update(text="第%d页的字" % g["no"], visual="办公桌上一支白色护手霜，旁边是键盘")
            if p["type"] == "视频":
                g.update(voiceover="这一镜说一句话", seconds=5)
        for b in p["body"]:
            b["text"] = "自家小店的护手霜，我自己用了两周，每天涂 3 次。"
        p["body"][-1]["text"] = "你们涂完护手霜多久能打字？评论区说说"
        p["tags"] = ["护手霜", "打工人好物", "办公室好物"]
        p["first_comment"] = "主页店铺可以找到，39 元 50g"
        p["image"].update(subject="白色软管护手霜，50g，哑光管身", palette="奶白、浅绿", real_photo_pages=[1])
        for k, v in over.items():
            p[k] = v
        self.save(p, "plans", lid + ".json")
        return p

    def check(self, lid="L1"):
        code, out = run("content_plan.py", "check", "--id", lid, cwd=self.work)
        return code, out

    def test_complete_plan_passes_and_exports_draft(self):
        lid, out = self.new_plan()
        self.assertIn("产品事实已齐", out)
        self.fill()
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("错误 0", out)
        draft = C.read_text(os.path.join(self.work, "xhs_launch", "plans", "L1_draft.txt"))[0]
        self.assertTrue(draft.startswith("打字不黏键盘？我用了两周\n"))
        self.assertIn("#护手霜 #打工人好物 #办公室好物", draft)
        self.assertEqual(nc.check(draft)["errors"], 0)

    def test_every_command_hint_ends_its_line(self):
        # 提示里的命令要能整行复制：命令后面不接说明文字，要么在行尾，要么包在反引号里
        lid, out = self.new_plan()
        outs = [out, self.ok("launch_log.py", "status"), self.ok("research.py", "keywords"), self.ok("research.py", "add", os.path.join(EX, "sample_notes.json")),
                self.ok("comment_insight.py", os.path.join(EX, "sample_comments.txt"), "--research"), self.ok("research.py", "analyze", "--days", "0")]
        self.fill()
        outs += [self.check()[1], self.ok("content_plan.py", "prompts", "--id", lid),
                 self.ok("launch_log.py", "publish", "--id", lid, "--url", "https://www.xiaohongshu.com/explore/" + NOTE_ID % 1),
                 self.ok("launch_log.py", "metrics", "--id", lid, "--impressions", 5000, "--views", 600, "--likes", 40, "--collects", 20, "--comments", 30),
                 self.ok("comment_insight.py", self.comments_file(), "--id", lid),
                 self.ok("launch_log.py", "verdict", "--id", lid, "--result", "证据不足", "--learning", "样本不够"), self.ok("launch_log.py", "next"),
                 self.ok("guide.py"), self.ok("guide.py", "commands"), self.ok("guide.py", "2"), self.ok("guide.py", "demo"), self.ok("guide.py", "demo", "--full")]
        seen = 0
        for out in outs:
            for line in out.splitlines():
                if line.startswith("$ "):                                   # 演示里回显的命令：整行都是命令
                    continue
                for m in re.finditer(r"python3 \S*?(?:%s)" % "|".join(re.escape(x) for x in ALL_SCRIPTS), line):
                    rest = line[m.end():]
                    if line[:m.start()].count("`") % 2:
                        rest = rest.split("`")[0]
                    self.assertNotRegex(re.sub(r'"[^"]*"', "", rest), "[（），。；：]", line)
                    self.assertNotIn("|", re.sub(r'"[^"]*"', "", rest), line)       # 「触达|互动|收藏」这种写法粘到终端里会被当成管道
                    seen += 1
        self.assertGreater(seen, 30)

    def test_empty_plan_lists_what_is_missing(self):
        self.new_plan()
        code, out = self.check()
        self.assertEqual(code, 1)
        for part in ("标题备选不足 3 个", "没有图上文字", "没有画面描述", "正文「开头钩子」未填写"):
            self.assertIn(part, out)
        self.assertFalse(os.path.exists(os.path.join(self.work, "xhs_launch", "plans", "L1_draft.txt")))
        self.assertIn("先运行 check", self.refused("content_plan.py", "prompts", "--id", "L1"))

    def test_placeholders_anywhere_are_errors(self):
        self.new_plan()
        for field, bad in (("titles", ["待补充", "39元的护手霜值不值", "敲键盘的人怎么选护手霜"]), ("first_comment", "TODO"), ("tags", ["护手霜", "XX", "好物"]),
                           ("first_comment", "店铺名【请填写】"), ("first_comment", "同上"), ("first_comment", "（待用户提供）")):
            self.fill(**{field: bad})
            code, out = self.check()
            self.assertEqual(code, 1, (field, bad, out))
            self.assertIn("占位内容", out)
        p = self.fill()
        p["image"]["subject"] = "待补充"
        self.save(p, "plans", "L1.json")
        self.assertIn("配图设定的主体描述里还有占位内容", self.check()[1])

    def test_ordinary_words_are_not_placeholders(self):
        for text in ("期待补货", "等待确认收货后再评价", "XXL 码也有", "对待用户要真诚", "看待定价的方式", "敬请期待更新"):
            self.assertIsNone(cp.PLACEHOLDER.search(text), text)
        for text in ("待补充", "价格待定", "这里填 XX", "TODO", "tbd", "【请填写价格】", "（待用户提供）", "____", "同上"):
            self.assertIsNotNone(cp.PLACEHOLDER.search(text), text)

    def test_missing_fact_is_an_error_until_answered(self):
        self.ok("launch_log.py", "init", "--product", "白茶护手霜", "--category", "护手霜", "--goal", "互动")
        self.ok("launch_log.py", "add", "--title", "t", "--angle", "痛点", "--hypothesis", "评论率高于基线")
        out = self.ok("content_plan.py", "new", "--id", "L1")
        self.assertIn("一次问清用户", out)
        self.fill()
        self.assertIn("信息缺失「价格」", self.check()[1])
        out = self.ok("launch_log.py", "fact", *["%s=无" % k for k in ll.FACTS])
        self.assertIn("「缺点」不能填「无」", out)                                 # 这两项答「无」不算回答
        self.assertIn("「身份」不能填「无」", out)
        out = self.check()[1]
        self.assertIn("信息缺失「缺点」", out)
        self.assertIn("信息缺失「身份」", out)
        self.assertNotIn("信息缺失「素材」", out)                                 # 别的项，用户明确说没有就是答案
        self.assertIn("不能填「无」", self.refused("launch_log.py", "fact", "缺点=无"))
        self.ok("launch_log.py", "fact", "缺点=香味半小时就散了", "身份=店主")
        self.assertNotIn("信息缺失", self.check()[1])

    def test_second_round_asks_for_everything_at_once(self):
        # 写笔记前的那一轮：缺的事实和写这一篇用得上的外观、语气、固定标签一起问，免得检查没过再回头问
        self.ok("launch_log.py", "init", "--product", "白茶护手霜", "--category", "护手霜", "--goal", "互动", "--price", "39 元 50g", "--identity", "店主")
        self.ok("launch_log.py", "add", "--title", "t", "--angle", "痛点", "--hypothesis", "评论率高于基线")
        out = self.ok("content_plan.py", "new", "--id", "L1")
        self.assertIn("上面打了空格 [ ] 的 5 项信息，一次问清用户", out)
        self.assertIn("同一轮里顺带问：产品外观（颜色、形状、材质、包装）、想用的语气、每篇都带的固定标签。", out)
        self.assertIn("填进方案文件的 image.subject、tone、fixed_tags", out)
        self.assertRegex(out, r'launch_log\.py fact 外观="…" 语气="…" 固定标签="…"\n')
        self.ok("launch_log.py", "fact", "外观=白色软管，绿色盖子", "语气=朋友聊天", "固定标签=打工人护手霜", *["%s=有" % k for k in ll.LATER])
        out = self.ok("content_plan.py", "new", "--id", "L1", "--force")
        self.assertNotIn("顺带问", out)                                          # 档案里有了就不再问
        plan = self.data("plans", "L1.json")
        self.assertEqual((plan["image"]["subject"], plan["tone"], plan["fixed_tags"]), ("白色软管，绿色盖子", "朋友聊天", ["打工人护手霜"]))

    def test_facts_in_the_plan_are_written_back_to_the_log(self):
        self.ok("launch_log.py", "init", "--product", "白茶护手霜", "--category", "护手霜", "--goal", "互动")
        self.ok("launch_log.py", "add", "--title", "t", "--angle", "痛点", "--hypothesis", "评论率高于基线")
        self.ok("content_plan.py", "new", "--id", "L1")
        p = self.fill()
        for f in p["facts_needed"]:
            f["value"] = "39 元 50g" if f["key"] == "价格" else "无"
        self.save(p, "plans", "L1.json")
        self.assertIn("已把「价格」写回产品档案", self.check()[1])
        self.assertEqual(self.data("launch_log.json")["product"]["facts"]["价格"], "39 元 50g")
        self.ok("launch_log.py", "fact", "价格=45 元 50g")
        self.assertIn("已按档案为准", self.check()[1])
        self.assertEqual({f["key"]: f["value"] for f in self.data("plans", "L1.json")["facts_needed"]}["价格"], "45 元 50g")

    def test_owner_must_disclose(self):
        self.new_plan(identity="品牌方")
        p = self.fill()
        for b in p["body"][:-1]:
            b["text"] = "用了两周，每天涂 3 次，涂完 1 分钟就能打字。"
        self.save(p, "plans", "L1.json")
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("档案里你的身份是「品牌方」", out)
        p["body"][1]["text"] = "自家产品，团队 5 个人用了两周。"
        self.save(p, "plans", "L1.json")
        self.assertNotIn("你的身份是", self.check()[1])

    def test_paid_content_must_say_so(self):
        self.new_plan(identity="品牌送测的合作")
        p = self.fill()
        for b in p["body"][:-1]:
            b["text"] = "用了两周，每天涂 3 次，涂完 1 分钟就能打字。"
        self.save(p, "plans", "L1.json")
        self.assertIn("报备", self.check()[1])

    def test_ordinary_user_needs_no_disclosure(self):
        self.new_plan(identity="自己买的用户")
        self.fill()
        self.assertNotIn("你的身份是", self.check()[1])

    def test_fixed_tags_are_added_automatically(self):
        self.new_plan()
        self.fill(fixed_tags=["阿七的工位"], tags=["护手霜", "#阿七的工位", "打工人好物"])
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("固定标签 #阿七的工位 已自动加进成稿", out)
        draft = C.read_text(os.path.join(self.work, "xhs_launch", "plans", "L1_draft.txt"))[0]
        self.assertTrue(draft.rstrip().endswith("#阿七的工位 #护手霜 #打工人好物"), draft)
        self.ok("launch_log.py", "add", "--title", "第二篇", "--angle", "教程", "--hypothesis", "教程体收藏点赞比高于 L1")
        self.assertIn("已沿用 L1 的配图设定和固定标签", self.ok("content_plan.py", "new", "--id", "L2"))
        p2 = self.data("plans", "L2.json")
        self.assertEqual((p2["fixed_tags"], p2["image"]["palette"]), (["阿七的工位"], "奶白、浅绿"))

    def test_template_follows_the_angle_and_says_why(self):
        _, out = self.new_plan()
        self.assertIn("模板「发布体」：角度「黏键盘痛点」里有「痛点」", out)
        self.assertIn("发布目标「互动」常用的模板是「征集互动、答疑科普」", out)
        self.assertIn("--force --template 征集互动", out)

    def test_unmatched_angle_falls_back_to_the_general_template(self):
        _, out = self.new_plan("--title", "t", "--angle", "白茶香", "--hypothesis", "评论率高于基线", goal="收藏")
        self.assertIn("模板「发布体」：角度「白茶香」没有对应的模板", out)
        self.assertIn("深度长文", out)
        self.assertEqual([b["section"] for b in self.data("plans", "L1.json")["body"]], [s for s, _ in cp.BODY_DEFAULT])

    def test_announcement_has_its_own_body_sections(self):
        self.new_plan("--title", "拿铁味上线", "--angle", "上线公告", "--hypothesis", "公告式标题点击率高于基线", goal="触达")
        p = self.data("plans", "L1.json")
        self.assertEqual(p["template"], "上线公告")
        self.assertEqual([b["section"] for b in p["body"]], ["开头钩子", "是什么", "怎么参与", "回报与限制", "结尾提问"])
        self.fill()
        self.assertEqual(self.check()[0], 0, self.check()[1])

    def test_every_template_builds_and_passes_when_filled(self):
        self.init()
        for i, name in enumerate(cp.T, 1):
            video = name == "情绪短片"
            self.ok("launch_log.py", "add", "--title", "第%d篇" % i, "--hypothesis", "评论率高于基线", *(["--type", "视频"] if video else []))
            self.ok("content_plan.py", "new", "--id", "L%d" % i, "--template", name)
            p = self.fill("L%d" % i, fixed_tags=[])
            self.assertEqual([b["section"] for b in p["body"]], [s for s, _ in cp.BODY.get(name, cp.BODY_DEFAULT)], name)
            code, out = self.check("L%d" % i)
            self.assertEqual(code, 0, name + "\n" + out)
            self.assertIn("第 1 %s：封面" % p["unit"], self.ok("content_plan.py", "prompts", "--id", "L%d" % i))

    def test_last_section_needs_a_question(self):
        self.new_plan()
        p = self.fill()
        p["body"][-1]["text"] = "评论区见。"
        self.save(p, "plans", "L1.json")
        self.assertIn("里没有问句", self.check()[1])

    def test_length_limits(self):
        self.new_plan()
        p = self.fill(titles=["这是一个明显超过二十个字的标题用来测试长度限制到底管不管用", "39元的护手霜值不值", "敲键盘的人怎么选护手霜"])
        p["pages"][0]["text"] = "封面上的字超过了十二个字的上限"
        p["tags"] = ["标签%d" % i for i in range(11)]
        self.save(p, "plans", "L1.json")
        out = self.check()[1]
        for part in ("标题超过 20 字", "超过 12 字", "超过 10 个"):
            self.assertIn(part, out)

    def test_real_photo_rules(self):
        self.new_plan()
        p = self.fill()
        p["image"]["real_photo_pages"] = []
        self.save(p, "plans", "L1.json")
        self.assertIn("没有一页标为用实拍", self.check()[1])                      # 有实拍素材却全用 AI
        p["image"].update(real_photo_pages=[1], subject="")
        self.save(p, "plans", "L1.json")
        self.assertIn("缺少主体描述", self.check()[1])                           # 让 AI 画产品却没有外观描述
        p["image"].update(real_photo_pages=[1, 9], subject="白色软管护手霜")
        self.save(p, "plans", "L1.json")
        self.assertIn("无效的页码：9", self.check()[1])

    def test_no_material_but_real_pages_flagged(self):
        self.new_plan(material="无")
        self.fill()
        self.assertIn("没有实拍素材", self.check()[1])

    def test_prompts_keep_the_product_real(self):
        self.new_plan()
        self.fill()
        self.assertEqual(self.check()[0], 0)
        out = self.ok("content_plan.py", "prompts", "--id", "L1")
        first = out.split("## 第 2 页")[0]
        self.assertIn("这一篇要准备：实拍 1 张（第 1 页）", first)                 # 开头先说清每一页的图从哪来
        self.assertIn("卡片 1 张（第 6 页）", first)
        self.assertIn("## 第 1 页：封面（实拍）", first)
        self.assertIn("**拍摄要求**：办公桌上一支白色护手霜，旁边是键盘", first)
        back = re.search(r"```\n(只生成场景和背景，不要画出任何产品.*?)\n```", first, re.S).group(1)
        self.assertNotIn("护手霜", back)                                         # 「不要画产品」的提示词里不能又点名产品
        self.assertIn("场景：办公桌上，旁边是键盘", back)
        self.assertEqual(out.count(cp.NEGATIVE), 1)                              # 反向提示词只印一次
        self.assertIn("画面中的产品：白色软管护手霜，50g，哑光管身", out)          # AI 页都用同一句产品描述
        self.assertIn("AI 合成", out)
        self.assertIn("画面中不要出现任何文字", out)
        self.assertIn("“第2页的字”", self.ok("content_plan.py", "prompts", "--id", "L1", "--with-text"))
        self.assertTrue(os.path.exists(os.path.join(self.work, "xhs_launch", "plans", "L1_prompts.md")))

    def test_card_prompt_does_not_ask_for_words_it_forbids(self):
        self.new_plan()
        p = self.fill()
        p["pages"][-1]["visual"] = "浅绿色纯色背景，中间大字写着缺点，下面一行小字写适合谁，右下角一片叶子的简笔画"
        self.save(p, "plans", "L1.json")
        out = self.ok("content_plan.py", "prompts", "--id", "L1")
        card = out.split("## 第 6 页：缺点与适合谁（卡片）")[1]
        base = re.search(r"\*\*底图提示词\*\*.*?```\n(.*?)\n```", card, re.S).group(1)
        self.assertTrue(base.startswith("只生成卡片的底图，不要出现任何文字、数字和字母，浅绿色纯色背景，右下角一片叶子的简笔画"), base)
        for word in ("大字", "小字", "写着", "后期加字"):
            self.assertNotIn(word, base)
        self.assertIn("**图上的字**：第6页的字", card)
        with_text = self.ok("content_plan.py", "prompts", "--id", "L1", "--with-text").split("## 第 6 页")[1]
        self.assertIn("中间大字写着缺点", with_text)                              # 让图里直接出字时，描述原样保留
        self.assertIn("“第6页的字”", with_text)

    def test_numbers_must_come_from_the_user(self):
        self.new_plan()
        p = self.fill()
        p["pages"][2]["text"] = "到手 29 元"                                      # 档案里是 39 元
        p["body"][2]["text"] = "自家小店的护手霜，一支能用 3 个月，持证 12 项。"       # 档案里没说过能用多久；「项」不是脚本认识的单位
        p["first_comment"] = "主页店铺可以找到，老客回购了 4 次"
        self.save(p, "plans", "L1.json")
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("数字没有出处：第 3 页的图上文字写的是「29 元」，用户给过的同类数字是「39元」（档案的卖点）。", out)
        self.assertIn("正文「正文要点」写的是「3 个月」，用户给过的同类数字是「两周」（档案的「使用情况」）", out)
        self.assertIn('launch_log.py fact 事实名="用户的原话"`', out)             # 告诉怎么把新的事实登记进去
        self.assertIn("（错误 2，警告 1）", out)                                   # 怎么登记是提示，不算进错误数
        self.assertIn("- [提示] 用户给了新的事实时这样登记", out)
        self.assertIn("[警告] 这些说法档案里没有：首评里的「4 次」", out)            # 次数、人数是软数字：提醒，不拦
        self.assertNotIn("12 项", out)
        self.assertFalse(os.path.exists(os.path.join(self.work, "xhs_launch", "plans", "L1_draft.txt")))
        self.ok("launch_log.py", "fact", "耐用=一支大概能用 3 个月", "回购=老客最多回购过四次")     # 用户补了事实，数字就有出处了
        p["pages"][2]["text"] = "到手 39 元"
        self.save(p, "plans", "L1.json")
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("错误 0，警告 0", out)

    def test_numbers_that_only_look_different_are_the_same(self):
        self.new_plan()
        p = self.fill()
        p["pages"][1]["text"] = "用了14天"                                        # 档案：两周
        p["pages"][2]["text"] = "涂完60秒能打字"                                  # 档案：1 分钟
        p["pages"][3]["text"] = "¥39 一支"                                        # 档案：39 元
        p["body"][2]["text"] = "自家小店的护手霜，50 克一支，香味 30 分钟就散。"       # 档案：50g、半小时
        self.save(p, "plans", "L1.json")
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("错误 0，警告 0", out)

    def test_banned_words_are_checked_everywhere_a_reader_looks(self):
        self.new_plan()
        for field, where in (("titles", "标题 2"), ("pages", "第 4 页的图上文字"), ("first_comment", "首评")):
            p = self.fill()
            if field == "titles":
                p["titles"][1] = "全网最好用的护手霜？"
            elif field == "pages":
                p["pages"][3]["text"] = "加微信领 4 页试用装"
            else:
                p["first_comment"] = "主页店铺可以找到，根治干裂"
            self.save(p, "plans", "L1.json")
            code, out = self.check()
            self.assertEqual(code, 1, (field, out))
            self.assertIn("[错误] [%s]" % where, out)
        p = self.fill()
        p["type"], p["unit"] = "视频", "镜头"                                      # 视频的口播也要查
        for g in p["pages"]:
            g.update(voiceover="这一镜说一句话", seconds=5)
        p["pages"][2]["voiceover"] = "这是全网第一的护手霜"
        self.save(p, "plans", "L1.json")
        self.assertIn("[错误] [第 3 镜头的口播]", self.check()[1])

    def test_pages_must_say_different_things(self):
        self.new_plan()
        p = self.fill()
        p["pages"][3]["text"] = p["pages"][4]["text"] = "不黏键盘"
        self.save(p, "plans", "L1.json")
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("第 4、5 页的文字一模一样", out)
        self.assertIn("第 4 页（要点一） 的任务是给出数字，但文字里没有数字", out)

    def test_disadvantage_cannot_be_none_in_the_plan(self):
        self.ok("launch_log.py", "init", "--product", "白茶护手霜", "--category", "护手霜", "--goal", "互动")
        self.ok("launch_log.py", "add", "--title", "t", "--angle", "痛点", "--hypothesis", "评论率高于基线")
        self.ok("content_plan.py", "new", "--id", "L1")
        p = self.fill()
        for f in p["facts_needed"]:
            f["value"] = "无" if f["key"] in ("缺点", "素材") else "店主" if f["key"] == "身份" else "用户说的 39 元 50g"
        self.save(p, "plans", "L1.json")
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("信息「缺点」不能填「无」", out)
        self.assertNotIn("信息「素材」不能填", out)
        self.assertNotIn("缺点", self.data("launch_log.json")["product"]["facts"])     # 「无」不写回档案

    def test_package_holds_everything_needed_to_publish(self):
        self.new_plan()
        self.fill()
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("检查过的范围：三个标题、每一页的字、正文、首评、标签", out)
        self.assertIn("L1_package.md", out)
        pack = C.read_text(os.path.join(self.work, "xhs_launch", "plans", "L1_package.md"))[0]
        for part in ("1. 打字不黏键盘？我用了两周", "2. 39元的护手霜值不值", "3. 敲键盘的人怎么选护手霜", "| 1 封面 | 第1页的字 | 实拍 |", "| 2 痛点场景 | 第2页的字 | AI 生成 |",
                     "| 6 缺点与适合谁 | 第6页的字 | 卡片 |", "#护手霜 #打工人好物 #办公室好物", "## 首评\n\n主页店铺可以找到，39 元 50g", "内容含 AI 合成", "launch_log.py publish --id L1"):
            self.assertIn(part, pack)

    def test_fewer_pages_keeps_the_last_one(self):
        _, out = self.new_plan(new=("--pages", "4"))
        self.assertEqual([g["role"] for g in self.data("plans", "L1.json")["pages"]], ["封面", "痛点场景", "这是什么", "缺点与适合谁"])
        self.assertNotIn("这个模板要用户给得出", out)
        self.ok("launch_log.py", "add", "--title", "实测", "--angle", "测评实测", "--hypothesis", "评论率高于 L1")
        out = self.ok("content_plan.py", "new", "--id", "L2")
        self.assertIn("这个模板要用户给得出：3 个测评维度，每个都有用户给的实测结果", out)   # 模板要的东西用户给不出，现在就换

    def test_background_prompt_never_names_the_product(self):
        p = {"product": "Nova Buds 降噪耳机", "category": "蓝牙耳机"}
        for visual, scene in (("办公桌上一支白色护手霜，旁边是键盘", ["办公桌上一支白色护手霜", "旁边是键盘"]),      # 说的不是这个产品，原样保留
                              ("木桌上放着一副白色耳机，窗外是早高峰", ["木桌上", "窗外是早高峰"]),
                              ("手里拿着 nova buds 降噪耳机的充电盒", []),
                              ("产品正面特写，背景是通勤地铁车厢", ["背景是通勤地铁车厢"]),
                              ("地铁车厢里，一个人戴着蓝牙耳机看手机", ["地铁车厢里"])):
            self.assertEqual(cp.scene_only(visual, cp.product_terms(p)), scene, visual)

    def test_video_plan(self):
        self.new_plan("--title", "30 秒看完", "--type", "视频", "--angle", "痛点", "--hypothesis", "视频的观看数高于图文基线")
        p = self.data("plans", "L1.json")
        self.assertEqual((p["unit"], p["image"]["ratio"], p["pages"][0]["seconds"]), ("镜头", "9:16", 3))
        p = self.fill()
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("错误 0，警告 0", out)
        long = "这一镜的口播写得特别长，这么短的时间里根本不可能念完，所以检查的时候应该提醒，把话分到别的镜头或者把这一镜加长"
        p["pages"][1]["voiceover"] = long                        # 只有一镜念不完：提醒，不拦
        self.save(p, "plans", "L1.json")
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("第 2 镜口播 %d 字 / 5 秒，这一镜念不完" % C.xhs_len(long), out)
        for g in p["pages"]:                                     # 全片都念不完：报错
            g["voiceover"] = long
        self.save(p, "plans", "L1.json")
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("语速超过每秒 5 字", out)
        for g in p["pages"]:
            g["voiceover"] = "这一镜说一句话"
        p["pages"][1].update(voiceover="", seconds="5秒")          # 秒数写成「5秒」也认
        p["pages"][2]["seconds"] = ""
        self.save(p, "plans", "L1.json")
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("第 2 镜头（%s） 没有口播" % p["pages"][1]["role"], out)
        self.assertIn("第 3 镜没有写秒数", out)
        self.assertNotIn("第 2、3 镜没有写秒数", out)

    def test_short_emotional_video_is_checked_differently(self):
        self.new_plan("--title", "下班后点一支", "--type", "视频", "--angle", "治愈短片", "--hypothesis", "短片的观看数高于图文基线", goal="触达")
        p = self.data("plans", "L1.json")
        self.assertEqual((p["template"], [b["section"] for b in p["body"]]), ("情绪短片", ["一句话", "结尾提问"]))
        p = self.fill()
        p["pages"][0]["voiceover"] = ""                          # 全片只说一句话
        p["body"][0]["text"] = "自家小店做的，下班后涂一点，我自己用了两周。"
        self.save(p, "plans", "L1.json")
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertNotIn("偏短", out)
        for g in p["pages"]:
            g["voiceover"] = ""
        p["pages"][1]["seconds"] = 20
        self.save(p, "plans", "L1.json")
        out = self.check()[1]
        self.assertIn("每个镜头的口播都是空的", out)
        self.assertIn("6 到 15 秒", out)
        self.assertIn("是视频模板", run("content_plan.py", "new", "--id", "L1", "--force", "--template", "情绪短片", cwd=self.init_other())[1])

    def init_other(self):
        d = tempfile.mkdtemp(prefix="xhs_other_")
        self.addCleanup(shutil.rmtree, d, True)
        run("launch_log.py", "init", "--product", "p", "--category", "c", cwd=d)
        run("launch_log.py", "add", "--title", "t", "--hypothesis", "评论率高于基线", cwd=d)
        return d

    def test_research_findings_reach_the_plan(self):
        self.init()
        self.ok("research.py", "add", os.path.join(EX, "sample_notes.json"), os.path.join(EX, "sample_search_paste.txt"))
        self.ok("comment_insight.py", os.path.join(EX, "sample_comments.txt"), "--research")
        self.ok("research.py", "analyze", "--days", "0")
        self.ok("launch_log.py", "add", "--title", "t", "--angle", "价格痛点", "--hypothesis", "评论率高于基线")
        out = self.ok("content_plan.py", "new", "--id", "L1")
        self.assertIn("## 来自调研（32 篇笔记，24 条评论）", out)
        self.assertIn("建议用「含数字」", out)
        self.assertRegex(out, r"用户原话：“")

    def test_sample_plan_is_fresh_and_passes(self):
        p = subprocess.run([sys.executable, "-B", os.path.join(HERE, "regen_sample_plan.py"), "--check"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(p.returncode, 0, p.stdout.decode("utf-8", "replace"))
        sample = C.read_json(os.path.join(EX, "sample_plan.json"))
        self.assertEqual(cp.check_plan(cp_defaults(sample)), ([], []))


def cp_defaults(p):
    """补上 load_plan 会补的默认值，让 check_plan 可以直接吃一个 dict。"""
    p = json.loads(json.dumps(p))
    p.setdefault("fixed_tags", [])
    p.setdefault("unit", "页")
    return p


# ---------- 7. 合规词表 ----------

class Compliance(Work):
    # 一篇挑不出毛病的草稿：把要测的说法放进 %s，查出来的问题就只可能来自那个说法
    GOOD = ("用了 7 天，说说真实感受。\n每天涂 3 次，涂完 1 分钟就能打字，39 元 50g 一支能用一个多月。\n香味半小时就散了，适合不喜欢香味的人。%s\n"
            "管口容易挤多，每次按半泵就够，我一开始总是挤多了浪费。\n你涂完护手霜多久能打字？")

    def issues(self, body, title="打工人实测一周护手霜", extra=()):
        r = nc.check("%s\n%s\n#护手霜 #打工人 #好物" % (title, body), extra)
        return {(i["level"], i["item"]) for i in r["issues"]}, r

    def said(self, phrase):
        return self.issues(self.GOOD % phrase)

    def test_clean_draft_has_no_issues(self):
        got, r = self.said("")
        self.assertEqual(got, set(), r["issues"])
        self.assertTrue(r["passed"])

    def test_words_the_report_asked_for(self):
        errors = {"百分百有效": "极限词", "全网最低价": "极限词", "全网最香": "极限词", "最好用的护手霜": "极限词", "销量第一": "极限词", "行业第一品牌": "极限词",
                  "某宝同款": "站外导流", "闲鱼出": "站外导流", "加我vx": "站外导流", "tb搜同款": "站外导流", "根治手干": "功效承诺", "可以治愈湿疹": "功效承诺"}
        for word, cat in errors.items():
            got, r = self.said(word)
            self.assertEqual(got, {("错误", cat)}, (word, r["issues"]))
        warnings = {"抖音上也有": "站外提及", "再也不干了": "绝对化承诺", "闭眼入": "夸大表述", "美白效果": "功效宣称"}
        for word, cat in warnings.items():
            got, r = self.said(word)
            self.assertEqual(got, {("警告", cat)}, (word, r["issues"]))
            self.assertTrue(r["passed"])

    def test_normal_phrases_are_not_flagged(self):
        for phrase in ("第一次用这个牌子", "第一下要轻一点", "第一泵挤出来是水", "唯一的缺点是香味淡", "不是最好的但够用", "100%棉的手套", "点上之后很治愈", "治愈系的味道",
                       "最好别空腹喝", "加VC的那款"):
            got, r = self.said(phrase)
            self.assertEqual(got, set(), (phrase, r["issues"]))

    def test_contact_details_and_links(self):
        for body in ("联系 13800138000 下单", "详情见 https://example.com/x", "官网 www.example.com"):
            got, r = self.issues("用了 7 天。%s。你们觉得呢？" % body)
            self.assertIn(("错误", "站外导流"), got, r["issues"])

    def test_structure_warnings(self):
        got, _ = self.issues("这个产品挺好的，推荐给需要的人，真的很不错，值得入手，用起来很舒服，朋友们可以试试看，我自己也很喜欢它，包装和质地都让人满意。")
        self.assertIn(("警告", "互动引导"), got)
        self.assertIn(("警告", "真实感"), got)
        got, _ = self.issues("用了 7 天，每天涂 3 次，涂完 1 分钟就能打字，39 元 50g 一支能用一个多月，香味半小时就散了，适合不喜欢香味的人。你涂完护手霜多久能打字？")
        self.assertEqual(got, {("警告", "开头"), ("警告", "正文")})   # 一整段、不到 80 字：提醒开头太长、正文偏短；结尾是问句，不再提醒互动引导
        self.assertEqual(self.said("")[0], set())

    def test_limits(self):
        r = nc.check("这是一个明显超过二十个字的标题用来测试长度限制到底管不管用\n正文\n" + " ".join("#标签%d" % i for i in range(11)))
        items = {i["item"] for i in r["issues"] if i["level"] == "错误"}
        self.assertEqual(items, {"标题", "标签"})
        self.assertFalse(nc.check("")["passed"])
        self.assertEqual(C.xhs_len("abcd中文"), 4)

    def test_draft_cli_and_exit_code(self):
        self.assertIn("通过，可以发布", self.ok("note_check.py", os.path.join(EX, "sample_draft.txt")))
        bad = self.write("bad.txt", "全网最好用的护手霜\n用了 7 天，加我微信下单。你们觉得呢？\n#护手霜 #好物 #打工人\n")
        out = self.refused("note_check.py", bad)
        self.assertIn("[错误][极限词]", out)
        self.assertIn("[错误][站外导流]", out)
        code, js = run("note_check.py", bad, "--json", cwd=self.work)
        self.assertFalse(json.loads(js)["passed"])

    def test_project_word_list(self):
        doc = C.read_text(os.path.join(ROOT, "references", "compliance.md"))[0]
        block = re.search(r"```\n(错误\|.*?)\n```", doc, re.S).group(1)
        self.write("xhs_launch/banned_words.txt", block + "\n")
        draft = self.write("d.txt", "吃了两周的记录\n吃了 14 天，说能降血糖，还能增强免疫力。你们吃过吗？\n#保健 #记录 #日常\n")
        out = self.refused("note_check.py", draft)
        self.assertIn("降血糖", out)
        self.assertIn("增强免疫力", out)
        self.assertEqual(run("note_check.py", draft, "--dir", "elsewhere", cwd=self.work)[0], 0)      # 另一个产品目录不受影响
        extra = self.write("more.txt", "错误|行业|吃了|测试用\n")
        self.assertIn("测试用", run("note_check.py", draft, "--dir", "elsewhere", "--words", extra, cwd=self.work)[1])

    def test_word_list_is_well_formed(self):
        seen = set()
        for no, line in enumerate(C.read_text(os.path.join(ROOT, "assets", "banned_words.txt"))[0].split("\n"), 1):
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("|")
            self.assertGreaterEqual(len(parts), 3, "第 %d 行：%s" % (no, line))
            self.assertIn(parts[0], ("错误", "警告"), line)
            self.assertNotIn(parts[2].lower(), seen, "重复的词：" + parts[2])
            seen.add(parts[2].lower())


# ---------- 8. 文档和脚本一致 ----------

def imported_modules(src):
    """源码里 import 的所有顶层模块名（函数里面的 import 也算）。"""
    tops = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            tops.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            tops.add(node.module.split(".")[0])
    return sorted(tops)


def is_stdlib(top):
    names = getattr(sys, "stdlib_module_names", None)           # Python 3.10 起才有
    if names is not None:
        return top in names
    if top in sys.builtin_module_names:
        return True
    origin = getattr(importlib.util.find_spec(top), "origin", None) or ""
    return origin in ("built-in", "frozen") or (origin.startswith(sysconfig.get_paths()["stdlib"]) and "site-packages" not in origin)


def subcommands(parser):
    for a in parser._actions:
        if a.__class__.__name__ == "_SubParsersAction":
            return a.choices
    return {}


def options(parser):
    out = set()
    for a in parser._actions:
        out.update(o for o in a.option_strings if o.startswith("--"))
    for sub in subcommands(parser).values():
        out |= options(sub)
    return out


PARSERS = {"launch_log.py": ll.build_parser, "research.py": rs.build_parser, "comment_insight.py": ci.build_parser,
           "content_plan.py": cp.build_parser, "note_check.py": nc.build_parser, "guide.py": guide.build_parser}


class Docs(unittest.TestCase):
    def docs(self):
        files = [os.path.join(ROOT, "SKILL.md")] + sorted(os.path.join(ROOT, "references", f) for f in os.listdir(os.path.join(ROOT, "references")))
        return [(os.path.relpath(f, ROOT), C.read_text(f)[0]) for f in files]

    def test_commands_in_docs_exist(self):
        checked = 0
        for name, text in self.docs():
            for code in re.findall(r"`([^`\n]+)`", text) + re.findall(r"```[a-z]*\n(.*?)```", text, re.S):
                for line in code.split("\n"):
                    for m in re.finditer(r"([a-z_]+\.py)((?:\s+[^\s`|→]+)*)", line):
                        script, rest = m.group(1), m.group(2).split()
                        if script not in PARSERS:
                            continue
                        parser = PARSERS[script]()
                        subs = subcommands(parser)
                        known = options(parser)
                        if subs and rest and re.fullmatch(r"[a-z]+", rest[0]):
                            self.assertIn(rest[0], subs, "%s：%s 没有子命令 %s（%s）" % (name, script, rest[0], line.strip()))
                            known = options(subs[rest[0]]) | {o for a in parser._actions for o in a.option_strings}
                        for tok in rest:
                            if tok.startswith("--"):
                                flag = tok.split("=")[0]
                                self.assertIn(flag, known, "%s：%s 没有参数 %s（%s）" % (name, script, flag, line.strip()))
                                checked += 1
        self.assertGreater(checked, 25)

    def test_flags_mentioned_alone_exist_somewhere(self):
        known = set()
        for build in PARSERS.values():
            known |= options(build())
        for name, text in self.docs():
            for flag in re.findall(r"`(--[a-z][a-z-]*)", text):
                self.assertIn(flag, known, "%s 提到了不存在的参数 %s" % (name, flag))

    def test_no_relative_script_commands(self):
        for name, text in self.docs():
            self.assertNotRegex(text, r"python3?\s+scripts/", name)
        for s in ALL_SCRIPTS + ["common.py"]:
            self.assertNotRegex(C.read_text(os.path.join(SCRIPTS, s))[0], r"python3?\s+scripts/", s)

    def test_files_named_in_docs_exist(self):
        for name, text in self.docs():
            for path in set(re.findall(r"`((?:references|assets|examples|scripts)/[\w./-]+)`", text)):
                self.assertTrue(os.path.exists(os.path.join(ROOT, path)), "%s 提到了不存在的文件 %s" % (name, path))
            for ref in set(re.findall(r"`([a-z_]+\.md)`", text)):
                self.assertTrue(os.path.exists(os.path.join(ROOT, "references", ref)) or ref == "SKILL.md", "%s 提到了不存在的 %s" % (name, ref))

    def test_skill_md_shape(self):
        text = C.read_text(os.path.join(ROOT, "SKILL.md"))[0]
        m = re.match(r"---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(m)
        head = dict(l.split(":", 1) for l in m.group(1).split("\n") if ":" in l)
        self.assertEqual(head["name"].strip(), "xhs-launch-loop")
        self.assertTrue(40 < len(head["description"].strip()) <= 1024)
        self.assertLess(len(text.encode("utf-8")), 12000, "SKILL.md 应保持在测试报告时（17.7KB）的三分之二以下")
        self.assertIn("<技能目录>", text)
        for stage in ("## ① 调研", "## ② 发布", "## ③ 反馈", "## ④ 迭代"):
            self.assertIn(stage, text)

    def test_thresholds_in_docs_match_code(self):
        text = "\n".join(t for _, t in self.docs())
        self.assertEqual((rs.MIN_NOTES, rs.MIN_GROUP, rs.MIN_AUTHORS, ci.MIN_COMMENTS, ci.MIN_MENTIONS), (20, 5, 3, 20, 3))
        self.assertEqual((ll.MIN_IMPRESSIONS, ll.MIN_COMMENTS, ll.MIN_LIKES, ll.MIN_MENTIONS), (1000, 20, 20, 3))
        self.assertEqual((nc.TITLE_MAX, nc.BODY_MAX, nc.TAG_MIN, nc.TAG_MAX, cp.COVER_MAX, cp.PAGE_TEXT_MAX), (20, 1000, 3, 10, 12, 40))
        for phrase in ("曝光满 1000", "有效评论满 20 条", "点赞满 20 个", "吐槽满 3 条", "标题不超过 20 字", "正文不超过 1000 字"):
            self.assertIn(phrase, text)

    def test_guide_sections_and_commands(self):
        titles = [t for t, _ in guide.sections()]
        self.assertEqual(titles, ["总览", "① 调研", "② 发布", "③ 反馈", "④ 迭代", "完整示例"])
        for _, items in guide.COMMANDS:
            for _, c in items:
                parser = PARSERS[c[0]]()
                subs = subcommands(parser)
                if subs:
                    self.assertIn(c[1], subs, c)
                    known = options(subs[c[1]])
                else:
                    known = options(parser)
                for tok in c[1:]:
                    if tok.startswith("--"):
                        self.assertIn(tok, known, c)
                    self.assertNotRegex(tok, r"[|；]| / ", c)          # 可选项写在说明里，命令本身粘过去就能跑
        text = run("guide.py", "commands", cwd=tempfile.gettempdir())[1]
        self.assertIn('comment_insight.py 评论.txt --research --author "作者昵称"', text)
        self.assertIn("--baseline --published 2026-11-20", text)
        self.assertNotIn("定位", text)

    def test_templates_documented(self):
        doc = C.read_text(os.path.join(ROOT, "references", "note_templates.md"))[0]
        for name in cp.T:
            self.assertIn(name, doc, "note_templates.md 没有提到模板「%s」" % name)
        for name, sections in cp.BODY.items():
            row = next(l for l in doc.split("\n") if l.startswith("| %s |" % name))
            for sec, _ in sections:
                self.assertIn(sec, row, "%s 的分段「%s」没写进文档" % (name, sec))

    def test_lexicon_assets_are_valid(self):
        pain = ci.load_json_asset("pain_lexicon.json")
        intents = ci.load_json_asset("intent_lexicon.json")
        self.assertGreaterEqual(len([k for k in pain if not k.startswith("_")]), 10)       # 不只是咖啡：通用维度
        for k in ("intents", "positive", "negative", "mask", "spam"):
            self.assertIn(k, intents)
        names = set(k for k in pain if not k.startswith("_"))
        for a in ("价格", "质地与手感", "味道与气味", "购买与售后", "效果与功效", "安全与不适", "信任与真实性"):
            self.assertIn(a, names)


# ---------- 9. 打包 ----------

class Package(Work):
    def test_package_fits_the_competition_limits(self):
        names, size = package.check()
        self.assertLessEqual(len(names), 30, "技能包不能超过 30 个文件")
        self.assertLess(size, 40 * 1024 * 1024)
        self.assertEqual(names[0], "SKILL.md")
        self.assertFalse([n for n in names if "__pycache__" in n or n.startswith(("tests/", "dist/")) or n.endswith(".pyc")])
        on_disk = {"%s/%s" % (d, f) for d in package.DIRS for f in os.listdir(os.path.join(ROOT, d)) if os.path.isfile(os.path.join(ROOT, d, f))}
        self.assertEqual(set(names[1:]), on_disk)                 # 技能目录里的每个文件都在包里
        files = [os.path.join(ROOT, n) for n in names]
        for f in files:
            if f.endswith(".py"):
                for top in imported_modules(C.read_text(f)[0]):
                    self.assertTrue(os.path.exists(os.path.join(SCRIPTS, top + ".py")) or is_stdlib(top), "%s 用了标准库以外的模块 %s" % (os.path.basename(f), top))

    def test_zip_unpacks_into_a_working_skill(self):
        path, names, _ = package.build(os.path.join(self.work, "dist"))
        with zipfile.ZipFile(path) as z:
            self.assertEqual(sorted(z.namelist()), sorted("xhs-launch-loop/" + n for n in names))
            z.extractall(os.path.join(self.work, "my skills"))    # 技能装在带空格的路径下
        again, _, _ = package.build(os.path.join(self.work, "dist2"))
        with open(path, "rb") as a, open(again, "rb") as b:
            self.assertEqual(a.read(), b.read())                  # 内容不变，压缩包不变
        user = os.path.join(self.work, "my shop")                 # 用户自己的文件夹，路径里带空格
        os.makedirs(user)
        skill = os.path.join(self.work, "my skills", "xhs-launch-loop")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        env.pop("XHS_LAUNCH_DIR", None)

        def sh(args, shell=False):
            p = subprocess.run(args, shell=shell, cwd=user, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
            out = p.stdout.decode("utf-8", "replace")
            self.assertEqual(p.returncode, 0, out)
            return out

        self.assertIn("演示完成", sh([sys.executable, "-B", os.path.join(skill, "scripts", "guide.py"), "demo", "--out", "演示"]))
        self.assertTrue(os.path.exists(os.path.join(user, "演示", "xhs_launch", "launch_log.json")))
        out = sh([sys.executable, "-B", os.path.join(skill, "scripts", "launch_log.py"), "init", "--product", "护手霜", "--category", "护手霜", "--audience", "打工人"])
        hint = re.search(r"调研再写新笔记：(.+)", out).group(1)
        self.assertIn('"%s"' % os.path.join(skill, "scripts", "research.py"), hint)      # 带空格的路径加了引号
        self.assertIn("搜索词", sh(hint, shell=True))                                    # 原样粘贴到终端就能跑
        left = sorted(os.path.relpath(os.path.join(d, f), skill) for d, _, fs in os.walk(skill) for f in fs)
        self.assertEqual(left, sorted(os.path.normpath(n) for n in names))        # 运行不会往技能目录里写东西


if __name__ == "__main__":
    unittest.main()

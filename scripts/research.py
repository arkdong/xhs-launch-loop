#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书发布前调研：搜索词 → 笔记入库 → 供需分析 → 发布假设候选。

用法（在你自己的工作目录运行，脚本用绝对路径）:
  python3 research.py keywords [--category 品类] [--selling-points a,b] [--audience ..] [--pains a,b] [--competitors a,b] [--full]
        给出 4 个必搜词和几个可选词（--full 给完整矩阵）。品类、卖点、人群不写时用产品档案里的
  python3 research.py add 文件 [更多文件…] [--keyword 搜索词] [--replace]
        把笔记并入语料库，并打印识别结果供核对。自动识别：
        - 从 App / 网页搜索结果直接复制的文本（标题、作者、点赞数各占一行）
        - 每行一篇：标题 | 赞 1.2万 | 藏 800 | 评 56 | 粉丝 900 | 作者 小鹿 | 2026-11-01 | 链接（后面几项可缺）
        - csv / tsv / Markdown 表格（有表头）；json / jsonl（各种工具的导出）
        UTF-8 和 GBK 都可以；文件名写 - 表示从标准输入读
  python3 research.py status
  python3 research.py analyze --topic 品类 [--selling-terms a,b] [--days 90] [--top 10] [--insight 洞察.json]
        撞卖点、角度供给、标题钩子、需求缺口、低粉爆款、假设候选
数据目录默认是当前目录下的 xhs_launch，可用 --dir 指定。只依赖 Python 3 标准库。所有频次与比例均由脚本计数。
"""
import argparse, json, math, os, re, shutil, sys
from collections import Counter, OrderedDict
from datetime import datetime

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import comment_insight as ci  # noqa: E402

MIN_NOTES = 20      # 少于这个数，统计结论只能当线索
MIN_GROUP = 5       # 比较两组时，每组至少这么多篇
MIN_AUTHORS = 3     # 一个结论至少要来自这么多个不同作者
MIN_MENTIONS = ci.MIN_MENTIONS
K = {
    "id": ["id", "note_id", "noteid", "feed_id", "feedid", "笔记id"],
    "title": ["title", "displaytitle", "display_title", "标题", "笔记标题"],
    "desc": ["desc", "content", "snippet", "正文", "内容", "描述", "text"],
    "likes": ["likes", "liked_count", "likedcount", "like_count", "点赞", "点赞数", "赞"],
    "collects": ["collects", "collected_count", "collectedcount", "favorites", "collect_count", "收藏", "收藏数", "藏"],
    "comments": ["comment_count", "commentcount", "comments_count", "评论数", "评论", "评"],
    "shares": ["shares", "shared_count", "sharedcount", "share_count", "分享", "分享数"],
    "author": ["nickname", "nick_name", "author", "作者", "昵称", "博主"],
    "followers": ["followers", "fans", "fans_count", "follower_count", "粉丝", "粉丝数"],
    "date": ["date", "time", "publish_time", "publishtime", "create_time", "发布时间", "日期", "时间"],
    "url": ["url", "link", "note_url", "链接"],
    "type": ["type", "note_type", "类型", "形式"],
}
# 角度：每个角度两组词。第一组是明确的说法，第二组是常见但没那么确定的说法（只在标题里找，这些词在正文里太常见）。
# 归类顺序见 angle_of()。以 re: 开头的是正则；其余的词前面是「不」「没」时不算（「不踩雷」不是避雷帖）。全部用小写。
ANGLES = [
    ("避雷踩坑", ["避雷", "避坑", "踩坑", "踩雷", "别买", "千万别", "劝退", "翻车", "不推荐", "黑榜", "黑名单", "拔草", "慎入", "慎买", "re:后悔(?!没早|没有早|买晚|没早点)"],
     ["别再买", "不要买", "别入", "交学费", "被坑", "吐槽"]),
    ("对比平替", ["对比", "re:(?<![a-z])vs(?![a-z])", "平替", "哪个好", "怎么选", "区别", "横评", "比大牌", "大牌同款"],
     ["re:(?<![a-z])pk(?![a-z])", "差在哪", "差别", "选哪", "哪款", "哪家", "二选一", "怎么挑", "如何选", "如何挑", "选购", "不输", "代替", "替代"]),
    ("测评实测", ["测评", "实测", "亲测", "评测", "开箱", "试用", "试吃", "试穿", "试色", "空瓶", "回购", "re:(?:使用|真实|上手|入住|初|深度)体验|体验(?:感|了|报告|一下|如何|怎么样)"],
     ["re:(?<![好难不没别])(?:试|用|喝|吃|穿|戴|涂|住|买)了", "上脚", "上身", "使用感", "真实感受", "用后感", "入手"]),
    ("教程攻略", ["教程", "攻略", "怎么做", "怎么用", "保姆级", "手把手", "指南", "喝法", "做法", "用法", "吃法", "穿法"],
     ["步骤", "方法", "入门", "技巧", "诀窍", "秘诀", "流程", "公式", "模板", "教你", "学会", "如何", "怎样", "怎么涂", "怎么穿", "怎么吃", "怎么搭", "怎么洗", "怎么买",
      "正确", "re:别再(?![问买])", "方案", "搭配", "re:[\\d一二两三四五六七八九十]\\s*步(?!行)"]),
    ("征集互动", ["征集", "看过来", "一人一个", "晒出", "投稿", "邀请你", "接龙"],
     ["re:(?:们|都来|全体|速来|所有人)[!！，, ]*集合|集合[!！啦了]", "等你", "抄作业", "在线等", "求推荐", "求助", "求问", "蹲一个", "有没有", "有吗", "评论区", "投票", "帮我选", "邀你", "喊你"]),
    ("结果公布", ["结果公布", "获奖", "公示", "开奖", "揭晓", "揭榜", "入围", "复盘", "中奖"], ["名单", "战报", "成绩单"]),
    ("上线公告", ["上线", "首发", "内测", "开放体验", "入驻", "上新", "官宣", "开售", "预售"],
     ["开启", "发布", "更新", "新品", "开抢", "预告", "返场", "补货", "上架", "到货", "开业", "来袭", "启动"]),
    ("答疑科普", ["为什么", "是真的吗", "真的能", "真的假的", "科普", "真相", "误区"],
     ["原因", "要不要", "该不该", "能不能", "值不值", "有必要", "有用吗", "值得买吗", "值得吗", "多少钱", "re:是什么(?!神仙|宝藏|绝世)", "什么是", "怎么回事", "怎么办", "re:吗[？?！!]*$"]),
    ("深度长文", ["一文", "拆解", "揭秘", "设计与实践", "原理"], ["实践", "深度", "读懂", "详解", "解析", "万字", "干货", "实战"]),
    ("清单合集", ["清单", "合集", "盘点", "榜单", "排行", "红榜"],
     ["推荐", "必买", "好物", "re:(?<![a-z])top(?![a-z])", "必入", "必备",
      "re:(?<![\\d第])(?:[2-9]|\\d{2,}|[两二三四五六七八九十几]+)\\s*(?:款|支|件|种|家|本|条|双|瓶|只|套|部|台|盒|包|杯|首|间|处|样|个(?![月小星礼钟人]))(?!装)"]),
    ("单品种草", ["种草", "安利", "救星", "挖到宝", "本命", "闭眼入", "相见恨晚", "后悔没早"],
     ["宝藏", "神器", "天花板", "yyds", "绝了", "爱了", "真香", "续命", "离不开", "别再问", "好用", "好吃", "好喝", "好看", "好闻", "好穿", "re:被.{0,4}(?:问|夸|要链接|种草)"]),
    ("个人故事", ["日记", "vlog", "那年"], ["我的", "我是", "终于", "坚持", "经历", "记录", "一周", "一个月", "我做了", "我开了", "创业", "辞职", "打卡"]),
]
# 「不踩雷」「不会后悔」是在夸，不是避雷帖
NOT_NEGATED = r"(?<![不没无零])(?<!不会)(?<!不是)(?<!没有)(?<!不再)(?<!不怕)"
HOOKS = [
    ("含数字", r"\d"),
    ("疑问句", r"[?？]|吗|怎么|如何|为什么|哪(?!怕)|多少|(?<!没)什么|几[个支款种次天块元]|难道|是否|(?!动不动|时不时)([一-鿿])[不没]\1"),
    ("点名人群", r"学生党|打工人|新手|小白|宝妈|宝爸|上班族|女生|男生|男士|女士|租房|宿舍|社畜|懒人|党|程序员|孕妇|敏感肌|[干油敏痘]皮|[干油敏]肌|混[干油]"
                 r"|的人(?![气品生群数物])|星人|一族|姐妹|集美|大学生|考研|妈妈|爸爸|宝宝|儿童|老人|长辈|小个子|微胖|通勤族"),
    ("负面/避雷", NOT_NEGATED + r"(?:避雷|避坑|踩坑|踩雷|别买|后悔(?!没早|没有早|买晚|没早点)|千万别|智商税|劝退|翻车|黑榜|不推荐|拔草|慎入|慎买|难用|鸡肋|被坑|交学费|怀疑人生)"),
    ("反差/意外", r"以为|没想到|居然|竟然|结果|原来|才知道"),
    ("结果承诺", r"只需|只要|搞定|学会|秒|分钟|一招|直接"),
    ("新闻动词", r"上线|公布|发布|开启|首发|揭晓|提出|来了|入驻"),
    ("感叹号", r"[!！]"),
    ("期数前缀", r"[Vv]ol\.?\s*\d|第\s*\d+\s*[期弹]|(?<!\d)0?\d\s*[｜|]"),
    ("分隔符｜", r"[｜|]"),
    ("表情符号", "[\U0001F300-\U0001FAFF☀-➿]"),
]
ZH = {"likes": "点赞数", "collects": "收藏数", "comments": "评论数", "followers": "粉丝数", "date": "日期", "author": "作者"}


# ---------- 读取：JSON ----------

def deep_get(obj, names, depth=0):
    """在嵌套 dict 中按候选键名找第一个非空标量（兼容各工具的导出结构）。"""
    if not isinstance(obj, dict) or depth > 4:
        return None
    low = {str(k).lower(): v for k, v in obj.items()}
    for n in names:
        v = low.get(n)
        if v not in (None, "", [], {}) and not isinstance(v, (dict, list)):
            return v
    for v in obj.values():
        if isinstance(v, dict):
            r = deep_get(v, names, depth + 1)
            if r is not None:
                return r
    return None


def find_comment_list(obj, depth=0):
    """笔记对象里自带的评论 → [{"text":…, "likes":…}]"""
    if not isinstance(obj, dict) or depth > 4:
        return []
    for k, v in obj.items():
        if str(k).lower() in ("comments", "comment_list", "评论列表", "热评") and isinstance(v, list):
            out = []
            for c in v:
                t = c if isinstance(c, str) else (deep_get(c, ["content", "text", "评论", "内容"]) if isinstance(c, dict) else None)
                if t:
                    out.append({"text": str(t), "likes": (C.num(deep_get(c, ci.LIKE_KEYS)) or 0) if isinstance(c, dict) else 0})
            return out
    for v in obj.values():
        if isinstance(v, dict):
            r = find_comment_list(v, depth + 1)
            if r:
                return r
    return []


def note_id(url):
    """从小红书链接里取笔记编号：同一篇笔记不管从哪搜到都只算一次，不同笔记不会因为标题像而被合并。"""
    u = str(url or "")
    for pat in (r"/(?:explore|discovery/item|item|notes?)/([0-9a-zA-Z]{16,})", r"/user/profile/[0-9a-zA-Z]+/([0-9a-zA-Z]{16,})",
                r"[?&](?:note_?id|noteId)=([0-9a-zA-Z]{16,})"):
        m = re.search(pat, u)
        if m:
            return m.group(1)
    m = re.search(r"xhslink\.com/(?:[a-zA-Z]/)?([0-9A-Za-z]{5,})", u)
    return ("xhslink:" + m.group(1)) if m else None


def norm(raw, keyword="", dflt=None):
    """任意来源的一条记录 → 统一的笔记结构。缺的数字存 None（未知），不存 0。"""
    dflt = dflt or {}
    title = deep_get(raw, K["title"])
    desc = deep_get(raw, K["desc"]) or ""
    if not title and not desc:
        return None
    url = str(deep_get(raw, K["url"]) or "")
    nid = deep_get(raw, K["id"]) or note_id(url)
    if nid and not url and re.fullmatch(r"[0-9a-f]{24}", str(nid)):
        url = "https://www.xiaohongshu.com/explore/%s" % nid
    t = str(deep_get(raw, K["type"]) or "").lower()
    followers = C.num(deep_get(raw, K["followers"]))
    return {
        "id": str(nid) if nid else None, "title": str(title or str(desc)[:20]).strip(), "desc": str(desc).strip()[:1500],
        "likes": C.num(deep_get(raw, K["likes"])), "collects": C.num(deep_get(raw, K["collects"])),
        "comments": C.num(deep_get(raw, K["comments"])), "shares": C.num(deep_get(raw, K["shares"])),
        "author": str(deep_get(raw, K["author"]) or dflt.get("author") or "").strip(),
        "followers": followers if followers is not None else dflt.get("followers"),
        "date": C.parse_date(deep_get(raw, K["date"]), dflt.get("asof")), "url": url,
        "type": "视频" if ("video" in t or "视频" in t) else ("图文" if t else ""),
        "comment_list": find_comment_list(raw)[:50], "keywords": [keyword] if keyword else [],
    }


NOTE_LISTS = ("feeds", "items", "notes", "note_list", "data", "results", "result", "list", "笔记")
ACCOUNT_KEYS = ("account", "user", "author", "博主", "账号")


def walk_records(data, dflt=None):
    """从任意 JSON 结构里找出「像笔记」的 dict。账号导出（account + notes）会把账号名和粉丝数带给每篇笔记。"""
    out = []
    if isinstance(data, list):
        for x in data:
            out += walk_records(x, dflt)
    elif isinstance(data, dict):
        low = {str(k).lower() for k in data}
        inner = next((k for k in NOTE_LISTS if isinstance(data.get(k), (list, dict))), None)
        if inner and not any(k in low for k in K["title"]):
            acc = next((data[k] for k in ACCOUNT_KEYS if isinstance(data.get(k), dict)), None)
            if acc:
                asof = C.parse_date(C.pick(acc, ["collected_at", "crawled_at", "crawl_time", "采集时间", "抓取时间"]) or C.pick(data, ["collected_at", "采集时间", "抓取时间"]))
                dflt = {"author": C.pick(acc, ["name", "nickname", "nick_name", "昵称", "名称"]), "followers": C.num(C.pick(acc, K["followers"])),
                        "asof": datetime.strptime(asof, "%Y-%m-%d") if asof else None}   # 「3天前」按采集那天算
            out += walk_records(data[inner], dflt)
        elif deep_get(data, K["title"]) or deep_get(data, K["desc"]):
            out.append((data, dflt))
    return out


# ---------- 读取：粘贴的文本 ----------

KW = OrderedDict([("likes", r"(?:点赞数?|赞|喜欢|❤️?|♡|♥|👍)"), ("collects", r"(?:收藏数?|藏|⭐|🌟|📁)"), ("comments", r"(?:评论数?|评|💬)"),
                  ("shares", r"(?:分享数?|转发数?)"), ("followers", r"(?:粉丝数?|粉)")])
ANY_KW = "|".join(KW.values())
SEP = r"[|｜\t]"
# 一行里「标题」到哪里结束：第一个像数据的东西之前
BOUND = re.compile(
    r"(?:^|\s|[|｜\t,，;；(（])(?:%s)\s*[:：]?\s*\d" % ANY_KW
    + r"|(?:^|\s|[|｜\t,，;；(（])\d[\d.,]*\s*(?:万|w|k|千)?\+?\s*个?(?:点赞|赞|收藏|藏|评论|评|粉丝|粉)(?![一-鿿])"
    + r"|https?://|%s\s*(?:作者|博主|昵称)\s*[:：]?|%s\s*@" % (SEP, SEP)
    + r"|%s\s*(?:视频|图文)\s*(?=$|%s)" % (SEP, SEP)
    + r"|%s\s*(?:编辑于\s*)?%s\s*[一-鿿]{0,7}\s*(?=$|%s)" % (SEP, C.DATE, SEP)
    + r"|%s\s*%s\s*(?=$|%s)" % (SEP, C.COUNT, SEP)
    + r"|\s\d+(?:[.,]\d+)*\s*(?:万|w|k)\+?\s*$", re.I)      # 行尾带单位的数字：「标题 1.5万」
COUNT_ONLY = re.compile(r"^(?:%s)\s*(?:赞|点赞)?$|^(?:赞|点赞|♡|❤️?|👍)$" % C.COUNT)
CARD_JUNK = re.compile(r"^(?:广告|赞助|置顶|视频|图文|直播中?|笔记|商品|用户|已关注|关注|综合|最新|最热|筛选|全部|相关搜索|大家都在搜|猜你想搜|搜索发现"
                       r"|-+\s*the end\s*-+|the end|没有更多.*|暂无更多.*|已经到底.*|到底了.*|加载中.*|正在加载.*|查看更多.*|展开更多.*|点击加载.*)$", re.I)
PAGE_TABS = ("综合", "最新", "最热", "筛选", "全部", "用户", "商品")
DATE_TAIL = re.compile(r"\s+(?:编辑于\s*)?(%s)(?:\s*[一-鿿]{2,7})?\s*$" % C.DATE)


def _fields(tail):
    """一行里标题之后的部分 → 各项数据"""
    raw = {}
    m = re.search(r"https?://[^\s|｜]+", tail)
    if m:
        raw["url"] = m.group(0).rstrip(")）,，;；")
        tail = tail.replace(m.group(0), " ")
    for k, kw in KW.items():
        m = re.search(r"%s\s*[:：]?\s*(%s)" % (kw, C.COUNT), tail, flags=re.I) or \
            re.search(r"(%s)\s*个?%s(?![一-鿿])" % (C.COUNT, kw), tail, flags=re.I)
        if m:
            raw[{"comments": "comment_count"}.get(k, k)] = m.group(1)
    m = re.search(r"(?:作者|博主|昵称)\s*[:：]?\s*([^|｜\t]+?)\s*(?=$|%s)|@([^\s|｜@]+)" % SEP, tail)
    if m:
        raw["author"] = (m.group(1) or m.group(2)).strip()
    m = re.search(C.DATE, tail)
    if m:
        raw["date"] = m.group(0)
    m = re.search(r"(?:^|%s)\s*(视频|图文)\s*(?=$|%s)" % (SEP, SEP), tail)
    if m:
        raw["type"] = m.group(1)
    if "likes" not in raw:   # 没写「赞」字、单独成列的数字，按点赞数处理
        m = re.search(r"(?:^|%s)\s*(%s)\s*(?=$|%s)" % (SEP, C.COUNT, SEP), tail) or re.fullmatch(r"\s*(\d+(?:[.,]\d+)*\s*(?:万|w|W|k|K)\+?)\s*", tail)
        if m:
            raw["likes"] = m.group(1)
    return raw


def parse_note_lines(lines):
    """每行一篇。标题原样保留：不删开头的数字，不在「｜」处截断。"""
    info = {"format": "每行一篇（标题 | 赞 … | 藏 … | 评 …）", "warnings": []}
    seq = [re.match(r"^\s*(\d{1,3})\s*[.、)）]\s*(?=\D)", l) for l in lines]
    nums = [int(x.group(1)) for x in seq if x]
    strip = len(nums) >= 3 and len(nums) >= len(lines) * 0.6 and sum(1 for a, b in zip(nums, nums[1:]) if b == a + 1) >= (len(nums) - 1) * 0.6
    out, loose = [], 0
    for l, x in zip(lines, seq):
        if l.startswith("#") or CARD_JUNK.match(l):
            continue
        if COUNT_ONLY.match(l) or C.is_date_line(l):      # 单独一行的数字或日期不是标题
            loose += 1
            continue
        l = re.sub(r"^\s*[-*•·]\s+", "", l[x.end():] if (strip and x) else l)
        m = BOUND.search(l)
        title = (l[:m.start()] if m else l).strip(" \t|｜,，;；")
        raw = _fields(l[m.start():]) if m else {}
        if not title:
            if raw and out and not any(k in out[-1] for k in ("likes", "collects", "comment_count")):
                out[-1].update(raw)        # 标题一行、数据另起一行
            else:
                loose += 1
            continue
        if len(title) < 2:
            continue
        raw["title"] = title
        out.append(raw)
    if loose:
        info["warnings"].append("有 %d 行只有数字或日期、没有标题，已跳过。如果是从搜索结果页复制的，请连同标题和作者一起复制。" % loose)
    # 「标题 | 昵称 | 赞 300」：第二列没写「作者」两个字。整份文件都是这个样子时按作者处理，否则保留在标题里并提醒。
    cols = lambda r: [x.strip() for x in re.split(r"\s*[|\t]\s*", r["title"]) if x.strip()]
    bare = [r for r in out if "author" not in r]
    two = [r for r in bare if len(cols(r)) == 2 and len(cols(r)[1]) <= 16 and len(r) > 1]
    if len(two) >= 3 and len(two) >= len(bare) * 0.8:
        for r in two:
            r["title"], r["author"] = cols(r)
        info["format"] = "每行一篇（标题 | 作者 | 赞 …）"
        info["notes"] = ["每行的第二列没有标注，已按作者处理（例如「%s」）。如果它其实是标题的一部分，把作者写成「作者 昵称」后重新入库。" % two[0]["author"]]
    else:
        odd = [r for r in bare if len(cols(r)) >= 2]
        if odd:
            info["warnings"].append("有 %d 行的标题里带「|」（例如「%s」），已整段当作标题。如果后半段是作者，请写成「标题 | 作者 昵称 | 赞 300」。" % (len(odd), odd[0]["title"][:30]))
    return out, info


def parse_note_blocks(lines):
    """从 App / 网页搜索结果复制的卡片：标题、作者、点赞数各占一行。返回 (记录, 说明) 或 None。"""
    anchors = [i for i, l in enumerate(lines) if COUNT_ONLY.match(l)]
    inline = sum(1 for l in lines if re.search(r"(?:%s)\s*[:：]?\s*\d" % ANY_KW, l) and not COUNT_ONLY.match(l))
    body = [l for l in lines if not CARD_JUNK.match(l) and not C.is_date_line(l)]      # 页面上的筛选标签、页脚和日期行不算卡片内容
    if not anchors or len(anchors) < len(body) * 0.15 or inline >= max(2, len(anchors) * 0.3):      # 只贴了一两篇也按卡片读：单独成行的数字不可能是标题
        return None
    aset, blocks, cur, orphan = set(anchors), [], [], 0
    for i, l in enumerate(lines):
        if i in aset:
            if cur:
                blocks.append((cur, l))
                cur = []
            else:
                orphan += 1
        else:
            cur.append(l)
    out, sizes, bare = [], [], 0
    for b, cnt in blocks:
        raw, texts, kinds = {}, [], []
        for l in b:
            if C.is_date_line(l) or re.fullmatch(r"(?:编辑于\s*)?%s" % C.DATE, l):
                raw["date"] = l
            elif l in ("视频", "图文"):
                kinds.append(l)
            elif not CARD_JUNK.match(l) and not l.startswith("#"):
                texts.append(l)
        if len(set(kinds)) == 1 and not any(l in PAGE_TABS for l in b):      # 和「全部 / 用户」一起出现的「图文」「视频」是搜索页顶部的筛选标签，不是这一篇的形式
            raw["type"] = kinds[0]
        if not texts:
            orphan += 1
            continue
        sizes.append(len(texts))
        raw["title"] = texts[0]
        if len(texts) >= 2:
            author = texts[-1]
            m = DATE_TAIL.search(author)
            if m:
                raw.setdefault("date", m.group(1))
                author = author[:m.start()]
            raw["author"] = author.strip()
            if len(texts) > 2:
                raw["desc"] = " ".join(texts[1:-1])
        m = re.match(C.COUNT, cnt)
        raw["likes"] = m.group(0) if m and re.match(r"\d", cnt) else "0"
        bare += raw["likes"] == "0" and not re.match(r"\d", cnt)
        out.append(raw)
    if not out:
        return None
    usual = Counter(sizes).most_common(1)[0][0]
    info = {"format": "从 App / 网页搜索结果复制的卡片（%s）" % {1: "标题 / 点赞数", 2: "标题 / 作者 / 点赞数"}.get(usual, "标题 / 摘要 / 作者 / 点赞数"), "warnings": []}
    if bare:
        info["notes"] = ["有 %d 篇的点赞位置只有「赞」字、没有数字：还没有人点赞时页面就是这样显示的，已记为 0 赞（这是读到的 0，不是缺失）。" % bare]
    odd = sum(1 for s in sizes if s != usual)
    if odd:
        info["warnings"].append("有 %d 篇的行数和别的不一样（多数是 %d 行文字加 1 行点赞数），标题和作者可能错位，请核对。" % (odd, usual))
    if usual == 1:
        info["warnings"].append("每篇只有一行文字，按标题处理；作者未知，无法判断是否来自同一个账号。")
    cur = [l for l in cur if not CARD_JUNK.match(l)]
    if cur:
        info["warnings"].append("末尾有 %d 行后面没有点赞数，没有计入（可能是最后一篇没复制完整）。" % len(cur))
    if orphan:
        info["warnings"].append("有 %d 个数字行前面没有标题，已跳过。" % orphan)
    return out, info


def read_notes(path, keyword=""):
    """读一个文件 → (笔记列表, 说明)"""
    text, enc = C.read_text(path)
    ext = os.path.splitext(path)[1].lower()
    info = {"format": "", "warnings": []}
    if ext in (".json", ".jsonl"):
        try:
            data = [json.loads(l) for l in text.splitlines() if l.strip()] if ext == ".jsonl" else json.loads(text)
        except ValueError as e:
            sys.exit("%s 不是合法的 JSON（%s）。" % (path, e))
        pairs = walk_records(data)
        info["format"] = "JSON"
    else:
        rows = C.table_rows(text, ext)
        if rows and any(C.pick(r, K["title"]) for r in rows):
            pairs = [(r, None) for r in rows]
            info["format"] = "表格（%d 行）" % len(rows)
        else:
            if rows or ext in (".csv", ".tsv"):
                info["warnings"].append("表格里没有找到「标题 / title」列，已按每行一篇处理。请确认第一行是表头。")
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            raws, info2 = parse_note_blocks(lines) or parse_note_lines(lines)
            pairs = [(r, None) for r in raws]
            info.update(format=info2["format"], warnings=info["warnings"] + info2["warnings"], notes=info2.get("notes", []))
    if enc != "UTF-8":
        info["format"] += "，编码 %s" % enc
    return [n for n in (norm(r, keyword, d) for r, d in pairs) if n], info


# ---------- 语料库 ----------

def trigrams(s):
    s = re.sub(r"[^\w一-鿿]", "", s.lower())
    return {s[i:i + 3] for i in range(max(1, len(s) - 2))}


def _fill(old, new):
    """同一篇笔记的两条记录合并：新数据优先，缺的互相补。"""
    for k in ("likes", "collects", "comments", "shares", "followers", "date"):
        if new.get(k) is not None:
            old[k] = new[k]
    for k in ("id", "author", "url", "type", "desc"):
        if new.get(k) and (not old.get(k) or (k == "desc" and len(new[k]) > len(old[k]))):
            old[k] = new[k]
    old["keywords"] = sorted(set(old.get("keywords") or []) | set(new.get("keywords") or []))
    if len(new.get("comment_list") or []) > len(old.get("comment_list") or []):
        old["comment_list"] = new["comment_list"]


def dedupe(notes):
    """先按笔记编号合并；编号不全时，只有标题几乎相同且作者不冲突才合并。返回 (笔记, 合并掉的篇数)。"""
    out, by_id, merged = [], {}, 0
    for n in notes:
        hit = by_id.get(n["id"]) if n.get("id") else None
        tg = trigrams(n["title"])
        if hit is None:
            for o in out:
                if o.get("id") and n.get("id"):
                    continue                       # 两篇都有编号且不同：一定是两篇
                if n.get("author") and o.get("author") and n["author"] != o["author"]:
                    continue
                if tg and o["_tg"] and len(tg & o["_tg"]) / len(tg | o["_tg"]) >= 0.8:
                    hit = o
                    break
        if hit is None:
            n["_tg"] = tg
            out.append(n)
        else:
            _fill(hit, n)
            merged += 1
            n = hit
        if n.get("id"):
            by_id[n["id"]] = n
    for n in out:
        n.pop("_tg", None)
    return out, merged


def upgrade(n):
    """兼容旧版语料库：keyword → keywords，评论从字符串改成对象。"""
    if "keywords" not in n:
        n["keywords"] = [n.pop("keyword")] if n.get("keyword") else []
    n["comment_list"] = [c if isinstance(c, dict) else {"text": str(c), "likes": 0} for c in n.get("comment_list") or []]
    for k in ("shares", "followers", "date", "id", "url", "type", "author", "desc"):
        n.setdefault(k, None if k in ("shares", "followers", "date", "id") else "")
    return n


def load_corpus(path):
    data = C.read_json(path)
    if data is None:
        return []
    return [upgrade(n) for n in (data.get("notes") if isinstance(data, dict) else data) or []]


def save_corpus(path, notes):
    C.write_json(path, {"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "notes": notes}, indent=1)


# ---------- 统计 ----------

def median(xs):
    xs = sorted(xs)
    if not xs:
        return 0
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def age_days(n):
    if not n["date"]:
        return None
    try:
        return max(0, (datetime.now() - datetime.strptime(n["date"], "%Y-%m-%d")).days)
    except ValueError:
        return None


def pick_basis(notes):
    """互动用什么口径比较：多数笔记三项齐全时用 赞+2藏+3评，否则只比点赞（缺的不当 0）。"""
    liked = [n for n in notes if n["likes"] is not None]
    full = [n for n in liked if n["collects"] is not None and n["comments"] is not None]
    return "full" if liked and len(full) >= 0.8 * len(liked) else "likes"


def eng(n, basis):
    if n["likes"] is None:
        return None
    if basis == "likes":
        return n["likes"]
    if n["collects"] is None or n["comments"] is None:
        return None
    return n["likes"] + 2 * n["collects"] + 3 * n["comments"]


def fit_slope(notes):
    """在这批笔记里估计粉丝量对互动的影响：log10(互动) 对 log10(粉丝) 的回归斜率，限制在 0 到 1。
    1 表示互动和粉丝成正比，0 表示无关。实际数据通常在中间，所以不直接用「每万粉互动」（那等于假定斜率是 1，会反过来偏向小号）。"""
    pts = [(math.log10(max(n["followers"], 100)), math.log10(n["_eng"] + 1)) for n in notes]
    mx, my = sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    return max(0.0, min(1.0, sum((x - mx) * (y - my) for x, y in pts) / sxx)) if sxx else 0.0


def adjuster(notes):
    """不同账号粉丝量差很多时，直接比互动数比的是账号大小。返回 (校正方法, {id(n): 校正值}, 说明)。
    优先在账号内部比（每个账号有足够多笔记时）；做不到再按粉丝量校正；都做不到就明说没有校正。"""
    valid = [n for n in notes if n["_eng"] is not None]
    raw = {id(n): n["_eng"] for n in valid}
    authors = {n["author"] for n in valid if n["author"]}
    known = [n for n in valid if n["author"]]
    if valid and len(known) == len(valid) and len(authors) == 1:
        return "同一账号", raw, "全部来自同一个账号，不需要按账号大小校正。"
    groups = {}
    for n in known:
        groups.setdefault(n["author"], []).append(n)
    big = {a: g for a, g in groups.items() if len(g) >= MIN_GROUP and median([x["_eng"] for x in g]) > 0}
    if len(big) >= 2 and sum(len(g) for g in big.values()) >= 0.8 * len(valid):
        adj = {}
        for g in big.values():
            base = median([x["_eng"] for x in g])
            adj.update({id(x): x["_eng"] / base for x in g})
        return "账号内相对值", adj, "笔记集中在 %d 个账号。下面的倍数按「这篇的互动 ÷ 它所在账号的互动中位数」比较：比的是写法，不是账号大小。" % len(big)
    fans = [n for n in valid if n["followers"]]
    if valid and (len(fans) >= 0.8 * len(valid) or len(fans) >= max(MIN_NOTES, 0.5 * len(valid))):
        fs = [n["followers"] for n in fans]
        times = max(fs) // max(1, min(fs))
        rest = "" if len(fans) == len(valid) else "没有粉丝数的 %d 篇不参与倍数比较。" % (len(valid) - len(fans))
        if times < 10:
            return "粉丝量接近", {id(n): n["_eng"] for n in fans}, "各账号粉丝量在同一量级，直接比较互动数。" + rest
        k = fit_slope(fans)
        if k < 0.1:
            return "粉丝量影响小", {id(n): n["_eng"] for n in fans}, "各账号粉丝量相差 %d 倍，但在这批笔记里粉丝多少和互动高低基本无关，直接比较互动数。%s" % (times, rest)
        return "按粉丝量校正", {id(n): n["_eng"] / max(n["followers"], 100) ** k for n in fans}, \
            "各账号粉丝量相差 %d 倍。在这批笔记里粉丝每多 10 倍，互动约多 %.1f 倍；下面的倍数已扣除这一影响，避免大号把某种写法带高。%s" % (times, 10 ** k, rest)
    return None, raw, "⚠️ 粉丝数不全，下面的倍数没有按账号大小校正：互动高可能只是因为账号大。倍数都标了「线索」，不出角度、钩子、形式的假设。"


def score(notes):
    """可复制度评分：互动分位 + 时效 + 赞粉比。用分位数而不是除以最大值，避免被单篇大爆款压扁。"""
    ranked = sorted((n for n in notes if n["_eng"] is not None), key=lambda n: n["_eng"])
    pos = {id(n): i for i, n in enumerate(ranked)}
    for n in notes:
        n["angle"] = angle_of(n["title"], n["desc"])
        n["like_fan_ratio"] = round(n["likes"] / max(1, n["followers"]), 2) if n["followers"] and n["likes"] is not None else None
        n["low_fan_hit"] = bool(n["like_fan_ratio"] is not None and ((n["followers"] < 5000 and n["likes"] >= 1000) or (n["like_fan_ratio"] >= 1 and n["likes"] >= 300)))
        if n["_eng"] is None:
            n["score"] = None
            continue
        e = 100 * pos[id(n)] / max(1, len(ranked) - 1)
        a = age_days(n)
        r = 40 if a is None else max(0, 100 - max(0, a - 7) * 100 / 173)
        n["score"] = round(0.40 * e + 0.25 * r + 0.35 * min(100, n["like_fan_ratio"] * 50)) if n["like_fan_ratio"] is not None else round(0.60 * e + 0.40 * r)


def has_word(text, w):
    """文本里有这个词，并且前面不是否定（「不踩雷」不算避雷帖）。以 re: 开头的按正则找。"""
    return bool(re.search(w[3:] if w.startswith("re:") else r"(?<![不没])" + re.escape(w), text.lower()))


def angle_of(title, desc=""):
    """一篇笔记的角度。先在标题里找明确的说法，再在标题里找不太确定的说法，最后在正文开头找明确的说法；
    每一轮按 ANGLES 的顺序取第一个命中的。都没有就是「其他」：宁可不归类，也不硬归。"""
    title, head = (title or "").strip(), (desc or "")[:200]
    for text, col in ((title, 1), (title, 2), (head, 1)):
        hit = next((a[0] for a in ANGLES if any(has_word(text, w) for w in a[col])), None)
        if hit:
            return hit
    return "其他"


def ref(n):
    """表格里用的短引用：只放标题。链接在「低粉爆款」「综合评分」这些逐篇列出的地方给。"""
    return "「%s」" % cut(n["title"], 24)


def brief(n):
    return {k: n.get(k) for k in ("title", "url", "author", "likes", "collects", "comments", "followers", "like_fan_ratio", "date", "angle", "score", "low_fan_hit")}


def compare(group, rest, adj):
    """两组笔记的互动中位数之比（用校正值）。任何一组不到 MIN_GROUP 篇返回 None。"""
    a = [adj[id(n)] for n in group if id(n) in adj]
    b = [adj[id(n)] for n in rest if id(n) in adj]
    if len(a) < MIN_GROUP or len(b) < MIN_GROUP or not median(b):
        return None
    return round(median(a) / median(b), 2)


def by_author(group, rest):
    """在每个账号内部各比一次：{作者: 倍数}。只算两边都不少于 MIN_GROUP 篇的账号。几个账号方向一致，结论才站得住。"""
    out = OrderedDict()
    for a in sorted({n["author"] for n in group if n["author"]}):
        x = [n["_eng"] for n in group if n["author"] == a]
        y = [n["_eng"] for n in rest if n["author"] == a]
        if len(x) >= MIN_GROUP and len(y) >= MIN_GROUP and median(y):
            out[a] = round(median(x) / median(y), 2)
    return out


def spread(group):
    """这组笔记来自几个作者。作者都未知时返回 None。"""
    names = [n["author"] for n in group if n["author"]]
    return len(set(names)) if names else None


def _norm_point(p):
    """卖点去掉空白和标点后的样子（数字中间的小数点留着：4.5 元不能变成 45 元）。"""
    return "".join(re.findall(r"\d+(?:\.\d+)?|[^\W_]", p or "", flags=re.U))


SAME_CHAR = {ord("黏"): "粘"}       # 两种写法都常见的字，比对时算同一个


def _fold(s):
    """比对卖点用：不分大小写，不管空格，「黏」和「粘」算同一个字。"""
    return re.sub(r"\s+", "", s or "").lower().translate(SAME_CHAR)


def _pieces(p):
    """卖点里连续 4 个字的片段，用来找只说了半句的笔记（「一杯不到4块」→「一杯不到」）。
    不从数字或英文单词中间切开：「39元50g」切出的「9元50」会把别的价格也算成撞卖点。片段里至少要有 2 个汉字。"""
    out, edge = [], "的了和与及是在有很都也就还"
    glued = lambda x, y: bool(re.match(r"[0-9A-Za-z.]{2}$", x + y))
    for i in range(len(p) - 3):
        t = p[i:i + 4]
        if t[0] in edge or t[-1] in edge or len(re.findall("[%s]" % ci.CJK, t)) < 2:
            continue
        if (i and glued(p[i - 1], p[i])) or (i + 4 < len(p) and glued(p[i + 3], p[i + 4])):
            continue
        out.append(t)
    return out


def selling_terms(points, extra=()):
    """卖点 → 用来在标题和正文里找「撞卖点」笔记的说法。
    points：产品档案里的卖点。每个卖点用原文加它的 4 字片段去找。
    extra：命令行补充的说法，每项是「卖点词」或「卖点=说法1/说法2」。同一个卖点常有别的说法（「一杯不到4块」也会被写成「一杯多少钱」），
    脚本不懂同义词，要由使用者补上。"""
    out = OrderedDict()
    for p in points:
        p = _norm_point(p)
        if len(p) < 2:
            continue
        out[p] = [p] + [t for t in _pieces(p) if t != p]
    for item in extra:
        name, _, syn = item.partition("=")
        if not syn and "＝" in item:
            name, _, syn = item.partition("＝")
        name = _norm_point(name)
        if len(name) < 2:
            continue
        terms = out.setdefault(name, [name])
        for t in re.split(r"[/／|｜]", syn):
            t = t.strip()
            if len(t) >= 2 and t not in terms:
                terms.append(t)
    return out


def analyze(notes, days=90, top=10, insight=None, selling=None, lex=None):
    lex = lex or ci.Lexicon()
    total_in = len(notes)
    notes, merged = dedupe(notes)
    dropped_old = 0
    if days:
        keep = [n for n in notes if age_days(n) is None or age_days(n) <= days]
        dropped_old = len(notes) - len(keep)
        notes = keep
    if not notes:
        return None
    basis = pick_basis(notes)
    for n in notes:
        n["_eng"] = eng(n, basis)
    score(notes)
    valid = [n for n in notes if n["_eng"] is not None]
    n_all, n_eng = len(notes), len(valid)
    med = median([n["_eng"] for n in valid])
    method, adj, adj_note = adjuster(notes)
    med_adj = median(list(adj.values())) if adj else 0
    authors = {n["author"] for n in notes if n["author"]}
    liked = [n for n in notes if n["likes"] is not None]
    R = {"total_input": total_in, "merged": merged, "analyzed": n_all, "with_engagement": n_eng, "dropped_old": dropped_old, "days": days,
         "basis": "赞 + 2×藏 + 3×评" if basis == "full" else "仅点赞",
         "basis_counts": {"liked": len(liked), "full": sum(1 for n in liked if n["collects"] is not None and n["comments"] is not None)},
         "lexicons": [os.path.basename(p) for p, _ in getattr(lex, "loaded", [])], "lexicon_notes": list(getattr(lex, "notes", [])),
         "missing": {k: sum(1 for n in notes if n[k] is None) for k in ("likes", "collects", "comments", "followers", "date")},
         "authors": len(authors), "no_author": sum(1 for n in notes if not n["author"]),
         "median_engagement": med, "adjust": method, "adjust_note": adj_note, "sample_sufficient": n_eng >= MIN_NOTES}
    stats_ok = R["sample_sufficient"]
    firm = stats_ok and method is not None      # 倍数能不能当结论：样本够，并且排除得了账号大小的影响。排除不了时只当线索

    # 撞卖点
    same = []
    folded = {id(n): (_fold(n["title"]), _fold(n["title"] + " " + n["desc"])) for n in notes} if selling else {}
    for point, terms in (selling or {}).items():
        per = OrderedDict()
        for t in terms:
            per[t] = [n for n in notes if _fold(t) in folded[id(n)][1]]
        # 一半以上笔记都有的说法太泛，分不出谁在讲这个卖点：不用它（卖点原文除外）
        too_wide = [t for t in terms[1:] if len(per[t]) > n_all * 0.5]
        hits, seen = [], set()
        for t in terms:
            if t in too_wide:
                continue
            for n in per[t]:
                if id(n) not in seen:
                    seen.add(id(n))
                    hits.append((n, t, _fold(t) in folded[id(n)][0]))
        hits.sort(key=lambda h: -(h[0]["_eng"] or 0))
        pieces = set(_pieces(point)) - {point}
        same.append({"selling_point": point, "terms": [t for t in terms if t not in too_wide], "pieces": [t for t in terms if t in pieces and t not in too_wide],
                     "ignored_terms": too_wide, "notes": len(hits), "in_title": sum(1 for h in hits if h[2]),
                     "share": round(len(hits) / n_all, 3), "top": [dict(brief(n), matched=t) for n, t, _ in hits[:5]]})
    R["same_selling_point"] = same

    # 角度供给。「其他」是没归类的笔记，只列出来，不当比较对象。
    angles = []
    for name in [a[0] for a in ANGLES] + ["其他"]:
        g = [n for n in notes if n["angle"] == name]
        gv = [n for n in g if n["_eng"] is not None]
        if not g:
            continue
        best = max(gv, key=lambda n: n["_eng"], default=None)
        comp = [n for n in gv if id(n) in adj]              # 可比的：有互动数据，并且能按账号大小校正
        vs = round(median([adj[id(n)] for n in comp]) / med_adj, 2) if med_adj and len(comp) >= MIN_MENTIONS else None
        sp = spread(g)
        words = next((a[1] + a[2] for a in ANGLES if a[0] == name), [])
        angles.append({"angle": name, "count": len(g), "share": round(len(g) / n_all, 3), "median_engagement": median([n["_eng"] for n in gv]) if gv else None,
                       "comparable": len(comp), "in_title": sum(1 for n in notes if any(has_word(n["title"], w) for w in words)) if words else None,
                       "vs_overall": vs, "authors": sp, "low_fan_hits": sum(1 for n in g if n["low_fan_hit"]), "best": ref(best) if best else "",
                       "opportunity": bool(firm and name != "其他" and len(comp) >= MIN_GROUP and len(g) / n_all <= 0.2 and vs is not None and vs >= 1.2
                                           and (sp is None or sp >= min(MIN_AUTHORS, len(authors))))})
    R["angles"] = sorted(angles, key=lambda x: (x["angle"] == "其他", -x["count"]))

    # 标题钩子
    hooks = []
    for name, pat in HOOKS:
        w = [n for n in valid if re.search(pat, n["title"])]
        wo = [n for n in valid if not re.search(pat, n["title"])]
        lift = compare(w, wo, adj)
        sp = spread(w)
        ex = max(w, key=lambda n: n["_eng"], default=None)
        top_author = Counter(n["author"] for n in w if n["author"]).most_common(1)
        per = by_author(w, wo)
        agree = all((v >= 1) == (lift >= 1) for v in per.values()) if lift is not None and len(per) >= 2 else None    # 各账号内部的方向是否一致
        wide = len(authors) <= 1 or sp is None or (sp >= MIN_AUTHORS and top_author[0][1] <= len(w) * 0.6)                 # 不是只来自一两个账号
        solid = bool(firm and lift is not None and agree is not False and (wide or agree))
        hooks.append({"hook": name, "used": len(w), "share": round(len(w) / n_eng, 3) if n_eng else 0, "lift": lift, "authors": sp, "solid": solid,
                      "by_author": per, "consistent": agree, "example": ref(ex) if ex else ""})
    R["hooks"] = sorted(hooks, key=lambda x: -(x["lift"] or 0))
    R["title_len_median"] = median([C.xhs_len(n["title"]) for n in notes])
    R["title_keywords"] = [{"word": w, "notes": c} for w, c in ci.keywords([n["title"] for n in notes], ci.load_stopwords(), 12)]

    # 形式
    forms = {}
    for f in ("图文", "视频"):
        g = [n for n in valid if n["type"] == f]
        if g:
            forms[f] = {"count": len(g), "median_engagement": median([n["_eng"] for n in g]), "authors": spread(g)}
    R["forms"] = forms
    form_lift, form_per = None, {}
    if len(forms) == 2:
        v, i = [n for n in valid if n["type"] == "视频"], [n for n in valid if n["type"] == "图文"]
        form_lift, form_per = compare(v, i, adj), by_author(v, i)
    R["form_lift_video_vs_image"], R["form_lift_by_author"] = form_lift, form_per
    cl = [n["collects"] / n["likes"] for n in notes if n["likes"] and n["collects"]]
    cm = [n["comments"] / n["likes"] for n in notes if n["likes"] and n["comments"]]
    R["ratios"] = {"collect_like_median": round(median(cl), 2) if cl else None, "comment_like_median": round(median(cm), 2) if cm else None, "n": len(cl)}

    # 需求侧：评论洞察（comment_insight.py --research 的结果），没有就用笔记自带的评论
    demand, source = insight, "评论洞察文件"
    embedded = [{"text": c["text"], "likes": c.get("likes") or 0, "user": "", "author": False} for n in notes for c in n.get("comment_list", [])]
    R["embedded_comments"], R["embedded_unused"] = len(embedded), len(embedded) if demand else 0
    if not demand:
        if len(embedded) >= 5:
            cleaned, stat = ci.prepare(embedded, lex)
            if cleaned:
                demand, source = ci.analyse(cleaned, lex=lex, stat=stat), "笔记数据里自带的评论"
    gaps = []
    if demand:
        R["demand_comments"], R["demand_source"] = demand.get("total", 0), source
        touch = {id(n): set(lex.analyse(n["title"])["aspects"]) for n in notes}
        for a in demand.get("aspects", []):
            concern = a.get("complaints", 0) + a.get("questions", 0)
            if not concern:
                continue
            words = [w for w in a.get("top_words", []) if len(w) >= 2]
            in_title = [n for n in notes if a["aspect"] in touch[id(n)] or any(w in n["title"].lower() for w in words)]
            in_body = [n for n in notes if n not in in_title and any(w in n["desc"].lower() for w in words)]
            gaps.append({"aspect": a["aspect"], "complaints": a.get("complaints", 0), "questions": a.get("questions", 0), "concern": concern, "words": words[:4],
                         "notes_in_title": len(in_title), "notes_in_body": len(in_body), "title_share": round(len(in_title) / n_all, 3),
                         "examples": [n["title"][:24] for n in in_title[:2]], "titles": [n["title"] for n in in_title[:10]],
                         "quotes": (a.get("complaint_quotes", []) + a.get("question_quotes", []))[:2],
                         "gap": bool(concern >= MIN_MENTIONS and len(in_title) / n_all <= 0.1)})
        gaps.sort(key=lambda x: (-x["gap"], -x["concern"]))
        R["question_topics"] = demand.get("question_topics", [])[:6]
        R["demand_sufficient"] = bool(demand.get("sample_sufficient", demand.get("total", 0) >= ci.MIN_COMMENTS))
    R["gaps"] = gaps

    ranked = sorted(valid, key=lambda n: -n["score"])
    R["low_fan_hits"] = [brief(n) for n in ranked if n["low_fan_hit"]][:top]
    R["top_notes"] = [brief(n) for n in ranked[:top]]

    # 假设候选：每条都对应上面的一个计数结果，并且达到最低样本量
    H, why_not = [], []
    g = next((g for g in gaps if g["gap"]), None)
    if g and R.get("demand_sufficient"):
        H.append({"basis": "需求缺口", "hypothesis": "以「%s」这个关注点开头的笔记，评论率和收藏点赞比会高于泛卖点开头" % g["aspect"],
                  "evidence": "%d 条评论里有 %d 条在吐槽或追问它，但 %d 篇笔记里只有 %d 篇在标题回应" % (R["demand_comments"], g["concern"], n_all, g["notes_in_title"]), "metric": "评论率"})
    elif g:
        why_not.append("「%s」看起来是缺口，但评论只有 %d 条，不到 %d 条。" % (g["aspect"], R.get("demand_comments", 0), ci.MIN_COMMENTS))
    elif not demand:
        why_not.append("没有评论数据，无法判断需求缺口。")
    named = [a for a in R["angles"] if a["angle"] != "其他"]
    a = next((a for a in named if a["opportunity"]), None)
    if a:
        base = "常见的「%s」角度" % named[0]["angle"] if named[0]["angle"] != a["angle"] else "这个品类的整体水平"
        H.append({"basis": "角度机会", "hypothesis": "用「%s」角度发布，互动率会高于%s" % (a["angle"], base),
                  "evidence": "该角度 %d 篇，只占 %s，互动中位数是整体的 %.1f 倍（%s）" % (a["count"], C.pct(a["count"], n_all), a["vs_overall"], method or "未按账号大小校正"), "metric": "互动率"})
    h = next((h for h in R["hooks"] if h["solid"] and h["lift"] >= 1.3), None)
    if h:
        H.append({"basis": "标题钩子", "hypothesis": "标题使用「%s」会比不使用的点击率更高" % h["hook"],
                  "evidence": "%d 篇使用，互动中位数是未使用的 %.1f 倍（%s）" % (h["used"], h["lift"], method or "未按账号大小校正"), "metric": "点击率"})
    if form_lift and firm and (form_lift >= 1.3 or form_lift <= 0.77):
        b, o = ("视频", "图文") if form_lift >= 1.3 else ("图文", "视频")
        if (forms[b]["authors"] or MIN_AUTHORS) >= min(MIN_AUTHORS, max(1, len(authors))):
            H.append({"basis": "内容形式", "hypothesis": "同一角度用%s发布，互动率会高于%s" % (b, o),
                      "evidence": "%s %d 篇、%s %d 篇，互动中位数相差 %.1f 倍（%s）" % (b, forms[b]["count"], o, forms[o]["count"], max(form_lift, 1 / form_lift), method or "未按账号大小校正"),
                      "metric": "互动率"})
    if not stats_ok:
        why_not.append("有互动数据的笔记只有 %d 篇，不到 %d 篇：角度、钩子、形式的比较不出假设。" % (n_eng, MIN_NOTES))
    if method is None:          # 两样都缺时两样都说：只补到 20 篇，倍数仍然只是线索，不要让用户白跑一趟
        why_not.append("粉丝数不全，倍数没法按账号大小校正：角度、钩子、形式的比较只当线索，不出假设。" if stats_ok else
                       "粉丝数也不全：就算补够篇数，倍数没法按账号大小校正，角度、钩子、形式的比较仍然只当线索。")
    R["hypotheses"], R["no_hypothesis_reasons"] = H, why_not
    # 线索候选：没有一条达到标准时，把最接近的几条列出来，并说清还差什么。只能当线索试，不能当结论
    leads = []
    if not H:
        thin = "有互动数据的笔记只有 %d 篇，不到 %d 篇" % (n_eng, MIN_NOTES)
        no_fans = "粉丝数不全，分不清是写法的功劳还是账号大"
        weak = "；".join(x for x in (thin if not stats_ok else "", no_fans if method is None else "") if x)      # 倍数为什么还不能当结论
        if g:
            leads.append({"basis": "需求缺口", "hypothesis": "以「%s」这个关注点开头的笔记，评论率会高于泛卖点开头" % g["aspect"], "metric": "评论率",
                          "evidence": "%d 条评论里有 %d 条在吐槽或追问它，%d 篇笔记里只有 %d 篇在标题回应" % (R["demand_comments"], g["concern"], n_all, g["notes_in_title"]),
                          "short_of": "评论只有 %d 条，不到 %d 条" % (R["demand_comments"], ci.MIN_COMMENTS) if R["demand_comments"] < ci.MIN_COMMENTS else "评论的条数还没有核对"})
        hot = next((x for x in sorted(gaps, key=lambda x: -x["concern"]) if x["concern"] >= MIN_MENTIONS and not x["gap"]), None)
        if hot and not g:      # 评论里最在意的点已经有人写了：不是缺口，但仍然是读者最想看到回应的地方
            leads.append({"basis": "最受关注的点", "hypothesis": "用评论里的原话开头、正面回应「%s」的笔记，评论率会高于罗列卖点的开头" % hot["aspect"], "metric": "评论率",
                          "evidence": "%d 条评论里有 %d 条在吐槽或追问它%s" % (R["demand_comments"], hot["concern"], "，例如“%s”" % cut(hot["quotes"][0]) if hot["quotes"] else ""),
                          "short_of": "不是缺口：已经有 %d 篇笔记在标题回应，要讲出和它们不一样的地方%s" % (
                              hot["notes_in_title"], "" if R.get("demand_sufficient") else "；评论也只有 %d 条，不到 %d 条" % (R["demand_comments"], ci.MIN_COMMENTS))})
        hk = next((h for h in R["hooks"] if h["lift"] and h["lift"] >= 1.3 and not h["solid"]), None)
        if hk:
            leads.append({"basis": "标题钩子", "hypothesis": "标题使用「%s」会比不使用的点击率更高" % hk["hook"], "metric": "点击率",
                          "evidence": "%d 篇使用，互动中位数是未使用的 %.1f 倍（%s）" % (hk["used"], hk["lift"], method or "未按账号大小校正"),
                          "short_of": weak or "只来自一两个账号，或者各账号内部的方向不一致"})
        an = next((x for x in named if x["vs_overall"] and x["vs_overall"] >= 1.2 and x["count"] / n_all <= 0.2 and not x["opportunity"]), None)
        if an:
            leads.append({"basis": "角度机会", "hypothesis": "用「%s」角度发布，互动率会高于这个品类的整体水平" % an["angle"], "metric": "互动率",
                          "evidence": "该角度 %d 篇，占 %s，互动中位数是整体的 %.1f 倍（%s）" % (an["count"], C.pct(an["count"], n_all), an["vs_overall"], method or "未按账号大小校正"),
                          "short_of": weak or "可比的笔记不到 %d 篇，或者只来自一两个账号" % MIN_GROUP})
    R["leads"] = leads[:3]
    for n in notes:
        n.pop("_eng", None)
    return R


# ---------- 报告 ----------

def cut(s, n=48):
    s = str(s).replace("|", " ").replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def fmt_n(v):
    return "—" if v is None else ("%d" % v if float(v).is_integer() else "%.1f" % v)


def fmt_note(b):
    fans = "粉丝 %d，赞粉比 %.2f" % (b["followers"], b["like_fan_ratio"]) if b.get("like_fan_ratio") is not None else "粉丝未知"
    t = "[%s](%s)" % (b["title"], b["url"]) if b["url"] else "「%s」" % b["title"]
    return "%s｜%s｜赞 %s 藏 %s 评 %s｜%s｜%s｜%s%s" % (t, b["author"] or "作者未知", fmt_n(b["likes"]), fmt_n(b["collects"]), fmt_n(b["comments"]), fans,
                                               b["date"] or "日期未知", b["angle"], ("｜评分 %d" % b["score"]) if b.get("score") is not None else "")


def to_markdown(R, topic):
    mi, n = R["missing"], R["analyzed"]
    L = ["# 发布前调研：%s" % (topic or "未命名"), "", "## 数据说明", ""]
    steps = ["输入 %d 篇" % R["total_input"]]
    if R["merged"]:
        steps.append("合并重复 %d 篇" % R["merged"])
    if R["dropped_old"]:
        steps.append("剔除超过 %d 天的 %d 篇" % (R["days"], R["dropped_old"]))
    L.append("- %s，分析 **%d** 篇，来自 %s。" % ("，".join(steps), n, ("%d 个作者" % R["authors"]) + ("（另有 %d 篇作者未知）" % R["no_author"] if R["no_author"] and R["authors"] else "") if R["authors"] else "未知作者"))
    bc = R.get("basis_counts") or {}
    L.append("- 互动口径：**%s**。%s" % (R["basis"], "有点赞数的 %d 篇里，收藏数和评论数也齐全的只有 %d 篇，不到八成，所以只比点赞；缺的数字按未知处理，不当 0。" % (bc.get("liked", 0), bc.get("full", 0))
                                    if R["basis"] == "仅点赞" else "三项不全的笔记不参与表现比较。"))
    lack = ["%s %d 篇" % (ZH[k], v) for k, v in mi.items() if v]
    if lack:
        L.append("- 缺失：%s。%s" % ("，".join(lack), "没有粉丝数就无法识别低粉爆款。" if mi["followers"] else ""))
    if not R["with_engagement"]:
        L.append("- ⚠️ **没有一篇笔记有互动数据**：下面只能看「大家在发什么」，看不出「什么写法表现好」。请补上点赞数后重新 add。")
    elif R["with_engagement"] < n:
        L.append("- %d 篇有互动数据，表现比较只用这些。" % R["with_engagement"])
    L.append("- %s" % R["adjust_note"])
    thin = not R["sample_sufficient"]
    if thin:
        L.append("- ⚠️ **有互动数据的笔记只有 %d 篇，不到 %d 篇**：下面的倍数都标了「线索」，不出统计类假设。再搜一两个词补到 %d 篇以上。" % (R["with_engagement"], MIN_NOTES, MIN_NOTES))
    if R.get("lexicons"):
        L.append("- 已加载项目词表：%s。词表变了，「需求缺口」里各维度的数字会跟着变。" % "、".join(R["lexicons"]))
        L += ["  - " + x for x in R.get("lexicon_notes") or []]
    L += ["- 数据只来自已收集的笔记，会有推广帖和幸存者偏差；所有数字为脚本计数。", ""]
    loose = thin or R["adjust"] is None                                                # 样本不够，或者没法按账号大小校正：每个倍数旁边都标出来
    times = lambda v, fmt="%.1f": (fmt + " 倍%s") % (v, "（线索）" if loose else "")

    L += ["## 1. 撞卖点：你的卖点有没有人讲过", ""]
    if not R["same_selling_point"]:
        L.append("没有提供卖点。加 `--selling-terms \"卖点=别的说法1/别的说法2\"` 重跑，可以看到已经在讲同一个卖点的笔记。")
    else:
        L += ["脚本只认字面：每个卖点按「原文 + 原文里连续 4 个字的片段 + 你补充的说法」去找，不分大小写和空格。同一个卖点常有别的说法，用 `--selling-terms \"卖点=说法1/说法2\"` 补上再跑一次。", ""]
    for s in R["same_selling_point"]:
        pieces = s.get("pieces", [])
        used = "、".join("「%s」" % t for t in s.get("terms", [s["selling_point"]]) if t not in pieces) + ("，以及原文的 %d 个片段" % len(pieces) if pieces else "")
        wide = "（「%s」一半以上的笔记都有，太泛，没有用它）" % "」「".join(s["ignored_terms"]) if s.get("ignored_terms") else ""
        if not s["notes"]:
            L.append("- **%s**：%d 篇里没有笔记提到（查的说法：%s）%s。可能是空白，也可能只是说法不同：补上别的说法再查一次，再下「没人讲过」的结论。" % (s["selling_point"], n, used, wide))
            continue
        L.append("- **%s**：%d 篇提到（%s），其中 %d 篇写进了标题（查的说法：%s）%s。这个卖点已经有人在讲，先看它们怎么讲，再决定怎么讲得不一样：" % (
            s["selling_point"], s["notes"], C.pct(s["notes"], n), s["in_title"], used, wide))
        L += ["  - " + fmt_note(b) + ("｜命中「%s」" % b["matched"] if b.get("matched") else "") for b in s["top"]]
    L += ["", "## 2. 角度供给：大家都在发什么", "",
          "每篇笔记只归一个角度：先看标题里明确的说法，再看不太确定的说法，按下表角度的固定顺序取第一个命中的。标题里同时有「怎么选」和「实测」的，只算进「对比平替」。"
          "「标题带这类词」是标题里出现这个角度的词的篇数，不管它最后归到哪，所以可能比「篇数」多。「其他」是没能归类的笔记，不参与比较。", "",
          ("「可比篇数」是有互动数据的篇数，倍数用它们算。这一批的倍数没有按账号大小校正。" if R["adjust"] is None else
             "「可比篇数」是有互动数据、并且能按账号大小校正的篇数，倍数只用它们算；「互动中位数」用这个角度全部有互动数据的笔记算，两列的口径不同。") +
          "机会 = 可比篇数至少 %d 篇、占比不超过 20%%、相对整体 1.2 倍以上，并且不是只来自一两个账号%s。可比篇数不到 %d 篇不算倍数，显示为「—」。" % (
              MIN_GROUP, "；有互动数据的笔记不到 %d 篇时不标机会" % MIN_NOTES if thin else "；倍数没有按账号大小校正时不标机会" if loose else "", MIN_MENTIONS), "",
          "| 角度 | 篇数 | 占比 | 标题带这类词 | 互动中位数 | 可比篇数 | 相对整体 | 作者数 | 代表笔记 | 机会 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for a in R["angles"]:
        L.append("| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            a["angle"], a["count"], C.pct(a["count"], n), a["in_title"] if a.get("in_title") is not None else "—", fmt_n(a["median_engagement"]), a.get("comparable", "—"),
            times(a["vs_overall"], "%s") if a["vs_overall"] is not None and a["angle"] != "其他" else "—",
            a["authors"] if a["authors"] is not None else "—", a["best"], "✅ 供给少互动高" if a["opportunity"] else ""))
    L += ["", "## 3. 标题钩子：哪种写法互动更高", "", "标题长度中位数 %s 字。提升度 = 用了这种写法的互动中位数 ÷ 没用的；两边各少于 %d 篇不计算。「各账号内部」是在单个账号里各比一次的结果。「可用」= 样本够、倍数排除得了账号大小的影响，并且不是只来自一两个账号，或者在两个以上账号内部方向一致。" % (fmt_n(R["title_len_median"]), MIN_GROUP), "",
          "| 钩子 | 使用篇数 | 占比 | 提升度 | 作者数 | 各账号内部 | 可用 | 代表标题 |", "|---|---|---|---|---|---|---|---|"]
    for h in R["hooks"]:
        per = " / ".join("%s %.1f" % (cut(k, 8), v) for k, v in h.get("by_author", {}).items())
        L.append("| %s | %d | %s | %s | %s | %s | %s | %s |" % (h["hook"], h["used"], C.pct(h["used"], R["with_engagement"]), times(float(h["lift"])) if h["lift"] else "样本不足", h["authors"] if h["authors"] is not None else "—",
                                                         per or "—", "是" if h["solid"] else ("各账号不一致" if h.get("consistent") is False else ""), h["example"]))
    L += ["", "标题高频词：" + ("、".join("%s(%d)" % (k["word"], k["notes"]) for k in R["title_keywords"]) or "无")]
    if R["forms"]:
        L += ["", "形式：" + "；".join("%s %d 篇，互动中位数 %s" % (k, v["count"], fmt_n(v["median_engagement"])) for k, v in R["forms"].items())
              + ("。视频是图文的 %.1f 倍%s（%s）%s%s。" % (R["form_lift_video_vs_image"], "（线索）" if loose else "", R["adjust"] or "未按账号大小校正",
                                                 "；账号内部：" + " / ".join("%s %.1f" % (cut(k, 8), v) for k, v in R["form_lift_by_author"].items()) if R.get("form_lift_by_author") else "",
                                                 "；较少的一种只来自 %d 个账号，只能当线索" % min(v["authors"] for v in R["forms"].values()) if min((v["authors"] or MIN_AUTHORS) for v in R["forms"].values()) < min(MIN_AUTHORS, max(1, R["authors"])) else "")
                 if R["form_lift_video_vs_image"] else "。任何一种不到 %d 篇时不比较。" % MIN_GROUP)]
    if R["ratios"]["n"]:
        L += ["", "收藏点赞比中位数 %s，评论点赞比中位数 %s（%d 篇有数据）。收藏点赞比接近或超过 1 说明被当作资料保存。" % (R["ratios"]["collect_like_median"], R["ratios"]["comment_like_median"], R["ratios"]["n"])]
    L += ["", "## 4. 需求缺口：用户在意、但很少有笔记回应的", ""]
    if not R["gaps"]:
        L.append("没有评论数据，无法计算缺口。把两三篇竞品笔记的评论区复制下来存成文件，运行 `%s`，再重跑 analyze。" % C.cmd("comment_insight.py", "评论文件", "--research"))
    else:
        L += ["基于 %d 条评论（%s）。在意 = 吐槽 + 疑问。缺口 = 在意不少于 %d 条，且在标题回应它的笔记不超过 10%%。标题里出现同一维度的任何说法都算回应（平价、平替、十块钱都算价格）。"
              % (R.get("demand_comments", 0), R.get("demand_source", ""), MIN_MENTIONS), "",
              "| 关注点 | 吐槽 | 疑问 | 标题回应 | 仅正文提到 | 判断 | 用户原话 |", "|---|---|---|---|---|---|---|"]
        for g in R["gaps"]:
            L.append("| %s | %d | %d | %d 篇%s | %d 篇 | %s | %s |" % (g["aspect"], g["complaints"], g["questions"], g["notes_in_title"], ("（如%s）" % "".join("「%s」" % x for x in g["examples"][:2])) if g["examples"] else "", g["notes_in_body"],
                                                               ("🎯 缺口" if R.get("demand_sufficient") else "缺口（线索）") if g["gap"] else ("提及较少" if g["concern"] < MIN_MENTIONS else "已有供给"), " / ".join("“%s”" % cut(q) for q in g["quotes"])))
        L += ["", "「标题回应」只认字面：标题里有这个维度词表里的词才算。括号里是算进去的标题，最多列两篇，全部在 analysis.json 的 gaps 里；觉得漏了或多了，对着标题核一遍。"]
        if not R.get("demand_sufficient"):
            L += ["", "⚠️ 评论不到 %d 条（或解析有疑点），缺口只能当线索。" % ci.MIN_COMMENTS]
        if R.get("embedded_unused"):
            L += ["", "笔记数据里还自带 %d 条评论，这次没有用：有评论洞察文件时只用洞察文件。想一起算，把这些评论另存成文件，和原来的评论文件一起交给 comment_insight.py --research（可以一次给多个文件）。" % R["embedded_unused"]]
        if R.get("question_topics"):
            L += ["", "评论区的问题，按主题计数（可直接做选题）："] + ["- **%s** %d 条：%s" % (q["topic"], q["count"], " / ".join(cut(x) for x in q["examples"])) for q in R["question_topics"]]
    L += ["", "## 5. 低粉爆款：最值得模仿的", "", "条件：粉丝少于 5000 且点赞过千，或点赞不少于 300 且赞粉比不低于 1。说明靠的是内容而不是账号。", ""]
    L += (["- " + fmt_note(b) for b in R["low_fan_hits"]] or ["- 未发现（%s）。" % ("没有粉丝数据" if R["missing"]["followers"] == n else "现有笔记里没有符合条件的")])
    L += ["", "## 6. 综合评分 Top %d" % len(R["top_notes"]), "", "评分 = 互动分位 40% + 时效 25% + 赞粉比 35%（无粉丝数时为互动 60% + 时效 40%）。", ""]
    L += ["%d. %s" % (i + 1, fmt_note(b)) for i, b in enumerate(R["top_notes"])] or ["没有可排序的笔记（缺互动数据）。"]
    L += ["", "## 7. 发布假设候选", ""]
    for i, h in enumerate(R["hypotheses"], 1):
        L += ["%d. **%s**：%s" % (i, h["basis"], h["hypothesis"]), "   - 依据：%s" % h["evidence"], "   - 主指标：%s" % h["metric"]]
    if not R["hypotheses"]:
        L.append("数据没有给出达到标准的假设。")
    L += ["- " + w for w in R["no_hypothesis_reasons"]]
    if not R["hypotheses"]:
        if R.get("leads"):
            L += ["", "**线索候选**（没有达到标准，只能先试试看。选它的话，登记时把「依据」和「还差什么」一起抄进 --evidence，开头写「先当线索」）：", ""]
            for i, h in enumerate(R["leads"], 1):
                L += ["%d. **%s（线索）**：%s" % (i, h["basis"], h["hypothesis"]), "   - 依据：%s" % h["evidence"], "   - 还差什么：%s" % h["short_of"], "   - 主指标：%s" % h["metric"]]
            L += ["", "补数据后重跑，线索可能变成正式的候选。"]
        else:
            L.append("可以补数据后重跑；也可以由你根据上面的表提出假设，但要在依据里写明「先当线索」和还差什么。")
    L += ["", "只选一条登记：`%s`" % C.cmd("launch_log.py", "add", "--title", '"暂定标题"', "--angle", '"角度"', "--hypothesis", '"假设"', "--evidence", '"依据"')]
    if R.get("no_comparator"):
        L += ["", "还没有一篇有数据的发布可以比，所以「高于基线」「高于 L1」这类假设暂时比不了。两条路选一条：",
              "- 这一篇照常登记假设。发布后的结论先记「证据不足」，它的数据就是下一篇的对照。",
              "- 以前发过同一个产品的笔记，先把它登记成基线：`%s`" % C.cmd("launch_log.py", "add", "--title", '"那一篇的标题"', "--baseline", "--published", "发布日期")]
    return "\n".join(L)


# ---------- 命令 ----------

def split(s):
    return [x.strip() for x in re.split(r"[,，、;；]", s or "") if x.strip()]


def corpus_path(a):
    return getattr(a, "corpus", None) or C.P(a, "research", "notes.json")


PERSONA = r"学生党|打工人|上班族|宝妈|宝爸|新手|小白|租房党?|宿舍党?|社畜|懒人|通勤党?|出差党?|独居|合租|备考|考研党?|加班|熬夜|带娃|健身|露营|程序员|[\u4e00-\u9fff]{2,3}(?:党|星人|人群|肌|皮)"
MUST_TERMS, TOP_PER_TERM = 4, 8          # 手动调研的工作量：4 个必搜词，每个看前 8 篇，一共 30 篇左右
NOTHING = re.compile(r"无|没有|暂无|不知道|不清楚|不确定|none", re.I)


UNIT = r"(?:元|块钱?|毛|rmb|¥|￥|g|克|kg|千克|公斤|斤|ml|毫升|l|升|oz|片|粒|颗|支|瓶|盒|包|袋|条|抽|只|个|枚|件|寸|cm|mm|米|瓦|w|mah|小时|分钟|天|折|%)"


def spec_only(point):
    """卖点是不是只有价格或规格（「39元50g」「39元一支」）：这种词搜不出同类笔记。"""
    rest = re.sub(r"\d+(?:\.\d+)?\s*%s?" % UNIT, "", _norm_point(point), flags=re.I)
    return len(re.sub(r"[一每仅才约起只就装/]|%s" % UNIT, "", rest, flags=re.I)) < 2


def short_point(s, c=""):
    """卖点原话 → 放进搜索框的词。6 个字以内原样用；更长的取「的」或逗号前后第一段够短的（「雨后森林的味道」→「雨后森林」），取不出来就用原话。"""
    s = s.strip()
    if C.xhs_len(s) <= 6:
        return s
    for part in re.split(r"[的，,、；;。\s]+", s):
        if 2 <= C.xhs_len(part) <= 6 and re.search("[一-鿿]{2}", part) and part not in c and not (c and c in part):
            return part
    return s


def search_words(sells, aud, c=""):
    """档案里的卖点和人群 → 适合放进搜索框的短词。返回 (卖点词, 人群词, 搜不了的卖点)。
    只有价格或规格的卖点不拿来搜，带数字的排到后面，太长的取前半句；
    人群描述太长时取里面的人群词，中心词（一般在最后）排第一（「租房独居的上班族」→ 上班族、租房、独居）。"""
    skipped = [s for s in sells if spec_only(s)]
    sells = [s for s in sells if not spec_only(s)]
    sells = [s for s in sells if not re.search(r"\d", s)] + [s for s in sells if re.search(r"\d", s)]
    words, short = [], []
    for s in sells:
        w = short_point(s, c)
        if w not in words:
            words.append(w)
    for x in aud:
        m = re.findall(PERSONA, x)
        for w in ([x] if len(x) <= 6 else m[::-1][:1] + m[:-1]):
            if w and w not in short:
                short.append(w)
    return words, short, skipped


def cmd_keywords(a):
    prod = (C.read_json(C.log_path(a)) or {}).get("product") or {}
    c = (a.category or prod.get("category") or "").strip()
    if not c:
        sys.exit("还不知道品类。加上 --category \"品类\"，或者先建档（建档后不用再写品类和卖点）：%s" % C.cmd(
            "launch_log.py", "init", "--product", '"产品名"', "--category", '"品类"', "--audience", '"目标人群"', "--selling-points", '"卖点1,卖点2"', "--goal", "互动"))
    facts = prod.get("facts") or {}
    known = lambda k: [x for x in split(facts.get(k)) if not NOTHING.fullmatch(x)]      # 档案里的可选事实：常见吐槽、竞品
    from_profile = [name for name, flag, v in (("品类", a.category, prod.get("category")), ("卖点", a.selling_points, prod.get("selling_points")),
                                               ("人群", a.audience, prod.get("audience")), ("痛点", a.pains, known("常见吐槽")), ("竞品", a.competitors, known("竞品"))) if not flag and v]
    pains, comps = split(a.pains) or known("常见吐槽"), split(a.competitors) or known("竞品")
    sells, aud, no_search = search_words(split(a.selling_points) or list(prod.get("selling_points") or []), split(a.audience) or split(prod.get("audience")), c)
    a.product = a.product or prod.get("name")
    left = []
    if a.full:
        G = [("品类基础（看整体供给）", [c + " 推荐", c + " 测评", c + " 怎么选"]),
             ("反面（看真实痛点）", [c + " 避雷", c + " 踩坑", c + " 缺点", c + " 后悔"]),
             ("卖点直搜（看有没有人讲过）", ["%s %s" % (c, s) for s in sells[:3]]),
             ("教程与用法（看使用门槛）", [c + " 教程", c + " 怎么用", c + " 新手"]),
             ("对比与平替（看决策逻辑）", [c + " 对比", c + " 平替"] + ["%s vs %s" % (comps[i], comps[i + 1]) for i in range(len(comps) - 1)][:2]),
             ("人群与场景（找细分入口）", ["%s %s" % (x, c) for x in aud[:3]]),
             ("竞品（逐个搜，看评论区）", comps[:5] + [x + " 缺点" for x in comps[:2]]),
             ("痛点直搜（验证缺口）", ["%s %s" % (c, p) for p in pains[:4]]),
             ("自家产品（已有口碑）", [a.product, a.product + " 真实测评"] if a.product and a.launched else [])]
    else:
        must = [c + " 推荐", c + " 测评", c + " 避雷"] + ["%s %s" % (c, s) for s in sells[:1]]
        if len(must) < MUST_TERMS:
            must.append(c + " 怎么选")
        G = [("必搜（%d 个）" % len(must), must),
             ("时间够再搜（可选）", ["%s %s" % (c, s) for s in sells[1:2]] + ["%s %s" % (c, p) for p in pains[:3]] + ["%s %s" % (x, c) for x in aud[:2]] + [x + " 测评" for x in comps[:1]])]
        if not G[1][1]:
            G[1][1].append(c + " 缺点")
        left = [(name, xs) for name, xs in (("卖点", sells[2:]), ("痛点", pains[3:]), ("人群", aud[2:]), ("竞品", comps[1:])) if xs]
    print("# 搜索词：%s%s\n" % (c, "（完整矩阵）" if a.full else ""))
    if from_profile:
        print("%s取自产品档案。\n" % "、".join(from_profile))
    n = 0
    for name, ks in G:
        ks = [k for k in ks if k]
        if not ks:
            continue
        print("## %s" % name)
        for k in ks:
            n += 1
            print("%d. %s" % (n, k))
        print()
    notes = []
    if no_search:
        notes.append("卖点「%s」只有价格或规格，搜不出同类笔记，没有拿来搜" % "」「".join(no_search))
    long = [s for s in sells[:2] if C.xhs_len(s) > 8]
    if long and not a.full:
        notes.append("卖点「%s」原话偏长，搜的时候可以只留核心的几个字" % "」「".join(long))
    if left:
        notes.append("没有排进去的：%s。想搜就照「品类 + 词」自己加" % "；".join("%s「%s」" % (name, "」「".join(xs)) for name, xs in left))
    if notes:
        print("说明：%s。\n" % "；".join(notes))
    if a.full:
        print("完整矩阵适合有搜索工具、能自动抓取的时候用。手动搜索用不带 --full 的那一份：%d 个必搜词就够。" % MUST_TERMS)
    else:
        print("工作量：必搜的 %d 个词，每个看「综合」排序的前 %d 篇，一共 %d 篇左右，最少 %d 篇。可选的词每搜一个多看 %d 篇左右，不搜也能分析。" % (
            MUST_TERMS, TOP_PER_TERM, MUST_TERMS * TOP_PER_TERM // 10 * 10, MIN_NOTES, TOP_PER_TERM))
        print("结果怎么带回来：")
        print("- 电脑网页版（浏览器打开 xiaohongshu.com）：在搜索结果页全选、复制，整段粘贴过来，不用整理。")
        print("- 手机 App：搜索结果页一般选不了字，截图发过来，由助手照着图转写成每行一篇（标题 | 作者 昵称 | 赞 数字）。")
        print("这样带回来的每篇只有标题、作者和点赞数，够看撞卖点、角度分布和标题写法；没有粉丝数，所以认不出低粉爆款，各种倍数也没法按账号大小校正，只能当线索。")
        print("每个词的结果由助手存成一个文件，放在 %s 里，再入库：" % C.where(C.P(a, "inbox")))
        print("  %s" % C.cmd("research.py", "add", "文件", "--keyword", '"搜索词"'))
        print("还要评论：从搜到的笔记里挑 2 到 3 篇评论多的，把评论区一起带回来，一共 %d 条以上，并记下每篇笔记作者的昵称。没有评论也能分析，只是少了「需求缺口」这一节。评论的命令在入库之后给出。" % ci.MIN_COMMENTS)
        print("想要更全的搜索词（有自动搜索工具时）加 --full。")
    miss = [x for x, v in (("--selling-points", sells), ("--pains", pains), ("--audience", aud), ("--competitors", comps)) if not v]
    if miss:
        print("\n提示：补充 %s 可以得到更贴近产品的搜索词。用户不知道竞品或痛点的话不用追问，搜完「避雷」那个词自然就有了。" % " ".join(miss))


def cmd_add(a):
    C.check_cwd()
    path = corpus_path(a)
    old = [] if a.replace else load_corpus(path)
    new, any_warn = [], False
    for f in a.files:
        if f != "-" and not os.path.exists(f):
            sys.exit("找不到文件：%s（当前目录 %s）" % (f, os.getcwd()))
        got, info = read_notes(f, a.keyword or "")
        if not got:
            sys.exit("%s 里没有识别到笔记。可以直接粘贴搜索结果页复制的内容，或者每行一篇：标题 | 赞 1.2万 | 藏 800 | 评 56 | 粉丝 900 | 作者 小鹿 | 2026-11-01 | 链接" % f)
        print("读取 %s：识别为「%s」，共 **%d** 篇。" % ("标准输入" if f == "-" else os.path.basename(f), info["format"], len(got)))
        for i, n in enumerate(got[:3], 1):
            print("  %d. %s｜作者 %s｜赞 %s 藏 %s 评 %s｜%s" % (i, n["title"][:40], n["author"] or "—", fmt_n(n["likes"]), fmt_n(n["collects"]), fmt_n(n["comments"]), n["date"] or "日期—"))
        if len(got) > 3:
            print("  …最后一篇：%s｜作者 %s｜赞 %s" % (got[-1]["title"][:40], got[-1]["author"] or "—", fmt_n(got[-1]["likes"])))
        for w in info.get("notes", []):
            print("  说明：%s" % w)
        for w in info["warnings"]:
            any_warn = True
            print("  ⚠️ %s" % w)
        new += got
    lack = ["%s %d 篇" % (ZH[k], v) for k, v in ((k, sum(1 for n in new if not n[k] and n[k] != 0)) for k in ("likes", "collects", "comments", "followers", "date", "author")) if v]
    if lack:
        print("缺失（按未知处理，不当 0）：%s。" % "，".join(lack))
    if all(n["likes"] is None for n in new):
        any_warn = True
        print("⚠️ 这批笔记都没有点赞数：只能分析「大家在发什么」，比不出「什么写法表现好」。有数字的话请带上重新入库。")
    merged, dup = dedupe(old + new)
    if a.replace and os.path.exists(path):
        shutil.copyfile(path, path + ".bak")
    save_corpus(path, merged)
    print("语料库 %d → %d 篇%s。保存在 %s" % (len(old), len(merged), ("（合并重复 %d 篇）" % dup) if dup else "", C.where(path)))
    print("请核对上面的篇数和前几条：%s篇数不对或标题、作者错位时，把内容整理成每行一篇后运行 %s" % ("有 ⚠️ 时尤其要看。" if any_warn else "", C.cmd("research.py", "add", "文件", "--replace")))
    prod = (C.read_json(C.log_path(a)) or {}).get("product") or {}
    steps = []
    if len(merged) < MIN_NOTES:
        steps.append("笔记还差 %d 篇到 %d 篇：再搜一两个词入库。现在就分析的话，结果只能当线索。" % (MIN_NOTES - len(merged), MIN_NOTES))
    if not os.path.exists(C.P(a, "research", "insight.json")):
        steps.append("评论还没有：挑 2 到 3 篇评论多的笔记，把评论区存成文件（一共 %d 条以上），作者的昵称各写一个 --author。没有评论就没有「需求缺口」这一节：\n   %s"
                     % (ci.MIN_COMMENTS, C.cmd("comment_insight.py", "评论文件", "--research", "--author", '"作者昵称"')))
    steps.append("分析%s：\n   %s" % ("（品类和卖点自动取自产品档案）" if prod.get("selling_points") else "", C.cmd("research.py", "analyze") if prod.get("selling_points")
                                   else C.cmd("research.py", "analyze", "--topic", '"品类"', "--selling-terms", '"卖点=别的说法1/别的说法2"')))
    print("下一步：")
    for i, s in enumerate(steps, 1):
        print("%d. %s" % (i, s))


def cmd_status(a):
    path = corpus_path(a)
    notes = load_corpus(path)
    if not notes:
        print("语料库为空（%s）。先运行 keywords 拿搜索词，再用 add 入库。" % C.where(path))
        return
    kws = Counter(k for n in notes for k in (n["keywords"] or ["未标注"]))
    print("语料库 %d 篇｜有点赞数 %d｜有粉丝数 %d｜有日期 %d｜作者 %d 个｜自带评论 %d 条" % (
        len(notes), sum(1 for n in notes if n["likes"] is not None), sum(1 for n in notes if n["followers"] is not None),
        sum(1 for n in notes if n["date"]), len({n["author"] for n in notes if n["author"]}), sum(len(n.get("comment_list", [])) for n in notes)))
    print("按搜索词：" + "；".join("%s %d" % kv for kv in kws.most_common()))
    print("位置：%s" % C.where(path))


def cmd_analyze(a):
    path = corpus_path(a)
    notes = load_corpus(path)
    if not notes:
        sys.exit("语料库为空（%s）。先用 add 入库。" % C.where(path))
    ipath = a.insight or C.P(a, "research", "insight.json")
    if a.insight and not os.path.exists(a.insight):
        sys.exit("找不到洞察文件：%s" % a.insight)
    insight = C.read_json(ipath)
    prod = (C.read_json(C.log_path(a)) or {}).get("product") or {}
    terms = selling_terms(prod.get("selling_points") or [], split(a.selling_terms))
    topic = a.topic or prod.get("category") or prod.get("name") or ""
    lex = ci.Lexicon([C.P(a, "lexicon.json")])
    R = analyze(notes, a.days, a.top, insight, terms, lex)
    if R is None:
        sys.exit("时间窗内没有笔记，请加大 --days 或用 --days 0 关闭时间窗。")
    launches = (C.read_json(C.log_path(a)) or {}).get("launches") or []
    R["no_comparator"] = not any(l.get("metrics") for l in launches)       # 还没有一篇有数据的发布：假设暂时没有对照
    md = to_markdown(R, topic)
    stem = os.path.splitext(os.path.basename(path))[0]
    base = os.path.dirname(os.path.abspath(path))
    jpath = a.json or os.path.join(base, "analysis.json" if stem == "notes" else stem + "_analysis.json")
    mpath = a.out or os.path.join(base, "brief.md" if stem == "notes" else stem + "_brief.md")
    C.write_json(jpath, R)        # 供阶段②的 content_plan.py 读取
    C.write_text(mpath, md + "\n")
    print(md)
    print("\n已保存：%s（报告）、%s（数据）" % (C.where(mpath), C.where(jpath)))


def build_parser():
    ap = argparse.ArgumentParser(description="小红书发布前调研")
    C.add_dir_arg(ap)
    ap.add_argument("--corpus", help="语料库路径，默认是 数据目录/research/notes.json")
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True

    def sp(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        C.add_dir_arg(s)
        s.add_argument("--corpus", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        s.set_defaults(fn=fn)
        return s

    s = sp("keywords", cmd_keywords, "给出搜索词")
    s.add_argument("--category", help="品类，例如 护手霜。不写时用产品档案里的")
    s.add_argument("--selling-points", help="核心卖点，逗号分隔。不写时用产品档案里的")
    s.add_argument("--audience", help="目标人群，逗号分隔。不写时用产品档案里的")
    s.add_argument("--pains", help="已知痛点，逗号分隔")
    s.add_argument("--competitors", help="竞品名，逗号分隔")
    s.add_argument("--product", help="产品名（配合 --launched）")
    s.add_argument("--launched", action="store_true", help="产品已经上市：加一组搜自家口碑的词")
    s.add_argument("--full", action="store_true", help="输出完整搜索词矩阵")
    s = sp("add", cmd_add, "把笔记并入语料库")
    s.add_argument("files", nargs="+", metavar="文件", help="笔记文件（可多个；- 表示标准输入）")
    s.add_argument("--keyword", help="这批笔记是用哪个搜索词搜到的")
    s.add_argument("--replace", action="store_true", help="清空语料库后重新入库（旧文件备份为 .bak）")
    sp("status", cmd_status, "语料库概况")
    s = sp("analyze", cmd_analyze, "分析语料库")
    s.add_argument("--topic", default="", help="品类名，用作报告标题")
    s.add_argument("--selling-terms", help="查「撞卖点」用的说法，逗号分隔，每项写成 卖点=说法1/说法2；产品档案里的卖点会自动带上，这里用来补充同义说法或另加卖点")
    s.add_argument("--days", type=int, default=90, help="只分析最近 N 天，0 为不限")
    s.add_argument("--top", type=int, default=10, help="综合评分列出前 N 篇，默认 10")
    s.add_argument("--insight", help="评论洞察 json；不填时自动读 数据目录/research/insight.json")
    s.add_argument("--out", help="报告保存路径，默认 数据目录/research/brief.md")
    s.add_argument("--json", help="分析数据保存路径，默认 数据目录/research/analysis.json")
    return ap


def main():
    a = build_parser().parse_args()
    C.data_dir(a)
    a.fn(a)


if __name__ == "__main__":
    C.run(main)

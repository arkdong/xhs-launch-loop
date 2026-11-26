#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布方案：把调研结论变成「发什么、每一页放什么」，并生成配图提示词。

用法（在你自己的工作目录运行，脚本用绝对路径）:
  python3 content_plan.py new --id L1 [--template 模板] [--goal 触达|互动|收藏] [--style 风格] [--pages N] [--force]
      读发布日志和调研分析，生成待填写的方案：数据目录/plans/L1.json
  python3 content_plan.py show --id L1        以 Markdown 查看方案
  python3 content_plan.py check --id L1       检查是否填完整、有没有占位内容、是否合规；通过后导出 plans/L1_draft.txt
  python3 content_plan.py prompts --id L1 [--with-text] [--out 文件]   生成每一页的配图提示词
  python3 content_plan.py templates           列出内容模板、发布目标和配图风格
数据目录默认是当前目录下的 xhs_launch，可用 --dir 指定。只依赖 Python 3 标准库。
脚本不编造产品信息：价格、时长、缺点等来自产品档案（launch_log.py init / fact），缺的会列出来。
"""
import argparse, json, os, re, shutil, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import launch_log as ll  # noqa: E402
import note_check as nc  # noqa: E402
import research as rs  # noqa: E402

COVER_MAX, PAGE_TEXT_MAX, MAX_PAGES = 12, 40, 18
SPEED_MAX, SHOT_SPEED_MAX = 5, 7      # 口播语速：全片平均每秒 5 字以内；单个镜头超过每秒 7 字就提醒

# 模板：(页面角色, 这一页要完成的任务, 构图提示)
T = {
    "上线公告": {"match": ["上线", "公告", "内测", "开放", "更新", "首发"], "pages": [
        ("是什么", "一句话说明上线了什么、对谁有用", "产品或功能主体特写"),
        ("怎么用", "三步以内的使用方法", "纯色背景步骤卡片"),
        ("亮点与权益", "读者能得到什么，带具体数字和时间", "纯色背景信息卡片"),
        ("常见问题", "预先回答两到三个最可能被问的问题", "纯色背景问答卡片")]},
    "征集互动": {"match": ["征集", "互动", "晒", "安利", "投稿", "接龙", "一人一个"], "pages": [
        ("征集什么", "一句话说清要大家发什么，并给一个示例", "示例作品或场景图"),
        ("怎么参与", "带什么话题、发在哪里、起止时间", "纯色背景步骤卡片"),
        ("有什么回报", "奖励或回应方式，带具体数字", "纯色背景信息卡片"),
        ("规则说明", "不符合条件的情况和截止时间", "纯色背景清单卡片")]},
    "结果公布": {"match": ["公布", "获奖", "结果", "榜单", "复盘", "总结"], "pages": [
        ("总体结果", "参与人数、作品数等总数字", "纯色背景大数字卡片"),
        ("亮点一", "点名一位参与者或一条反馈，说明好在哪", "该作品或反馈的截图式画面"),
        ("亮点二", "第二个亮点", "该作品或反馈的截图式画面"),
        ("我们改了什么", "根据反馈做的改动和下一步计划", "纯色背景信息卡片")]},
    "深度长文": {"match": ["一文", "长文", "拆解", "原理", "深度", "读懂"], "pages": [
        ("导读", "三行以内的摘要：问题、做法、结果", "纯色背景文字卡片"),
        ("背景与问题", "为什么要做，原来卡在哪", "示意图"),
        ("方案", "怎么做的，一张结构图说清", "结构示意图"),
        ("效果", "结果数字和对比", "数据图表卡片"),
        ("总结与下一篇", "一句话结论，预告后续", "纯色背景文字卡片")]},
    "情绪短片": {"match": ["情绪", "治愈", "短片", "陪伴", "萌"], "pages": [
        ("单一动作", "全片只做一个动作、只说一句话，15 秒以内", "固定机位，主体正对镜头")]},
    "避雷踩坑": {"match": ["避雷", "踩坑", "踩雷", "坑"], "pages": [
        ("坑一", "最常见的坑，说清后果", "问题细节特写"),
        ("坑二", "第二个坑", "问题细节特写"),
        ("坑三", "第三个坑", "问题细节特写"),
        ("怎么避开", "给出可照做的判断标准", "纯色背景清单卡片"),
        ("我的选择", "自己最后怎么选，以及它的缺点", "产品在真实场景中")]},
    "测评实测": {"match": ["测评", "实测", "评测", "体验", "亲测"], "pages": [
        ("结论先行", "一句话结论和适合谁", "纯色背景结论卡片"),
        ("维度一", "第一个测评维度和实测数字", "实测过程特写"),
        ("维度二", "第二个维度和数字", "实测过程特写"),
        ("维度三", "第三个维度和数字", "实测过程特写"),
        ("缺点与适合谁", "缺点、不适合的人", "纯色背景信息卡片")]},
    "教程攻略": {"match": ["教程", "攻略", "步骤", "喝法", "做法", "怎么用", "怎么做"], "pages": [
        ("准备清单", "需要的东西和数量", "俯拍平铺所有物品"),
        ("步骤一", "第一步，动作和用量", "俯拍手部操作"),
        ("步骤二", "第二步", "俯拍手部操作"),
        ("步骤三", "第三步，出成品", "俯拍手部操作"),
        ("常见翻车点", "最容易出错的地方和补救", "纯色背景提示卡片")]},
    "对比平替": {"match": ["对比", "平替", "vs", "怎么选", "横评"], "pages": [
        ("对比总表", "三到四个维度的对比表", "纯色背景表格卡片"),
        ("差异一", "最大的差异，带数字", "左右分屏对比"),
        ("差异二", "第二个差异", "左右分屏对比"),
        ("怎么选", "选 A 如果…选 B 如果…", "纯色背景决策卡片")]},
    "答疑科普": {"match": ["答疑", "科普", "为什么", "真的吗", "问答", "疑问"], "pages": [
        ("一句话答案", "先给答案，不绕弯", "纯色背景大字卡片"),
        ("原因一", "第一个原因，用大白话", "示意图或细节特写"),
        ("原因二", "第二个原因", "示意图或细节特写"),
        ("怎么做", "读者可以照做的方法", "纯色背景步骤卡片")]},
    "清单合集": {"match": ["清单", "合集", "盘点", "推荐"], "pages": [
        ("条目一", "名称、一句话理由、价格或数字", "单品特写"),
        ("条目二", "同上", "单品特写"),
        ("条目三", "同上", "单品特写"),
        ("条目四", "同上", "单品特写"),
        ("总结表", "一张表看完所有条目", "纯色背景表格卡片")]},
    "个人故事": {"match": ["故事", "经历", "记录", "日记"], "pages": [
        ("之前", "当时的状态和问题", "生活场景，偏暗色调"),
        ("转折", "发生了什么、做了什么改变", "动作瞬间特写"),
        ("之后", "现在的结果，带数字", "生活场景，明亮色调"),
        ("学到的", "一条可以带走的经验", "纯色背景金句卡片")]},
    "发布体": {"match": ["发布", "新品", "上新", "痛点", "种草"], "pages": [
        ("痛点场景", "用一个具体场景或用户原话说出痛点", "生活场景，人物处在困扰中，不露正脸"),
        ("这是什么", "一句话说明产品和它解决什么", "产品主体特写，背景干净"),
        ("要点一", "最重要的一个事实，带数字", "使用过程特写"),
        ("要点二", "第二个事实，带数字", "使用结果或对比"),
        ("缺点与适合谁", "至少一条缺点，一句适合人群", "纯色背景信息卡片")]},
}
# 正文分几段、每段写什么。多数模板用通用的五段；公告、征集、结果、长文、短片各有自己的骨架（依据见 references/content_rules.md 第 5 节）。
BODY_DEFAULT = [
    ("开头钩子", "30 字内，用用户原话或具体场景，直接回应痛点"),
    ("我为什么能说", "一句话：真实使用时长，以及你和产品的关系（品牌方、店主要直接说）"),
    ("正文要点", "与各{unit}一一对应，每点一行并带具体数字"),
    ("缺点与适合谁", "至少一条缺点，这是可信度的来源"),
    ("结尾提问", "一个容易回答的具体问题，优先用调研里被问得多的主题"),
]
BODY = {
    "上线公告": [
        ("开头钩子", "30 字内，用读者的处境或一个问题开头"),
        ("是什么", "两行说清上线了什么、对谁有用，并说明你和产品的关系"),
        ("怎么参与", "📅 时间 ✅ 使用或参与方式，每项一行"),
        ("回报与限制", "🎁 读者能得到什么（带数字）⚠️ 哪些情况不算、有什么限制"),
        ("结尾提问", "一个容易回答的具体问题"),
    ],
    "征集互动": [
        ("开头钩子", "30 字内，用读者的处境或一个问题开头"),
        ("征集什么", "一句话说清要大家发什么，给一个示例。要求小而具体：一人一个、发一张图、不用精修"),
        ("怎么参与", "📅 起止时间 ✅ 发在评论区还是带话题发笔记"),
        ("回报与规则", "🎁 奖励或回应方式（带数字）⚠️ 不符合条件的情况"),
        ("结尾提问", "把征集的要求再问一遍，让人看完就能回"),
    ],
    "结果公布": [
        ("开头钩子", "一句话说结果，带总数字"),
        ("亮点", "点名一到两位参与者或一条反馈，说明好在哪，并注明来源"),
        ("我们改了什么", "根据反馈做的改动，写具体改了哪里"),
        ("接下来", "下一步计划和时间"),
        ("结尾提问", "一个容易回答的具体问题"),
    ],
    "深度长文": [
        ("导读", "三行以内：问题、做法、结果"),
        ("我为什么能说", "一句话：你做了什么、做了多久，以及你和产品的关系"),
        ("要点摘要", "正文只放 300 到 600 字的摘要，每个要点带数字，细节放在图里"),
        ("局限", "这个做法的局限，或不适用的情况"),
        ("结尾提问", "一个容易回答的具体问题"),
    ],
    "情绪短片": [
        ("一句话", "60 到 70 字，只补一句画面里没说的话"),
        ("结尾提问", "一个不费力就能回的问题"),
    ],
}
STYLES = {
    "实拍生活感": "真实手机摄影质感，自然窗边光，生活化场景，轻微景深，色彩真实不过饱和，像普通人随手拍但构图干净",
    "知识卡片": "扁平化信息图卡片，纯色或浅色渐变背景，大面积留白，简洁图标，圆角矩形分区，排版清晰",
    "手绘插画": "手绘风格插画，柔和线条，低饱和配色，可爱但不幼稚，留白充足",
    "产品特写": "商业产品摄影，柔和棚拍光，干净的纯色背景，材质细节清晰，轻微倒影",
    "对比拼图": "左右分屏对比构图，中间细分隔线，两侧光线和角度一致，差异一目了然",
}
NEGATIVE = "水印，logo，品牌商标，乱码文字，变形的手，多余的手指，畸形人脸，真实名人，低清晰度，过度磨皮，过度饱和，塑料质感"
# 发布目标 → 常用模板和依据（依据见 references/content_rules.md 的样本分析，是官方账号的做法，只作参考）
GOAL_TEMPLATES = {
    "触达": (["情绪短片", "上线公告"], "样本里薯队长的短视频点赞中位数约为同账号图文的 12 倍；公告类标题直接说新闻"),
    "互动": (["征集互动", "答疑科普"], "样本里请每个人在评论区发一样具体东西的笔记，评论数超过点赞数"),
    "收藏": (["深度长文", "教程攻略", "对比平替"], "样本里规则说明和深度长文的收藏数接近或超过点赞数"),
}
SERIES_PREFIX = re.compile(r"^\s*([Vv]ol\.?\s*\d|第\s*\d+\s*[期弹]|0?\d\s*[｜|])")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
# 占位内容：没写完就留在方案里的字样。「期待补货」「等待确认」「XXL」这类正常说法不算。
PLACEHOLDER = re.compile(
    r"(?<![期等接招对看款交虐善优亟])待(?:填|补|定|写|确认|提供|用户|核实|更新|替换|完善)"
    r"|(?<![A-Za-z])(?i:todo|tbd|fixme)(?![A-Za-z])|(?<![A-Za-z])[Xx]{2,}(?![A-Za-z])|[＿_]{2,}"
    r"|【\s*(?:请|此处|这里|填|写|补)[^】]*】|【\s*】|[（(\[]\s*(?:待|请填|请补|此处|这里填)[^）)\]]*[）)\]]|占位(?:符|内容|文字)|同上")
OWNER = re.compile(r"品牌方|主理人|创始人|老板|店主|店家|掌柜|自家|自己(?:的)?(?:品牌|店|产品|公司)|自己做|开发者|作者本人|员工|同事|公司|官方")
PAID = re.compile(r"(?<!无)(?<!没有)(?<!不是)(?:合作|报酬|赞助|商单|送测|寄送|置换|免费(?:收到|拿到|送))")
DISCLOSE = re.compile(r"自家|我们家|我家(?:的)?(?:产品|店|品牌|小店)|本店|小店|自己做的|我做的|我们做的|我开发|我们开发|我是.{0,10}(?:主理人|店主|创始人|老板|品牌方|员工|开发者|作者)"
                      r"|主理人|品牌方|利益相关|合作|赞助|送测|官方|我们(?:的)?(?:品牌|团队|产品|店)|自己的(?:品牌|店|产品)")
NONE_WORDS = re.compile(r"^\s*(无|没有|暂无|没|none|no)\s*[。.]?\s*$", re.I)


def plan_dir(a):
    return C.P(a, "plans")


def plan_path(a):
    return os.path.join(plan_dir(a), "%s.json" % a.id.upper())


def load_plan(a):
    p = C.read_json(plan_path(a))
    if p is None:
        sys.exit("找不到发布方案 %s。先运行：%s" % (C.where(plan_path(a)), C.cmd("content_plan.py", "new", "--id", a.id.upper())))
    p.setdefault("fixed_tags", [])
    p.setdefault("tags", [])
    p.setdefault("first_comment", "")
    p.setdefault("unit", "镜头" if p.get("type") == "视频" else "页")
    p.setdefault("image", {})
    for k, v in (("style", "实拍生活感"), ("ratio", "3:4"), ("subject", ""), ("palette", ""), ("brand_tag", ""), ("real_photo_pages", [])):
        p["image"].setdefault(k, v)
    fr = p.setdefault("from_research", {})
    for k, v in (("sample", "未做调研"), ("caveats", []), ("same_selling_point", []), ("pain_quotes", []), ("questions", []), ("title_hooks_to_use", []),
                 ("title_hooks_to_avoid", []), ("title_len_median", None), ("title_keywords", []), ("reference_notes", [])):
        fr.setdefault(k, v)
    return p


def save_plan(a, plan):
    C.write_json(plan_path(a), plan)


def latest_other_plan(a):
    """沿用上一份方案的视觉设定和固定标签，保证账号的系列感。"""
    d = plan_dir(a)
    if not os.path.isdir(d):
        return None
    cands = [os.path.join(d, f) for f in os.listdir(d) if re.fullmatch(r"L\d+\.json", f) and f != "%s.json" % a.id.upper()]
    return C.read_json(max(cands, key=os.path.getmtime)) if cands else None


def blank(s):
    """空的，或者只有标点。"""
    return not re.search(r"\w", str(s or ""))


def pick_template(angle, forced, goal, is_video):
    """返回 (模板名, 为什么选它)。顺序：你指定的 > 角度对应的 > 通用的发布体。
    发布目标不决定模板（它决定主指标和结尾怎么引导），只把这个目标常用的模板作为建议列出来。"""
    angle = angle or ""
    usual = [c for c in GOAL_TEMPLATES[goal][0] if c != "情绪短片" or is_video] if goal in GOAL_TEMPLATES else []
    if forced:
        return forced, "你用 --template 指定的。"
    for name, t in T.items():
        hit = name if name in angle else next((m for m in t["match"] if m in angle.lower()), None)
        if hit and (name != "情绪短片" or is_video):
            why = "角度「%s」里有「%s」，对应这个模板。" % (angle, hit)
            if usual and name not in usual:
                why += "发布目标「%s」常用的模板是「%s」；这次的假设是围绕角度提的，所以按角度选。模板决定页面结构，目标决定主指标和结尾怎么引导。想按目标选，加 --force --template %s 重建。" % (
                    goal, "、".join(usual), usual[0])
            return name, why
    why = "角度%s没有对应的模板，用通用的「发布体」。" % ("「%s」" % angle if angle else "没填，")
    if usual:
        why += "发布目标「%s」常用的模板是「%s」，想用的话加 --force --template %s 重建。" % (goal, "、".join(usual), usual[0])
    return "发布体", why + "全部模板见 templates 子命令。"


def research_brief(R):
    """从调研分析里带出写方案用得上的东西。只带达到最低样本量的结论，其余标成线索。"""
    if not R:
        return {"sample": "未做调研", "caveats": ["没有调研分析（research.py analyze 的结果）。标题建议、用户原话和对标笔记都是空的，方案只能靠产品事实来写。"], "same_selling_point": [],
                "pain_quotes": [], "questions": [], "title_hooks_to_use": [], "title_hooks_to_avoid": [], "title_len_median": None, "title_keywords": [], "reference_notes": []}, []
    cave = []
    if not R.get("sample_sufficient", True):
        cave.append("有互动数据的笔记不到 %d 篇，标题写法的倍数只是线索。" % rs.MIN_NOTES)
    if R.get("adjust") is None and R.get("with_engagement"):
        cave.append("笔记没有粉丝数，互动高可能只是因为账号大。")
    if "demand_comments" in R and not R.get("demand_sufficient"):
        cave.append("评论不到 %d 条，用户原话只是线索。" % rs.ci.MIN_COMMENTS)
    solid = [h for h in R.get("hooks", []) if h.get("lift") and h.get("solid", True)]
    gaps = [g for g in R.get("gaps", []) if g.get("gap")] or [g for g in R.get("gaps", []) if g.get("complaints", 0) >= rs.MIN_MENTIONS][:1]
    voiced = gaps or sorted(R.get("gaps", []), key=lambda g: -g.get("concern", 0))      # 没有达到条数的痛点时，原话仍然可以借来当说法，但只是线索
    refs = (R.get("low_fan_hits") or R.get("top_notes") or [])[:3]
    same = [{"selling_point": s["selling_point"], "notes": s["notes"], "in_title": s.get("in_title", 0),
             "top_title": s["top"][0]["title"] if s.get("top") else "", "top_likes": s["top"][0].get("likes") if s.get("top") else None} for s in R.get("same_selling_point", []) if s.get("notes")]
    brief = {
        "sample": "%s 篇笔记，%s 条评论" % (R.get("analyzed", "未知"), R.get("demand_comments", "0")), "caveats": cave, "same_selling_point": same,
        "pain_quotes": [q for g in voiced[:2] for q in g.get("quotes", [])[:2]],
        "questions": ["%s（%d 条）：%s" % (q["topic"], q["count"], q["examples"][0] if q.get("examples") else "") for q in R.get("question_topics", []) if q["topic"] != "其他问题"][:4],
        "title_hooks_to_use": [h["hook"] for h in solid if h["lift"] >= 1.2][:3], "title_hooks_to_avoid": [h["hook"] for h in solid if h["lift"] <= 0.8][:3],
        "title_len_median": int(R["title_len_median"]) if R.get("title_len_median") else None, "title_keywords": [k["word"] for k in R.get("title_keywords", [])[:6]],
        "reference_notes": [{"title": n["title"], "url": n.get("url", ""), "likes": n.get("likes"), "angle": n.get("angle", "")} for n in refs],
    }
    return brief, gaps


def cmd_new(a):
    C.check_cwd()
    log = ll.load(a)
    launch = ll.find(log, a.id)
    a.id = launch["id"]
    if a.template and a.template not in T:
        sys.exit("没有模板「%s」。可用：%s" % (a.template, "、".join(T)))
    if a.style not in STYLES:
        sys.exit("没有风格「%s」。可用：%s" % (a.style, "、".join(STYLES)))
    path = plan_path(a)
    if os.path.exists(path):
        if not a.force:
            sys.exit("方案已存在：%s。继续填写即可；要重建请加 --force（旧方案会另存为 .bak）。" % C.where(path))
        shutil.copyfile(path, path + ".bak")
    R = C.read_json(getattr(a, "analysis", None) or C.P(a, "research", "analysis.json")) or {}
    prod = log["product"]
    goal = a.goal or ll.goal_of(log, launch)
    is_video = launch.get("type") == "视频"
    tname, why = pick_template(launch.get("angle", ""), a.template, goal, is_video)
    if tname == "情绪短片" and not is_video:
        sys.exit("「情绪短片」是视频模板，但 %s 登记的形式是图文。请用 --template 换一个模板，或者重新登记一篇视频：%s" % (launch["id"], C.cmd("launch_log.py", "add", "--type", "视频", "--title", '"标题"', "--hypothesis", '"假设"')))
    prev = latest_other_plan(a)
    roles = T[tname]["pages"]
    if a.pages:
        roles = roles[:max(1, a.pages - 1)]
    unit = "镜头" if is_video else "页"
    pages = [{"no": 1, "role": "封面", "task": "一眼看懂这篇讲什么、和我有什么关系；大字不超过 %d 字" % COVER_MAX,
              "composition": "主体居中偏下，上方三分之一留白放标题", "text": "", "visual": "", "product_in_frame": True}]
    for i, (role, task, comp) in enumerate(roles, 2):
        pg = {"no": i, "role": role, "task": task, "composition": comp, "text": "", "visual": "",
              "product_in_frame": not any(k in role for k in ("痛点", "之前", "转折", "原因")) and "卡片" not in comp}
        if is_video:
            pg.update({"voiceover": "", "seconds": 5})
        pages.append(pg)
    if is_video:
        pages[0].update({"voiceover": "", "seconds": 3, "task": "前 3 秒钩子：一句话痛点或结果，画面直接给结果"})
        if tname == "情绪短片":
            pages[0]["task"] = "开场：主体直接入镜，不要片头和自我介绍"

    brief, gaps = research_brief(R)
    facts = [{"key": k, "question": q, "value": str(prod["facts"].get(k) or "").strip()} for k, q in ll.FACTS.items()]
    for g in gaps[:2]:      # 调研里用户最在意的点：需要用户给出真实的回答，脚本不替他回答
        facts.append({"key": "回应「%s」" % g["aspect"], "question": "评论里有人说：%s。你的产品在这一点上的真实情况是什么？" % " / ".join("“%s”" % q for q in g.get("quotes", [])[:2]), "value": ""})
    plan = {
        "id": launch["id"], "template": tname, "template_reason": why, "type": launch.get("type", "图文"), "unit": unit,
        "product": prod["name"], "audience": prod.get("audience", ""), "tone": prod.get("tone", ""),
        "angle": launch.get("angle", ""), "hypothesis": launch["hypothesis"], "baseline": bool(launch.get("baseline")), "evidence": launch.get("evidence", ""),
        "goal": goal, "main_metric": ll.GOALS.get(goal, ""),
        "from_research": brief,
        "facts_needed": facts,
        "titles": ["", "", ""],
        "pages": pages,
        "body": [{"section": sec, "guide": guide.replace("{unit}", unit), "text": ""} for sec, guide in BODY.get(tname, BODY_DEFAULT)],
        "fixed_tags": (prev or {}).get("fixed_tags", []), "tags": [], "first_comment": "",
        "image": {"style": a.style, "ratio": "9:16" if is_video else "3:4", "subject": "", "palette": "", "brand_tag": "", "real_photo_pages": []},
    }
    if prev:   # 同一账号的图要像一套：沿用上一份方案的产品描述、配色、角标
        for k in ("subject", "palette", "brand_tag"):
            plan["image"][k] = prev.get("image", {}).get(k, "")
        if not a.style_given:
            plan["image"]["style"] = prev.get("image", {}).get("style", a.style)
    save_plan(a, plan)
    print("已生成发布方案骨架：%s（共 %d %s）" % (C.where(path), len(pages), unit))
    print("模板「%s」：%s" % (tname, why))
    if goal in GOAL_TEMPLATES:
        print("发布目标「%s」→ 主指标：%s。%s。" % (goal, ll.GOALS[goal], GOAL_TEMPLATES[goal][1]))
    else:
        print("还没定发布目标。用 %s 定下来，方案会按目标定主指标。" % C.cmd("launch_log.py", "init", "--force", "--goal", "触达|互动|收藏"))
    if prev:
        print("已沿用 %s 的配图设定和固定标签，保持系列一致。" % prev["id"])
    print()
    print(render(plan))
    miss = [f for f in facts if blank(f["value"])]
    print("\n下一步：")
    if miss:
        std = [f["key"] for f in miss if f["key"] in ll.FACTS]
        print("1. 上面打了空格 [ ] 的 %d 项信息，一次问清用户（不要分几轮问），没有的填「无」。" % len(miss))
        if std:
            print("   产品事实写进档案，以后每篇都能复用：%s" % C.cmd("launch_log.py", "fact", *['%s="…"' % k for k in std]))
        if len(std) < len(miss):
            print("   「回应…」是这一篇特有的，直接填在方案文件 facts_needed 对应项的 value 里。")
        print("2. 填写方案文件里所有空字段（titles、pages 的 text 和 visual、body 的 text、tags、first_comment、image）。")
        print("3. 检查：%s" % C.cmd("content_plan.py", "check", "--id", plan["id"]))
    else:
        print("1. 产品事实已齐。填写方案文件里所有空字段（titles、pages 的 text 和 visual、body 的 text、tags、first_comment、image）。")
        print("2. 检查：%s" % C.cmd("content_plan.py", "check", "--id", plan["id"]))


def text_name(p):
    """pages 里的 text：图文是图上的字，视频是这一镜的字幕或贴纸。"""
    return "字幕或贴纸" if p.get("type") == "视频" else "图上文字"


def all_tags(p):
    """固定标签每篇都带：导出成稿时自动排在前面，不用在 tags 里重复写。"""
    out = []
    for t in list(p.get("fixed_tags", [])) + list(p.get("tags", [])):
        t = str(t).strip().lstrip("#").strip()
        if t and t not in out:
            out.append(t)
    return out


def render(p):
    fr = p["from_research"]
    likes = lambda n: "赞 %s" % ("未知" if n.get("likes") is None else n["likes"])
    L = ["# 发布方案 %s：%s" % (p["id"], p["product"]), "",
         "- 形式：%s｜模板：%s｜角度：%s" % (p["type"], p["template"], p["angle"] or "未填"),
         "- 目标人群：%s｜语气：%s" % (p["audience"] or "未填", p["tone"] or "未填"),
         "- %s" % ("基线：这一篇没有假设，只记录数据" if p.get("baseline") else "发布假设：%s" % p["hypothesis"]), "- 依据：%s" % (p["evidence"] or "未填"),
         "- 发布目标：%s｜主指标：%s" % (p.get("goal") or "未定", p.get("main_metric") or "未定"), "",
         "## 来自调研（%s）" % fr["sample"], ""]
    L += ["- ⚠️ " + c for c in fr["caveats"]]
    for s in fr["same_selling_point"]:
        L.append("- 撞卖点：已有 %d 篇笔记在讲「%s」（%d 篇写进标题），最高的一篇是「%s」（%s）。这一篇要讲出不一样的地方。" % (
            s["notes"], s["selling_point"], s["in_title"], s["top_title"], "赞 %s" % ("未知" if s["top_likes"] is None else s["top_likes"])))
    L += ["- 用户原话：%s" % (" / ".join("“%s”" % q for q in fr["pain_quotes"]) or "没有"),
          "- 被问得多的主题：%s" % ("；".join(fr["questions"]) or "没有"),
          "- 标题写法：%s%s；长度参考：%s；高频词：%s" % (
              "建议用「%s」" % "」「".join(fr["title_hooks_to_use"]) if fr["title_hooks_to_use"] else "调研里没有达到样本量的写法结论",
              "；谨慎用「%s」" % "」「".join(fr["title_hooks_to_avoid"]) if fr["title_hooks_to_avoid"] else "",
              "%s 字" % fr["title_len_median"] if fr["title_len_median"] else "未知", "、".join(fr["title_keywords"]) or "没有"),
          "- 对标笔记：%s" % ("；".join(("[%s](%s)" % (n["title"], n["url"]) if n["url"] else "「%s」" % n["title"]) + "（%s）" % likes(n) for n in fr["reference_notes"]) or "没有"), "",
          "## 需要用户提供的信息（不得编造）", ""]
    for f in p["facts_needed"]:
        L.append("- [%s] **%s**：%s%s" % (" " if blank(f["value"]) else "x", f["key"], f["question"], "" if blank(f["value"]) else "\n  → " + f["value"]))
    L += ["", "## 标题（3 个备选，各不超过 20 字）", ""] + ["%d. %s" % (i + 1, t or "（空）") for i, t in enumerate(p["titles"])]
    L += ["", "## 逐%s内容" % p["unit"], "", "| %s | 角色 | 任务 | %s | 画面 |%s" % (p["unit"], text_name(p), " 口播 | 秒 |" if p["type"] == "视频" else ""), "|---|---|---|---|---|%s" % ("---|---|" if p["type"] == "视频" else "")]
    for g in p["pages"]:
        row = "| %d | %s | %s | %s | %s |" % (g["no"], g["role"], g["task"], g["text"] or "（空）", g["visual"] or "（空）")
        if p["type"] == "视频":
            row += " %s | %s |" % (g.get("voiceover") or "（空）", g.get("seconds", ""))
        L.append(row)
    L += ["", "## 正文", ""]
    for b in p["body"]:
        L += ["**%s**（%s）" % (b["section"], b["guide"]), "", b["text"] or "（空）", ""]
    im = p["image"]
    L += ["## 标签与首评", "", "- 固定标签（每篇都带，导出时自动加上）：%s" % (" ".join("#" + t.lstrip("#") for t in p.get("fixed_tags", [])) or "（空：建议 1 到 2 个账号自己的标签）"),
          "- 本篇标签：%s" % (" ".join("#" + t.lstrip("#") for t in p["tags"]) or "（空：连同固定标签一共 3 到 10 个）"), "- 首评：%s" % (p["first_comment"] or "（空）"), "",
          "## 配图设定", "", "- 风格：%s｜比例：%s" % (im["style"], im["ratio"]),
          "- 主体描述：%s" % (im["subject"] or "（空：产品外观的客观描述，颜色、形状、材质、尺寸。要用户告诉你或给照片，不能猜）"),
          "- 配色：%s" % (im["palette"] or "（空：2 到 3 个主色）"),
          "- 品牌角标：%s" % (im.get("brand_tag") or "（可选：每张图顶部固定出现的账号名或产品名）"),
          "- 用实拍的%s：%s" % (p["unit"], "、".join(str(x) for x in im["real_photo_pages"]) or "（空：有实拍素材的页码写在这里，例如 [1, 3]；产品外观以实拍为准）")]
    return "\n".join(L)


def compose_draft(p):
    body = "\n\n".join(b["text"].strip() for b in p["body"] if b["text"].strip())
    return "%s\n%s\n\n%s\n" % ((p["titles"][0] if p["titles"] else "").strip(), body, " ".join("#" + t for t in all_tags(p)))


def fields(p):
    """方案里所有由人或模型填写的文字：[(位置, 文字)]。占位内容在这些位置都要查。"""
    out = [("标题 %d" % (i + 1), t) for i, t in enumerate(p["titles"])]
    for g in p["pages"]:
        name = "第 %d %s" % (g["no"], p["unit"])
        out += [(name + "的" + text_name(p), g.get("text", "")), (name + "的画面", g.get("visual", ""))]
        if p["type"] == "视频":
            out.append((name + "的口播", g.get("voiceover", "")))
    out += [("正文「%s」" % b["section"], b["text"]) for b in p["body"]]
    out += [("首评", p.get("first_comment", "")), ("标签", " ".join(all_tags(p)))]
    out += [("配图设定的主体描述", p["image"].get("subject", "")), ("配图设定的配色", p["image"].get("palette", "")), ("配图设定的品牌角标", p["image"].get("brand_tag", ""))]
    out += [("信息「%s」" % f["key"], f.get("value", "")) for f in p["facts_needed"]]
    return out


def real_pages(p):
    out = set()
    for x in p["image"].get("real_photo_pages", []):
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            pass
    return out


def secs_of(g):
    """这一镜的秒数。写成 3、"3"、"3s"、"3 秒" 都认，认不出来按 0 算。"""
    m = re.search(r"\d+(?:\.\d+)?", str(g.get("seconds") or ""))
    return float(m.group(0)) if m else 0.0


def is_card(g):
    return any(k in g["composition"] for k in ("卡片", "表格"))


def sync_facts(a, p):
    """产品事实以档案为准：档案里有的带进方案；方案里填了而档案没有的写回档案，下一篇不用再问。返回提示。"""
    data = ll.load(a, must=False)
    if not data:
        return []
    facts, notes, log_changed, plan_changed = data["product"]["facts"], [], False, False
    for f in p["facts_needed"]:
        k = f["key"]
        if k not in ll.FACTS:
            continue
        lv, pv = str(facts.get(k) or "").strip(), str(f.get("value") or "").strip()
        if lv and lv != pv:
            if pv:
                notes.append("「%s」方案里写的是「%s」，产品档案里是「%s」，已按档案为准。要改请运行：%s" % (k, pv, lv, C.cmd("launch_log.py", "fact", '%s="新的内容"' % k)))
            f["value"], plan_changed = lv, True
        elif pv and not lv and not PLACEHOLDER.search(pv):
            facts[k], log_changed = pv, True
            notes.append("已把「%s」写回产品档案，下一篇不用再问。" % k)
    if log_changed:
        ll.save(a, data)
    if plan_changed:
        save_plan(a, p)
    return notes


def check_plan(p, extra_words=()):
    E, W = [], []
    fact = {f["key"]: str(f.get("value") or "").strip() for f in p["facts_needed"]}
    for f in p["facts_needed"]:
        if blank(f.get("value")):
            E.append("信息缺失「%s」：%s 确实没有就填「无」。" % (f["key"], f["question"]))
    titles = [t.strip() for t in p["titles"] if t.strip()]
    if len(titles) < 3:
        E.append("标题备选不足 3 个（现有 %d 个）。" % len(titles))
    for t in titles:
        if nc.xhs_len(t) > nc.TITLE_MAX:
            E.append("标题超过 %d 字：%s（%d 字）" % (nc.TITLE_MAX, t, nc.xhs_len(t)))
        if SERIES_PREFIX.search(t):
            W.append("标题以期数或编号开头：%s。样本里一个账号的这类标题点赞中位数是其他标题的 0.57 倍（7 篇，仅作参考）。建议把新闻放在前面，期数放到封面角标。" % t)
        if EMOJI.search(t):
            W.append("标题含表情符号：%s。样本的两个账号里，含表情的标题点赞中位数约为同账号其他标题的一半。建议把表情留给正文分点。" % t)
    if len(set(titles)) < len(titles):
        W.append("标题备选有重复，三个标题应各用不同的写法。")
    if p.get("goal") == "互动" and p["body"] and p["body"][-1]["text"].strip() and "评论" not in p["body"][-1]["text"] + p.get("first_comment", ""):
        W.append("发布目标是互动，但结尾和首评都没有请读者在评论区发一样具体的东西。")
    if len(p["pages"]) > MAX_PAGES:
        E.append("图片超过 %d 张。" % MAX_PAGES)
    real, nos = real_pages(p), {g["no"] for g in p["pages"]}
    bad = [str(x) for x in p["image"].get("real_photo_pages", []) if not str(x).isdigit() or int(x) not in nos]
    if bad:
        E.append("配图设定的 real_photo_pages 里有无效的页码：%s。只能写 %s 里的数字，例如 [1, 3]。" % ("、".join(bad), "、".join(str(x) for x in sorted(nos))))
    for g in p["pages"]:
        name = "第 %d %s（%s）" % (g["no"], p["unit"], g["role"])
        if blank(g.get("text")):
            E.append("%s 没有%s。" % (name, text_name(p)))
        elif g["role"] == "封面" and nc.xhs_len(g["text"]) > COVER_MAX:
            E.append("%s 文字 %d 字，超过 %d 字，手机上看不清。" % (name, nc.xhs_len(g["text"]), COVER_MAX))
        elif nc.xhs_len(g["text"]) > PAGE_TEXT_MAX:
            W.append("%s 文字 %d 字，超过 %d 字，建议拆页或精简。" % (name, nc.xhs_len(g["text"]), PAGE_TEXT_MAX))
        if blank(g.get("visual")):
            E.append("%s 没有画面描述，无法生成配图提示词。" % name)
        if p["type"] == "视频" and blank(g.get("voiceover")) and p["template"] != "情绪短片":
            E.append("%s 没有口播。没有人声的镜头写环境音或音乐，例如「（只有冲泡的水声）」。" % name)
    if p["type"] == "视频":
        secs = sum(secs_of(g) for g in p["pages"])
        untimed = [str(g["no"]) for g in p["pages"] if not secs_of(g)]
        if untimed:
            E.append("第 %s 镜没有写秒数（seconds），没法检查时长和语速。" % "、".join(untimed))
        words = sum(nc.xhs_len(g.get("voiceover", "")) for g in p["pages"])
        for g in p["pages"]:
            n, t = nc.xhs_len(g.get("voiceover", "")), secs_of(g)
            if t and n / t > SHOT_SPEED_MAX:
                W.append("第 %d 镜口播 %d 字 / %g 秒，这一镜念不完（每秒最多念 5 字左右）。把话分到相邻的镜头，或者把这一镜加长。" % (g["no"], n, t))
        if p["template"] == "情绪短片" and all(blank(g.get("voiceover")) for g in p["pages"]):
            E.append("情绪短片全片只说一句话，但每个镜头的口播都是空的。把这句话写进它出现的那个镜头。")
        if p["template"] == "情绪短片" and secs > 15:
            W.append("情绪短片总时长 %g 秒，样本中表现最好的都在 6 到 15 秒。" % secs)
        elif secs > 90:
            W.append("总时长 %g 秒，建议 30 到 60 秒。" % secs)
        if secs and not untimed and words / secs > SPEED_MAX:
            E.append("口播 %d 字 / %g 秒，语速超过每秒 %d 字，念不完。删口播，或者把镜头的秒数加长。" % (words, secs, SPEED_MAX))
    for b in p["body"]:
        if blank(b["text"]):
            E.append("正文「%s」未填写。" % b["section"])
    if p["template"] != "情绪短片" and p["body"] and p["body"][0]["text"].strip() and nc.xhs_len(p["body"][0]["text"].splitlines()[0]) > 45:
        W.append("开头第一句超过 45 字，前两行决定是否展开。")
    last = p["body"][-1]["text"] if p["body"] else ""
    if last.strip() and not re.search(r"[?？]", last):
        E.append("正文最后一段「%s」里没有问句。评论是下一轮反馈的来源。" % p["body"][-1]["section"])
    if blank(p.get("first_comment")):
        W.append("没有首评。首评可以补充购买方式或再抛一个问题。")
    im = p["image"]
    ai_product = [g["no"] for g in p["pages"] if g["no"] not in real and not is_card(g) and g.get("product_in_frame", True)]
    if blank(im.get("subject")) and ai_product:
        E.append("配图设定缺少主体描述（image.subject），而第 %s %s要用 AI 画出产品：多张图里的产品会长得不一样。请向用户要产品外观（颜色、形状、材质、尺寸）或照片，不能猜；这些%s改用实拍的话，把页码写进 real_photo_pages。" % (
            "、".join(str(x) for x in ai_product), p["unit"], p["unit"]))
    if blank(im.get("palette")) and len(real) < len(p["pages"]):
        W.append("配图设定缺少配色，系列图风格可能不统一。")
    src = fact.get("素材", "")
    if src and NONE_WORDS.match(src) and real:
        W.append("产品档案里写的是没有实拍素材，但第 %s %s标了用实拍。请确认。" % ("、".join(str(x) for x in sorted(real)), p["unit"]))
    elif src and not NONE_WORDS.match(src) and not real and ai_product:
        W.append("你有实拍素材（%s），但没有一%s标为用实拍。产品外观以实拍为准：建议封面和产品特写用实拍，把页码写进 image.real_photo_pages；想要 AI 的画面感，prompts 会给出「实拍做参考图、只生成背景」的提示词。" % (src[:30], p["unit"]))
    # 占位内容：任何一个要填的位置都不能留
    holes = []
    for where, text in fields(p):
        m = PLACEHOLDER.search(str(text or ""))
        if m:
            holes.append("%s里还有占位内容「%s」" % (where, m.group(0)))
    for h in holes[:8]:
        E.append(h + "，请换成真实内容；不知道的去问用户，不要留着。")
    if len(holes) > 8:
        E.append("还有 %d 处占位内容没有列出。" % (len(holes) - 8))
    # 身份与利益相关
    who, text = fact.get("身份", ""), compose_draft(p) + p.get("first_comment", "")
    if who and PAID.search(who) and not re.search(r"合作|赞助|送测|寄送|利益相关", text):
        W.append("档案里你的身份是「%s」。收了报酬或拿了样品的内容要写明利益相关，商业合作要走平台的品牌合作报备。正文和首评里都没有提到，请补上；报备这一步脚本检查不了。" % who[:20])
    elif who and OWNER.search(who) and not DISCLOSE.search(text):
        W.append("档案里你的身份是「%s」，但正文和首评都没有说明这一点。用普通用户的口吻发自家产品，容易被读者和平台当成软广。在正文开头直接写一句（例如「自家产品」「我是主理人」）；用认证的品牌号或店铺号发的话可以忽略。" % who[:20])
    fr = p["from_research"]
    if fr["title_hooks_to_use"] and titles:
        pats = dict(rs.HOOKS)
        if not any(re.search(pats[h], t) for h in fr["title_hooks_to_use"] if h in pats for t in titles):
            W.append("三个标题都没有用到调研里有效的写法：%s。" % "、".join(fr["title_hooks_to_use"]))
    if fr["pain_quotes"] and p["body"] and p["body"][0]["text"].strip():
        words = set(re.findall(r"[一-鿿]{2}", "".join(fr["pain_quotes"])))
        if not any(w in p["body"][0]["text"] + "".join(titles) for w in words):
            W.append("开头和标题都没有回应调研里的用户原话：%s。" % " / ".join(fr["pain_quotes"][:2]))
    for i in nc.check(compose_draft(p), extra_words, min_body=0 if p["template"] == "情绪短片" else 80)["issues"]:
        (E if i["level"] == "错误" else W).append("[成稿][%s] %s" % (i["item"], i["message"]))
    return E, W


def cmd_show(a):
    p = load_plan(a)
    sync_facts(a, p)
    print(render(p))


def cmd_check(a):
    p = load_plan(a)
    notes = sync_facts(a, p)
    E, W = check_plan(p, [C.P(a, "banned_words.txt")])
    path = os.path.join(plan_dir(a), "%s_draft.txt" % p["id"])
    if not E:
        C.write_text(path, compose_draft(p))
    print("# 发布方案检查 %s\n\n结论：%s（错误 %d，警告 %d）\n" % (p["id"], "通过" if not E else "未通过，请补全后重新检查", len(E), len(W)))
    for x in notes:
        print("- [提示] " + x)
    for x in E:
        print("- [错误] " + x)
    for x in W:
        print("- [警告] " + x)
    fixed = [t for t in all_tags(p) if t in [str(x).lstrip("#").strip() for x in p.get("fixed_tags", [])]]
    if fixed:
        print("- [提示] 固定标签 %s 已自动加进成稿，不用在 tags 里重复写。" % " ".join("#" + t for t in fixed))
    if not E:
        print("\n成稿已导出：%s\n下一步：%s" % (C.where(path), C.cmd("content_plan.py", "prompts", "--id", p["id"])))
    else:
        print("\n方案文件：%s" % C.where(plan_path(a)))
    sys.exit(1 if E else 0)


def build_prompt(p, g, with_text, background_only=False):
    im = p["image"]
    card = is_card(g)
    style = STYLES["知识卡片"] if card and im["style"] in ("实拍生活感", "产品特写") else STYLES.get(im["style"], STYLES["实拍生活感"])
    visual = g["visual"].strip().rstrip("。.")
    if background_only:
        parts = ["只生成场景和背景，不要画出产品本身，产品的位置留空，用来叠放实拍图。场景参考：" + visual]
    else:
        parts = [visual]
        if not card and g.get("product_in_frame", True) and im["subject"].strip():
            parts.append("画面中的产品：" + im["subject"].strip().rstrip("。."))
    parts += [g["composition"], style]
    if im["palette"].strip():
        parts.append("配色：" + im["palette"].strip())
    if im.get("brand_tag", "").strip():
        parts.append("顶部居中预留一小块品牌角标位置")
    parts.append("竖版 %s 构图，高清，细节清晰" % im["ratio"])
    if with_text:
        parts.append("画面中醒目的简体中文大字：“%s”，字体粗黑、清晰可读、无错别字" % g["text"].strip())
    else:
        parts.append("预留干净的留白区域用于后期加字，画面中不要出现任何文字")
    return "，".join(x for x in parts if x)


def cmd_prompts(a):
    p = load_plan(a)
    sync_facts(a, p)
    E, _ = check_plan(p, [C.P(a, "banned_words.txt")])
    if E and not a.force:
        sys.exit("方案还有 %d 个错误，先运行 check 并补全：%s\n（确需跳过加 --force。）" % (len(E), C.cmd("content_plan.py", "check", "--id", p["id"])))
    im = p["image"]
    real = real_pages(p)
    size = "1242×1660" if im["ratio"] == "3:4" else "1080×1920"
    L = ["# 配图提示词 %s：%s" % (p["id"], p["product"]), "",
         "- 风格：%s｜比例 %s（建议 %s 像素）｜共 %d %s，其中 %d %s用实拍" % (im["style"], im["ratio"], size, len(p["pages"]), p["unit"], len(real), p["unit"]),
         "- 产品外观以实拍为准。AI 画出来的产品和实物不一样，读者收到货会觉得被骗：有实拍时用实拍，或者用实拍做参考图、只让 AI 生成背景。",
         "- 系列一致：出现产品的图都用同一段产品描述，所有图用同一组配色；支持参考图的工具，把产品实拍或第 1 张生成结果作为参考图。",
         "- 用了 AI 生成的图片，发布时在小红书发布页勾选「内容含 AI 合成」的声明。",
         "- 提示词是中文，可直接用于支持中文的生图工具；用英文工具时，把提示词和反向提示词译成英文再用。%s" % ("已按「图中直接出字」生成，适合能稳定渲染中文的模型。" if a.with_text else "默认图中不出字，文字用修图或排版工具后期添加，最稳。"), ""]
    for g in p["pages"]:
        L += ["## 第 %d %s：%s" % (g["no"], p["unit"], g["role"]), ""]
        if g["no"] in real:
            L += ["**用实拍。** 拍摄要求：%s；%s。" % (g["visual"].strip().rstrip("。."), g["composition"]), "",
                  "想让这一%s更有画面感，可以用 AI 辅助，但产品本身必须来自实拍：把实拍抠图后叠在下面这张背景上，或者用实拍做参考图（图生图）。发布时勾选 AI 声明。" % p["unit"], "",
                  "**背景提示词（可选）**", "", "```", build_prompt(p, g, False, background_only=True), "```", "", "**反向提示词**", "", "```", NEGATIVE, "```", ""]
        else:
            L += ["**提示词**", "", "```", build_prompt(p, g, a.with_text), "```", "", "**反向提示词**", "", "```", NEGATIVE, "```", ""]
        L += ["**后期加字**：%s" % g["text"], "- 位置：%s" % ("上方三分之一，居中" if g["role"] == "封面" else "顶部标题区，左对齐"),
              "- 字体：粗黑体，字号以手机上一眼能读为准；重点词可用配色中的强调色"]
        if im.get("brand_tag", "").strip():
            L.append("- 品牌角标：顶部居中小字「%s」，每张图位置和样式相同" % im["brand_tag"].strip())
        L.append("")
        if p["type"] == "视频":
            L += ["**口播**（约 %g 秒）：%s" % (secs_of(g), (g.get("voiceover") or "").strip() or "（这一镜不说话）"), ""]
    text = "\n".join(L)
    out = a.out or os.path.join(plan_dir(a), "%s_prompts.md" % p["id"])
    C.write_text(out, text + "\n")
    print(text)
    print("\n已保存：%s" % C.where(out))
    print("发布后登记：%s" % C.cmd("launch_log.py", "publish", "--id", p["id"], "--url", '"笔记链接"', "--final-title", '"最终用的标题"'))


def cmd_templates(a):
    print("# 内容模板\n")
    for name, t in T.items():
        print("- **%s**（角度里有这些词时自动选它：%s）：封面 → %s" % (name, "、".join(t["match"]), " → ".join(r for r, _, _ in t["pages"])))
    print("\n选模板的顺序：--template 指定的 > 角度对应的 > 通用的发布体。发布目标不决定模板，它决定主指标和结尾怎么引导；下面列出每个目标常用的模板，想用就加 --template。\n\n# 发布目标\n")
    for k, (tpls, why) in GOAL_TEMPLATES.items():
        print("- **%s**：主指标 %s；常用模板 %s。%s。" % (k, ll.GOALS[k], "、".join(tpls), why))
    print("\n# 配图风格\n")
    for k, v in STYLES.items():
        print("- **%s**：%s" % (k, v))


def build_parser():
    ap = argparse.ArgumentParser(description="小红书发布方案与配图提示词")
    C.add_dir_arg(ap)
    ap.add_argument("--analysis", default=argparse.SUPPRESS, help="调研分析 json；默认 数据目录/research/analysis.json")
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True

    def sp(name, fn, help_, need_id=True):
        s = sub.add_parser(name, help=help_)
        C.add_dir_arg(s)
        s.add_argument("--analysis", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        if need_id:
            s.add_argument("--id", required=True, help="发布编号，例如 L1")
        s.set_defaults(fn=fn)
        return s

    s = sp("new", cmd_new, "生成待填写的发布方案")
    s.add_argument("--template", help="指定模板：%s" % "、".join(T))
    s.add_argument("--goal", choices=list(ll.GOALS), help="这一篇的发布目标，默认用登记时或产品档案里的")
    s.add_argument("--style", default=None, help="配图风格：%s" % "、".join(STYLES))
    s.add_argument("--pages", type=int, help="总页数（含封面）")
    s.add_argument("--force", action="store_true", help="重建已有的方案（旧方案另存为 .bak）")
    sp("show", cmd_show, "查看方案")
    sp("check", cmd_check, "检查方案，通过后导出成稿")
    s = sp("prompts", cmd_prompts, "生成配图提示词")
    s.add_argument("--with-text", action="store_true", help="让图中直接出字")
    s.add_argument("--out", help="保存路径，默认 数据目录/plans/<编号>_prompts.md")
    s.add_argument("--force", action="store_true", help="方案有错误也生成")
    sp("templates", cmd_templates, "列出模板、目标和风格", need_id=False)
    return ap


def main():
    a = build_parser().parse_args()
    C.data_dir(a)
    if a.cmd == "new":
        a.style_given = a.style is not None
        a.style = a.style or "实拍生活感"
    a.fn(a)


if __name__ == "__main__":
    C.run(main)

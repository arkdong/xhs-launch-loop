#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布方案：把调研结论变成「发什么、每一页放什么、需要哪些真实信息」，并生成配图提示词。

子命令:
  new     --id L1 [--template 模板] [--style 风格] [--pages N]
          读取发布日志和调研分析，生成待填写的发布方案 xhs_launch/plans/L1.json
  show    --id L1            以 Markdown 查看方案和待填项
  check   --id L1            检查方案是否填完整、是否合规；通过后导出 xhs_launch/plans/L1_draft.txt
  prompts --id L1 [--with-text] [--out 文件]   生成每一页的配图提示词
  templates                  列出可用的内容模板和配图风格
通用参数: --log 发布日志路径  --analysis 调研分析 json 路径
只依赖 Python 标准库。脚本不编造产品信息：价格、时长、缺点等必须由用户提供。
"""
import argparse, json, os, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import note_check as nc  # noqa: E402

DEFAULT_LOG = os.path.join("xhs_launch", "launch_log.json")
DEFAULT_ANALYSIS = os.path.join("xhs_launch", "research", "analysis.json")
PLAN_DIR = os.path.join("xhs_launch", "plans")
COVER_MAX, PAGE_TEXT_MAX, MAX_PAGES = 12, 40, 18

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
    "发布体": {"match": ["发布", "新品", "上新", "首发", "痛点"], "pages": [
        ("痛点场景", "用一个具体场景或用户原话说出痛点", "生活场景，人物处在困扰中，不露正脸"),
        ("这是什么", "一句话说明产品和它解决什么", "产品主体特写，背景干净"),
        ("要点一", "最重要的一个事实，带数字", "使用过程特写"),
        ("要点二", "第二个事实，带数字", "使用结果或对比"),
        ("缺点与适合谁", "至少一条缺点，一句适合人群", "纯色背景信息卡片")]},
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
}
STYLES = {
    "实拍生活感": "真实手机摄影质感，自然窗边光，生活化场景，轻微景深，色彩真实不过饱和，像普通人随手拍但构图干净",
    "知识卡片": "扁平化信息图卡片，纯色或浅色渐变背景，大面积留白，简洁图标，圆角矩形分区，排版清晰",
    "手绘插画": "手绘风格插画，柔和线条，低饱和配色，可爱但不幼稚，留白充足",
    "产品特写": "商业产品摄影，柔和棚拍光，干净的纯色背景，材质细节清晰，轻微倒影",
    "对比拼图": "左右分屏对比构图，中间细分隔线，两侧光线和角度一致，差异一目了然",
}
NEGATIVE = "水印，logo，品牌商标，乱码文字，变形的手，多余的手指，畸形人脸，真实名人，低清晰度，过度磨皮，过度饱和，塑料质感"
FACTS = [
    ("一句话定位", "用一句话说清：这是什么，给谁用，解决什么？"),
    ("价格与单次成本", "售价多少？折算到每次使用大约多少钱？"),
    ("真实使用情况", "你（或真实用户）用了多久、多少次？在什么场景用？"),
    ("一个具体结果", "有没有一个可以量化的结果（省了多少时间、多少钱、几步完成）？"),
    ("一个缺点", "它最明显的缺点或不适合的人是什么？"),
    ("可用实拍素材", "手头有哪些真实照片或视频（产品、使用过程、成品）？"),
    ("购买与合作声明", "读者在站内怎么找到它？是否有商业合作需要标注？"),
]
# 发布目标 → 主指标与建议模板（依据见 references/content_rules.md 的样本分析）
GOALS = {
    "触达": ("点击率与观看", ["情绪短片", "上线公告"], "样本中短视频的点赞中位数约为图文的 12 倍；标题直接说新闻"),
    "互动": ("评论率", ["征集互动", "答疑科普"], "样本中请每人在评论区晒一样东西的笔记，评论数超过点赞数"),
    "收藏": ("收藏点赞比", ["深度长文", "教程攻略", "对比平替"], "样本中规则说明和深度长文的收藏数接近或超过点赞数"),
}
SERIES_PREFIX = re.compile(r"^\s*([Vv]ol\.?\s*\d|第\s*\d+\s*[期弹]|0?\d\s*[｜|])")
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
PLACEHOLDER = re.compile(r"待填|待补|XX|xx|TODO|todo|【.*?】|＿＿|___|……$")


def load_json(path, what):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def plan_path(a):
    return os.path.join(PLAN_DIR, "%s.json" % a.id.upper())


def load_plan(a):
    p = load_json(plan_path(a), "plan")
    if p is None:
        sys.exit("找不到发布方案 %s。先运行：python scripts/content_plan.py new --id %s" % (plan_path(a), a.id))
    return p


def save_plan(a, plan):
    os.makedirs(PLAN_DIR, exist_ok=True)
    with open(plan_path(a), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)


def latest_other_plan(pid):
    """沿用上一份方案的视觉设定和固定标签，保证账号的系列感。"""
    if not os.path.isdir(PLAN_DIR):
        return None
    cands = [os.path.join(PLAN_DIR, f) for f in os.listdir(PLAN_DIR) if f.endswith(".json") and f != "%s.json" % pid.upper()]
    if not cands:
        return None
    with open(max(cands, key=os.path.getmtime), encoding="utf-8") as f:
        return json.load(f)


def pick_template(angle, forced, goal=None, is_video=False):
    if forced:
        if forced not in T:
            sys.exit("没有模板「%s」。可用：%s" % (forced, "、".join(T)))
        return forced
    for name, t in T.items():
        if name != "发布体" and (name in (angle or "") or any(m in (angle or "") for m in t["match"])):
            return name
    if goal:
        return next(c for c in GOALS[goal][1] if c != "情绪短片" or is_video)
    for name, t in T.items():
        if name in (angle or "") or any(m in (angle or "") for m in t["match"]):
            return name
    return "发布体"


def cmd_new(a):
    log = load_json(a.log, "log")
    if log is None:
        sys.exit("还没有发布日志（%s）。请先完成阶段①并用 launch_log.py add 登记本次发布。" % a.log)
    launch = next((l for l in log["launches"] if l["id"].lower() == a.id.lower()), None)
    if launch is None:
        sys.exit("发布日志里没有 %s。现有：%s" % (a.id, "、".join(l["id"] for l in log["launches"]) or "无"))
    if os.path.exists(plan_path(a)) and not a.force:
        sys.exit("方案已存在：%s。继续填写即可；要重建请加 --force。" % plan_path(a))
    R = load_json(a.analysis, "analysis") or {}
    is_video = launch.get("type") == "视频"
    tname = pick_template(launch.get("angle", ""), a.template, a.goal, is_video)
    if tname == "情绪短片" and not is_video:
        sys.exit("「情绪短片」是视频模板，但 %s 登记的形式是图文。请用 launch_log.py add --type 视频 重新登记，或换一个模板。" % launch["id"])
    prev = latest_other_plan(a.id)
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

    # 从调研里带出可用的依据
    gaps = [g for g in R.get("gaps", []) if g.get("gap")] or R.get("gaps", [])[:1]
    hooks = [h["hook"] for h in R.get("hooks", []) if h.get("lift") and h["lift"] >= 1.2][:3]
    weak = [h["hook"] for h in R.get("hooks", []) if h.get("lift") and h["lift"] < 0.8][:2]
    refs = (R.get("low_fan_hits") or R.get("top_notes") or [])[:3]
    facts = [{"key": k, "question": q, "value": ""} for k, q in FACTS]
    for g in gaps[:2]:
        facts.append({"key": "回应「%s」" % g["pain"], "question": "评论里有人说：%s。你的真实回答是什么？" % " / ".join("“%s”" % q for q in g.get("quotes", [])[:2]), "value": ""})
    prod = log["product"]
    plan = {
        "id": launch["id"], "template": tname, "type": launch.get("type", "图文"), "unit": unit,
        "product": prod["name"], "audience": prod.get("audience", ""), "tone": prod.get("tone", ""),
        "angle": launch.get("angle", ""), "hypothesis": launch["hypothesis"], "evidence": launch.get("evidence", ""),
        "goal": a.goal or "", "main_metric": GOALS[a.goal][0] if a.goal else "",
        "from_research": {
            "sample": "%s 篇笔记，%s 条评论" % (R.get("analyzed", "未获取"), R.get("demand_comments", "未获取")),
            "pain_quotes": [q for g in gaps[:2] for q in g.get("quotes", [])[:2]],
            "questions": R.get("unanswered_questions", [])[:4],
            "title_hooks_to_use": hooks, "title_hooks_to_avoid": weak,
            "title_len_median": int(R["title_len_median"]) if R.get("title_len_median") else None, "title_keywords": [k["word"] for k in R.get("title_keywords", [])[:6]],
            "reference_notes": [{"title": n["title"], "url": n.get("url", ""), "likes": n["likes"], "angle": n.get("angle", "")} for n in refs],
        },
        "facts_needed": facts,
        "titles": ["", "", ""],
        "pages": pages,
        "body": [
            {"section": "开头钩子", "guide": "30 字内，用用户原话或具体场景，直接回应痛点", "text": ""},
            {"section": "我为什么能说", "guide": "一句话：真实使用时长或身份", "text": ""},
            {"section": "正文要点", "guide": "与各%s一一对应，每点一行并带具体数字" % unit, "text": ""},
            {"section": "缺点与适合谁", "guide": "至少一条缺点，这是可信度的来源", "text": ""},
            {"section": "结尾提问", "guide": "一个容易回答的具体问题，优先用调研里的高频问题", "text": ""},
        ],
        "fixed_tags": (prev or {}).get("fixed_tags", []), "tags": [], "first_comment": "",
        "image": {"style": a.style, "ratio": "9:16" if is_video else "3:4", "subject": "", "palette": "", "brand_tag": "", "real_photo_pages": []},
    }
    if prev:   # 同一账号的图要像一套：沿用上一份方案的产品描述、配色、角标
        for k in ("subject", "palette", "brand_tag"):
            plan["image"][k] = prev.get("image", {}).get(k, "")
        if not a.style_given:
            plan["image"]["style"] = prev.get("image", {}).get("style", a.style)
    if a.style not in STYLES:
        sys.exit("没有风格「%s」。可用：%s" % (a.style, "、".join(STYLES)))
    save_plan(a, plan)
    print("已生成发布方案骨架：%s（模板：%s，共 %d %s）" % (plan_path(a), tname, len(pages), unit))
    if a.goal:
        print("发布目标「%s」→ 主指标：%s；建议模板：%s。依据：%s。" % (a.goal, GOALS[a.goal][0], "、".join(GOALS[a.goal][1]), GOALS[a.goal][2]))
    else:
        print("未指定发布目标。可用 --goal 触达|互动|收藏 让方案按目标选模板和主指标。")
    if prev:
        print("已沿用 %s 的配图设定和固定标签，保持系列一致。" % prev["id"])
    print()
    print(render(plan))
    print("\n下一步：先向用户确认「需要用户提供的信息」，再填写方案里所有空字段，然后运行 check。")


def render(p):
    fr = p["from_research"]
    L = ["# 发布方案 %s：%s" % (p["id"], p["product"]), "",
         "- 形式：%s｜模板：%s｜角度：%s" % (p["type"], p["template"], p["angle"] or "未填"),
         "- 目标人群：%s｜语气：%s" % (p["audience"] or "未填", p["tone"] or "未填"),
         "- 发布假设：%s" % p["hypothesis"], "- 依据：%s" % (p["evidence"] or "未填"),
         "- 发布目标：%s｜主指标：%s" % (p.get("goal") or "未指定", p.get("main_metric") or "未指定"), "",
         "## 来自调研（%s）" % fr["sample"], "",
         "- 用户原话：%s" % (" / ".join("“%s”" % q for q in fr["pain_quotes"]) or "未获取"),
         "- 高频问题：%s" % ("；".join(fr["questions"]) or "未获取"),
         "- 标题建议使用：%s｜谨慎使用：%s｜长度参考 %s 字｜高频词：%s" % ("、".join(fr["title_hooks_to_use"]) or "无明显信号", "、".join(fr["title_hooks_to_avoid"]) or "无",
                                                    fr["title_len_median"] or "未知", "、".join(fr["title_keywords"]) or "未获取"),
         "- 对标笔记：%s" % ("；".join(("[%s](%s)" % (n["title"], n["url"]) if n["url"] else "「%s」" % n["title"]) + "（赞 %d）" % n["likes"] for n in fr["reference_notes"]) or "未获取"), "",
         "## 需要用户提供的信息（不得编造）", ""]
    for f in p["facts_needed"]:
        L.append("- [%s] **%s**：%s%s" % ("x" if f["value"].strip() else " ", f["key"], f["question"], ("\n  → " + f["value"]) if f["value"].strip() else ""))
    L += ["", "## 标题（3 个备选，各不超过 20 字）", ""] + ["%d. %s" % (i + 1, t or "（待写）") for i, t in enumerate(p["titles"])]
    L += ["", "## 逐%s内容" % p["unit"], "", "| %s | 角色 | 任务 | 图上文字 | 画面 |%s" % (p["unit"], " 口播 | 秒 |" if p["type"] == "视频" else ""), "|---|---|---|---|---|%s" % ("---|---|" if p["type"] == "视频" else "")]
    for g in p["pages"]:
        row = "| %d | %s | %s | %s | %s |" % (g["no"], g["role"], g["task"], g["text"] or "（待写）", g["visual"] or "（待写）")
        if p["type"] == "视频":
            row += " %s | %s |" % (g.get("voiceover") or "（待写）", g.get("seconds", ""))
        L.append(row)
    L += ["", "## 正文", ""]
    for b in p["body"]:
        L += ["**%s**（%s）" % (b["section"], b["guide"]), "", b["text"] or "（待写）", ""]
    L += ["## 标签与首评", "", "- 标签：%s" % (" ".join("#" + t.lstrip("#") for t in p["tags"]) or "（待写，3 到 10 个）"), "- 首评：%s" % (p["first_comment"] or "（待写）"), "",
          "## 配图设定", "", "- 风格：%s｜比例：%s" % (p["image"]["style"], p["image"]["ratio"]),
          "- 主体描述：%s" % (p["image"]["subject"] or "（待写：产品外观的客观描述，颜色、形状、材质、尺寸）"),
          "- 配色：%s" % (p["image"]["palette"] or "（待写：2 到 3 个主色）"),
          "- 品牌角标：%s" % (p["image"].get("brand_tag") or "（可选：每张图顶部固定出现的账号名或产品名，形成系列感）"),
          "- 固定标签：%s" % (" ".join("#" + t.lstrip("#") for t in p.get("fixed_tags", [])) or "（建议：1 到 2 个每篇都带的账号标签）"),
          "- 用实拍的%s：%s" % (p["unit"], "、".join(str(x) for x in p["image"]["real_photo_pages"]) or "（待定：有实拍素材的优先用实拍）")]
    return "\n".join(L)


def compose_draft(p):
    body = "\n\n".join(b["text"].strip() for b in p["body"] if b["text"].strip())
    tags = " ".join("#" + t.lstrip("#").strip() for t in p["tags"] if t.strip())
    return "%s\n%s\n\n%s\n" % ((p["titles"][0] if p["titles"] else "").strip(), body, tags)


def check_plan(p):
    E, W = [], []
    for f in p["facts_needed"]:
        if not f["value"].strip():
            E.append("信息缺失「%s」：%s 若确实没有请填「无」并说明。" % (f["key"], f["question"]))
    titles = [t.strip() for t in p["titles"] if t.strip()]
    if len(titles) < 3:
        E.append("标题备选不足 3 个（现有 %d 个）。" % len(titles))
    for t in titles:
        if nc.xhs_len(t) > nc.TITLE_MAX:
            E.append("标题超过 %d 字：%s（%d 字）" % (nc.TITLE_MAX, t, nc.xhs_len(t)))
    for t in titles:
        if SERIES_PREFIX.search(t):
            W.append("标题以期数或编号开头：%s。样本账号里这类标题的点赞中位数只有其他标题的五到六成，建议把新闻放在前面，期数放到封面角标。" % t)
        if EMOJI.search(t):
            W.append("标题含表情符号：%s。样本的两个账号里含表情的标题点赞中位数约为不含的一半，建议把表情留给正文分点。" % t)
    miss = [t for t in p.get("fixed_tags", []) if t.lstrip("#") not in [x.lstrip("#") for x in p["tags"]]]
    if miss:
        W.append("标签里缺少固定标签：%s。" % " ".join("#" + t.lstrip("#") for t in miss))
    if p.get("goal") == "互动" and p["body"] and p["body"][-1]["text"].strip() and "评论" not in p["body"][-1]["text"] + p.get("first_comment", ""):
        W.append("发布目标是互动，但结尾和首评都没有请读者在评论区发一样具体的东西。")
    if p["template"] == "情绪短片":
        secs = sum(int(g.get("seconds") or 0) for g in p["pages"])
        if secs > 15:
            W.append("情绪短片总时长 %d 秒，样本中表现最好的都在 6 到 15 秒。" % secs)
    if len(set(titles)) < len(titles):
        W.append("标题备选有重复，三个标题应各用不同的钩子。")
    if len(p["pages"]) > MAX_PAGES:
        E.append("图片超过 %d 张。" % MAX_PAGES)
    for g in p["pages"]:
        name = "第 %d %s（%s）" % (g["no"], p["unit"], g["role"])
        if not g["text"].strip():
            E.append("%s 没有图上文字。" % name)
        elif g["role"] == "封面" and nc.xhs_len(g["text"]) > COVER_MAX:
            E.append("%s 文字 %d 字，超过 %d 字，手机上看不清。" % (name, nc.xhs_len(g["text"]), COVER_MAX))
        elif nc.xhs_len(g["text"]) > PAGE_TEXT_MAX:
            W.append("%s 文字 %d 字，超过 %d 字，建议拆页或精简。" % (name, nc.xhs_len(g["text"]), PAGE_TEXT_MAX))
        if not g["visual"].strip():
            E.append("%s 没有画面描述，无法生成配图提示词。" % name)
        if p["type"] == "视频" and not g.get("voiceover", "").strip():
            E.append("%s 没有口播。" % name)
    if p["type"] == "视频":
        secs = sum(int(g.get("seconds") or 0) for g in p["pages"])
        words = sum(nc.xhs_len(g.get("voiceover", "")) for g in p["pages"])
        if secs > 90:
            W.append("总时长 %d 秒，建议 30 到 60 秒。" % secs)
        if secs and words / secs > 5:
            E.append("口播 %d 字 / %d 秒，语速超过每秒 5 字，念不完。" % (words, secs))
    for b in p["body"]:
        if not b["text"].strip():
            E.append("正文「%s」未填写。" % b["section"])
    if p["body"] and p["body"][0]["text"].strip() and nc.xhs_len(p["body"][0]["text"].splitlines()[0]) > 45:
        W.append("开头第一句超过 45 字，前两行决定是否展开。")
    last = p["body"][-1]["text"] if p["body"] else ""
    if last.strip() and not re.search(r"[?？]", last):
        E.append("结尾提问里没有问句。评论是下一轮反馈的来源。")
    if not p["first_comment"].strip():
        W.append("没有首评。首评可以补充购买方式或再抛一个问题。")
    if not p["image"]["subject"].strip():
        E.append("配图设定缺少主体描述，多张图里的产品会长得不一样。")
    if not p["image"]["palette"].strip():
        W.append("配图设定缺少配色，系列图风格可能不统一。")
    blob = json.dumps({k: p[k] for k in ("titles", "pages", "body", "first_comment")}, ensure_ascii=False)
    m = PLACEHOLDER.search(blob)
    if m:
        E.append("方案里还有占位内容「%s」，请替换为真实内容。" % m.group(0))
    fr = p["from_research"]
    if fr["title_hooks_to_use"] and titles:
        pats = dict(HOOK_PATS)
        if not any(re.search(pats[h], t) for h in fr["title_hooks_to_use"] if h in pats for t in titles):
            W.append("三个标题都没有用到调研里有效的钩子：%s。" % "、".join(fr["title_hooks_to_use"]))
    if fr["pain_quotes"] and p["body"][0]["text"].strip():
        words = set(re.findall(r"[一-鿿]{2}", "".join(fr["pain_quotes"])))
        if not any(w in p["body"][0]["text"] + "".join(titles) for w in words):
            W.append("开头和标题都没有回应调研里的用户原话：%s。" % " / ".join(fr["pain_quotes"][:2]))
    r = nc.check(compose_draft(p))
    for i in r["issues"]:
        (E if i["level"] == "错误" else W).append("[成稿][%s] %s" % (i["item"], i["message"]))
    return E, W


HOOK_PATS = [("含数字", r"\d"), ("疑问句", r"[?？]|吗|怎么|如何|为什么|哪个"),
             ("点名人群", r"学生党|打工人|新手|小白|宝妈|上班族|女生|男生|租房|宿舍|社畜|懒人|党"),
             ("负面/避雷", r"避雷|踩坑|踩雷|别买|后悔|千万别|智商税|劝退|翻车"), ("反差/意外", r"以为|没想到|居然|竟然|结果|原来|才知道"),
             ("结果承诺", r"只需|只要|搞定|学会|秒|分钟|一招|直接"), ("分隔符｜", r"[｜|]"), ("表情符号", r"[\U0001F300-\U0001FAFF☀-➿]")]


def cmd_show(a):
    print(render(load_plan(a)))


def cmd_check(a):
    p = load_plan(a)
    E, W = check_plan(p)
    print("# 发布方案检查 %s\n\n结论：%s（错误 %d，警告 %d）\n" % (p["id"], "通过" if not E else "未通过，请补全后重新检查", len(E), len(W)))
    for x in E:
        print("- [错误] " + x)
    for x in W:
        print("- [警告] " + x)
    if not E:
        path = os.path.join(PLAN_DIR, "%s_draft.txt" % p["id"])
        with open(path, "w", encoding="utf-8") as f:
            f.write(compose_draft(p))
        print("\n成稿已导出：%s\n下一步：python scripts/content_plan.py prompts --id %s" % (path, p["id"]))
    sys.exit(1 if E else 0)


def build_prompt(p, g, with_text):
    im = p["image"]
    card = any(k in g["composition"] for k in ("卡片", "表格"))
    style = STYLES["知识卡片"] if card and im["style"] in ("实拍生活感", "产品特写") else STYLES[im["style"]]
    parts = [g["visual"].strip().rstrip("。.")]
    if not card and g.get("product_in_frame", True):
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
    E, _ = check_plan(p)
    if E and not a.force:
        sys.exit("方案还有 %d 个错误，先运行 check 并补全（确需跳过加 --force）。" % len(E))
    im = p["image"]
    real = set(int(x) for x in im.get("real_photo_pages", []))
    size = "1242×1660" if im["ratio"] == "3:4" else "1080×1920"
    L = ["# 配图提示词 %s：%s" % (p["id"], p["product"]), "",
         "- 风格：%s｜比例 %s（建议 %s 像素）｜共 %d %s" % (im["style"], im["ratio"], size, len(p["pages"]), p["unit"]),
         "- 系列一致性：出现产品的图都使用同一段产品描述，所有图使用同一组配色；支持参考图的工具，请把第 1 张生成结果或产品实拍作为参考图。",
         "- 产品外观以实拍为准：有实拍图时优先用图生图或只生成背景，避免 AI 画出与实物不符的产品。",
         "- 发布时如使用了 AI 生成图片，请在小红书发布页勾选内容含 AI 合成的声明。",
         "- 提示词为中文，可直接用于支持中文的生图工具；用 Midjourney、DALL·E、Flux 等英文工具时，请把每条提示词和反向提示词译成英文再用。%s" % ("已按「图中直接出字」生成，适合能稳定渲染中文的模型。" if a.with_text else "默认图中不出字，文字用修图或排版工具后期添加，最稳。"), ""]
    for g in p["pages"]:
        L += ["## 第 %d %s：%s" % (g["no"], p["unit"], g["role"]), ""]
        if g["no"] in real:
            L += ["**使用实拍。** 拍摄要求：%s；%s。" % (g["visual"], g["composition"]), ""]
        else:
            L += ["**提示词**", "", "```", build_prompt(p, g, a.with_text), "```", "", "**反向提示词**", "", "```", NEGATIVE, "```", ""]
        L += ["**后期加字**：%s" % g["text"], "- 位置：%s" % ("上方三分之一，居中" if g["role"] == "封面" else "顶部标题区，左对齐"),
              "- 字体：粗黑体，字号以手机上一眼能读为准；重点词可用配色中的强调色"]
        if im.get("brand_tag", "").strip():
            L.append("- 品牌角标：顶部居中小字「%s」，每张图位置和样式相同" % im["brand_tag"].strip())
        L.append("")
        if p["type"] == "视频":
            L += ["**口播**（约 %s 秒）：%s" % (g.get("seconds", ""), g.get("voiceover", "")), ""]
    text = "\n".join(L)
    out = a.out or os.path.join(PLAN_DIR, "%s_prompts.md" % p["id"])
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print("\n已保存：%s" % out)


def cmd_templates(a):
    print("# 内容模板\n")
    for name, t in T.items():
        print("- **%s**（角度含：%s）：封面 → %s" % (name, "、".join(t["match"]), " → ".join(r for r, _, _ in t["pages"])))
    print("\n# 发布目标（new --goal）\n")
    for k, (metric, tpls, why) in GOALS.items():
        print("- **%s**：主指标 %s；建议模板 %s。%s。" % (k, metric, "、".join(tpls), why))
    print("\n# 配图风格\n")
    for k, v in STYLES.items():
        print("- **%s**：%s" % (k, v))


def main():
    ap = argparse.ArgumentParser(description="小红书发布方案与配图提示词")
    ap.add_argument("--log", default=DEFAULT_LOG)
    ap.add_argument("--analysis", default=DEFAULT_ANALYSIS)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def sp(name, fn, need_id=True):
        s = sub.add_parser(name)
        s.add_argument("--log", default=argparse.SUPPRESS)
        s.add_argument("--analysis", default=argparse.SUPPRESS)
        if need_id:
            s.add_argument("--id", required=True)
        s.set_defaults(fn=fn)
        return s

    s = sp("new", cmd_new)
    s.add_argument("--template", choices=list(T)); s.add_argument("--goal", choices=list(GOALS)); s.add_argument("--style", default=None); s.add_argument("--pages", type=int); s.add_argument("--force", action="store_true")
    sp("show", cmd_show)
    sp("check", cmd_check)
    s = sp("prompts", cmd_prompts)
    s.add_argument("--with-text", action="store_true"); s.add_argument("--out"); s.add_argument("--force", action="store_true")
    sp("templates", cmd_templates, need_id=False)
    a = ap.parse_args()
    if a.cmd == "new":
        a.style_given = a.style is not None
        a.style = a.style or "实拍生活感"
    a.fn(a)


if __name__ == "__main__":
    main()

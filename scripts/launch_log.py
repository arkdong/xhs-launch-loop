#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布日志：把每篇小红书笔记记录为一次「发布」，贯穿 调研→发布→反馈→迭代。

用法（在你自己的工作目录运行，脚本用绝对路径）:
  python3 launch_log.py status
  python3 launch_log.py init --product 产品名 --category 品类 --audience 人群 --selling-points "卖点1,卖点2"
                             [--price 价格] [--goal 互动] [--identity 品牌方] [--fact 缺点=…] [--tone 语气]     --goal 可选 触达 / 互动 / 收藏
  python3 launch_log.py fact 价格="39 元 50g" 缺点="冬天不够润"        补充或修改产品事实
  python3 launch_log.py add --title 暂定标题 --hypothesis 假设 [--angle 角度] [--evidence 依据] [--type 视频]
  python3 launch_log.py add --title 标题 --baseline [--published 2026-11-20] [--url 链接]   没有假设的笔记（已经发过的、随手发的），登记为基线
  python3 launch_log.py publish --id L1 --url 链接 [--final-title 最终标题] [--date 2026-11-20]
  python3 launch_log.py metrics --id L1 --impressions N --views N --likes N --collects N --comments N [--shares N --follows N --label 72h]
  python3 launch_log.py verdict --id L1 --result 证据不足 --learning 一句话 [--force 理由]     --result 可选 成立 / 不成立 / 证据不足 / 基线
  python3 launch_log.py next
  python3 launch_log.py report [--out 文件]
数据目录默认是当前目录下的 xhs_launch，可用 --dir 指定（不同产品用不同目录）。只依赖 Python 3 标准库。
"""
import argparse, os, re, sys
from collections import Counter, OrderedDict
from datetime import datetime

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

RESULTS = ["成立", "不成立", "证据不足", "基线"]
GOALS = OrderedDict([("触达", "点击率与观看"), ("互动", "评论率"), ("收藏", "收藏点赞比")])
MAIN_RATE = {"触达": ("ctr", "点击率"), "互动": ("comment_rate", "评论率"), "收藏": ("collect_like", "收藏点赞比")}
MIN_IMPRESSIONS = 1000   # 曝光不到这个数，数据还不稳定
MIN_COMMENTS = 20        # 评论不到这个数，评论洞察只能当线索
MIN_LIKES = 20           # 点赞不到这个数，收藏点赞比不稳定
MIN_MENTIONS = 3         # 累计不到这个数，不算一个痛点
# 写笔记前必须由用户提供的事实。建档时一次问清，之后每篇笔记直接复用。只做反馈分析用不到，可以先空着。
FACTS = OrderedDict([
    ("价格", "售价多少，什么规格？折算到每次使用大约多少钱？"),
    ("使用情况", "你（或真实用户）用了多久、多少次？在什么场景用？"),
    ("结果", "有没有一个可以量化的结果（省了多少时间、多少钱、几步完成）？"),
    ("缺点", "它最明显的缺点或不适合的人是什么？"),
    ("素材", "手头有哪些真实照片或视频（产品、使用过程、成品）？"),
    ("购买方式", "读者在小红书站内怎么找到它（店铺名、商品卡、主页）？"),
    ("身份", "你和产品的关系：品牌方 / 店主 / 员工 / 自己买的用户 / 收了报酬的合作？"),
])
# 有就记、答不上来不追问的事实：调研和写笔记时会用上，但不拦流程
OPTIONAL_FACTS = OrderedDict([
    ("定位", "一句话：这是什么，给谁用，解决什么？"),
    ("外观", "产品长什么样（颜色、形状、材质、包装）？拍摄和配图时用"),
    ("竞品", "读者常拿来和它比的产品或品牌"),
    ("常见吐槽", "这类产品最常被吐槽的地方"),
    ("固定标签", "每篇都要带的话题标签"),
])
NONE_FACT = re.compile(r"^\s*(无|没有|暂无|没|none|n/?a|-+|—+)\s*[。.]?\s*$", re.I)
# 这两项不能答「无」。别的项（比如素材、结果）用户明确说没有时可以填「无」；没问到、答不上来的一律空着
NO_NONE = OrderedDict([("缺点", "每个产品都有不适合的人或场景，写「无」读者不信，方案检查也过不了"), ("身份", "你和产品的关系必须写明，这是平台的要求")])


def drop_none(facts):
    """把「缺点=无」「身份=无」拿掉，返回给用户看的说明。"""
    bad = [k for k, v in facts.items() if k in NO_NONE and NONE_FACT.match(v)]
    for k in bad:
        facts.pop(k)
    return ["「%s」不能填「无」，没有存：%s。不知道就先空着，写笔记前再问用户。" % (k, NO_NONE[k]) for k in bad]
EMPTY_HYPO = re.compile(r"^\s*(无|暂无|没有|待定|待补|待填|todo|tbd|n/?a|none|-+|—+|？+|\?+)?\s*$", re.I)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load(a, must=True):
    path = C.log_path(a)
    data = C.read_json(path)
    if data is None:
        if must:
            sys.exit("还没有发布日志（%s）。请先建档。建档要问用户什么、命令怎么写，运行下面这条就会列出来：\n%s" % (C.where(path), C.cmd("launch_log.py", "status")))
        return None
    p = data.setdefault("product", {})
    for k, v in (("name", ""), ("category", ""), ("audience", ""), ("tone", ""), ("goal", ""), ("selling_points", []), ("facts", {})):
        p.setdefault(k, v)
    for l in data.setdefault("launches", []):
        for k, v in (("hypothesis", ""), ("evidence", ""), ("angle", ""), ("type", "图文"), ("metrics", []), ("verdict", None), ("baseline", False)):
            l.setdefault(k, v)
    return data


def save(a, data):
    data["updated_at"] = now()
    C.write_json(C.log_path(a), data)


def find(data, lid):
    for l in data["launches"]:
        if l["id"].lower() == lid.lower():
            return l
    sys.exit("找不到发布 %s。现有编号：%s" % (lid, "、".join(l["id"] for l in data["launches"]) or "无"))


def rate(a, b):
    return round(a / b, 4) if a is not None and b else None


def pct(v):
    return "未知" if v is None else C.rate_pct(v, 1)


def show(v):
    return "—" if v is None else str(v)


def compute(m):
    g = lambda k: m.get(k) or 0
    inter = g("likes") + g("collects") + g("comments") + g("shares")
    return {
        "ctr": rate(m.get("views"), m.get("impressions")),                 # 点击率 = 观看 / 曝光
        "engagement": rate(inter, m.get("views")),                         # 互动率 = (赞+藏+评+转) / 观看
        "collect_like": round(g("collects") / m["likes"], 2) if m.get("likes") and m.get("collects") is not None else None,  # 收藏点赞比
        "comment_rate": rate(m.get("comments"), m.get("views")),
        "follow_rate": rate(m.get("follows"), m.get("views")),
    }


def exact(m):
    """没有四舍五入的比率：两篇之间的变化幅度用它算，免得先取整再相除把 +158% 算成 +157%。"""
    g = lambda k: m.get(k) or 0
    div = lambda a, b: (a / b) if a is not None and b else None
    return {"ctr": div(m.get("views"), m.get("impressions")), "engagement": div(g("likes") + g("collects") + g("comments") + g("shares"), m.get("views")),
            "collect_like": div(g("collects"), m.get("likes")) if m.get("collects") is not None else None, "comment_rate": div(m.get("comments"), m.get("views"))}


def diagnose(m, r, prev, goal=""):
    """经验线只用来提示方向，不下因果结论；真正的基准是和自己的另一篇对比。"""
    d = []
    if not m.get("views"):
        d.append("没有观看数，算不出点击率、互动率和评论率，只能看点赞、收藏、评论的绝对数。观看（阅读）数在创作者中心的笔记数据里。")
    if m.get("impressions") is None:
        d.append("没有曝光数，算不出点击率，也无法判断数据是否稳定。在创作者中心的笔记数据里能看到曝光（展现）数。")
    elif m["impressions"] < MIN_IMPRESSIONS:
        d.append("曝光不足 %d，数据还不稳定，先不要下结论；24 到 72 小时后再记录一次。" % MIN_IMPRESSIONS)
    if r["ctr"] is not None:
        if r["ctr"] < 0.08:
            d.append("点击率 %s，低于 8%% 的经验线：刷到的人里点开的少，先怀疑封面和标题。下一次只改封面文字和标题，其他不动。" % pct(r["ctr"]))
        elif r["ctr"] >= 0.15:
            d.append("点击率 %s，达到 15%% 的经验线：封面和标题这次没有拖后腿。是不是这个角度起的作用，要和另一篇对比才知道。" % pct(r["ctr"]))
    if r["engagement"] is not None:
        if r["engagement"] < 0.03:
            d.append("互动率 %s，低于 3%% 的经验线：点开的人里互动的少。检查正文前两行有没有兑现标题，内容够不够具体。" % pct(r["engagement"]))
        elif r["engagement"] >= 0.08:
            d.append("互动率 %s，达到 8%% 的经验线。互动里有多少是认可、多少是吐槽，要看评论内容，这个数本身说明不了。" % pct(r["engagement"]))
    if r["collect_like"] is not None:
        if r["collect_like"] >= 1:
            d.append("收藏点赞比 %.2f，大于 1：收藏的人比点赞的多，读者更像是把它当资料存。可以考虑做成系列教程或清单。" % r["collect_like"])
        elif r["collect_like"] < 0.3:
            d.append("收藏点赞比 %.2f，低于 0.3 的经验线：点赞的多、收藏的少。想提高收藏，在正文补上可以照做的步骤或清单。" % r["collect_like"])
    if r["comment_rate"] is not None and r["comment_rate"] < 0.005 and (m.get("views") or 0) >= 500:
        d.append("评论率 %s，低于 0.5%% 的经验线：结尾留一个容易回答的具体问题。评论是下一轮反馈的来源。" % pct(r["comment_rate"]))
    if m.get("comments") is not None and m["comments"] < MIN_COMMENTS:
        d.append("评论 %d 条，不到 %d 条：评论里看到的东西只能当线索%s。" % (m["comments"], MIN_COMMENTS, "" if goal == "触达" else "，关于评论的假设只能登记为「证据不足」"))
    if prev:
        pr, mine, theirs = prev["rates"], exact(m), exact(prev["raw"]) if prev.get("raw") else prev["rates"]
        for key, name in (("ctr", "点击率"), ("engagement", "互动率"), ("comment_rate", "评论率"), ("collect_like", "收藏点赞比")):
            if r.get(key) is not None and pr.get(key) and mine.get(key) is not None and theirs.get(key):
                change = (mine[key] - theirs[key]) / theirs[key]
                if abs(change) >= 0.1:
                    d.append("对比 %s：%s %s → %s（%s%s）%s。" % (prev["id"], name, fmt_rate(key, pr[key]), fmt_rate(key, r[key]), "+" if change > 0 else "", C.rate_pct(change, 0),
                                                               "，这是这一篇的主指标" if MAIN_RATE.get(goal, ("",))[0] == key else ""))
    else:
        d.append("没有另一篇有数据的发布可以对比：这一篇的数字就是你的基线，下一篇和它比。")
    return d


def comparator(data, l):
    """拿来对比的那一篇：编号比它早、有数据的最近一篇；没有的话，用后来补登记的有数据的一篇（通常是基线）。"""
    ls = data["launches"]
    i = ls.index(l)
    for o in list(reversed(ls[:i])) + ls[i + 1:]:
        if o["metrics"]:
            return o
    return None


def goal_of(data, l):
    return l.get("goal") or data["product"].get("goal") or ""


def fmt_rate(key, v):
    return show(v) if key == "collect_like" else pct(v)


def missing_facts(p):
    return [k for k in FACTS if not str(p["facts"].get(k) or "").strip()]


def readers(l, ins=None):
    """这篇笔记的评论里有多少是读者说的。返回 {"valid", "read", "others", "rate"} 或 None（没有评论洞察）。
    平台的评论数连作者自己的回复、广告都算；只算读者的评论率更能说明读者的反应。"""
    ins = ins or l.get("insight") or {}
    if ins.get("total") is None or not (ins.get("parse") or ins.get("read")):
        return None
    read = (ins.get("parse") or {}).get("raw_entries") or ins.get("read") or ins["total"]
    views = l["metrics"][-1]["raw"].get("views") if l["metrics"] else None
    return {"valid": ins["total"], "read": read, "others": read - ins["total"], "rate": (ins["total"] / views) if views else None}


def reader_note(l, ins=None):
    """平台评论数里读者评论占多少的一句话；不值得说时返回空。"""
    x = readers(l, ins)
    m = l["metrics"][-1]["raw"] if l["metrics"] else {}
    if not x or not x["others"] or x["rate"] is None or m.get("comments") is None:
        return ""
    return "平台显示的评论数 %d 条里包含作者自己的回复和无关评论。评论洞察读到 %d 条，其中读者的有效评论 %d 条；只算读者，评论率约 %s。和别的笔记比评论率时，两边要用同一种口径。" % (
        m["comments"], x["read"], x["valid"], pct(x["rate"]))


def profile_lines(p):
    L = ["- 产品：%s｜品类：%s" % (p["name"], p["category"] or "未填"), "- 目标人群：%s" % (p["audience"] or "未填")]
    sp = p["selling_points"]
    L.append("- 卖点（%d 条）：%s" % (len(sp), "；".join("%s %s" % ("①②③④⑤⑥⑦⑧⑨⑩"[i] if i < 10 else "%d." % (i + 1), x) for i, x in enumerate(sp))) if sp else "- 卖点：未填")
    L.append("- 语气：%s｜发布目标：%s" % (p["tone"] or "未填", ("%s（主指标：%s）" % (p["goal"], GOALS[p["goal"]])) if p["goal"] in GOALS else "未定"))
    for k in list(FACTS) + [k for k in p["facts"] if k not in FACTS]:
        if str(p["facts"].get(k) or "").strip():
            L.append("- %s：%s" % (k, p["facts"][k]))
    return L


def cmd_status(a):
    data = load(a, must=False)
    if not data:
        print(intake(a))
        return
    p = data["product"]
    print("# 产品档案\n\n" + "\n".join(profile_lines(p)))
    miss = missing_facts(p)
    if miss:
        print("- 写笔记前还缺：%s（用 fact 补上；只做反馈分析用不到，可以先空着）" % "、".join(miss))
    print("- 数据目录：%s\n" % C.where(C.data_dir(a)))
    print("# 发布记录（共 %d 次）\n" % len(data["launches"]))
    if not data["launches"]:
        print("还没有登记发布，用 add 登记第一次。")
    for l in data["launches"]:
        v = l.get("verdict")
        print("- %s｜%s｜%s｜%s\n  %s%s\n  结论：%s%s%s" % (
            l["id"], l["status"], l["type"], l.get("final_title") or l["title"],
            "基线（没有假设，只记录数据）" if l["baseline"] else "假设：" + l["hypothesis"], ("\n  依据：" + l["evidence"]) if l.get("evidence") else "",
            v["result"] if v else "待复盘", ("｜" + v["learning"]) if v else "", ("（证据未达标，强制登记：%s）" % v["forced"]) if v and v.get("forced") else ""))
    pend = [l["id"] for l in data["launches"] if l["status"] == "已发布" and not l.get("verdict")]
    if pend:
        print("\n待复盘：%s（提供评论和数据即可进入反馈阶段）" % "、".join(pend))


GOAL_ASK = "发这一篇最想要什么，三选一：触达（让更多人看到）、互动（多评论）、收藏（被当资料存下来）"
LATER = ("使用情况", "结果", "缺点", "素材", "购买方式")      # 写笔记前才用得上的事实：第二轮再问


def intake(a):
    """还没有档案时给助手看的：建档前要问用户什么，按用户要做的事分两组，每组后面是照着填的命令。
    提问最多两轮：这里是第一轮；第二轮在写笔记之前，由 content_plan.py new 列出当时还缺的。"""
    L = ["尚未建立发布日志（%s）。" % C.where(C.log_path(a)),
         "先问清下面的事再建档。按用户要做的事选一组，一次问完；用户答不上来的先空着，不要填「无」，更不要替他编。", "",
         "## 一、只想看一篇已经发出去的笔记（复盘）", "",
         "问 4 样：",
         "1. 产品叫什么",
         "2. " + GOAL_ASK,
         "3. 那篇笔记的标题和发布日期",
         "4. 用户在小红书的昵称，用来把他自己的回复和读者的评论分开",
         "同时请用户把评论区和数据发过来。数据是曝光、观看、点赞、收藏、评论这几个数，有几个给几个。", "",
         "建档，再把那篇笔记登记成基线：",
         C.cmd("launch_log.py", "init", "--product", '"产品名"', "--goal", "互动"),
         C.cmd("launch_log.py", "add", "--title", '"那篇笔记的标题"', "--baseline", "--published", "2026-11-20"), "",
         "## 二、要调研、写新笔记", "",
         "调研前问 7 样：",
         "1. 产品叫什么，属于什么品类（读者搜它的时候会打的那个词）",
         "2. 给谁用",
         "3. 最想让人记住的一两个卖点，记用户的原话",
         "4. 价格：" + FACTS["价格"],
         "5. " + GOAL_ASK,
         "6. 身份：" + FACTS["身份"],
         "7. 知道就说、不知道就跳过：读者常拿它和谁比，这类产品最常被吐槽什么，想用什么语气，以前有没有发过这个产品的笔记", "",
         "建档：",
         C.cmd("launch_log.py", "init", "--product", '"产品名"', "--category", '"品类"', "--audience", '"目标人群"', "--selling-points", '"卖点1,卖点2"', "--price", '"价格和规格"',
               "--goal", "互动", "--identity", '"品牌方"'),
         "第 7 样里答了的接在这条命令后面：--tone \"语气\" --fact 竞品=\"…\" --fact 常见吐槽=\"…\"。以前发过的笔记另外登记成基线，命令见第一组。", "",
         "写笔记之前还有第二轮，到时候一次问完。生成方案骨架时会列出当时还缺的，一般是这几样："]
    L += ["- %s：%s" % (k, FACTS[k]) for k in LATER]
    L += ["- 外观：%s" % OPTIONAL_FACTS["外观"],
          "用户想跳过调研直接写笔记时，两轮合成一轮问。用户明确说没有的（比如没有实拍素材）才填「无」，缺点和身份不能填「无」。"]
    return "\n".join(L)


def split_points(text):
    """卖点怎么拆：用了英文逗号或分号，就只按它们拆（卖点里面的中文逗号保留）；没有的话才按中文的逗号、顿号、分号拆。"""
    text = str(text or "")
    return [x.strip() for x in re.split(r"[,;\n]" if re.search(r"[,;\n]", text) else r"[，、；]", text) if x.strip()]


def parse_facts(pairs):
    out = OrderedDict()
    for x in pairs or []:
        m = re.match(r"^\s*([^=＝:：]+?)\s*[=＝:：]\s*(.*)$", x, flags=re.S)
        if not m:
            sys.exit("事实要写成「键=值」，例如 价格=\"39 元 50g\"。收到的是：%s" % x)
        out[m.group(1).strip()] = m.group(2).strip()
    return out


def take_tone(p, facts):
    """「语气」记在档案的 tone 里，不算产品事实：fact 语气="…" 和 --fact 语气="…" 都认。返回记下的语气。"""
    tone = str(facts.pop("语气", "") or "").strip()
    if tone and not NONE_FACT.match(tone):
        p["tone"] = tone
        return tone
    return ""


def cmd_init(a):
    C.check_cwd()
    old = load(a, must=False)
    if old and not a.force:
        sys.exit("发布日志已存在（产品：%s）。要给另一个产品建档，换一个数据目录：加 --dir 新目录；要修改这个产品的档案，加 --force（只更新你给出的项，保留历史发布）。" % old["product"]["name"])
    data = old or {"version": 2, "created_at": now(), "launches": [], "product": {"name": "", "category": "", "audience": "", "tone": "", "goal": "", "selling_points": [], "facts": {}}}
    p = data["product"]
    if not a.product and not p["name"]:
        sys.exit("建档需要 --product 产品名。")
    for k, v in (("name", a.product), ("category", a.category), ("audience", a.audience), ("tone", a.tone), ("goal", a.goal)):
        if v:
            p[k] = v
    if a.selling_points or a.selling_point:
        p["selling_points"] = split_points(a.selling_points) + [x.strip() for x in a.selling_point or [] if x.strip()]
    facts = parse_facts(a.fact)
    take_tone(p, facts)
    if a.price:
        facts["价格"] = a.price
    if a.identity:
        facts["身份"] = a.identity
    refused = drop_none(facts)
    p["facts"].update(facts)
    save(a, data)
    print("%s：%s → %s\n" % ("已更新档案" if old else "已建档", p["name"], C.where(C.log_path(a))))
    print("存下来的内容（和用户说的对一遍，尤其是卖点拆得对不对）：\n" + "\n".join(profile_lines(p)))
    if len(p["selling_points"]) > 1 and a.selling_points and not re.search(r"[,;\n]", a.selling_points):
        print("  卖点是按中文逗号、顿号拆开的。有哪条被拆散了，用 --force 重给：每条卖点各写一次 --selling-point \"…\"，或者用英文逗号分隔。")
    for x in refused:
        print(x)
    miss = missing_facts(p)
    if miss:
        print("\n写笔记（阶段 ②）之前还需要这些事实；只做反馈分析（阶段 ③）用不到，可以先空着。用户明确说没有的（比如没有实拍素材）才填「无」：")
        for k in miss:
            print("- %s：%s" % (k, FACTS[k]))
        print("补充：%s" % C.cmd("launch_log.py", "fact", *['%s="…"' % k for k in miss[:3]]))
    if not p["goal"]:
        print("还没定发布目标。--goal 从三个里选一个：触达（让更多人看到）、互动（多评论）、收藏（被当资料存下来）。")
    print("\n下一步，按你要做的事选一条：")
    print("- 调研再写新笔记：%s%s" % (C.cmd("research.py", "keywords", *([] if p["category"] else ["--category", '"品类"'])), "\n  （品类、卖点、人群自动取自档案，不用再写。）" if p["category"] else ""))
    print("- 先看一篇已经发出去的笔记的反馈：%s" % C.cmd("launch_log.py", "add", "--title", '"那篇笔记的标题"', "--baseline", "--published", "发布日期"))


def cmd_fact(a):
    data = load(a)
    facts = parse_facts(a.pairs)
    tone = take_tone(data["product"], facts)
    refused = drop_none(facts)
    if not facts and not tone:
        sys.exit("\n".join(refused) or "没有可以记的内容。事实要写成「键=值」，例如 缺点=\"香味半小时就散了\"。")
    data["product"]["facts"].update(facts)
    save(a, data)
    print("已更新：%s" % "；".join(["%s = %s" % kv for kv in facts.items()] + (["语气 = %s" % tone] if tone else [])))
    for x in refused:
        print(x)
    miss = missing_facts(data["product"])
    print("还缺：%s" % "、".join(miss) if miss else "写笔记需要的事实已齐。")


def insight_path(a, lid):
    return C.P(a, "feedback", "%s_insight.json" % lid)


def step_comments(lid):
    return C.cmd("comment_insight.py", '"评论文件"', "--id", lid, "--author", '"你的昵称"')


def step_metrics(lid, label=""):
    return C.cmd("launch_log.py", "metrics", "--id", lid, *((["--label", label] if label else []) + ["--impressions", "N", "--views", "N", "--likes", "N", "--collects", "N", "--comments", "N"]))


def step_verdict(l):
    return C.cmd("launch_log.py", "verdict", "--id", l["id"], "--result", "基线" if l["baseline"] else "证据不足", "--learning", '"一句话结论"')


RESULT_HINT = "--result 从 成立、不成立、证据不足 里选一个。"


def cmd_add(a):
    data = load(a)
    if a.baseline and a.hypothesis:
        sys.exit("--baseline 和 --hypothesis 只能选一个：有假设就不是基线。")
    if not a.baseline and EMPTY_HYPO.match(a.hypothesis or ""):
        sys.exit("每次发布要带一个可以被证伪的假设（例如「以黏键盘痛点开头，评论率会高于上一篇」）。\n"
                 "如果这篇没有假设（已经发过的笔记、随手发的），用 --baseline 登记为基线，不要编一个假设。")
    when = None
    if a.published is not None:      # 这篇已经发出去了：直接记成已发布
        when = now() if a.published == "" else C.parse_date(a.published)
        if not when:
            sys.exit("--published 后面写发布日期，例如 2026-11-20 或「3天前」；收到的是：%s" % a.published)
    lid = "L%d" % (len(data["launches"]) + 1)
    goal = a.goal or data["product"].get("goal") or ""
    l = {"id": lid, "status": "已发布" if when else "计划中", "type": a.type, "title": a.title, "angle": a.angle or "", "baseline": bool(a.baseline),
         "hypothesis": "" if a.baseline else a.hypothesis.strip(), "evidence": a.evidence or "", "goal": goal,
         "main_metric": a.metric or GOALS.get(goal, ""), "created_at": now(), "metrics": [], "verdict": None}
    if when:
        l.update(published_at=when, url=a.url or "")
    elif a.url:
        l["url"] = a.url
    others = [o for o in data["launches"] if o["metrics"]]
    data["launches"].append(l)
    save(a, data)
    if a.baseline:
        print("已登记发布 %s：%s（基线，没有假设）。它的数据会成为以后各篇的对比基准。" % (lid, a.title))
    else:
        print("已登记发布 %s：%s\n待验证假设：%s" % (lid, a.title, l["hypothesis"]))
        named = re.findall(r"[Ll]\d+", l["hypothesis"])
        known = [o["id"] for o in data["launches"] if o is not l]
        ghost = [x.upper() for x in named if x.upper() not in known]
        if ghost:
            print("注意：假设里提到了 %s，但发布日志里没有这个编号。现有编号：%s。" % ("、".join(ghost), "、".join(known) or "无"))
        if not others:
            print("注意：现在没有另一篇有数据的笔记可以对比。假设可以照常登记，但这一篇发完只能判「证据不足」，它的数据会成为基线，下一篇再和它比。\n"
                  "以前发过笔记的话，先把其中一篇登记成基线并录入数据：%s" % C.cmd("launch_log.py", "add", "--title", '"旧笔记标题"', "--baseline", "--published", "发布日期"))
        elif not named and not re.search(r"高于|低于|超过|不如|多于|少于|比|更", l["hypothesis"]):
            print("注意：假设里没有写和哪一篇比、看哪个指标，复盘时没法判断。建议写成「……，%s高于 %s」这样。" % (GOALS.get(goal, "评论率"), others[-1]["id"]))
    if when:
        print("发布日期记为 %s。" % when[:10])
        print("下一步（两件事，先后都行）：\n- 看评论：%s\n- 录数据：%s" % (step_comments(lid), step_metrics(lid)))
    elif a.baseline:
        print("下一步（发出去以后）：%s\n已经发出去的笔记，登记时加 --published 发布日期 就不用这一步。" % C.cmd("launch_log.py", "publish", "--id", lid, "--url", '"笔记链接"'))
    else:
        print("下一步（发布方案）：%s" % C.cmd("content_plan.py", "new", "--id", lid))


def cmd_publish(a):
    data = load(a)
    l = find(data, a.id)
    when = now()
    if a.date:
        when = C.parse_date(a.date)
        if not when:
            sys.exit("--date 后面写发布日期，例如 2026-11-20；收到的是：%s" % a.date)
    l.update({"status": "已发布", "url": a.url or l.get("url", ""), "published_at": when})
    if a.final_title:
        l["final_title"] = a.final_title
    save(a, data)
    print("%s 已标记为已发布，发布日期记为 %s%s。" % (l["id"], when[:10], "" if a.date else "（今天；不是今天发的，加 --date 2026-11-20 重跑）"))
    print("建议在 24 小时、72 小时、7 天各记录一次数据：\n%s" % step_metrics(l["id"], "24h"))


def cmd_metrics(a):
    data = load(a)
    l = find(data, a.id)
    m = {k: (max(0, getattr(a, k)) if getattr(a, k) is not None else None) for k in ("impressions", "views", "likes", "collects", "comments", "shares", "follows")}
    if all(v is None for v in m.values()):
        sys.exit("没有收到任何数字。把创作者中心里这篇笔记的数据填进来，有几个填几个：--impressions 曝光 --views 观看 --likes 点赞 --collects 收藏 --comments 评论 --shares 分享 --follows 涨粉")
    r = compute(m)
    o = comparator(data, l)
    prev = {"id": o["id"], "rates": o["metrics"][-1]["rates"], "raw": o["metrics"][-1]["raw"]} if o else None
    diag = diagnose(m, r, prev, goal_of(data, l))
    l["metrics"].append({"recorded_at": now(), "label": a.label or "", "raw": m, "rates": r, "diagnosis": diag})
    if l["status"] == "计划中":
        l["status"] = "已发布"
    ins = C.read_json(insight_path(a, l["id"]))
    note = reader_note(l, ins) if isinstance(ins, dict) else ""
    if note:
        diag.append(note)
    save(a, data)
    print("# %s 数据诊断%s\n" % (l["id"], ("（%s）" % a.label) if a.label else ""))
    print("| 指标 | 数值 |\n|---|---|")
    print("| 曝光 / 观看 | %s / %s |" % (show(m["impressions"]), show(m["views"])))
    print("| 点赞 / 收藏 / 评论 / 分享 / 涨粉 | %s |" % " / ".join(show(m[k]) for k in ("likes", "collects", "comments", "shares", "follows")))
    print("| 点击率 | %s |\n| 互动率 | %s |\n| 收藏点赞比 | %s |\n| 评论率 | %s |\n" % (pct(r["ctr"]), pct(r["engagement"]), show(r["collect_like"]), pct(r["comment_rate"])))
    print("## 诊断\n\n「经验线」只用来提示方向，不是行业标准；真正的基准是和你自己的另一篇对比。\n")
    for x in diag:
        print("- " + x)
    print("\n%s" % ("这篇是基线，没有假设：复盘时登记 --result 基线。" if l["baseline"] else "待验证假设：%s" % l["hypothesis"]))
    if isinstance(ins, dict):
        print("下一步（下结论，评论已经分析过）：%s" % step_verdict(l))
    else:
        print("下一步（分析评论）：%s\n然后登记结论：%s" % (step_comments(l["id"]), step_verdict(l)))
    if not l["baseline"]:
        print(RESULT_HINT)


def evidence_gaps(data, l, ins):
    """判「成立 / 不成立」前要过的门槛，返回没过的原因。曝光和对比对象任何假设都要；评论数、点赞数按这一篇的主指标要求。"""
    why, goal = [], goal_of(data, l)
    m = l["metrics"][-1]["raw"] if l["metrics"] else None
    if not m:
        why.append("还没有录入数据（先运行 metrics）。")
    elif m.get("impressions") is None:
        why.append("没有曝光数，无法判断数据是否稳定。")
    elif m["impressions"] < MIN_IMPRESSIONS:
        why.append("曝光 %d，不到 %d。" % (m["impressions"], MIN_IMPRESSIONS))
    if goal == "收藏":
        if m and (m.get("likes") or 0) < MIN_LIKES:
            why.append("点赞 %d 个，不到 %d 个，收藏点赞比还不稳定。" % (m.get("likes") or 0, MIN_LIKES))
    elif goal != "触达":       # 互动，或者没定目标：都要看评论
        if ins and ins.get("total") is not None and ins["total"] < MIN_COMMENTS:
            why.append("有效评论 %d 条，不到 %d 条。" % (ins["total"], MIN_COMMENTS))
        elif not ins and ((m or {}).get("comments") or 0) < MIN_COMMENTS:
            why.append("评论 %d 条，不到 %d 条。" % ((m or {}).get("comments") or 0, MIN_COMMENTS))
        if ins and ins.get("parse", {}).get("warnings") and not ins["parse"].get("checked"):
            why.append("评论解析有疑点，条数还没核对（核对后给 comment_insight.py 加 --checked 重跑）。")
    o = comparator(data, l)
    if not o:
        why.append("没有另一篇有数据的发布可以对比，单篇笔记判断不了「更高」还是「更低」。把以前发过的笔记用 add --baseline 登记并录入数据，就有对比了。")
    elif m and goal in MAIN_RATE and l.get("main_metric", GOALS[goal]) == GOALS[goal]:
        key, name = MAIN_RATE[goal]
        lack = [x["id"] for x in (l, o) if x["metrics"][-1]["rates"].get(key) is None]
        if lack:
            why.append("主指标「%s」在 %s 上算不出来（缺观看数、曝光数或点赞数），没法比较。" % (name, "、".join(lack)))
    return why


def cmd_verdict(a):
    data = load(a)
    l = find(data, a.id)
    ipath = a.insight or insight_path(a, l["id"])
    if a.insight and not os.path.exists(a.insight):
        sys.exit("找不到洞察文件：%s" % a.insight)
    ins = C.read_json(ipath)
    if l["baseline"] and a.result in ("成立", "不成立"):
        sys.exit("%s 是基线，没有假设可以判定。请用 --result 基线，在 --learning 里写下这篇的数据水平和你观察到的事。" % l["id"])
    if not l["baseline"] and a.result == "基线":
        sys.exit("%s 登记时带了假设，结论只能是 成立 / 不成立 / 证据不足。" % l["id"])
    v = {"result": a.result, "learning": a.learning, "decided_at": now()}
    if a.result in ("成立", "不成立"):
        why = evidence_gaps(data, l, ins)
        if why and not a.force:
            sys.exit("证据还不够，不能登记「%s」：\n- %s\n请改为 --result 证据不足（在 --learning 里写下目前看到的线索），等数据够了再判。\n"
                     "如果你有脚本看不到的依据，加 --force \"理由\" 强制登记，理由会写进日志和报告。" % (a.result, "\n- ".join(why)))
        if why:
            v["forced"] = a.force
            v["unmet"] = why
    if ins:
        qc = ins.get("question_count") or {}
        l["insight"] = {"total": ins.get("total", 0), "sample_sufficient": bool(ins.get("sample_sufficient")), "read": (ins.get("parse") or {}).get("raw_entries"),
                        "question_count": {"total": qc.get("total", len(ins.get("questions_to_answer", []))), "open": qc.get("open", len(ins.get("questions_to_answer", [])))},
                        "claim_checks": [{"claim": c["claim"], "source": c["source"], "replies": [n for x in c["replies"] for n in x["numbers"]], "readers": len(c["readers"])}
                                         for c in ins.get("claim_checks") or []],
                        "intents": {i["intent"]: i["share"] for i in ins.get("intent_distribution", [])},
                        "pains": {x["aspect"]: {"count": x["complaints"], "questions": x.get("questions", 0), "quotes": x.get("complaint_quotes", [])[:2]}
                                  for x in ins.get("aspects", []) if x.get("complaints") or x.get("questions")}
                        or {k: {"count": c["count"], "questions": 0, "quotes": c.get("quotes", [])[:2]} for k, c in ins.get("pain_clusters", {}).items()},
                        "question_topics": [{"topic": q["topic"], "count": q["count"], "examples": q.get("examples", [])[:1]} for q in ins.get("question_topics", [])],
                        "questions": ins.get("questions_to_answer", [])[:5], "keywords": [k["word"] for k in ins.get("keywords", [])[:10]]}
    l["verdict"] = v
    l["status"] = "已复盘"
    save(a, data)
    print("%s %s → %s%s\n沉淀：%s" % (l["id"], "基线" if l["baseline"] else "假设「%s」" % l["hypothesis"], a.result, "（证据未达标，强制登记）" if v.get("forced") else "", a.learning))
    goal, o = goal_of(data, l), comparator(data, l)
    if goal in MAIN_RATE and l["metrics"]:
        key, name = MAIN_RATE[goal]
        mine = l["metrics"][-1]["rates"].get(key)
        theirs = o["metrics"][-1]["rates"].get(key) if o else None
        print("主指标（目标：%s）%s：%s %s%s" % (goal, name, l["id"], fmt_rate(key, mine), ("，对比 %s %s" % (o["id"], fmt_rate(key, theirs))) if o else ""))
        if key == "comment_rate" and reader_note(l):
            print("注意：" + reader_note(l))
        if not l["baseline"] and mine is not None and theirs:      # 结论和数字的方向对不上时提醒一句（不拦：假设也可能说的是别的指标，或者「更低」）
            if a.result == "成立" and mine <= theirs:
                print("注意：%s的%s没有高于 %s。如果假设说的是主指标「更高」，结论应该是「不成立」，请核对后重新登记。" % (l["id"], name, o["id"]))
            elif a.result == "不成立" and mine >= theirs * 1.1:
                print("注意：%s的%s比 %s 高出一成以上。如果假设说的是主指标「更高」，结论应该是「成立」，请核对后重新登记。" % (l["id"], name, o["id"]))
    if not ins:
        print("提示：没有找到这次发布的评论洞察（%s），痛点不会累计到 next。" % C.where(ipath))
    elif ins.get("total", 0) < MIN_COMMENTS:
        print("注意：有效评论 %d 条，不到 %d 条。评论里的吐槽和问题只当线索累计，next 和报告里会一直带着这个标记。" % (ins.get("total", 0), MIN_COMMENTS))
    if ins and ins.get("claim_checks"):
        print("注意：档案里有 %d 条带数字的说法在评论区被追问，或者和评论区的数字对不上（见评论洞察的「说法核对」），next 和报告里会列为「待核实」。" % len(ins["claim_checks"]))
    print("下一步：%s" % C.cmd("launch_log.py", "next"))


def summarize(data):
    ls = data["launches"]
    goal = data["product"].get("goal") or ""
    key, name = MAIN_RATE.get(goal, ("engagement", "互动率"))
    scored = [(l, l["metrics"][-1]) for l in ls if l["metrics"]]
    best = sorted(scored, key=lambda x: -(x[1]["rates"].get(key) or 0))
    pains, asks, quotes, questions, topics, samples, checks = Counter(), Counter(), {}, [], Counter(), [], []
    q_open = 0
    for l in ls:
        ins = l.get("insight") or {}
        if ins.get("total") is not None:
            samples.append((l["id"], ins["total"]))
        for k, c in ins.get("pains", {}).items():
            pains[k] += c.get("count", 0)
            asks[k] += c.get("questions", 0)
            quotes.setdefault(k, [])
            quotes[k] += [(q, l["id"]) for q in c.get("quotes", [])]
        for q in ins.get("question_topics", []):
            topics[q["topic"]] += q["count"]
        questions += [(q, l["id"]) for q in ins.get("questions", [])]
        q_open += (ins.get("question_count") or {}).get("open", len(ins.get("questions", [])))
        checks += [(l["id"], c) for c in ins.get("claim_checks") or []]
    done = lambda r: [l for l in ls if l.get("verdict") and l["verdict"]["result"] == r]
    total = sum(n for _, n in samples)
    return {"best": best, "rank_by": name, "rank_key": key, "proven": done("成立"), "disproven": done("不成立"), "baselines": [l for l in ls if l["baseline"]],
            "open": [l for l in ls if not l["baseline"] and (not l.get("verdict") or l["verdict"]["result"] == "证据不足")],
            "pains": pains.most_common(), "asks": asks, "quotes": quotes, "questions": questions, "questions_open": q_open,
            "samples": samples, "comments": total, "enough": total >= MIN_COMMENTS, "checks": checks,
            "topics": sorted(topics.most_common(), key=lambda kv: kv[0] == "其他问题")}       # 没归类的问题排在最后


def render_next(data):
    s = summarize(data)
    if not data["launches"]:
        return "还没有任何发布记录。先完成一次 调研→发布→反馈，再来迭代。"
    tag = lambda l: "（证据未达标，强制登记）" if l["verdict"].get("forced") else ""
    L = ["# 下一次发布的依据（%s）" % data["product"]["name"], ""]
    if s["checks"]:
        L += ["## 待核实的说法", "", "档案里的数字在评论区被追问，或者和评论区的数字对不上。先确认数字站得住：对的就去评论区回答，不对就改档案；确认之前下一篇不要用它："]
        for lid, c in s["checks"]:
            bits = (["作者回复里是 %s" % "、".join(c["replies"])] if c.get("replies") else []) + (["%d 条读者评论在问或给出了别的数字" % c["readers"]] if c.get("readers") else [])
            L.append("- %s：档案（%s）「%s」，%s。" % (lid, c["source"], c["claim"], "；".join(bits)))
        L.append("")
    L += ["## 已被验证有效，继续沿用", ""] + (["- %s：%s（%s）%s" % (l["id"], l["verdict"]["learning"], l["hypothesis"], tag(l)) for l in s["proven"]] or ["- 暂无"])
    L += ["", "## 已被证伪，不要重复", ""] + (["- %s：%s（%s）%s" % (l["id"], l["verdict"]["learning"], l["hypothesis"], tag(l)) for l in s["disproven"]] or ["- 暂无"])
    L += ["", "## 尚未验证的假设", ""] + (["- %s：%s" % (l["id"], l["hypothesis"]) for l in s["open"]] or ["- 暂无，需要提出新假设"])
    if s["baselines"]:
        L += ["", "## 基线（没有假设，只作对比基准）", ""] + ["- %s「%s」%s" % (l["id"], l.get("final_title") or l["title"], ("：" + l["verdict"]["learning"]) if l.get("verdict") else "") for l in s["baselines"]]
    L += ["", "## 表现排序（按%s%s）" % (s["rank_by"], "，这个产品的主指标" if data["product"].get("goal") in MAIN_RATE else ""), ""]
    for l, m in s["best"]:
        L.append("- %s「%s」角度：%s｜曝光 %s｜点击率 %s｜互动率 %s｜评论率 %s｜收藏点赞比 %s" % (
            l["id"], l.get("final_title") or l["title"], l["angle"] or "未填", show(m["raw"].get("impressions")),
            pct(m["rates"]["ctr"]), pct(m["rates"]["engagement"]), pct(m["rates"].get("comment_rate")), show(m["rates"]["collect_like"])))
    if not s["best"]:
        L.append("- 暂无数据")
    if len(s["best"]) == 1:
        L.append("只有一篇有数据，排不出高低；它就是基线。")
    L += ["", "## 评论里的线索（跨发布累计）", ""]
    if s["samples"]:
        L.append("累计有效评论 %d 条（%s）。累计满 %d 条、同一维度吐槽满 %d 条，才算痛点；不到的只是线索，不要据此改产品或定下一篇。同一个维度里可能混着不同的问题，先看原话。"
                 % (s["comments"], "，".join("%s %d 条" % x for x in s["samples"]), MIN_COMMENTS, MIN_MENTIONS))
        if not s["enough"]:
            L.append("⚠️ 样本不足：累计有效评论不到 %d 条，下面全部只是线索。" % MIN_COMMENTS)
        L.append("")
    for k, c in s["pains"]:
        if not c and not s["asks"][k]:
            continue
        L.append("- **%s**：吐槽 %d 条，疑问 %d 条（%s）" % (k, c, s["asks"][k], "痛点" if c >= MIN_MENTIONS and s["enough"] else "线索"))
        for q, lid in s["quotes"][k][:3]:
            L.append("  - “%s”（%s）" % (q, lid))
    if not s["pains"]:
        L.append("- 暂无评论洞察。复盘前先分析评论（comment_insight.py 评论文件 --id 编号），verdict 会自动累计。")
    L += ["", "## 评论区的问题（按主题累计）", ""] + (["- %s：%d 条" % kv for kv in s["topics"]] or ["- 暂无"])
    if s["questions"]:
        more = s["questions_open"] - len(s["questions"][:8])
        L += ["", "还没回复的问题，原话（每次发布最多记 5 条%s）：" % ("，另有 %d 条见各次的评论洞察" % more if more > 0 else "")] + ["- %s（%s）" % (q, lid) for q, lid in s["questions"][:8]]
    L += ["", "## 建议", ""]
    if s["checks"]:
        L.append("- 先核实「待核实的说法」里的数字，再写下一篇。")
    if s["best"] and s["best"][0][1]["rates"].get("ctr") is not None and max(m["rates"].get("ctr") or 0 for _, m in s["best"]) < 0.08:
        L.append("- 点击率最高的一篇也低于 8% 的经验线，下一次优先只测试封面和标题。")
    big = [(k, c) for k, c in s["pains"] if c >= MIN_MENTIONS]
    if big and s["enough"]:
        L.append("- 「%s」累计 %d 条吐槽：先看原话是不是同一个问题。是的话，可以把它登记为下一篇的假设（用读者原话开头），同时记进产品改进清单。" % big[0])
    elif big:
        L.append("- 「%s」累计 %d 条吐槽，但累计有效评论只有 %d 条，不到 %d 条：先当线索，看原话是不是同一个问题。要拿它定下一篇，在假设的依据里写明「样本不足，先当线索」。"
                 % (big[0][0], big[0][1], s["comments"], MIN_COMMENTS))
    elif s["pains"]:
        L.append("- 还没有哪个维度累计到 %d 条吐槽：继续收集评论，不要根据一两条评论定角度。" % MIN_MENTIONS)
    asked = [(k, c) for k, c in s["topics"] if c >= MIN_MENTIONS and k != "其他问题"]
    if asked:
        L.append("- 「%s」被问了 %d 次：在下一篇正文和首评里直接回答，或者做一篇答疑笔记%s。" % (asked[0][0], asked[0][1], "" if s["enough"] else "（累计有效评论不到 %d 条，先当线索）" % MIN_COMMENTS))
    if s["questions_open"]:
        L.append("- 评论区还有 %d 个问题没看到作者回复：先回复，再写下一篇。" % s["questions_open"])
    L.append("- 一次只改一个变量（角度、标题、封面、形式之一），否则无法判断假设是否成立。")
    return "\n".join(L)


def cmd_next(a):
    print(render_next(load(a)))


def cmd_report(a):
    data = load(a)
    p = data["product"]
    L = ["# %s 小红书发布复盘报告" % p["name"], "", "生成时间：%s｜累计发布 %d 次" % (now(), len(data["launches"])), "",
         "目标人群：%s｜卖点：%s" % (p["audience"] or "未填", "、".join(p["selling_points"]) or "未填"), ""]
    for l in data["launches"]:
        L += ["## %s %s" % (l["id"], l.get("final_title") or l["title"]), "",
              "- 状态：%s｜形式：%s｜角度：%s" % (l["status"], l["type"], l["angle"] or "未填"),
              "- 链接：%s" % (l.get("url") or "未回填"), "- 基线：没有假设，只记录数据" if l["baseline"] else "- 假设：%s" % l["hypothesis"]]
        for m in l["metrics"]:
            L.append("- 数据（%s%s）：曝光 %s，观看 %s，点赞 %s，收藏 %s，评论 %s；点击率 %s，互动率 %s，评论率 %s，收藏点赞比 %s" % (
                m["recorded_at"], ("，" + m["label"]) if m.get("label") else "", show(m["raw"].get("impressions")), show(m["raw"].get("views")),
                show(m["raw"].get("likes")), show(m["raw"].get("collects")), show(m["raw"].get("comments")),
                pct(m["rates"]["ctr"]), pct(m["rates"]["engagement"]), pct(m["rates"].get("comment_rate")), show(m["rates"]["collect_like"])))
        if l["metrics"]:
            L += ["  - " + d for d in l["metrics"][-1]["diagnosis"]]
            goal = goal_of(data, l)
            if goal in MAIN_RATE:
                L.append("  - 主指标（目标：%s）：%s %s" % (goal, MAIN_RATE[goal][1], fmt_rate(MAIN_RATE[goal][0], l["metrics"][-1]["rates"].get(MAIN_RATE[goal][0]))))
        ins = l.get("insight")
        if ins:
            L.append("- 评论：有效 %d 条%s" % (ins.get("total", 0), "" if ins.get("total", 0) >= MIN_COMMENTS else "（⚠️ 不到 %d 条，评论里的发现只是线索）" % MIN_COMMENTS))
            if reader_note(l) and reader_note(l) not in l["metrics"][-1]["diagnosis"]:
                L.append("  - " + reader_note(l))
            for c in ins.get("claim_checks") or []:
                L.append("  - 待核实：档案（%s）「%s」%s%s。" % (c["source"], c["claim"], "，作者回复里是 " + "、".join(c["replies"]) if c.get("replies") else "",
                                                       "，%d 条读者评论在问或给出了别的数字" % c["readers"] if c.get("readers") else ""))
        v = l.get("verdict")
        if v:
            L.append("- 结论：**%s**。%s" % (v["result"], v["learning"]))
            if v.get("forced"):
                L.append("  - 证据未达标（%s），强制登记的理由：%s" % (" ".join(v.get("unmet", [])), v["forced"]))
        L.append("")
    L.append(render_next(data))
    text = "\n".join(L)
    if a.out:
        C.write_text(a.out, text + "\n")
        print("复盘报告已写入 %s" % C.where(a.out))
    else:
        print(text)


def build_parser():
    ap = argparse.ArgumentParser(description="小红书发布日志")
    C.add_dir_arg(ap)
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True

    def sp(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        C.add_dir_arg(s)
        s.set_defaults(fn=fn)
        return s

    sp("status", cmd_status, "查看产品档案与各次发布")
    s = sp("init", cmd_init, "建立或修改产品档案")
    s.add_argument("--product", help="产品名")
    s.add_argument("--category", help="品类，例如 护手霜")
    s.add_argument("--audience", help="目标人群")
    s.add_argument("--selling-points", help="卖点，用英文逗号分隔；卖点里面有逗号的，改用 --selling-point 一条一条给")
    s.add_argument("--selling-point", action="append", metavar="一条卖点", help="一条卖点，原样保存，可多次")
    s.add_argument("--tone", help="语气，例如 朋友聊天")
    s.add_argument("--price", help="价格与规格，例如 39 元 50g")
    s.add_argument("--goal", choices=list(GOALS), help="发布目标")
    s.add_argument("--identity", help="你和产品的关系，例如 品牌方 / 自己买的用户")
    s.add_argument("--fact", action="append", metavar="键=值", help="其他事实，可多次：缺点=… 使用情况=… 结果=… 素材=… 购买方式=…；可选的还有 外观=… 竞品=… 常见吐槽=… 固定标签=… 语气=… 定位=…")
    s.add_argument("--force", action="store_true", help="修改已有档案（保留历史发布）")
    s = sp("fact", cmd_fact, "补充或修改产品事实")
    s.add_argument("pairs", nargs="+", metavar="键=值")
    s = sp("add", cmd_add, "登记一次发布")
    s.add_argument("--title", required=True, help="暂定标题（发布时可以用 publish --final-title 改）")
    s.add_argument("--hypothesis", help="可被证伪的假设")
    s.add_argument("--baseline", action="store_true", help="没有假设的笔记，登记为基线")
    s.add_argument("--published", nargs="?", const="", default=None, metavar="日期", help="这篇已经发出去了：直接记为已发布。后面可以写发布日期（2026-11-20），不写就记今天")
    s.add_argument("--url", help="笔记链接（已经发出去的笔记）")
    s.add_argument("--angle", help="这一篇的切入角度，例如 价格痛点、避雷、教程")
    s.add_argument("--evidence", help="调研依据，一句话")
    s.add_argument("--type", default="图文", choices=["图文", "视频"], help="笔记形式，默认 图文")
    s.add_argument("--goal", choices=list(GOALS), help="这一篇的发布目标，默认用产品档案里的")
    s.add_argument("--metric", help="主指标，默认由发布目标决定")
    s = sp("publish", cmd_publish, "标记已发布")
    s.add_argument("--id", required=True, help="发布编号，例如 L1")
    s.add_argument("--url", help="笔记链接")
    s.add_argument("--final-title", help="最终发布用的标题")
    s.add_argument("--date", help="发布日期，例如 2026-11-20；不写就记今天")
    s = sp("metrics", cmd_metrics, "记录数据并诊断")
    s.add_argument("--id", required=True, help="发布编号，例如 L1")
    s.add_argument("--label", help="这是发布后多久的数据，如 24h / 72h / 7d")
    for k, h in (("impressions", "曝光（展现）"), ("views", "观看（阅读）"), ("likes", "点赞"), ("collects", "收藏"), ("comments", "评论"), ("shares", "分享"), ("follows", "涨粉")):
        s.add_argument("--" + k, type=int, default=None, metavar="N", help=h + "数；没有的不填，按未知处理")
    s = sp("verdict", cmd_verdict, "登记复盘结论")
    s.add_argument("--id", required=True, help="发布编号，例如 L1")
    s.add_argument("--result", required=True, choices=RESULTS, help="带假设的发布：成立 / 不成立 / 证据不足；基线：基线")
    s.add_argument("--learning", required=True, help="一句话沉淀")
    s.add_argument("--insight", help="评论洞察 json；不填时自动读 数据目录/feedback/<编号>_insight.json")
    s.add_argument("--force", metavar="理由", help="证据未达标时强制登记 成立 / 不成立，并写明理由")
    sp("next", cmd_next, "下一次发布与产品改进的依据")
    s = sp("report", cmd_report, "导出复盘报告")
    s.add_argument("--out", help="报告保存路径；不填时直接输出")
    return ap


def main():
    a = build_parser().parse_args()
    C.data_dir(a)
    a.fn(a)


if __name__ == "__main__":
    C.run(main)

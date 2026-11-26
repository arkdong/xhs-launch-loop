#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布日志：把每篇小红书笔记记录为一次「发布」，贯穿 调研→发布→反馈→迭代。

用法（在你自己的工作目录运行，脚本用绝对路径）:
  python3 launch_log.py status
  python3 launch_log.py init --product 产品名 --category 品类 --audience 人群 --selling-points "卖点1,卖点2"
                             [--price 价格] [--goal 触达|互动|收藏] [--identity 品牌方] [--fact 缺点=…] [--tone 语气]
  python3 launch_log.py fact 价格="39 元 50g" 缺点="冬天不够润"        补充或修改产品事实
  python3 launch_log.py add --title 暂定标题 --hypothesis 假设 [--angle 角度] [--evidence 依据] [--type 图文|视频]
  python3 launch_log.py add --title 标题 --baseline                   没有假设的笔记（已经发过的、随手发的），登记为基线
  python3 launch_log.py publish --id L1 --url 链接 [--final-title 最终标题] [--date 2026-11-20]
  python3 launch_log.py metrics --id L1 --impressions N --views N --likes N --collects N --comments N [--shares N --follows N --label 72h]
  python3 launch_log.py verdict --id L1 --result 成立|不成立|证据不足|基线 --learning 一句话 [--force 理由]
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
# 写笔记前必须由用户提供的事实。建档时一次问清，之后每篇笔记直接复用。
FACTS = OrderedDict([
    ("定位", "用一句话说清：这是什么，给谁用，解决什么？"),
    ("价格", "售价多少？折算到每次使用大约多少钱？"),
    ("使用情况", "你（或真实用户）用了多久、多少次？在什么场景用？"),
    ("结果", "有没有一个可以量化的结果（省了多少时间、多少钱、几步完成）？"),
    ("缺点", "它最明显的缺点或不适合的人是什么？"),
    ("素材", "手头有哪些真实照片或视频（产品、使用过程、成品）？"),
    ("购买方式", "读者在小红书站内怎么找到它（店铺名、商品卡、主页）？"),
    ("身份", "你和产品的关系：品牌方 / 店主 / 员工 / 自己买的用户 / 收了报酬的合作？"),
])
EMPTY_HYPO = re.compile(r"^\s*(无|暂无|没有|待定|待补|待填|todo|tbd|n/?a|none|-+|—+|？+|\?+)?\s*$", re.I)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load(a, must=True):
    path = C.log_path(a)
    data = C.read_json(path)
    if data is None:
        if must:
            sys.exit("还没有发布日志（%s）。请先建档：\n%s" % (C.where(path), C.cmd("launch_log.py", "init", "--product", '"产品名"', "--category", '"品类"', "--audience", '"目标人群"',
                                                                 "--selling-points", '"卖点1,卖点2"', "--price", '"价格"', "--goal", "互动")))
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
    return "未知" if v is None else "%.1f%%" % (v * 100)


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


def diagnose(m, r, prev, goal=""):
    """经验阈值，仅用于给出方向；真正的基准是与自己上一次发布对比。"""
    d = []
    if not m.get("views"):
        d.append("没有观看数，算不出点击率、互动率和评论率，只能看点赞、收藏、评论的绝对数。观看（阅读）数在创作者中心的笔记数据里。")
    if m.get("impressions") is None:
        d.append("没有曝光数，算不出点击率，也无法判断数据是否稳定。在创作者中心的笔记数据里能看到曝光（展现）数。")
    elif m["impressions"] < MIN_IMPRESSIONS:
        d.append("曝光不足 %d，数据还不稳定，先不要下结论；24 到 72 小时后再记录一次。" % MIN_IMPRESSIONS)
    if r["ctr"] is not None:
        if r["ctr"] < 0.08:
            d.append("点击率 %s 偏低：问题在封面和标题，用户刷到了但没点开。下一次只改封面文字和标题，其他不动。" % pct(r["ctr"]))
        elif r["ctr"] >= 0.15:
            d.append("点击率 %s 较好：封面标题的角度有效，下一次保留这个角度。" % pct(r["ctr"]))
    if r["engagement"] is not None:
        if r["engagement"] < 0.03:
            d.append("互动率 %s 偏低：点开后没有被打动，检查正文前两行是否兑现了标题承诺，内容是否具体。" % pct(r["engagement"]))
        elif r["engagement"] >= 0.08:
            d.append("互动率 %s 较好：内容本身被认可。" % pct(r["engagement"]))
    if r["collect_like"] is not None:
        if r["collect_like"] >= 1:
            d.append("收藏点赞比 %.2f，大于 1：用户把它当「有用的资料」，适合做成系列教程或清单。" % r["collect_like"])
        elif r["collect_like"] < 0.3:
            d.append("收藏点赞比 %.2f 偏低：情绪共鸣多、实用价值少，可在正文补充可照做的步骤或清单。" % r["collect_like"])
    if r["comment_rate"] is not None and r["comment_rate"] < 0.005 and (m.get("views") or 0) >= 500:
        d.append("评论率 %s 偏低：缺少讨论钩子，结尾留一个容易回答的具体问题，评论是下一轮反馈的来源。" % pct(r["comment_rate"]))
    if m.get("comments") is not None and m["comments"] < MIN_COMMENTS:
        d.append("评论 %d 条，不到 %d 条：评论里看到的东西只能当线索%s。" % (m["comments"], MIN_COMMENTS, "" if goal == "触达" else "，关于评论的假设只能登记为「证据不足」"))
    if prev:
        pr = prev["rates"]
        for key, name in (("ctr", "点击率"), ("engagement", "互动率"), ("comment_rate", "评论率"), ("collect_like", "收藏点赞比")):
            if r.get(key) is not None and pr.get(key):
                change = (r[key] - pr[key]) / pr[key]
                if abs(change) >= 0.1:
                    d.append("对比 %s：%s %s → %s（%s%.0f%%）%s。" % (prev["id"], name, fmt_rate(key, pr[key]), fmt_rate(key, r[key]), "+" if change > 0 else "", change * 100,
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


def cmd_status(a):
    data = load(a, must=False)
    if not data:
        print("尚未建立发布日志（%s）。先建档：\n%s" % (C.where(C.log_path(a)), C.cmd("launch_log.py", "init", "--product", '"产品名"', "--category", '"品类"', "--audience", '"目标人群"',
                                                                 "--selling-points", '"卖点1,卖点2"', "--price", '"价格"', "--goal", "互动")))
        return
    p = data["product"]
    print("# 产品档案\n\n- 产品：%s｜品类：%s\n- 目标人群：%s\n- 卖点：%s\n- 语气：%s｜发布目标：%s" % (
        p["name"], p["category"] or "未填", p["audience"] or "未填", "、".join(p["selling_points"]) or "未填", p["tone"] or "未填",
        ("%s（主指标：%s）" % (p["goal"], GOALS[p["goal"]])) if p["goal"] in GOALS else "未定"))
    for k in FACTS:
        if str(p["facts"].get(k) or "").strip():
            print("- %s：%s" % (k, p["facts"][k]))
    for k, v in p["facts"].items():
        if k not in FACTS and str(v).strip():
            print("- %s：%s" % (k, v))
    miss = missing_facts(p)
    if miss:
        print("- 还缺：%s（写笔记前一次问清，用 fact 补上；确实没有就填「无」）" % "、".join(miss))
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


def parse_facts(pairs):
    out = OrderedDict()
    for x in pairs or []:
        m = re.match(r"^\s*([^=＝:：]+?)\s*[=＝:：]\s*(.*)$", x, flags=re.S)
        if not m:
            sys.exit("事实要写成「键=值」，例如 价格=\"39 元 50g\"。收到的是：%s" % x)
        out[m.group(1).strip()] = m.group(2).strip()
    return out


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
    if a.selling_points:
        p["selling_points"] = [s.strip() for s in re.split(r"[,，、;；]", a.selling_points) if s.strip()]
    facts = parse_facts(a.fact)
    if a.price:
        facts["价格"] = a.price
    if a.identity:
        facts["身份"] = a.identity
    p["facts"].update(facts)
    save(a, data)
    print("%s：%s → %s" % ("已更新档案" if old else "已建档", p["name"], C.where(C.log_path(a))))
    miss = missing_facts(p)
    if miss:
        print("写笔记前还需要这些事实（一次问清，没有的填「无」）：")
        for k in miss:
            print("- %s：%s" % (k, FACTS[k]))
        print("补充：%s" % C.cmd("launch_log.py", "fact", *['%s="…"' % k for k in miss[:3]]))
    if not p["goal"]:
        print("还没定发布目标：--goal 触达（让更多人看到）｜互动（多评论）｜收藏（被当资料存下来）。")
    print("下一步（调研）：%s" % C.cmd("research.py", "keywords", "--category", C.quote(p["category"] or "品类"), "--selling-points",
                                 C.quote(",".join(p["selling_points"]) or "卖点")))


def cmd_fact(a):
    data = load(a)
    facts = parse_facts(a.pairs)
    data["product"]["facts"].update(facts)
    save(a, data)
    print("已更新：%s" % "；".join("%s = %s" % kv for kv in facts.items()))
    miss = missing_facts(data["product"])
    print("还缺：%s" % "、".join(miss) if miss else "写笔记需要的事实已齐。")


def cmd_add(a):
    data = load(a)
    if a.baseline and a.hypothesis:
        sys.exit("--baseline 和 --hypothesis 只能选一个：有假设就不是基线。")
    if not a.baseline and EMPTY_HYPO.match(a.hypothesis or ""):
        sys.exit("每次发布要带一个可以被证伪的假设（例如「以黏键盘痛点开头，评论率会高于上一篇」）。\n"
                 "如果这篇没有假设（已经发过的笔记、随手发的），用 --baseline 登记为基线，不要编一个假设。")
    lid = "L%d" % (len(data["launches"]) + 1)
    goal = a.goal or data["product"].get("goal") or ""
    data["launches"].append({"id": lid, "status": "计划中", "type": a.type, "title": a.title, "angle": a.angle or "", "baseline": bool(a.baseline),
                             "hypothesis": "" if a.baseline else a.hypothesis.strip(), "evidence": a.evidence or "", "goal": goal,
                             "main_metric": a.metric or GOALS.get(goal, ""), "created_at": now(), "metrics": [], "verdict": None})
    save(a, data)
    if a.baseline:
        print("已登记发布 %s：%s（基线，没有假设）。它的数据会成为以后各篇的对比基准。" % (lid, a.title))
        print("下一步：%s" % C.cmd("launch_log.py", "publish", "--id", lid, "--url", '"笔记链接"'))
    else:
        print("已登记发布 %s：%s\n待验证假设：%s" % (lid, a.title, a.hypothesis.strip()))
        print("下一步（发布方案）：%s" % C.cmd("content_plan.py", "new", "--id", lid))


def cmd_publish(a):
    data = load(a)
    l = find(data, a.id)
    l.update({"status": "已发布", "url": a.url or l.get("url", ""), "published_at": a.date or now()})
    if a.final_title:
        l["final_title"] = a.final_title
    save(a, data)
    print("%s 已标记为已发布。建议在 24 小时、72 小时、7 天各记录一次数据：\n%s" % (
        l["id"], C.cmd("launch_log.py", "metrics", "--id", l["id"], "--label", "24h", "--impressions", "N", "--views", "N", "--likes", "N", "--collects", "N", "--comments", "N")))


def cmd_metrics(a):
    data = load(a)
    l = find(data, a.id)
    m = {k: (max(0, getattr(a, k)) if getattr(a, k) is not None else None) for k in ("impressions", "views", "likes", "collects", "comments", "shares", "follows")}
    if all(v is None for v in m.values()):
        sys.exit("没有收到任何数字。把创作者中心里这篇笔记的数据填进来，有几个填几个：--impressions 曝光 --views 观看 --likes 点赞 --collects 收藏 --comments 评论 --shares 分享 --follows 涨粉")
    r = compute(m)
    o = comparator(data, l)
    prev = {"id": o["id"], "rates": o["metrics"][-1]["rates"]} if o else None
    diag = diagnose(m, r, prev, goal_of(data, l))
    l["metrics"].append({"recorded_at": now(), "label": a.label or "", "raw": m, "rates": r, "diagnosis": diag})
    if l["status"] == "计划中":
        l["status"] = "已发布"
    save(a, data)
    print("# %s 数据诊断%s\n" % (l["id"], ("（%s）" % a.label) if a.label else ""))
    print("| 指标 | 数值 |\n|---|---|")
    print("| 曝光 / 观看 | %s / %s |" % (show(m["impressions"]), show(m["views"])))
    print("| 点赞 / 收藏 / 评论 / 分享 / 涨粉 | %s |" % " / ".join(show(m[k]) for k in ("likes", "collects", "comments", "shares", "follows")))
    print("| 点击率 | %s |\n| 互动率 | %s |\n| 收藏点赞比 | %s |\n| 评论率 | %s |\n" % (pct(r["ctr"]), pct(r["engagement"]), show(r["collect_like"]), pct(r["comment_rate"])))
    print("## 诊断\n")
    for x in diag:
        print("- " + x)
    print("\n%s" % ("这篇是基线，没有假设：复盘时登记 --result 基线。" if l["baseline"] else "待验证假设：%s" % l["hypothesis"]))
    print("下一步：分析评论 %s\n然后登记结论 %s" % (C.cmd("comment_insight.py", "评论文件", "--id", l["id"]),
                                         C.cmd("launch_log.py", "verdict", "--id", l["id"], "--result", "基线" if l["baseline"] else "成立|不成立|证据不足", "--learning", '"一句话沉淀"')))


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
    ipath = a.insight or C.P(a, "feedback", "%s_insight.json" % l["id"])
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
        l["insight"] = {"total": ins.get("total", 0), "sample_sufficient": bool(ins.get("sample_sufficient")),
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
        if not l["baseline"] and mine is not None and theirs:      # 结论和数字的方向对不上时提醒一句（不拦：假设也可能说的是别的指标，或者「更低」）
            if a.result == "成立" and mine <= theirs:
                print("注意：%s的%s没有高于 %s。如果假设说的是主指标「更高」，结论应该是「不成立」，请核对后重新登记。" % (l["id"], name, o["id"]))
            elif a.result == "不成立" and mine >= theirs * 1.1:
                print("注意：%s的%s比 %s 高出一成以上。如果假设说的是主指标「更高」，结论应该是「成立」，请核对后重新登记。" % (l["id"], name, o["id"]))
    if not ins:
        print("提示：没有找到这次发布的评论洞察（%s），痛点不会累计到 next。" % C.where(ipath))
    elif ins.get("total", 0) < MIN_COMMENTS:
        print("注意：有效评论 %d 条，不到 %d 条。评论里的痛点和问题只当线索累计。" % (ins.get("total", 0), MIN_COMMENTS))
    print("下一步：%s" % C.cmd("launch_log.py", "next"))


def summarize(data):
    ls = data["launches"]
    scored = [(l, l["metrics"][-1]) for l in ls if l["metrics"]]
    best = sorted(scored, key=lambda x: -(x[1]["rates"].get("engagement") or 0))
    pains, asks, quotes, questions, topics = Counter(), Counter(), {}, [], Counter()
    for l in ls:
        ins = l.get("insight") or {}
        for k, c in ins.get("pains", {}).items():
            pains[k] += c.get("count", 0)
            asks[k] += c.get("questions", 0)
            quotes.setdefault(k, [])
            quotes[k] += [(q, l["id"]) for q in c.get("quotes", [])]
        for q in ins.get("question_topics", []):
            topics[q["topic"]] += q["count"]
        questions += [(q, l["id"]) for q in ins.get("questions", [])]
    done = lambda r: [l for l in ls if l.get("verdict") and l["verdict"]["result"] == r]
    return {"best": best, "proven": done("成立"), "disproven": done("不成立"), "baselines": [l for l in ls if l["baseline"]],
            "open": [l for l in ls if not l["baseline"] and (not l.get("verdict") or l["verdict"]["result"] == "证据不足")],
            "pains": pains.most_common(), "asks": asks, "quotes": quotes, "questions": questions,
            "topics": sorted(topics.most_common(), key=lambda kv: kv[0] == "其他问题")}       # 没归类的问题排在最后


def render_next(data):
    s = summarize(data)
    if not data["launches"]:
        return "还没有任何发布记录。先完成一次 调研→发布→反馈，再来迭代。"
    tag = lambda l: "（证据未达标，强制登记）" if l["verdict"].get("forced") else ""
    L = ["# 下一次发布的依据（%s）" % data["product"]["name"], ""]
    L += ["## 已被验证有效，继续沿用", ""] + (["- %s：%s（%s）%s" % (l["id"], l["verdict"]["learning"], l["hypothesis"], tag(l)) for l in s["proven"]] or ["- 暂无"])
    L += ["", "## 已被证伪，不要重复", ""] + (["- %s：%s（%s）%s" % (l["id"], l["verdict"]["learning"], l["hypothesis"], tag(l)) for l in s["disproven"]] or ["- 暂无"])
    L += ["", "## 尚未验证的假设", ""] + (["- %s：%s" % (l["id"], l["hypothesis"]) for l in s["open"]] or ["- 暂无，需要提出新假设"])
    if s["baselines"]:
        L += ["", "## 基线（没有假设，只作对比基准）", ""] + ["- %s「%s」%s" % (l["id"], l.get("final_title") or l["title"], ("：" + l["verdict"]["learning"]) if l.get("verdict") else "") for l in s["baselines"]]
    L += ["", "## 表现排序（按互动率）", ""]
    for l, m in s["best"]:
        L.append("- %s「%s」角度：%s｜曝光 %s｜点击率 %s｜互动率 %s｜收藏点赞比 %s" % (l["id"], l.get("final_title") or l["title"], l["angle"] or "未填", show(m["raw"].get("impressions")),
                                                                  pct(m["rates"]["ctr"]), pct(m["rates"]["engagement"]), show(m["rates"]["collect_like"])))
    if not s["best"]:
        L.append("- 暂无数据")
    L += ["", "## 产品改进线索（跨发布累计）", "", "累计吐槽达到 %d 条才算痛点；不到的只是线索，不要据此改产品或定下一篇。" % MIN_MENTIONS, ""]
    for k, c in s["pains"]:
        if not c and not s["asks"][k]:
            continue
        L.append("- **%s**：吐槽 %d 条，疑问 %d 条%s" % (k, c, s["asks"][k], "" if c >= MIN_MENTIONS else "（线索）"))
        for q, lid in s["quotes"][k][:3]:
            L.append("  - “%s”（%s）" % (q, lid))
    if not s["pains"]:
        L.append("- 暂无评论洞察。复盘前运行 comment_insight.py 评论文件 --id 编号，verdict 会自动累计。")
    L += ["", "## 评论区的问题（按主题累计）", ""] + (["- %s：%d 条" % kv for kv in s["topics"]] or ["- 暂无"])
    if s["questions"]:
        L += ["", "原话："] + ["- %s（%s）" % (q, lid) for q, lid in s["questions"][:8]]
    L += ["", "## 建议", ""]
    if s["best"] and s["best"][0][1]["rates"].get("ctr") is not None and s["best"][0][1]["rates"]["ctr"] < 0.08:
        L.append("- 历史最好的一篇点击率仍低于 8%，下一次优先只测试封面和标题。")
    big = [(k, c) for k, c in s["pains"] if c >= MIN_MENTIONS]
    if big:
        L.append("- 「%s」累计 %d 条吐槽：用用户原话做下一篇的开头，并把它登记为新假设；同时记进产品改进清单。" % big[0])
    elif s["pains"]:
        L.append("- 还没有哪个痛点累计到 %d 条：继续收集评论，不要根据一两条评论定角度。" % MIN_MENTIONS)
    asked = [(k, c) for k, c in s["topics"] if c >= MIN_MENTIONS and k != "其他问题"]
    if asked:
        L.append("- 「%s」被问了 %d 次：做一篇答疑笔记，或在下一篇正文和首评里直接回答。" % asked[0])
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
            L.append("- 数据（%s%s）：曝光 %s，观看 %s，点击率 %s，互动率 %s，收藏点赞比 %s" % (m["recorded_at"], ("，" + m["label"]) if m.get("label") else "", show(m["raw"].get("impressions")), show(m["raw"].get("views")),
                                                                     pct(m["rates"]["ctr"]), pct(m["rates"]["engagement"]), show(m["rates"]["collect_like"])))
        if l["metrics"]:
            L += ["  - " + d for d in l["metrics"][-1]["diagnosis"]]
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
    s.add_argument("--selling-points", help="卖点，逗号分隔")
    s.add_argument("--tone", help="语气，例如 朋友聊天")
    s.add_argument("--price", help="价格与规格，例如 39 元 50g")
    s.add_argument("--goal", choices=list(GOALS), help="发布目标")
    s.add_argument("--identity", help="你和产品的关系，例如 品牌方 / 自己买的用户")
    s.add_argument("--fact", action="append", metavar="键=值", help="其他事实，可多次：缺点=… 使用情况=… 结果=… 素材=… 购买方式=… 定位=…")
    s.add_argument("--force", action="store_true", help="修改已有档案（保留历史发布）")
    s = sp("fact", cmd_fact, "补充或修改产品事实")
    s.add_argument("pairs", nargs="+", metavar="键=值")
    s = sp("add", cmd_add, "登记一次发布")
    s.add_argument("--title", required=True, help="暂定标题（发布时可以用 publish --final-title 改）")
    s.add_argument("--hypothesis", help="可被证伪的假设")
    s.add_argument("--baseline", action="store_true", help="没有假设的笔记，登记为基线")
    s.add_argument("--angle", help="这一篇的切入角度，例如 价格痛点、避雷、教程")
    s.add_argument("--evidence", help="调研依据，一句话")
    s.add_argument("--type", default="图文", choices=["图文", "视频"], help="笔记形式，默认 图文")
    s.add_argument("--goal", choices=list(GOALS), help="这一篇的发布目标，默认用产品档案里的")
    s.add_argument("--metric", help="主指标，默认由发布目标决定")
    s = sp("publish", cmd_publish, "标记已发布")
    s.add_argument("--id", required=True, help="发布编号，例如 L1")
    s.add_argument("--url", help="笔记链接")
    s.add_argument("--final-title", help="最终发布用的标题")
    s.add_argument("--date", help="发布日期，例如 2026-11-20；默认现在")
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

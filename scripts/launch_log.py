#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布日志：把每篇小红书笔记记录为一次「发布」，贯穿 调研→发布→反馈→迭代。

子命令:
  status                       查看产品档案与各次发布状态
  init     --product ...       建立产品档案
  add      --title ... --hypothesis ...   登记一次计划中的发布，返回编号 L1、L2...
  publish  --id L1 --url ...   标记已发布
  metrics  --id L1 --impressions .. --views .. --likes .. --collects .. --comments ..   记录数据并诊断
  verdict  --id L1 --result 成立|不成立|证据不足 --learning ... [--insight insight.json]
  next                         汇总历史，输出下一次发布与产品改进的依据
  report   [--out report.md]   导出 Markdown 复盘报告
通用参数: --log 路径（默认 ./xhs_launch/launch_log.json）
只依赖 Python 标准库。
"""
import argparse, json, os, sys
from collections import Counter
from datetime import datetime

DEFAULT_LOG = os.path.join("xhs_launch", "launch_log.json")
RESULTS = ["成立", "不成立", "证据不足"]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load(path, must=True):
    if not os.path.exists(path):
        if must:
            sys.exit("还没有发布日志（%s）。请先运行：python scripts/launch_log.py init --product \"产品名\" --audience \"目标人群\" --selling-points \"卖点1,卖点2\"" % path)
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data["updated_at"] = now()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def find(data, lid):
    for l in data["launches"]:
        if l["id"].lower() == lid.lower():
            return l
    sys.exit("找不到发布 %s。现有编号：%s" % (lid, "、".join(l["id"] for l in data["launches"]) or "无"))


def rate(a, b):
    return round(a / b, 4) if b else None


def pct(v):
    return "未知" if v is None else "%.1f%%" % (v * 100)


def compute(m):
    inter = m["likes"] + m["collects"] + m["comments"] + m["shares"]
    return {
        "ctr": rate(m["views"], m["impressions"]),                 # 点击率 = 观看 / 曝光
        "engagement": rate(inter, m["views"]),                     # 互动率 = (赞+藏+评+转) / 观看
        "collect_like": round(m["collects"] / m["likes"], 2) if m["likes"] else None,  # 收藏点赞比
        "comment_rate": rate(m["comments"], m["views"]),
        "follow_rate": rate(m["follows"], m["views"]),
    }


def diagnose(m, r, prev):
    """经验阈值，仅用于给出方向；真正的基准是与自己上一次发布对比。"""
    d = []
    if m["impressions"] and m["impressions"] < 1000:
        d.append("曝光不足 1000，数据还不稳定，先不要下结论；24 到 72 小时后再记录一次。")
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
    if r["comment_rate"] is not None and r["comment_rate"] < 0.005 and m["views"] >= 500:
        d.append("评论率 %s 偏低：缺少讨论钩子，结尾留一个容易回答的具体问题，评论是下一轮反馈的来源。" % pct(r["comment_rate"]))
    if prev:
        pr = prev["rates"]
        for key, name in (("ctr", "点击率"), ("engagement", "互动率"), ("comment_rate", "评论率")):
            if r.get(key) is not None and pr.get(key):
                change = (r[key] - pr[key]) / pr[key]
                if abs(change) >= 0.1:
                    d.append("对比上一次发布 %s：%s 从 %s 变为 %s（%s%.0f%%）。" % (prev["id"], name, pct(pr[key]), pct(r[key]), "+" if change > 0 else "", change * 100))
    return d or ["各项指标处于常见区间，没有明显短板；继续用评论洞察寻找下一个角度。"]


def cmd_status(a):
    data = load(a.log, must=False)
    if not data:
        print("尚未建立发布日志（%s）。先用 init 建档。" % a.log)
        return
    p = data["product"]
    print("# 产品档案\n\n- 产品：%s\n- 目标人群：%s\n- 卖点：%s\n- 语气：%s\n" % (p["name"], p["audience"] or "未填", "、".join(p["selling_points"]) or "未填", p["tone"] or "未填"))
    print("# 发布记录（共 %d 次）\n" % len(data["launches"]))
    if not data["launches"]:
        print("还没有登记发布，用 add 登记第一次。")
    for l in data["launches"]:
        print("- %s｜%s｜%s｜%s\n  假设：%s%s\n  结论：%s%s" % (l["id"], l["status"], l["type"], l.get("final_title") or l["title"], l["hypothesis"], ("\n  依据：" + l["evidence"]) if l.get("evidence") else "",
              l["verdict"]["result"] if l.get("verdict") else "待验证", ("｜" + l["verdict"]["learning"]) if l.get("verdict") else ""))
    pend = [l["id"] for l in data["launches"] if l["status"] == "已发布" and not l.get("verdict")]
    if pend:
        print("\n待复盘：%s（提供评论和数据即可进入反馈阶段）" % "、".join(pend))


def cmd_init(a):
    old = load(a.log, must=False)
    if old and not a.force:
        sys.exit("发布日志已存在（产品：%s）。如需为另一个产品建档请用 --log 指定新路径；如需覆盖档案信息加 --force（保留历史发布）。" % old["product"]["name"])
    data = old or {"version": 1, "created_at": now(), "launches": []}
    data["product"] = {"name": a.product, "audience": a.audience or "", "tone": a.tone or "",
                       "selling_points": [s.strip() for s in (a.selling_points or "").replace("，", ",").split(",") if s.strip()]}
    save(a.log, data)
    print("已建档：%s → %s" % (a.product, a.log))


def cmd_add(a):
    data = load(a.log)
    lid = "L%d" % (len(data["launches"]) + 1)
    data["launches"].append({"id": lid, "status": "计划中", "type": a.type, "title": a.title, "angle": a.angle or "",
                             "hypothesis": a.hypothesis, "evidence": a.evidence or "", "created_at": now(), "metrics": [], "verdict": None})
    save(a.log, data)
    print("已登记发布 %s：%s\n待验证假设：%s" % (lid, a.title, a.hypothesis))


def cmd_publish(a):
    data = load(a.log)
    l = find(data, a.id)
    l.update({"status": "已发布", "url": a.url or "", "published_at": a.date or now()})
    if a.final_title:
        l["final_title"] = a.final_title
    save(a.log, data)
    print("%s 已标记为已发布。建议在 24 小时、72 小时、7 天各记录一次数据。" % l["id"])


def cmd_metrics(a):
    data = load(a.log)
    l = find(data, a.id)
    m = {k: max(0, getattr(a, k) or 0) for k in ("impressions", "views", "likes", "collects", "comments", "shares", "follows")}
    if not m["views"]:
        sys.exit("至少需要提供 --views（观看/阅读数）。")
    r = compute(m)
    prev = None
    for o in reversed(data["launches"]):
        if o["id"] != l["id"] and o["metrics"]:
            prev = {"id": o["id"], "rates": o["metrics"][-1]["rates"]}
            break
    diag = diagnose(m, r, prev)
    l["metrics"].append({"recorded_at": now(), "label": a.label or "", "raw": m, "rates": r, "diagnosis": diag})
    if l["status"] == "计划中":
        l["status"] = "已发布"
    save(a.log, data)
    print("# %s 数据诊断%s\n" % (l["id"], ("（%s）" % a.label) if a.label else ""))
    print("| 指标 | 数值 |\n|---|---|")
    print("| 曝光 / 观看 | %d / %d |" % (m["impressions"], m["views"]))
    print("| 点赞 / 收藏 / 评论 / 分享 / 涨粉 | %d / %d / %d / %d / %d |" % (m["likes"], m["collects"], m["comments"], m["shares"], m["follows"]))
    print("| 点击率 | %s |\n| 互动率 | %s |\n| 收藏点赞比 | %s |\n| 评论率 | %s |\n" % (pct(r["ctr"]), pct(r["engagement"]), r["collect_like"] if r["collect_like"] is not None else "未知", pct(r["comment_rate"])))
    print("## 诊断\n")
    for x in diag:
        print("- " + x)
    print("\n待验证假设：%s\n下一步：结合评论洞察，用 verdict 登记结论。" % l["hypothesis"])


def cmd_verdict(a):
    data = load(a.log)
    l = find(data, a.id)
    v = {"result": a.result, "learning": a.learning, "decided_at": now()}
    if a.insight:
        if not os.path.exists(a.insight):
            sys.exit("找不到洞察文件：%s" % a.insight)
        with open(a.insight, encoding="utf-8") as f:
            ins = json.load(f)
        l["insight"] = {"total": ins.get("total", 0),
                        "intents": {i["intent"]: i["share"] for i in ins.get("intent_distribution", [])},
                        "pains": {k: {"count": c["count"], "quotes": c["quotes"][:2]} for k, c in ins.get("pain_clusters", {}).items()},
                        "questions": ins.get("questions_to_answer", [])[:5],
                        "keywords": [k["word"] for k in ins.get("keywords", [])[:10]]}
    l["verdict"] = v
    l["status"] = "已复盘"
    save(a.log, data)
    print("%s 假设「%s」→ %s\n沉淀：%s\n运行 next 查看下一次发布的依据。" % (l["id"], l["hypothesis"], a.result, a.learning))


def summarize(data):
    ls = data["launches"]
    scored = [(l, l["metrics"][-1]) for l in ls if l["metrics"]]
    best = sorted(scored, key=lambda x: -(x[1]["rates"].get("engagement") or 0))
    pains, quotes, questions = Counter(), {}, []
    for l in ls:
        ins = l.get("insight") or {}
        for k, c in ins.get("pains", {}).items():
            pains[k] += c["count"]
            quotes.setdefault(k, [])
            quotes[k] += [(q, l["id"]) for q in c["quotes"]]
        questions += [(q, l["id"]) for q in ins.get("questions", [])]
    return {
        "best": best,
        "proven": [l for l in ls if l.get("verdict") and l["verdict"]["result"] == "成立"],
        "disproven": [l for l in ls if l.get("verdict") and l["verdict"]["result"] == "不成立"],
        "open": [l for l in ls if not l.get("verdict") or l["verdict"]["result"] == "证据不足"],
        "pains": pains.most_common(), "quotes": quotes, "questions": questions,
    }


def render_next(data):
    s = summarize(data)
    L = ["# 下一次发布的依据（%s）" % data["product"]["name"], ""]
    if not data["launches"]:
        return "还没有任何发布记录。先完成一次 调研→发布→反馈，再来迭代。"
    L += ["## 已被验证有效，继续沿用", ""] + (["- %s：%s（%s）" % (l["id"], l["verdict"]["learning"], l["hypothesis"]) for l in s["proven"]] or ["- 暂无"])
    L += ["", "## 已被证伪，不要重复", ""] + (["- %s：%s（%s）" % (l["id"], l["verdict"]["learning"], l["hypothesis"]) for l in s["disproven"]] or ["- 暂无"])
    L += ["", "## 尚未验证的假设", ""] + (["- %s：%s" % (l["id"], l["hypothesis"]) for l in s["open"]] or ["- 暂无，需要提出新假设"])
    L += ["", "## 表现排序（按互动率）", ""]
    for l, m in s["best"]:
        L.append("- %s「%s」角度：%s｜点击率 %s｜互动率 %s｜收藏点赞比 %s" % (l["id"], l.get("final_title") or l["title"], l["angle"] or "未填", pct(m["rates"]["ctr"]), pct(m["rates"]["engagement"]), m["rates"]["collect_like"]))
    if not s["best"]:
        L.append("- 暂无数据")
    L += ["", "## 产品改进线索（跨发布累计的痛点）", ""]
    for k, c in s["pains"]:
        L.append("- **%s**：累计 %d 条" % (k, c))
        for q, lid in s["quotes"][k][:3]:
            L.append("  - “%s”（%s）" % (q, lid))
    if not s["pains"]:
        L.append("- 暂无评论洞察，复盘时用 verdict --insight 带上洞察文件即可累计。")
    L += ["", "## 可直接做成选题的高频问题", ""] + (["- %s（%s）" % (q, lid) for q, lid in s["questions"][:8]] or ["- 暂无"])
    L += ["", "## 建议", ""]
    if s["best"] and s["best"][0][1]["rates"].get("ctr") is not None and s["best"][0][1]["rates"]["ctr"] < 0.08:
        L.append("- 历史最好的一篇点击率仍低于 8%，下一次优先只测试封面和标题。")
    if s["pains"]:
        L.append("- 用「%s」这个痛点的用户原话做下一篇的开头，并把它登记为新假设。" % s["pains"][0][0])
    if s["questions"]:
        L.append("- 把高频问题合并成一篇答疑笔记，这是成本最低的下一次发布。")
    L.append("- 一次只改一个变量（角度、标题、封面、形式之一），否则无法判断假设是否成立。")
    return "\n".join(L)


def cmd_next(a):
    print(render_next(load(a.log)))


def cmd_report(a):
    data = load(a.log)
    p = data["product"]
    L = ["# %s 小红书发布复盘报告" % p["name"], "", "生成时间：%s｜累计发布 %d 次" % (now(), len(data["launches"])), "",
         "目标人群：%s｜卖点：%s" % (p["audience"] or "未填", "、".join(p["selling_points"]) or "未填"), ""]
    for l in data["launches"]:
        L += ["## %s %s" % (l["id"], l.get("final_title") or l["title"]), "",
              "- 状态：%s｜形式：%s｜角度：%s" % (l["status"], l["type"], l["angle"] or "未填"),
              "- 链接：%s" % (l.get("url") or "未回填"), "- 假设：%s" % l["hypothesis"]]
        for m in l["metrics"]:
            L.append("- 数据 %s %s：曝光 %d，观看 %d，点击率 %s，互动率 %s，收藏点赞比 %s" % (m["recorded_at"], m["label"], m["raw"]["impressions"], m["raw"]["views"], pct(m["rates"]["ctr"]), pct(m["rates"]["engagement"]), m["rates"]["collect_like"]))
        if l["metrics"]:
            L += ["  - " + d for d in l["metrics"][-1]["diagnosis"]]
        if l.get("verdict"):
            L.append("- 结论：**%s**。%s" % (l["verdict"]["result"], l["verdict"]["learning"]))
        L.append("")
    L.append(render_next(data))
    text = "\n".join(L)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("复盘报告已写入 %s" % a.out)
    else:
        print(text)


def main():
    ap = argparse.ArgumentParser(description="小红书发布日志")
    ap.add_argument("--log", default=DEFAULT_LOG)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def sp(name, fn):
        s = sub.add_parser(name)
        s.add_argument("--log", default=argparse.SUPPRESS)
        s.set_defaults(fn=fn)
        return s

    sp("status", cmd_status)
    s = sp("init", cmd_init)
    s.add_argument("--product", required=True); s.add_argument("--audience"); s.add_argument("--selling-points"); s.add_argument("--tone"); s.add_argument("--force", action="store_true")
    s = sp("add", cmd_add)
    s.add_argument("--title", required=True); s.add_argument("--hypothesis", required=True); s.add_argument("--angle"); s.add_argument("--evidence", help="调研依据，一句话"); s.add_argument("--type", default="图文", choices=["图文", "视频"])
    s = sp("publish", cmd_publish)
    s.add_argument("--id", required=True); s.add_argument("--url"); s.add_argument("--final-title"); s.add_argument("--date")
    s = sp("metrics", cmd_metrics)
    s.add_argument("--id", required=True); s.add_argument("--label", help="如 24h / 72h / 7d")
    for k in ("impressions", "views", "likes", "collects", "comments", "shares", "follows"):
        s.add_argument("--" + k, type=int, default=0)
    s = sp("verdict", cmd_verdict)
    s.add_argument("--id", required=True); s.add_argument("--result", required=True, choices=RESULTS); s.add_argument("--learning", required=True); s.add_argument("--insight")
    sp("next", cmd_next)
    s = sp("report", cmd_report)
    s.add_argument("--out")
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

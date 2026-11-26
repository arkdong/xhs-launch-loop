#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书笔记发布前检查：长度、标签、极限词/敏感词、导流、钩子、互动引导。

用法:
  python note_check.py draft.txt [--json]
草稿格式: 第一行为标题（可带 "标题：" 前缀），其余为正文；话题标签写成 #标签 。
退出码: 0 = 无错误级问题，1 = 有错误级问题需要修改。
"""
import argparse, json, os, re, sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
TITLE_MAX, BODY_MAX, TAG_MIN, TAG_MAX = 20, 1000, 3, 10
# 含极限词字样但属于正常表达的搭配，不报错
SAFE = ["第一次", "第一天", "第一步", "第一眼", "第一口", "第一反应", "第一周", "第一个月", "第一篇", "第一时间",
        "最近", "最后", "最初", "最开始", "最好是", "最好别", "最好不要", "唯一的缺点", "唯一缺点", "唯一不足"]
HOOKS = ["？", "?", "！", "!", "谁懂", "救命", "后悔", "别再", "千万别", "终于", "原来", "居然", "没想到", "踩雷", "避雷",
         "亲测", "实测", "天", "年", "个月", "块", "元", "分钟", "我", "你", "到底", "多少", "怎么", "为什么",
         "打工人", "学生党", "新手", "小白", "宝妈", "上班族", "懒人"]
CTA = ["评论区", "你们", "大家", "留言", "告诉我", "有没有", "吗？", "吗?", "收藏", "蹲", "想看", "交流", "求推荐"]


def load_rules():
    rules = []
    with open(os.path.join(BASE, "banned_words.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) == 3:
                rules.append(tuple(parts))
    return rules


def xhs_len(s):
    """按小红书计数习惯：中文和全角算 1，英文数字两个算 1。"""
    wide = len(re.findall(r"[^\x00-\x7f]", s))
    narrow = len(re.findall(r"[\x21-\x7e]", s))
    return wide + (narrow + 1) // 2


def check(text):
    lines = [l.rstrip() for l in text.strip().splitlines()]
    lines = [l for l in lines if l.strip()] if lines else []
    issues = []

    def add(level, item, msg):
        issues.append({"level": level, "item": item, "message": msg})

    if not lines:
        add("错误", "内容", "草稿为空。")
        return {"passed": False, "issues": issues, "stats": {}}
    title = re.sub(r"^\s*(标题|title)\s*[:：]\s*", "", lines[0], flags=re.I).strip("# ").strip()
    body = "\n".join(lines[1:]).strip()
    tags = re.findall(r"#([^\s#]{1,20})", body)
    body_plain = re.sub(r"#[^\s#]{1,20}", "", body).strip()
    tl, bl = xhs_len(title), xhs_len(body_plain)

    if tl > TITLE_MAX:
        add("错误", "标题", "标题 %d 字，超过上限 %d 字，需删减 %d 字。" % (tl, TITLE_MAX, tl - TITLE_MAX))
    elif tl < 6:
        add("警告", "标题", "标题只有 %d 字，信息量偏少，建议 10 到 20 字。" % tl)
    if not any(h in title for h in HOOKS) and not re.search(r"\d", title):
        add("警告", "标题", "标题缺少钩子：建议加入数字、人群、反差或疑问。")
    if not body_plain:
        add("错误", "正文", "没有正文。")
    elif bl > BODY_MAX:
        add("错误", "正文", "正文 %d 字，超过上限 %d 字。" % (bl, BODY_MAX))
    elif bl < 80:
        add("警告", "正文", "正文仅 %d 字，偏短，难以承载真实体验细节。" % bl)
    if len(tags) < TAG_MIN:
        add("警告", "标签", "话题标签 %d 个，建议 %d 到 %d 个（品类词 + 场景词 + 人群词）。" % (len(tags), TAG_MIN, TAG_MAX))
    elif len(tags) > TAG_MAX:
        add("错误", "标签", "话题标签 %d 个，超过 %d 个，容易被判定堆砌。" % (len(tags), TAG_MAX))
    if len(set(tags)) < len(tags):
        add("警告", "标签", "存在重复标签。")

    full = title + "\n" + body
    masked = full
    for s in SAFE:
        masked = masked.replace(s, "＿" * len(s))
    for level, cat, word in load_rules():
        n = masked.lower().count(word.lower())
        if n:
            add(level, cat, "出现「%s」%d 次，%s。" % (word, n, "必须替换或删除" if level == "错误" else "建议改成具体描述"))
    if re.search(r"1[3-9]\d{9}", full):
        add("错误", "站外导流", "疑似手机号。")
    if re.search(r"https?://|www\.", full, flags=re.I):
        add("错误", "站外导流", "包含外部链接。")

    first = body_plain.splitlines()[0] if body_plain else ""
    if first and xhs_len(first) > 45:
        add("警告", "开头", "第一句 %d 字过长，前两行决定是否展开，建议压到 30 字内。" % xhs_len(first))
    if body_plain and not any(c in body_plain[-120:] for c in CTA):
        add("警告", "互动引导", "结尾没有互动引导，建议留一个具体问题，评论就是下一轮反馈的来源。")
    paras = [p for p in body_plain.split("\n") if p.strip()]
    if paras and max(xhs_len(p) for p in paras) > 180:
        add("警告", "排版", "存在超过 180 字的大段文字，手机上难读，建议分段。")
    if body_plain and not re.search(r"\d", body_plain):
        add("警告", "真实感", "正文没有任何具体数字（价格、时长、次数），真实体验感偏弱。")

    errors = sum(1 for i in issues if i["level"] == "错误")
    return {"passed": errors == 0, "errors": errors, "warnings": len(issues) - errors, "issues": issues,
            "stats": {"title": title, "title_len": tl, "body_len": bl, "tags": tags}}


def main():
    ap = argparse.ArgumentParser(description="小红书笔记发布前检查")
    ap.add_argument("file")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args()
    if not os.path.exists(a.file):
        sys.exit("找不到文件：%s" % a.file)
    with open(a.file, encoding="utf-8-sig") as f:
        r = check(f.read())
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        s = r["stats"]
        print("# 发布前检查")
        if s:
            print("\n标题：%s（%d/%d 字）｜正文 %d/%d 字｜标签 %d 个" % (s["title"], s["title_len"], TITLE_MAX, s["body_len"], BODY_MAX, len(s["tags"])))
        print("\n结论：%s（错误 %d，警告 %d）\n" % ("通过，可以发布" if r["passed"] else "未通过，请修改后重新检查", r.get("errors", 1), r.get("warnings", 0)))
        for i in sorted(r["issues"], key=lambda x: x["level"] != "错误"):
            print("- [%s][%s] %s" % (i["level"], i["item"], i["message"]))
        if not r["issues"]:
            print("- 未发现问题。")
    sys.exit(0 if r["passed"] else 1)


if __name__ == "__main__":
    main()

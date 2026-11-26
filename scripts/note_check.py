#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书笔记发布前检查：长度、标签、极限词/敏感词、导流、钩子、互动引导。

用法:
  python3 note_check.py 草稿.txt [--json] [--words 自己的词表.txt]
草稿格式: 第一行为标题（可带 "标题：" 前缀），其余为正文；话题标签写成 #标签 。
词表: assets/banned_words.txt，每行「级别|类别|词|提示」（提示可省略）。数据目录里的 banned_words.txt 会自动追加，行业专用词写在那里。
退出码: 0 = 无错误级问题，1 = 有错误级问题需要修改。只依赖 Python 3 标准库。
"""
import argparse, json, os, re, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

TITLE_MAX, BODY_MAX, TAG_MIN, TAG_MAX = 20, 1000, 3, 10
# 含极限词字样但属于正常表达的搭配，不报错
# 「第一」后面跟量词是在数数（第一次、第一下、第一泵），不是排名；「第一名」「第一品牌」「第一梯队」仍然会报
ORDINAL = ("次天步眼口周篇张款支件条行句页批代层遍年季集期节章位个瓶盒杯包颗套双台部只顿晚回轮屏段项点类种"
           "下刀泵抹滴勺片块根本站家场局关题课堂道面格栏列排单笔份封幅首锅碗盘壶罐袋箱管枚粒束朵棵株间栋辆把扇门夜早缕波任届版稿幕话卷册手线趟圈针泡刷")
SAFE = re.compile(
    r"第一(?:[" + ORDINAL + r"]|反应|时间|感觉|印象|视角|人称|学期|桶金)"
    r"|最好(?:是|别|不要|先|提前|搭配|配合|分[两三]次)|唯一(?:的)?(?:缺点|不足|槽点|遗憾|问题)|不是(?:最好|唯一|第一|顶级|万能)|(?:没有|不存在)万能|不(?:敢说|能说|是说)最"
    r"|(?:100%|百分百)\s*(?:纯?棉|全棉|羊毛|羊绒|真丝|桑蚕丝|亚麻|纯牛奶|生牛乳|果汁|原创|实拍|真实|自费|无广)|永久(?:磁铁|磁|居民|地址)"
    r"|治愈系|(?:很|好|太|超|巨|特别|非常|真的|蛮|挺|被|有被)治愈|治愈(?:感|力|心情|自己|一下|时刻|瞬间|小物|好物|角落|日常|生活|的一天|我的心|了我的心|了一天)")
HOOKS = ["？", "?", "！", "!", "谁懂", "救命", "后悔", "别再", "千万别", "终于", "原来", "居然", "没想到", "踩雷", "避雷",
         "亲测", "实测", "天", "年", "个月", "块", "元", "分钟", "我", "你", "到底", "多少", "怎么", "为什么",
         "打工人", "学生党", "新手", "小白", "宝妈", "上班族", "懒人"]
CTA = ["评论区", "你们", "大家", "留言", "告诉我", "有没有", "吗？", "吗?", "收藏", "蹲", "想看", "交流", "求推荐"]


def load_rules(extra=()):
    """读词表，返回 [(级别, 类别, 词, 提示)]，长词在前。extra 是追加的词表文件（不存在就跳过）。"""
    rules, seen = [], set()
    for path in [os.path.join(C.ASSETS, "banned_words.txt")] + [p for p in extra if p and os.path.exists(p)]:
        for line in C.read_text(path)[0].split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [x.strip() for x in line.split("|")]
            if len(parts) >= 3 and parts[0] in ("错误", "警告") and parts[2] and parts[2].lower() not in seen:
                seen.add(parts[2].lower())
                rules.append((parts[0], parts[1], parts[2], parts[3] if len(parts) > 3 else ""))
    return sorted(rules, key=lambda r: -len(r[2]))


xhs_len = C.xhs_len
LEN_RULE = "字数按小红书的算法：汉字和全角符号算 1 个字，英文字母、数字和半角符号每 2 个算 1 个字。"


def scan(text, rules):
    """在一段文字里找词表里的词，以及手机号和外部链接。返回 [(级别, 类别, 说明)]。
    rules 来自 load_rules，长词在前：命中后盖掉，短词不再重复报。正文、标题、图上的字、口播、首评都用它查。"""
    text, out = str(text or ""), []
    masked = SAFE.sub(lambda m: "＿" * len(m.group(0)), text).lower()
    for level, cat, word, hint in rules:
        w = word.lower()
        pat = re.compile(("(?<![a-z])" if re.match("[a-z]", w) else "") + re.escape(w) + ("(?![a-z])" if re.search("[a-z]$", w) else ""))   # 英文缩写不在单词中间匹配（加v 不命中 加VC）
        masked, n = pat.subn("＿" * len(w), masked)
        if n:
            out.append((level, cat, "出现「%s」%d 次，%s。" % (word, n, hint or ("必须替换或删除" if level == "错误" else "建议改成具体描述"))))
    if re.search(r"1[3-9]\d{9}", text):
        out.append(("错误", "站外导流", "疑似手机号。"))
    if re.search(r"https?://|www\.", text, flags=re.I):
        out.append(("错误", "站外导流", "包含外部链接。"))
    return out


def check(text, extra_words=(), min_body=80):
    """min_body：正文少于这么多字时提醒偏短。情绪短片这类本来就极短的笔记传 0。"""
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
    elif bl < min_body:
        add("警告", "正文", "正文仅 %d 字，偏短，难以承载真实体验细节。" % bl)
    if len(tags) < TAG_MIN:
        add("警告", "标签", "话题标签 %d 个，建议 %d 到 %d 个（品类词 + 场景词 + 人群词）。" % (len(tags), TAG_MIN, TAG_MAX))
    elif len(tags) > TAG_MAX:
        add("错误", "标签", "话题标签 %d 个，超过 %d 个，容易被判定堆砌。" % (len(tags), TAG_MAX))
    if len(set(tags)) < len(tags):
        add("警告", "标签", "存在重复标签。")

    for level, cat, msg in scan(title + "\n" + body, load_rules(extra_words)):
        add(level, cat, msg)

    first = body_plain.splitlines()[0] if body_plain else ""
    if first and xhs_len(first) > 45:
        add("警告", "开头", "第一句 %d 字过长，前两行决定是否展开，建议压到 30 字内。" % xhs_len(first))
    if body_plain and not any(c in body_plain[-120:] for c in CTA) and not re.search(r"[?？]", body_plain[-120:]):
        add("警告", "互动引导", "结尾没有互动引导，建议留一个具体问题，评论就是下一轮反馈的来源。")
    paras = [p for p in body_plain.split("\n") if p.strip()]
    if paras and max(xhs_len(p) for p in paras) > 180:
        add("警告", "排版", "存在超过 180 字的大段文字，手机上难读，建议分段。")
    if body_plain and not re.search(r"\d", body_plain):
        add("警告", "真实感", "正文没有任何具体数字（价格、时长、次数），真实体验感偏弱。")

    errors = sum(1 for i in issues if i["level"] == "错误")
    return {"passed": errors == 0, "errors": errors, "warnings": len(issues) - errors, "issues": issues,
            "stats": {"title": title, "title_len": tl, "body_len": bl, "tags": tags}}


def build_parser():
    ap = argparse.ArgumentParser(description="小红书笔记发布前检查")
    ap.add_argument("file", metavar="草稿文件", help="第一行是标题，其余是正文和 #标签；- 表示标准输入")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--words", action="append", default=[], help="追加的词表文件（可多次），格式同 assets/banned_words.txt")
    C.add_dir_arg(ap)
    return ap


def main():
    a = build_parser().parse_args()
    if a.file != "-" and not os.path.exists(a.file):
        sys.exit("找不到文件：%s（当前目录 %s）" % (a.file, os.getcwd()))
    r = check(C.read_text(a.file)[0], [C.P(a, "banned_words.txt")] + a.words)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        s = r["stats"]
        print("# 发布前检查")
        if s:
            print("\n标题：%s（%d/%d 字）｜正文 %d/%d 字｜标签 %d 个" % (s["title"], s["title_len"], TITLE_MAX, s["body_len"], BODY_MAX, len(s["tags"])))
            print(LEN_RULE + "这里只查这一段文字；图上的字、首评、其余备选标题要另外查，或者用 content_plan.py check 一起查。")
        print("\n结论：%s（错误 %d，警告 %d）\n" % ("通过，可以发布" if r["passed"] else "未通过，请修改后重新检查", r.get("errors", 1), r.get("warnings", 0)))
        for i in sorted(r["issues"], key=lambda x: x["level"] != "错误"):
            print("- [%s][%s] %s" % (i["level"], i["item"], i["message"]))
        if not r["issues"]:
            print("- 未发现问题。")
    sys.exit(0 if r["passed"] else 1)


if __name__ == "__main__":
    C.run(main)

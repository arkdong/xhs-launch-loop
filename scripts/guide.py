#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用指南与演示。

  python3 guide.py            总览：这个技能能做什么、怎么开口
  python3 guide.py 1          单个阶段的说明和示例（1 调研 / 2 发布 / 3 反馈 / 4 迭代）
  python3 guide.py all        全部内容
  python3 guide.py commands   所有命令一览，路径已经填好，可以直接复制
  python3 guide.py demo       用示例数据把四个阶段完整跑一遍（临时目录，不联网，不影响你的文件）

说明文字全部来自 references/examples.md，只维护那一份。只依赖 Python 3 标准库。
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

DOC = os.path.join(C.SKILL, "references", "examples.md")
EX = os.path.join(C.SKILL, "examples")

STAGES = {
    "1": "① 调研", "调研": "① 调研", "research": "① 调研",
    "2": "② 发布", "发布": "② 发布", "publish": "② 发布",
    "3": "③ 反馈", "反馈": "③ 反馈", "feedback": "③ 反馈",
    "4": "④ 迭代", "迭代": "④ 迭代", "next": "④ 迭代",
}
COMMANDS = [
    ("开始前", [
        ("看有没有产品档案和历史发布", ["launch_log.py", "status"]),
        ("建档：产品事实一次给全，以后每篇复用", ["launch_log.py", "init", "--product", '"产品名"', "--category", '"品类"', "--audience", '"目标人群"', "--selling-points", '"卖点1,卖点2"',
                                "--price", '"价格和规格"', "--goal", "触达|互动|收藏", "--identity", '"品牌方 / 店主 / 自己买的用户"',
                                "--fact", '缺点="…"', "--fact", '使用情况="…"', "--fact", '结果="…"', "--fact", '素材="…"', "--fact", '购买方式="…"', "--fact", '定位="…"']),
        ("之后补充或修改事实", ["launch_log.py", "fact", '价格="…"', '缺点="…"']),
    ]),
    ("① 调研", [
        ("搜索词（默认 6 到 8 个，够手动搜；品类、卖点、人群取自档案）", ["research.py", "keywords"]),
        ("笔记入库：搜索结果直接全选复制存成文件即可", ["research.py", "add", "搜索结果.txt", "--keyword", '"搜索词"']),
        ("竞品评论：评论区直接复制存成文件即可", ["comment_insight.py", "竞品评论.txt", "--research"]),
        ("供需分析", ["research.py", "analyze"]),
        ("登记这次发布和它的假设", ["launch_log.py", "add", "--title", '"暂定标题"', "--angle", '"角度"', "--hypothesis", '"假设"', "--evidence", '"依据"']),
        ("已经发过、没有假设的笔记，登记为基线", ["launch_log.py", "add", "--title", '"标题"', "--baseline"]),
    ]),
    ("② 发布", [
        ("生成方案骨架", ["content_plan.py", "new", "--id", "L1"]),
        ("检查方案，通过后导出成稿", ["content_plan.py", "check", "--id", "L1"]),
        ("生成配图提示词", ["content_plan.py", "prompts", "--id", "L1"]),
        ("只检查一篇现成的草稿", ["note_check.py", "草稿.txt"]),
        ("发布后回填链接", ["launch_log.py", "publish", "--id", "L1", "--url", '"笔记链接"', "--final-title", '"最终标题"']),
    ]),
    ("③ 反馈", [
        ("解析这一篇的评论", ["comment_insight.py", "评论.txt", "--id", "L1"]),
        ("录入数据并诊断", ["launch_log.py", "metrics", "--id", "L1", "--impressions", "N", "--views", "N", "--likes", "N", "--collects", "N", "--comments", "N"]),
        ("给假设下结论", ["launch_log.py", "verdict", "--id", "L1", "--result", "成立|不成立|证据不足", "--learning", '"一句话沉淀"']),
    ]),
    ("④ 迭代", [
        ("下一篇发什么、产品改什么", ["launch_log.py", "next"]),
        ("导出复盘报告", ["launch_log.py", "report", "--out", "xhs_launch/report.md"]),
    ]),
]


def sections():
    """按二级标题切分 examples.md，返回 [(标题, 正文)]。"""
    out, title, buf = [], None, []
    for line in C.read_text(DOC)[0].split("\n"):
        if line.startswith("## "):
            if title:
                out.append((title, "\n".join(buf).strip()))
            title, buf = line[3:].strip(), []
        elif title:
            buf.append(line)
    if title:
        out.append((title, "\n".join(buf).strip()))
    return out


def how_to_run():
    return ("怎么运行：在你自己的工作目录里运行，脚本用绝对路径，数据写在 当前目录/xhs_launch/。例如：\n  %s\n每条命令的输出末尾都有写好路径的下一步命令。全部命令：%s"
            % (C.cmd("launch_log.py", "status"), C.cmd("guide.py", "commands")))


def show(prefix):
    for title, body in sections():
        if title.startswith(prefix):
            print("## %s\n\n%s\n" % (title, body))
            print(how_to_run())
            return True
    return False


def show_commands():
    print("# 全部命令\n\n在你自己的工作目录运行（不要 cd 到技能目录）。数据写在 当前目录/xhs_launch/；不同产品用 --dir 指到不同目录。\n")
    for stage, items in COMMANDS:
        print("## %s\n" % stage)
        for what, c in items:
            print("%s：\n  %s\n" % (what, C.cmd(*c)))
    print("每个脚本加 -h 可以看全部参数。")


def run(cmd, cwd, full):
    """运行一条脚本命令，打印命令和（截断的）真实输出。失败时返回 False。"""
    print("$ " + C.cmd(*[C.quote(c) if i else c for i, c in enumerate(cmd)]))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.pop("XHS_LAUNCH_DIR", None)
    p = subprocess.run([sys.executable, "-B", os.path.join(C.SCRIPTS, cmd[0])] + cmd[1:], cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = [l for l in p.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    limit = len(lines) if full else 10
    for l in lines[:limit]:
        print("  " + (l if full or len(l) <= 160 else l[:160] + "…"))
    if len(lines) > limit:
        print("  …（还有 %d 行，加 --full 查看全部）" % (len(lines) - limit))
    print()
    return p.returncode == 0


def demo_steps(ex=None):
    """演示用的全部命令，按阶段分组：[(阶段标题, [命令, …])]。
    "COPY_PLAN" 表示把 examples/sample_plan.json 复制进去，代替「填写方案」这一步。"""
    ex = ex or (lambda name: os.path.join(EX, name))
    return [
        ("建档：产品事实一次给全", [
            ["launch_log.py", "init", "--product", "冷萃咖啡液", "--category", "咖啡液", "--audience", "早八打工人", "--selling-points", "3秒冷萃,一杯不到4块",
             "--price", "59 元 20 条，每杯不到 3 块，加牛奶约 4 块", "--goal", "互动", "--identity", "品牌方", "--tone", "朋友聊天",
             "--fact", "定位=即冲冷萃咖啡液，给早八没时间排队的打工人", "--fact", "使用情况=团队 5 个人连续喝了 7 天，每天早上在工位冲，一条兑 200ml 冰牛奶",
             "--fact", "结果=每天早上少排队 15 分钟；以前买楼下便利店的拿铁，一杯 9 块 9", "--fact", "缺点=单喝偏苦，不加奶的人慎重；包装不好撕",
             "--fact", "素材=产品图 3 张、冲泡过程视频 1 段", "--fact", "购买方式=小红书店铺：早八咖啡局"],
        ]),
        ("① 调研：拿搜索词；把从 App 复制的搜索结果和工具导出的数据入库；分析竞品评论；做供需分析", [
            ["research.py", "keywords"],
            ["research.py", "add", ex("sample_search_paste.txt"), "--keyword", "咖啡液 避雷"],
            ["research.py", "add", ex("sample_notes.json"), "--keyword", "冷萃咖啡液"],
            ["comment_insight.py", ex("sample_comments_paste.txt"), "--research", "--author", "示例作者"],
            ["research.py", "analyze", "--days", "0", "--selling-terms", "一杯不到4块=多少钱/每杯,3秒冷萃=3秒/秒冲"],
        ]),
        ("登记：以前发过的一篇记为基线，这次要发的一篇带上假设", [
            ["launch_log.py", "add", "--title", "冷萃咖啡液开箱", "--baseline"],
            ["launch_log.py", "metrics", "--id", "L1", "--impressions", "8000", "--views", "900", "--likes", "60", "--collects", "25", "--comments", "6"],
            ["launch_log.py", "verdict", "--id", "L1", "--result", "基线", "--learning", "卖点罗列式开头：点击率 11.2%，评论率 0.7%"],
            ["launch_log.py", "add", "--title", "打工人算账：一杯咖啡到底多少钱", "--angle", "价格痛点", "--hypothesis", "以价格痛点开头，评论率高于基线 L1",
             "--evidence", "示例：评论里问价格的最多，很少有笔记在标题回应"],
        ]),
        ("② 发布：生成方案骨架，填入内容（这里用示例方案代替），检查，生成配图提示词", [
            ["content_plan.py", "new", "--id", "L2"],
            "COPY_PLAN",
            ["content_plan.py", "check", "--id", "L2"],
            ["content_plan.py", "prompts", "--id", "L2"],
            ["launch_log.py", "publish", "--id", "L2", "--url", "https://www.xiaohongshu.com/explore/demo", "--final-title", "打工人算账：一杯咖啡到底多少钱"],
        ]),
        ("③ 反馈：解析评论，录入数据，给假设下结论", [
            ["comment_insight.py", ex("sample_comments.txt"), "--id", "L2"],
            ["launch_log.py", "metrics", "--id", "L2", "--impressions", "12000", "--views", "1800", "--likes", "96", "--collects", "140", "--comments", "31", "--shares", "12", "--follows", "9"],
            ["launch_log.py", "verdict", "--id", "L2", "--result", "成立", "--learning", "价格痛点开头的评论率 1.7%，是基线 0.7% 的两倍多，下一篇继续用痛点开头"],
        ]),
        ("④ 迭代：下一篇发什么、产品改什么", [
            ["launch_log.py", "next"],
            ["launch_log.py", "report", "--out", os.path.join("xhs_launch", "report.md")],
        ]),
    ]


def demo(out, full):
    work = os.path.abspath(out) if out else tempfile.mkdtemp(prefix="xhs_demo_")
    os.makedirs(work, exist_ok=True)
    if os.path.exists(os.path.join(work, "xhs_launch")):
        print("目录 %s 里已有 xhs_launch，为避免覆盖你的数据，演示已取消。请换一个 --out 目录。" % work)
        return 1
    print("演示：用虚构的「冷萃咖啡液」示例数据把闭环跑一遍。所有数字都是示例，不代表真实市场。\n工作目录：%s\n" % work)
    ok = True
    try:
        for title, cmds in demo_steps():
            print("=" * 8 + " " + title + " " + "=" * 8)
            for c in cmds:
                if c == "COPY_PLAN":
                    shutil.copy(os.path.join(EX, "sample_plan.json"), os.path.join(work, "xhs_launch", "plans", "L2.json"))
                    print("（把 examples/sample_plan.json 复制为 xhs_launch/plans/L2.json，代替「填写方案」这一步）\n")
                    continue
                if not run(c, work, full):
                    ok = False
                    print("这一步没有通过，演示停止。")
                    return 1
        print("演示完成。四个阶段也可以单独使用，把最后的数字换成 1 到 4 可以看每个阶段的示例：%s" % C.cmd("guide.py", "1"))
        if out:
            print("产出文件保留在：%s" % os.path.join(work, "xhs_launch"))
        return 0
    finally:
        if not out:
            shutil.rmtree(work, ignore_errors=True)
        elif not ok:
            print("已生成的文件保留在：%s" % work)


def build_parser():
    ap = argparse.ArgumentParser(description="xhs-launch-loop 使用指南与演示")
    ap.add_argument("topic", nargs="?", default="总览", help="留空看总览；1/2/3/4 看单个阶段；all 看全部；commands 看全部命令；demo 运行演示")
    ap.add_argument("--full", action="store_true", help="demo 时显示每一步的完整输出")
    ap.add_argument("--out", help="demo 时把产出文件保留到这个目录（默认用临时目录并清理）")
    return ap


def main():
    a = build_parser().parse_args()
    t = a.topic.strip()
    if t == "demo":
        sys.exit(demo(a.out, a.full))
    if t in ("commands", "命令"):
        show_commands()
        return
    if t == "all":
        for title, body in sections():
            print("## %s\n\n%s\n" % (title, body))
        print(how_to_run())
        return
    prefix = STAGES.get(t.lower(), t)
    if show(prefix):
        return
    print("没有找到「%s」。可用：%s，或 all、commands、demo。" % (t, "、".join(s[0] for s in sections())))
    sys.exit(1)


if __name__ == "__main__":
    C.run(main)

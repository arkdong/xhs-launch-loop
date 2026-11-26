#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用指南与演示。

  python scripts/guide.py            总览：这个技能能做什么、怎么开口
  python scripts/guide.py 1          单个阶段的说明和示例（1 调研 / 2 发布 / 3 反馈 / 4 迭代）
  python scripts/guide.py all        全部内容
  python scripts/guide.py demo       用示例数据把四个阶段完整跑一遍（不联网，不影响用户文件）

说明文字全部来自 references/examples.md，只维护那一份。只依赖 Python 3 标准库。
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOC = os.path.join(ROOT, "references", "examples.md")
EX = os.path.join(ROOT, "examples")

STAGES = {
    "1": "① 调研", "调研": "① 调研", "research": "① 调研",
    "2": "② 发布", "发布": "② 发布", "publish": "② 发布",
    "3": "③ 反馈", "反馈": "③ 反馈", "feedback": "③ 反馈",
    "4": "④ 迭代", "迭代": "④ 迭代", "next": "④ 迭代",
}


def sections():
    """按二级标题切分 examples.md，返回 [(标题, 正文)]。"""
    out, title, buf = [], None, []
    with open(DOC, encoding="utf-8") as f:
        for line in f:
            if line.startswith("## "):
                if title:
                    out.append((title, "".join(buf).strip()))
                title, buf = line[3:].strip(), []
            elif title:
                buf.append(line)
    if title:
        out.append((title, "".join(buf).strip()))
    return out


def show(prefix):
    for title, body in sections():
        if title.startswith(prefix):
            print("## %s\n\n%s\n" % (title, body))
            return True
    return False


def run(cmd, cwd, full):
    """运行一条脚本命令，打印命令和（截断的）真实输出。失败时返回 False。"""
    shown = "python scripts/" + " ".join(
        os.path.relpath(c, EX).join(["examples/", ""]) if c.startswith(EX) else c for c in cmd)
    print("$ " + shown)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-B", os.path.join(HERE, cmd[0])] + cmd[1:],
                       cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = [l for l in p.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    limit = len(lines) if full else 10
    for l in lines[:limit]:
        print("  " + l)
    if len(lines) > limit:
        print("  …（还有 %d 行，加 --full 查看全部）" % (len(lines) - limit))
    print()
    return p.returncode == 0


def demo(out, full):
    work = os.path.abspath(out) if out else tempfile.mkdtemp(prefix="xhs_demo_")
    os.makedirs(work, exist_ok=True)
    if os.path.exists(os.path.join(work, "xhs_launch")):
        print("目录 %s 里已有 xhs_launch，为避免覆盖你的数据，演示已取消。请换一个 --out 目录。" % work)
        return 1
    notes = os.path.join(EX, "sample_notes.json")
    comments = os.path.join(EX, "sample_comments.txt")
    plan = os.path.join(EX, "sample_plan.json")
    print("演示：用虚构的「冷萃咖啡液」示例数据把闭环跑一遍。所有数字都是示例，不代表真实市场。\n")
    ok = True
    try:
        steps = [
            ("建档", [["launch_log.py", "init", "--product", "冷萃咖啡液", "--audience", "早八打工人",
                      "--selling-points", "3秒冷萃,一杯不到4块", "--tone", "真实体验感"]]),
            ("① 调研：入库 24 篇同类笔记，分析竞品评论，做供需分析，登记本次假设", [
                ["research.py", "add", notes, "--keyword", "冷萃咖啡液"],
                ["comment_insight.py", comments, "--json", "insight.json"],
                ["research.py", "analyze", "--topic", "冷萃咖啡液", "--days", "0",
                 "--insight", "insight.json", "--out", "xhs_launch/research/brief.md"],
                ["launch_log.py", "add", "--title", "打工人算账：一杯咖啡到底多少钱", "--type", "图文",
                 "--angle", "价格痛点", "--hypothesis", "以价格痛点开头的评论率高于泛卖点开头",
                 "--evidence", "示例：评论里反复问价格，很少有笔记在标题回应"],
            ]),
            ("② 发布：生成方案骨架，填入真实信息（此处用示例方案代替），检查，生成配图提示词", [
                ["content_plan.py", "new", "--id", "L1", "--goal", "互动"],
                "COPY_PLAN",
                ["content_plan.py", "check", "--id", "L1"],
                ["content_plan.py", "prompts", "--id", "L1"],
                ["launch_log.py", "publish", "--id", "L1", "--url", "https://example.com/note/demo",
                 "--final-title", "打工人算账：一杯咖啡到底多少钱"],
            ]),
            ("③ 反馈：解析评论（示例里复用同一份评论），录入数据，给假设下结论", [
                ["comment_insight.py", comments, "--json", "insight.json"],
                ["launch_log.py", "metrics", "--id", "L1", "--impressions", "12000", "--views", "1800",
                 "--likes", "96", "--collects", "140", "--comments", "31", "--shares", "12", "--follows", "9"],
                ["launch_log.py", "verdict", "--id", "L1", "--result", "证据不足",
                 "--learning", "首次发布没有对照，本次评论率记为基线，下一篇用泛卖点开头做对照",
                 "--insight", "insight.json"],
            ]),
            ("④ 迭代：下一次发什么、产品改什么", [
                ["launch_log.py", "next"],
                ["launch_log.py", "report", "--out", "xhs_launch/report.md"],
            ]),
        ]
        for title, cmds in steps:
            print("=" * 8 + " " + title + " " + "=" * 8)
            for c in cmds:
                if c == "COPY_PLAN":
                    shutil.copy(plan, os.path.join(work, "xhs_launch", "plans", "L1.json"))
                    print("（把 examples/sample_plan.json 复制为 xhs_launch/plans/L1.json，"
                          "代替「向用户要真实信息并填写方案」这一步）\n")
                    continue
                if not run(c, work, full):
                    ok = False
                    print("这一步没有通过，演示停止。")
                    return 1
        print("演示完成。四个阶段也可以单独使用：python scripts/guide.py 1|2|3|4 查看每一步的示例。")
        if out:
            print("产出文件保留在：%s" % os.path.join(work, "xhs_launch"))
        return 0
    finally:
        if not out:
            shutil.rmtree(work, ignore_errors=True)
        elif not ok:
            print("已生成的文件保留在：%s" % work)


def main():
    ap = argparse.ArgumentParser(description="xhs-launch-loop 使用指南与演示")
    ap.add_argument("topic", nargs="?", default="总览",
                    help="留空看总览；1/2/3/4 看单个阶段；all 看全部；demo 运行演示")
    ap.add_argument("--full", action="store_true", help="demo 时显示每一步的完整输出")
    ap.add_argument("--out", help="demo 时把产出文件保留到这个目录（默认用临时目录并清理）")
    a = ap.parse_args()
    t = a.topic.strip()
    if t == "demo":
        return demo(a.out, a.full)
    if t == "all":
        for title, body in sections():
            print("## %s\n\n%s\n" % (title, body))
        return 0
    prefix = STAGES.get(t.lower(), t)
    if show(prefix):
        return 0
    print("没有找到「%s」。可用：%s，或 all、demo。" % (t, "、".join(s[0] for s in sections())))
    return 1


if __name__ == "__main__":
    sys.exit(main())

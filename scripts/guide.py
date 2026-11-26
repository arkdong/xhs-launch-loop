#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用指南与演示。

  python3 guide.py            总览：这个技能能做什么、怎么开口
  python3 guide.py 1          单个阶段的说明和示例（1 调研 / 2 发布 / 3 反馈 / 4 迭代）
  python3 guide.py all        全部内容
  python3 guide.py commands   所有命令一览，路径已经填好，可以直接复制
  python3 guide.py demo       用示例数据把四个阶段完整跑一遍（临时目录，不联网，不影响你的文件），每条命令只列要点
  python3 guide.py demo --full          每条命令的完整输出
  python3 guide.py demo --out 目录      把演示的产出文件留在这个目录

说明文字全部来自 references/examples.md，只维护那一份。只依赖 Python 3 标准库。
"""
import argparse
import os
import re
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
        ("建档，只看一篇已经发出去的笔记的反馈：两项就够。发布目标从 触达、互动、收藏 里选一个", ["launch_log.py", "init", "--product", '"产品名"', "--goal", "互动"]),
        ("建档，要调研和写笔记：用户答不上来的项先不写，不要填「无」。身份照实写：品牌方、店主、自己买的用户、收了报酬的合作",
         ["launch_log.py", "init", "--product", '"产品名"', "--category", '"品类"', "--audience", '"目标人群"', "--selling-points", '"卖点1,卖点2"',
          "--price", '"价格和规格"', "--goal", "互动", "--identity", '"品牌方"',
          "--fact", '缺点="…"', "--fact", '使用情况="…"', "--fact", '结果="…"', "--fact", '素材="…"', "--fact", '购买方式="…"']),
        ("之后补充或修改事实。有就记的还有：外观、语气、竞品、常见吐槽、固定标签", ["launch_log.py", "fact", '价格="…"', '缺点="…"']),
    ]),
    ("① 调研", [
        ("搜索词：必搜 4 个，每个看前 8 篇，一共 30 篇左右；品类、卖点、人群取自档案", ["research.py", "keywords"]),
        ("笔记入库：每个搜索词的结果存成一个文件，原样粘贴不用整理", ["research.py", "add", "搜索结果.txt", "--keyword", '"搜索词"']),
        ("别人笔记下的评论：评论区原样粘贴存成文件，--author 写那篇笔记作者的昵称", ["comment_insight.py", "评论.txt", "--research", "--author", '"作者昵称"']),
        ("供需分析", ["research.py", "analyze"]),
        ("登记这次发布和它的假设", ["launch_log.py", "add", "--title", '"暂定标题"', "--angle", '"角度"', "--hypothesis", '"假设"', "--evidence", '"依据"']),
        ("已经发出去、没有假设的笔记，登记为基线", ["launch_log.py", "add", "--title", '"标题"', "--baseline", "--published", "2026-11-20"]),
    ]),
    ("② 发布", [
        ("生成方案骨架", ["content_plan.py", "new", "--id", "L1"]),
        ("检查方案，通过后导出成稿", ["content_plan.py", "check", "--id", "L1"]),
        ("生成配图提示词", ["content_plan.py", "prompts", "--id", "L1"]),
        ("只检查一篇现成的草稿", ["note_check.py", "草稿.txt"]),
        ("发布后回填链接", ["launch_log.py", "publish", "--id", "L1", "--url", '"笔记链接"', "--final-title", '"最终标题"']),
    ]),
    ("③ 反馈", [
        ("解析这一篇的评论，--author 写用户自己的昵称，用来分出作者回复", ["comment_insight.py", "评论.txt", "--id", "L1", "--author", '"你的昵称"']),
        ("录入数据并诊断", ["launch_log.py", "metrics", "--id", "L1", "--impressions", "N", "--views", "N", "--likes", "N", "--collects", "N", "--comments", "N"]),
        ("给假设下结论：--result 从 成立、不成立、证据不足 里选一个，基线那一篇写 基线", ["launch_log.py", "verdict", "--id", "L1", "--result", "证据不足", "--learning", '"一句话沉淀"']),
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


# 演示默认只列每条命令输出里的要点。每种命令一组 (行首的写法, 连着留几行)：行首的空格不算，只取第一次出现。
# 整行原样打印，不截断，所以不会把一条命令从中间切开。
# 一条写法都没对上时退回到前 6 行。测试保证演示走不到这一步：哪个脚本的输出改了写法，这里要跟着改。
DIGEST = {
    "launch_log.py init": [("已建档", 1), ("- 卖点", 1), ("- 语气", 1)],
    "research.py keywords": [("## 必搜", 5), ("工作量：", 1)],
    "research.py add": [("读取 ", 1), ("缺失", 1), ("语料库 ", 1)],
    "comment_insight.py --research": [("解析：", 1), (r"\| 维度 \|", 3), ("## 问题主题", 1), (r"- \*\*.+?\*\* \d+ 条：", 1)],
    "research.py analyze": [("- 输入 ", 1), (r"- \*\*.+?\*\*：\d+ 篇提到", 1), (r"## 4\. 需求缺口", 1), (r"\| 关注点 \|", 3), (r"## 7\. 发布假设候选", 7)],
    "launch_log.py add": [("已登记发布", 1), ("待验证假设", 1)],
    "launch_log.py metrics": [(r"\| 点击率", 4), ("- 没有另一篇", 1), ("- 对比 ", 4)],
    "launch_log.py verdict": [(r"L\d+ ", 1), ("沉淀：", 1), ("主指标", 1), ("注意：", 1)],
    "content_plan.py new": [("已生成发布方案骨架", 1), ("- 发布假设", 1), ("## 需要用户提供的信息", 1), (r"- \[ \] ", 1), (r"1\. 上面打了空格", 1)],
    "content_plan.py check": [("结论：", 1), ("检查过的范围", 1), ("已导出两份", 3)],
    "content_plan.py prompts": [("- 这一篇要准备", 1), ("## 第 1 页", 2), (r"\*\*后期加字\*\*", 1), ("## 第 2 页", 5)],
    "launch_log.py publish": [(r"L\d+ 已标记为已发布", 1)],
    "comment_insight.py --id": [("解析：", 1), ("## 说法核对", 1), ("- 档案（", 2), (r"\| 维度 \|", 3), ("还没回复的问题", 3)],
    "launch_log.py next": [("## 待核实的说法", 1), (r"- L\d+：档案", 1), ("## 已被验证有效", 2), ("## 基线", 2), ("## 建议", 5)],
    "launch_log.py report": [("复盘报告已写入", 1)],
}


def digest_key(cmd):
    """演示里一条命令用哪一组要点：脚本名加子命令；comment_insight.py 没有子命令，按 --research 和 --id 分。"""
    if cmd[0] == "comment_insight.py":
        return "comment_insight.py " + ("--research" if "--research" in cmd else "--id")
    return "%s %s" % (cmd[0], cmd[1])


def digest(key, lines):
    """从一条命令的输出里挑出要点，顺序不变。返回 (要点行, 有没有对上写法)。"""
    keep = set()
    for pattern, n in DIGEST.get(key, []):
        rx = re.compile(r"\s*(?:%s)" % pattern)
        first = next((i for i, l in enumerate(lines) if rx.match(l)), None)
        if first is not None:
            keep.update(range(first, min(first + n, len(lines))))
    if not keep:
        return lines[:6], False
    return [lines[i] for i in sorted(keep)], True


def run(cmd, cwd, full):
    """运行一条脚本命令，打印命令和它的真实输出（默认只列要点，full 时全部打印）。失败时返回 False。"""
    print("$ " + C.cmd(*[C.quote(c) if i else c for i, c in enumerate(cmd)]))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.pop("XHS_LAUNCH_DIR", None)
    p = subprocess.run([sys.executable, "-B", os.path.join(C.SCRIPTS, cmd[0])] + cmd[1:], cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = [l for l in p.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
    shown = lines if full or p.returncode else digest(digest_key(cmd), lines)[0]      # 出错时全部打印，方便看原因
    for l in shown:
        print("  " + l)
    if len(shown) < len(lines):
        print("  （以上是要点，完整输出共 %d 行）" % len(lines))
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
             "--fact", "结果=每天早上少排队 15 分钟，7 天一共少排 105 分钟；以前买楼下便利店的拿铁，一杯 9 块 9", "--fact", "缺点=单喝偏苦，不加奶的人慎重；包装不好撕",
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
            ["launch_log.py", "add", "--title", "冷萃咖啡液开箱", "--baseline", "--published", "2026-11-01"],
            ["launch_log.py", "metrics", "--id", "L1", "--impressions", "8000", "--views", "900", "--likes", "60", "--collects", "25", "--comments", "6"],
            ["launch_log.py", "verdict", "--id", "L1", "--result", "基线", "--learning", "卖点罗列式开头：点击率 11.3%，评论率 0.7%"],
            # 假设和依据照抄上一步分析给出的第一条候选（需求缺口：价格）；测试会核对这里的数字和分析结果一致
            ["launch_log.py", "add", "--title", "打工人算账：一杯咖啡到底多少钱", "--angle", "价格痛点", "--hypothesis", "以价格痛点开头，评论率高于基线 L1",
             "--evidence", "调研的需求缺口「价格」：21 条评论里有 9 条在吐槽或追问它，但 32 篇笔记里只有 3 篇在标题回应"],
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
    print("演示：用虚构的「冷萃咖啡液」示例数据把闭环跑一遍。所有数字都是示例，不代表真实市场。")
    print("工作目录：%s%s" % (work, "" if out else "（临时目录，演示结束后自动删除）"))
    print("行首带「$」的是实际运行的命令%s\n" % ("。" if full else "，下面只列每条命令输出里的要点。"))
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
        print("演示完成。")
        if not full:
            print("上面每条命令只列了要点。看完整输出：%s" % C.cmd("guide.py", "demo", "--full"))
        if out:
            print("产出文件保留在：%s" % os.path.join(work, "xhs_launch"))
        else:
            print("演示用的临时目录已经删除，上面出现的文件路径都不在了。想留下产出文件（方案、成稿、配图提示词、复盘报告）：%s" % C.cmd("guide.py", "demo", "--out", "目录"))
        print("四个阶段也可以单独使用，把最后的数字换成 1 到 4 可以看每个阶段的示例：%s" % C.cmd("guide.py", "1"))
        return 0
    finally:
        if not out:
            shutil.rmtree(work, ignore_errors=True)
        elif not ok:
            print("已生成的文件保留在：%s" % work)


def build_parser():
    ap = argparse.ArgumentParser(description="xhs-launch-loop 使用指南与演示")
    ap.add_argument("topic", nargs="?", default="总览", help="留空看总览；1/2/3/4 看单个阶段；all 看全部；commands 看全部命令；demo 运行演示")
    ap.add_argument("--full", action="store_true", help="demo 时显示每条命令的完整输出（默认只列要点）")
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

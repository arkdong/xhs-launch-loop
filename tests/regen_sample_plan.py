#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重新生成 examples/sample_plan.json，让示例方案始终和脚本生成的骨架一致。

做法：用 guide.py 里的演示步骤跑到「生成方案骨架」为止，得到最新的骨架（模板、调研结论、产品事实），
再把现有示例里手写的内容（标题、每页文字和画面、正文、标签、首评、配图设定）填回去。

  python3 tests/regen_sample_plan.py           重写 examples/sample_plan.json
  python3 tests/regen_sample_plan.py --check   只比较，不一致时退出码为 1（测试用）
"""
import json
import os
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import guide  # noqa: E402

SAMPLE = os.path.join(ROOT, "examples", "sample_plan.json")
NOTE = "示例方案：guide.py demo 用它代替「填写方案」这一步。产品和所有数字都是虚构的。由 tests/regen_sample_plan.py 生成，不要手改骨架部分。"


def skeleton():
    """跑演示步骤直到生成 L2 的方案骨架，返回骨架。"""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.pop("XHS_LAUNCH_DIR", None)
    with tempfile.TemporaryDirectory(prefix="xhs_regen_") as work:
        for _, cmds in guide.demo_steps():
            for c in cmds:
                if c == "COPY_PLAN":
                    with open(os.path.join(work, "xhs_launch", "plans", "L2.json"), encoding="utf-8") as f:
                        return json.load(f)
                p = subprocess.run([sys.executable, "-B", os.path.join(ROOT, "scripts", c[0])] + c[1:], cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                if p.returncode:
                    sys.exit("演示步骤失败：%s\n%s" % (" ".join(c), p.stdout.decode("utf-8", "replace")))
    sys.exit("演示步骤里没有「生成方案」这一步。")


def build():
    with open(SAMPLE, encoding="utf-8") as f:
        old = json.load(f)
    new = skeleton()
    new["titles"] = old["titles"]
    by_no = {g["no"]: g for g in old["pages"]}
    for g in new["pages"]:
        src = by_no[g["no"]]
        if src["role"] != g["role"]:
            sys.exit("第 %d 页的角色变了（%s → %s），示例里手写的内容需要重写。" % (g["no"], src["role"], g["role"]))
        g.update({k: src[k] for k in ("text", "visual", "product_in_frame")})
    by_sec = {b["section"]: b["text"] for b in old["body"]}
    for b in new["body"]:
        if b["section"] not in by_sec:
            sys.exit("正文多了一段「%s」，示例里没有对应的内容。" % b["section"])
        b["text"] = by_sec[b["section"]]
    for k in ("tags", "fixed_tags", "first_comment", "image"):
        new[k] = old[k]
    answers = {f["key"]: f.get("value", "") for f in old["facts_needed"]}       # 「回应…」是这一篇特有的信息，档案里没有，要手写
    for f in new["facts_needed"]:
        if not str(f.get("value") or "").strip():
            if not str(answers.get(f["key"]) or "").strip():
                sys.exit("方案多了一项要填的信息「%s」，示例里没有对应的回答。在 examples/sample_plan.json 的 facts_needed 里补上再运行。" % f["key"])
            f["value"] = answers[f["key"]]
    out = {"_说明": NOTE}
    out.update(new)
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def main():
    text = build()
    with open(SAMPLE, encoding="utf-8") as f:
        same = f.read() == text
    if "--check" in sys.argv[1:]:
        print("examples/sample_plan.json " + ("和脚本生成的骨架一致。" if same else "已经过期，运行 python3 tests/regen_sample_plan.py 重新生成。"))
        sys.exit(0 if same else 1)
    with open(SAMPLE, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("已重写 %s%s" % (SAMPLE, "（内容没有变化）" if same else ""))


if __name__ == "__main__":
    main()

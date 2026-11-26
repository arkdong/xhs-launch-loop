#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包技能：只收技能运行需要的文件，检查大赛的体积限制，生成 dist/xhs-launch-loop.zip。

  python3 package.py                  生成 dist/xhs-launch-loop.zip
  python3 package.py --list           只列出会打包的文件
  python3 package.py --copy-to 目录    另外把技能文件夹同步到 目录/xhs-launch-loop（先清空再复制）

压缩包里只有一个顶层文件夹 xhs-launch-loop/，内容是 SKILL.md、scripts、references、assets、examples。
测试、README、许可证和缓存文件不进包。同样的内容每次打出的压缩包完全一样。
"""
import argparse
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "xhs-launch-loop"
DIRS = ("scripts", "references", "assets", "examples")
MAX_FILES, MAX_BYTES = 30, 40 * 1024 * 1024      # 大赛限制：不超过 30 个文件、40 MB


def files(root=ROOT):
    """技能包里的文件，相对路径，顺序固定。"""
    out = ["SKILL.md"]
    for d in DIRS:
        base = os.path.join(root, d)
        out += sorted("%s/%s" % (d, f) for f in os.listdir(base) if os.path.isfile(os.path.join(base, f)) and not f.startswith(".") and not f.endswith((".pyc", ".tmp")))
    return out


def check(root=ROOT):
    """返回 (文件列表, 总字节数)；超出限制时直接退出。"""
    fs = files(root)
    size = sum(os.path.getsize(os.path.join(root, f)) for f in fs)
    if len(fs) > MAX_FILES:
        sys.exit("技能包有 %d 个文件，超过 %d 个的限制。" % (len(fs), MAX_FILES))
    if size > MAX_BYTES:
        sys.exit("技能包 %.1f MB，超过 %d MB 的限制。" % (size / 1048576.0, MAX_BYTES // 1048576))
    return fs, size


def build(out_dir, root=ROOT):
    fs, size = check(root)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, NAME + ".zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in fs:
            info = zipfile.ZipInfo("%s/%s" % (NAME, f), date_time=(2026, 1, 1, 0, 0, 0))      # 固定时间：内容不变，压缩包就不变
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(os.path.join(root, f), "rb") as src:
                z.writestr(info, src.read())
    return path, fs, size


def copy_to(parent, root=ROOT):
    fs, _ = check(root)
    dst = os.path.join(parent, NAME)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    for f in fs:
        os.makedirs(os.path.dirname(os.path.join(dst, f)), exist_ok=True)
        shutil.copyfile(os.path.join(root, f), os.path.join(dst, f))
    return dst


def main():
    ap = argparse.ArgumentParser(description="打包 xhs-launch-loop 技能")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"), help="压缩包输出目录，默认 dist/")
    ap.add_argument("--list", action="store_true", help="只列出会打包的文件")
    ap.add_argument("--copy-to", metavar="目录", help="另外把技能文件夹同步到 目录/%s" % NAME)
    a = ap.parse_args()
    if a.list:
        fs, size = check()
        print("\n".join(fs))
        print("共 %d 个文件，%.0f KB（限制 %d 个、%d MB）" % (len(fs), size / 1024.0, MAX_FILES, MAX_BYTES // 1048576))
        return
    path, fs, size = build(a.out)
    print("已生成 %s：%d 个文件，原始大小 %.0f KB，压缩后 %.0f KB（限制 %d 个、%d MB）" % (path, len(fs), size / 1024.0, os.path.getsize(path) / 1024.0, MAX_FILES, MAX_BYTES // 1048576))
    if a.copy_to:
        print("已同步文件夹 %s" % copy_to(a.copy_to))


if __name__ == "__main__":
    main()

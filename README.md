# xhs-launch-loop：小红书发布闭环

把每一篇小红书笔记当作一次产品发布来运营的 Agent Skill：发之前调研，发的时候有方案，发之后看反馈，再决定下一篇。

A Xiaohongshu (RED) launch-loop skill for AI agents. It treats every note as a product launch: research before posting, a page-by-page plan when posting, comment and metric analysis after posting, then a decision on the next note. Python 3 standard library only, no scraping, no login.

## 四个阶段

| 阶段 | 做什么 | 用户会得到 |
|---|---|---|
| ① 调研 | 看同类笔记和评论，决定这次用什么角度 | 调研简报，加一条待验证的假设 |
| ② 发布 | 定下发什么、每一页放什么 | 3 个标题、逐页图文、正文、标签、配图提示词，并通过合规检查 |
| ③ 反馈 | 读评论和数据，判断假设对不对 | 评论洞察、数据诊断、成立 / 不成立 / 证据不足 |
| ④ 迭代 | 决定下一篇发什么、产品改什么 | 下一次发布简报，加产品改进清单 |

四个阶段可以从头走，也可以只用其中一个。所有发布记在一份发布日志里（`xhs_launch/launch_log.json`）。

## 设计取舍

- **不抓取、不登录、不代发。** 数据来自环境里已有的搜索工具，或者用户自己带回来的搜索结果和评论区：网页版复制的内容原样粘贴，手机截图由智能体转写，都不用整理。发布由用户在 App 里完成。
- **数字来自脚本。** 解析、计数、对比都由脚本完成，模型负责判断、写作和提问。
- **结论有门槛。** 笔记不到 20 篇、评论不到 20 条、同一痛点不到 3 条、倍数没法排除账号大小的影响时，只标成线索；曝光不到 1000 或没有可比的发布时，脚本拒绝登记「成立 / 不成立」。
- **事实只来自用户。** 价格、使用感受、缺点由用户提供。方案里留着占位内容，或者出现了档案和调研原话里找不到出处的数字，都过不了检查。
- **少问、问在点上。** 建档前问一轮，写笔记前问一轮，每轮一次问完；只做复盘时四样就够。
- **按账号内部比较。** 样本集中在几个账号时，比的是「这篇 ÷ 它所在账号的中位数」，避免把账号大小当成写法的功劳。

## 安装

需要 Python 3.8 或更高版本，没有第三方依赖。

1. 从 `dist/xhs-launch-loop.zip`（用 `python3 package.py` 生成）解压出 `xhs-launch-loop/` 文件夹，或者直接复制仓库里的 `SKILL.md`、`scripts/`、`references/`、`assets/`、`examples/`。
2. 把这个文件夹放进智能体的技能目录，或者按平台的方式上传压缩包。
3. 对智能体说「这个技能怎么用」或「演示一遍」。

## 自己试一下

脚本在哪个目录运行，数据就写在哪个目录的 `xhs_launch/` 里，所以请在你自己的工作目录里用绝对路径调用：

```bash
cd ~/my-shop
python3 /path/to/xhs-launch-loop/scripts/guide.py            # 使用说明
python3 /path/to/xhs-launch-loop/scripts/guide.py demo       # 用示例数据把四个阶段跑一遍，每条命令只列要点；不联网，不改动你的文件
python3 /path/to/xhs-launch-loop/scripts/guide.py commands   # 全部命令，路径已经填好
```

每条命令的输出末尾都有填好绝对路径的「下一步」命令。示例里的产品「冷萃咖啡液」和所有数字都是虚构的。

## 目录

```
SKILL.md        技能说明：智能体读这一份
scripts/        6 个脚本和公共函数（research、comment_insight、content_plan、note_check、launch_log、guide、common）
references/     各阶段的方法和规则，SKILL.md 按需引用
assets/         通用词表：评论关注点、意图、违规词、停用词
examples/       示例数据，guide.py demo 用
tests/          回归测试和测试用的粘贴样本（不进技能包）
package.py      打包脚本（不进技能包）
```

技能包共 26 个文件，约 450 KB（大赛限制 30 个文件、40 MB）。

## 开发

```bash
python3 -m unittest discover -s tests       # 全部测试，约一分钟
python3 tests/regen_sample_plan.py          # 改了方案骨架后，重新生成 examples/sample_plan.json
python3 package.py                          # 生成 dist/xhs-launch-loop.zip
python3 package.py --copy-to 某个目录        # 同时同步一份解压后的技能文件夹
```

测试覆盖：粘贴的搜索结果和评论区的解析、在任意目录运行、分析和结论的门槛、发布方案检查（占位内容、违规词、数字的出处）、建档时问什么、演示和它自己的分析是否一致、合规词表、文档里的命令和阈值是否与脚本一致、打包后的压缩包能否直接使用。在 Python 3.8、3.9、3.11、3.12、3.13 上通过。

品类特有的痛点词和好评词不要改 `assets/`，写进项目自己的 `xhs_launch/lexicon.json`（格式见 `references/feedback.md`）；行业违规词写进 `xhs_launch/banned_words.txt`（见 `references/compliance.md`）。

## 许可证

MIT，见 [LICENSE](LICENSE)。

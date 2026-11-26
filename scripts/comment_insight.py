#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书评论洞察：意图分布、高频关键词、痛点聚类、待回复问题。

用法:
  python comment_insight.py comments.txt [--json out.json] [--top 15]
输入: .txt(每行一条) / .csv(自动找 评论/内容/content/comment 列) / .json(字符串数组或含 content 字段的对象数组)
只依赖 Python 标准库。
"""
import argparse, csv, json, os, re, sys
from collections import Counter, defaultdict

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
TEXT_KEYS = ["评论内容", "评论", "内容", "content", "comment", "text"]
LIKE_KEYS = ["点赞数", "点赞", "likes", "like_count", "like"]


def load_json(name):
    with open(os.path.join(BASE, name), encoding="utf-8") as f:
        return json.load(f)


def load_stopwords():
    with open(os.path.join(BASE, "stopwords.txt"), encoding="utf-8") as f:
        return set(f.read().split())


def to_int(v):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return 0


def pick(d, keys):
    low = {str(k).strip().lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in low and low[k.lower()] not in (None, ""):
            return low[k.lower()]
    return None


def read_comments(path):
    """返回 [(text, likes)]"""
    ext = os.path.splitext(path)[1].lower()
    with open(path, encoding="utf-8-sig") as f:
        raw = f.read()
    rows = []
    if ext == ".json":
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("comments") or data.get("data") or []
        for it in data:
            if isinstance(it, str):
                rows.append((it, 0))
            elif isinstance(it, dict):
                rows.append((str(pick(it, TEXT_KEYS) or ""), to_int(pick(it, LIKE_KEYS))))
    elif ext == ".csv":
        reader = csv.DictReader(raw.splitlines())
        for it in reader:
            rows.append((str(pick(it, TEXT_KEYS) or ""), to_int(pick(it, LIKE_KEYS))))
    else:
        for line in raw.splitlines():
            rows.append((line, 0))
    out, seen = [], set()
    for text, likes in rows:
        t = clean(text)
        if len(t) >= 2 and t not in seen:
            seen.add(t)
            out.append((t, likes))
    return out


def clean(t):
    t = re.sub(r"\[[^\]]{1,6}R?\]", "", t)          # [笑哭R] 这类表情
    t = re.sub(r"@\S+", "", t)                      # @某人
    t = re.sub(r"^\s*(回复\s*\S+?[:：]|\d+[\.、]\s*)", "", t)
    t = re.sub(r"\s*(\d{1,2}-\d{1,2}|\d+天前|\d+小时前|昨天.*|刚刚)\s*(\S{2,6})?\s*$", "", t)  # 尾部时间地区
    return t.strip()


def classify(text, lexicon):
    hits = []
    for intent, words in lexicon.items():
        for w in words:
            if (re.search(w, text) if ".*" in w else w in text):
                hits.append(intent)
                break
    # "提问" 很宽泛：若同时命中更具体的意图，保留两者；都没命中归为其他
    return hits or ["其他"]


def keywords(texts, stop, top):
    """无分词依赖的中文关键词：统计 2-4 字片段的出现评论数，去掉停用词和被更长片段覆盖的片段。"""
    df = Counter()
    for t in texts:
        grams = set()
        for seg in re.findall(r"[一-鿿]+|[A-Za-z][A-Za-z0-9]+", t):
            if re.match(r"[A-Za-z]", seg):
                grams.add(seg.lower())
                continue
            for n in (2, 3, 4):
                for i in range(len(seg) - n + 1):
                    g = seg[i:i + n]
                    if g in stop or g[0] in stop and g[-1] in stop:
                        continue
                    if any(ch in "的了吗呢吧啊呀哦么" for ch in (g[0], g[-1])) or g[0] in "个一是我你就都也还有在":
                        continue
                    grams.add(g)
        df.update(grams)
    cand = [(g, c) for g, c in df.items() if c >= 2]
    cand.sort(key=lambda x: (-x[1], -len(x[0])))
    kept = []
    for g, c in cand:
        # 被同频更长片段包含 -> 丢弃短的；包含同频更短片段 -> 已保留的短片段换成长的
        if any(g in k and kc >= c * 0.8 for k, kc in kept if len(k) > len(g)):
            continue
        # 跨词边界的碎片：是更高频词多带一个字，或只叠住了更高频词的一部分
        if any(kc > c and ((k in g and len(g) - len(k) == 1 and c < kc * 0.8) or (k not in g and _partial(k, g))) for k, kc in kept):
            continue
        kept = [(k, kc) for k, kc in kept if not (k in g and c >= kc * 0.8 and len(g) > len(k))]
        kept.append((g, c))
    kept.sort(key=lambda x: (-x[1], -len(x[0])))
    return kept[:top]


def _partial(k, g):
    """g 的开头是 k 的结尾，或 g 的结尾是 k 的开头"""
    for n in range(1, min(len(k), len(g))):
        if g.startswith(k[-n:]) or g.endswith(k[:n]):
            return True
    return False


def analyse(comments, top=15):
    lexicon, pains, stop = load_json("intent_lexicon.json"), load_json("pain_lexicon.json"), load_stopwords()
    n = len(comments)
    intent_count, intent_samples = Counter(), defaultdict(list)
    questions = []
    for text, likes in comments:
        intents = classify(text, lexicon)
        for it in intents:
            intent_count[it] += 1
            intent_samples[it].append((likes, text))
        if "提问" in intents:
            questions.append((likes, text))
    clusters = {}
    for name, words in pains.items():
        matched = [(likes, t) for t, likes in comments if any(w in t for w in words)]
        if matched:
            matched.sort(key=lambda x: -x[0])
            hit_words = Counter(w for _, t in matched for w in words if w in t)
            clusters[name] = {"count": len(matched), "share": round(len(matched) / n, 3),
                              "top_words": [w for w, _ in hit_words.most_common(4)],
                              "quotes": [t for _, t in matched[:3]]}
    clusters = dict(sorted(clusters.items(), key=lambda kv: -kv[1]["count"]))
    questions.sort(key=lambda x: -x[0])

    def share(k):
        return round(intent_count.get(k, 0) / n, 3) if n else 0

    actions = []
    if share("购买意向") >= 0.15:
        actions.append("购买意向占比高：在首评或正文末尾补充购买方式，并准备一篇「怎么选/怎么买」的跟进笔记。")
    if share("提问") >= 0.25:
        actions.append("提问占比高：把下方高频问题整理成一篇答疑笔记，并在 24 小时内逐条回复。")
    if share("痛点吐槽") >= 0.15:
        actions.append("吐槽占比高：优先核对痛点聚类第一名，判断是产品问题还是预期管理问题，分别进入产品改进清单或下一篇的开头。")
    if share("求教程") >= 0.1:
        actions.append("求教程明显：下一次发布改用教程体或出视频版分步演示。")
    if share("质疑广告") >= 0.08:
        actions.append("出现广告质疑：下一篇增加真实使用细节与缺点描述，减少卖点罗列。")
    if share("建议期待") >= 0.08:
        actions.append("用户在提需求：把「建议期待」中的原话登记进产品改进清单。")
    if clusters:
        first = next(iter(clusters))
        actions.append("最集中的痛点是「%s」（%d 条），可作为下一篇笔记的开头钩子。" % (first, clusters[first]["count"]))
    if n < 20:
        actions.insert(0, "样本仅 %d 条，结论仅供参考，建议累计到 20 条以上再做判断。" % n)

    return {
        "total": n,
        "sample_sufficient": n >= 20,
        "intent_distribution": [{"intent": k, "count": c, "share": round(c / n, 3),
                                 "examples": [t for _, t in sorted(intent_samples[k], key=lambda x: -x[0])[:2]]}
                                for k, c in intent_count.most_common()],
        "keywords": [{"word": w, "comments": c} for w, c in keywords([t for t, _ in comments], stop, top)],
        "pain_clusters": clusters,
        "questions_to_answer": [t for _, t in questions[:10]],
        "actions": actions,
    }


def to_markdown(r):
    L = ["# 评论洞察报告", "", "共解析 **%d** 条有效评论%s" % (r["total"], "" if r["sample_sufficient"] else "（样本不足 20 条，结论仅供参考）"), ""]
    L += ["## 意图分布", "", "| 意图 | 条数 | 占比 | 代表评论 |", "|---|---|---|---|"]
    for it in r["intent_distribution"]:
        L.append("| %s | %d | %.0f%% | %s |" % (it["intent"], it["count"], it["share"] * 100, " / ".join(it["examples"]).replace("|", " ")))
    L += ["", "## 高频关键词", "", "、".join("%s(%d)" % (k["word"], k["comments"]) for k in r["keywords"]) or "无（评论过少）"]
    L += ["", "## 痛点聚类", ""]
    if not r["pain_clusters"]:
        L.append("未识别到明显痛点。")
    for name, c in r["pain_clusters"].items():
        L.append("- **%s**：%d 条（%.0f%%），高频词：%s" % (name, c["count"], c["share"] * 100, "、".join(c["top_words"])))
        for q in c["quotes"]:
            L.append("  - “%s”" % q)
    L += ["", "## 待回复问题", ""] + (["- " + q for q in r["questions_to_answer"]] or ["无"])
    L += ["", "## 行动建议", ""] + (["- " + a for a in r["actions"]] or ["- 暂无明确信号，继续积累评论。"])
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="小红书评论洞察")
    ap.add_argument("file", help="评论文件 .txt/.csv/.json")
    ap.add_argument("--json", help="同时把结构化结果写入该路径")
    ap.add_argument("--top", type=int, default=15, help="关键词数量")
    a = ap.parse_args()
    if not os.path.exists(a.file):
        sys.exit("找不到文件：%s" % a.file)
    comments = read_comments(a.file)
    if not comments:
        sys.exit("没有解析到有效评论。请确认文件为 UTF-8 编码，txt 每行一条，csv/json 含 评论/content 字段。")
    r = analyse(comments, a.top)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
    print(to_markdown(r))


if __name__ == "__main__":
    main()

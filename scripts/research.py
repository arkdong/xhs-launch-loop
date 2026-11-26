#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书发布前调研：关键词矩阵 → 笔记入库 → 供需分析 → 发布假设候选。

子命令:
  keywords --category 品类 [--product ..] [--audience ..] [--pains a,b] [--competitors a,b]
        生成分组搜索关键词矩阵（品类/正反面/人群/场景/竞品/痛点）
  add <文件> [--keyword 搜索词]
        把笔记数据并入语料库。支持 .json/.jsonl（含小红书 MCP、xhs-cli 等工具的导出结构）、.csv、
        .txt/.md（每行一篇：标题 | 赞 1.2万 | 藏 800 | 评 56 | 粉丝 900 | 2026-11-01 | 链接）
  analyze [--days 90] [--top 10] [--insight insight.json] [--out brief.md] [--json out.json]
        去重、时间窗、可复制度评分、低粉爆款、角度供给、标题钩子提升度、需求缺口、假设候选
  status    语料库概况
通用参数: --corpus 路径（默认 ./xhs_launch/research/notes.json）
只依赖 Python 标准库。所有频次与比例均由脚本计数，不是估计值。
"""
import argparse, csv, json, os, re, sys
from datetime import datetime, timedelta

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comment_insight as ci  # noqa: E402

DEFAULT_CORPUS = os.path.join("xhs_launch", "research", "notes.json")
K = {
    "id": ["id", "note_id", "noteid", "feed_id", "feedid", "笔记id"],
    "title": ["title", "displaytitle", "display_title", "标题", "笔记标题"],
    "desc": ["desc", "content", "snippet", "正文", "内容", "描述", "text"],
    "likes": ["likes", "liked_count", "likedcount", "like_count", "点赞", "点赞数", "赞"],
    "collects": ["collects", "collected_count", "collectedcount", "favorites", "collect_count", "收藏", "收藏数", "藏"],
    "comments": ["comment_count", "commentcount", "comments_count", "评论数", "评论", "评"],
    "shares": ["shares", "shared_count", "sharedcount", "share_count", "分享", "分享数"],
    "author": ["nickname", "nick_name", "author", "作者", "昵称"],
    "followers": ["followers", "fans", "fans_count", "follower_count", "粉丝", "粉丝数"],
    "date": ["date", "time", "publish_time", "publishtime", "create_time", "发布时间", "日期"],
    "url": ["url", "link", "note_url", "链接"],
    "type": ["type", "note_type", "类型", "形式"],
}
ANGLES = [
    ("避雷踩坑", ["避雷", "踩坑", "踩雷", "别买", "千万别", "后悔", "劝退", "翻车", "不推荐"]),
    ("对比平替", ["对比", "vs", "VS", "平替", "哪个好", "怎么选", "还是", "区别", "横评"]),
    ("测评实测", ["测评", "实测", "亲测", "评测", "体验", "开箱", "试了", "用了", "喝了", "吃了"]),
    ("教程攻略", ["教程", "攻略", "步骤", "方法", "怎么做", "怎么用", "保姆级", "手把手", "指南", "入门", "喝法", "做法"]),
    ("征集互动", ["征集", "集合", "看过来", "一人一个", "晒出", "投稿", "邀请你", "等你", "接龙"]),
    ("结果公布", ["结果公布", "获奖", "公示", "开奖", "揭晓", "揭榜", "入围", "复盘"]),
    ("上线公告", ["上线", "开启", "首发", "内测", "开放体验", "入驻", "发布", "更新"]),
    ("答疑科普", ["为什么", "是真的吗", "真的能", "真的假的", "原因", "科普", "真相", "误区"]),
    ("深度长文", ["一文", "拆解", "揭秘", "设计与实践", "实践", "原理", "深度"]),
    ("清单合集", ["清单", "合集", "盘点", "推荐", "必买", "好物", "top", "TOP", "款"]),
    ("个人故事", ["我的", "我是", "终于", "坚持", "那年", "经历", "日记", "记录", "vlog", "一周", "一个月"]),
]
HOOKS = [
    ("含数字", r"\d"),
    ("疑问句", r"[?？]|吗|怎么|如何|为什么|哪个"),
    ("点名人群", r"学生党|打工人|新手|小白|宝妈|上班族|女生|男生|租房|宿舍|社畜|懒人|党"),
    ("负面/避雷", r"避雷|踩坑|踩雷|别买|后悔|千万别|智商税|劝退|翻车"),
    ("反差/意外", r"以为|没想到|居然|竟然|结果|原来|才知道"),
    ("结果承诺", r"只需|只要|搞定|学会|秒|分钟|一招|直接"),
    ("新闻动词", r"上线|公布|发布|开启|首发|揭晓|提出|来了|入驻"),
    ("感叹号", r"[!！]"),
    ("期数前缀", r"[Vv]ol\.?\s*\d|第\s*\d+\s*[期弹]|(?<!\d)0?\d\s*[｜|]"),
    ("分隔符｜", r"[｜|]"),
    ("表情符号", r"[\U0001F300-\U0001FAFF☀-➿]"),
]


def num(v):
    """'1.2万' '3k' '1,024' '10万+' -> int"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().lower().replace(",", "").replace("+", "")
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(万|w|千|k)?$", s)
    if not m:
        return None
    x = float(m.group(1)) * {"万": 1e4, "w": 1e4, "千": 1e3, "k": 1e3, None: 1}[m.group(2)]
    return int(x)


def parse_date(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or re.fullmatch(r"\d{10,13}", str(v).strip()):
        t = float(v)
        t = t / 1000 if t > 1e11 else t
        try:
            return datetime.fromtimestamp(t).strftime("%Y-%m-%d")
        except (ValueError, OSError, OverflowError):
            return None
    s = str(v).strip()
    m = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", s)
    if m:
        return "%04d-%02d-%02d" % tuple(int(x) for x in m.groups())
    m = re.search(r"(\d+)\s*天前", s)
    if m:
        return (datetime.now() - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
    m = re.fullmatch(r"(\d{1,2})[-/.月](\d{1,2})日?", s)
    if m:
        return "%04d-%02d-%02d" % (datetime.now().year, int(m.group(1)), int(m.group(2)))
    return None


def deep_get(obj, names, depth=0):
    """在嵌套 dict 中按候选键名找第一个非空标量（兼容各工具的导出结构）。"""
    if not isinstance(obj, dict) or depth > 4:
        return None
    low = {str(k).lower(): v for k, v in obj.items()}
    for n in names:
        v = low.get(n)
        if v not in (None, "", [], {}) and not isinstance(v, (dict, list)):
            return v
    for v in obj.values():
        if isinstance(v, dict):
            r = deep_get(v, names, depth + 1)
            if r is not None:
                return r
    return None


def find_comment_list(obj, depth=0):
    if not isinstance(obj, dict) or depth > 4:
        return []
    for k, v in obj.items():
        if str(k).lower() in ("comments", "comment_list", "评论列表", "热评") and isinstance(v, list):
            out = []
            for c in v:
                t = c if isinstance(c, str) else (deep_get(c, ["content", "text", "评论", "内容"]) if isinstance(c, dict) else None)
                if t:
                    out.append(str(t))
            return out
    for v in obj.values():
        if isinstance(v, dict):
            r = find_comment_list(v, depth + 1)
            if r:
                return r
    return []


def norm(raw, keyword=""):
    title = deep_get(raw, K["title"])
    desc = deep_get(raw, K["desc"]) or ""
    if not title and not desc:
        return None
    nid = deep_get(raw, K["id"])
    url = deep_get(raw, K["url"]) or ""
    if not nid and url:
        m = re.search(r"/(?:explore|item|discovery/item)/([0-9a-f]{16,})", str(url))
        nid = m.group(1) if m else None
    if nid and not url and re.fullmatch(r"[0-9a-f]{24}", str(nid)):
        url = "https://www.xiaohongshu.com/explore/%s" % nid
    t = str(deep_get(raw, K["type"]) or "").lower()
    return {
        "id": str(nid) if nid else None, "title": str(title or desc[:20]).strip(), "desc": str(desc).strip()[:1500],
        "likes": num(deep_get(raw, K["likes"])) or 0, "collects": num(deep_get(raw, K["collects"])) or 0,
        "comments": num(deep_get(raw, K["comments"])) or 0, "shares": num(deep_get(raw, K["shares"])) or 0,
        "author": str(deep_get(raw, K["author"]) or ""), "followers": num(deep_get(raw, K["followers"])),
        "date": parse_date(deep_get(raw, K["date"])), "url": str(url),
        "type": "视频" if ("video" in t or "视频" in t) else ("图文" if t else ""),
        "comment_list": find_comment_list(raw)[:50], "keyword": keyword,
    }


def walk_records(data):
    """从任意 JSON 结构里找出「像笔记」的 dict 列表。"""
    if isinstance(data, list):
        if data and all(isinstance(x, dict) for x in data):
            return data
        out = []
        for x in data:
            out += walk_records(x)
        return out
    if isinstance(data, dict):
        for k in ("feeds", "items", "notes", "data", "results", "list"):
            if k in data and isinstance(data[k], (list, dict)):
                r = walk_records(data[k])
                if r:
                    return r
        return [data] if deep_get(data, K["title"]) else []
    return []


LINE_PAT = {
    "likes": r"(?:点赞|赞|❤️?|👍)\s*[:：]?\s*([\d.,]+\s*[万wk千]?\+?)",
    "collects": r"(?:收藏|藏|⭐|📁)\s*[:：]?\s*([\d.,]+\s*[万wk千]?\+?)",
    "comment_count": r"(?:评论|评|💬)\s*[:：]?\s*([\d.,]+\s*[万wk千]?\+?)",
    "followers": r"(?:粉丝|粉)\s*[:：]?\s*([\d.,]+\s*[万wk千]?\+?)",
}


def parse_line(line):
    line = line.strip().lstrip("-*•0123456789.、 ")
    if len(line) < 4 or line.startswith("#"):
        return None
    raw = {}
    m = re.search(r"https?://\S+", line)
    if m:
        raw["url"] = m.group(0).rstrip(")|｜")
        line = line.replace(m.group(0), " ")
    for k, p in LINE_PAT.items():
        m = re.search(p, line, flags=re.I)
        if m:
            raw[k] = m.group(1).replace(" ", "")
    m = re.search(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}|\d+\s*天前", line)
    if m:
        raw["date"] = m.group(0)
    if "视频" in line:
        raw["type"] = "视频"
    title = re.split(r"\s*[|｜\t]\s*|\s{2,}", line)[0]
    title = re.split(r"(?:点赞|赞|❤|👍|收藏|藏|⭐|评论|评|💬|粉丝)\s*[:：]?\s*\d", title)[0].strip(" ,，;；")
    if len(title) < 2 or (len(raw) == 0 and len(title) < 6):
        return None
    raw["title"] = title
    return raw


def read_notes(path, keyword=""):
    ext = os.path.splitext(path)[1].lower()
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    if ext == ".json":
        raws = walk_records(json.loads(text))
    elif ext == ".jsonl":
        raws = []
        for l in text.splitlines():
            if l.strip():
                raws += walk_records(json.loads(l))
    elif ext == ".csv":
        raws = list(csv.DictReader(text.splitlines()))
    else:
        raws = [r for r in (parse_line(l) for l in text.splitlines()) if r]
    return [n for n in (norm(r, keyword) for r in raws) if n]


def trigrams(s):
    s = re.sub(r"[^\w一-鿿]", "", s.lower())
    return {s[i:i + 3] for i in range(max(1, len(s) - 2))}


def dedupe(notes):
    out, seen_id = [], set()
    for n in sorted(notes, key=lambda x: -(x["likes"] + x["collects"])):
        if n["id"] and n["id"] in seen_id:
            continue
        tg = trigrams(n["title"])
        dup = False
        for o in out:
            og = o["_tg"]
            if tg and og and len(tg & og) / len(tg | og) >= 0.6 and (not n["author"] or not o["author"] or n["author"] == o["author"]):
                dup = True
                break
        if dup:
            continue
        if n["id"]:
            seen_id.add(n["id"])
        n["_tg"] = tg
        out.append(n)
    for n in out:
        n.pop("_tg", None)
    return out


def load_corpus(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)["notes"]


def save_corpus(path, notes):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "notes": notes}, f, ensure_ascii=False, indent=1)


def median(xs):
    xs = sorted(xs)
    if not xs:
        return 0
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def eng(n):
    return n["likes"] + 2 * n["collects"] + 3 * n["comments"]


def age_days(n):
    if not n["date"]:
        return None
    try:
        return max(0, (datetime.now() - datetime.strptime(n["date"], "%Y-%m-%d")).days)
    except ValueError:
        return None


def score(notes):
    """可复制度评分：互动分位 + 时效 + 赞粉比。用分位数而不是除以最大值，避免被单篇大爆款压扁。"""
    ranked = sorted(notes, key=eng)
    pos = {id(n): i for i, n in enumerate(ranked)}
    for n in notes:
        e = 100 * pos[id(n)] / max(1, len(notes) - 1)
        a = age_days(n)
        r = 40 if a is None else max(0, 100 - max(0, a - 7) * 100 / 173)
        if n["followers"] is not None:
            ratio = n["likes"] / max(1, n["followers"])
            n["like_fan_ratio"] = round(ratio, 2)
            rep = min(100, ratio * 50)
            n["score"] = round(0.40 * e + 0.25 * r + 0.35 * rep)
            n["low_fan_hit"] = bool((n["followers"] < 5000 and n["likes"] >= 1000) or (ratio >= 1 and n["likes"] >= 300))
        else:
            n["like_fan_ratio"] = None
            n["score"] = round(0.60 * e + 0.40 * r)
            n["low_fan_hit"] = False
        n["angle"] = next((name for name, ws in ANGLES if any(w in n["title"] for w in ws)), None) or \
            next((name for name, ws in ANGLES if any(w in n["desc"][:200] for w in ws)), "其他")
    return sorted(notes, key=lambda x: -x["score"])


def ref(n):
    return "[%s](%s)" % (n["title"][:24], n["url"]) if n["url"] else "「%s」" % n["title"][:24]


def analyze(notes, days, top, insight):
    total_in = len(notes)
    notes = dedupe(notes)
    dropped_old = 0
    if days:
        keep = [n for n in notes if age_days(n) is None or age_days(n) <= days]
        dropped_old = len(notes) - len(keep)
        notes = keep
    if not notes:
        return None
    notes = score(notes)
    n_all = len(notes)
    med = median([eng(n) for n in notes])
    R = {"total_input": total_in, "analyzed": n_all, "dropped_old": dropped_old, "days": days,
         "with_followers": sum(1 for n in notes if n["followers"] is not None),
         "with_date": sum(1 for n in notes if n["date"]), "median_engagement": med,
         "sample_sufficient": n_all >= 20}

    # 角度供给
    angles = []
    for name in [a for a, _ in ANGLES] + ["其他"]:
        g = [n for n in notes if n["angle"] == name]
        if g:
            best = max(g, key=eng)
            m = median([eng(n) for n in g])
            angles.append({"angle": name, "count": len(g), "share": round(len(g) / n_all, 3), "median_engagement": m,
                           "vs_overall": round(m / med, 2) if med else None, "low_fan_hits": sum(1 for n in g if n["low_fan_hit"]),
                           "best": ref(best), "opportunity": bool(len(g) >= 2 and len(g) / n_all <= 0.2 and med and m >= med * 1.2)})
    R["angles"] = sorted(angles, key=lambda x: -x["count"])

    # 标题钩子提升度
    hooks = []
    for name, pat in HOOKS:
        w = [eng(n) for n in notes if re.search(pat, n["title"])]
        wo = [eng(n) for n in notes if not re.search(pat, n["title"])]
        lift = round(median(w) / median(wo), 2) if len(w) >= 5 and len(wo) >= 5 and median(wo) else None
        ex = max((n for n in notes if re.search(pat, n["title"])), key=eng, default=None)
        hooks.append({"hook": name, "used": len(w), "share": round(len(w) / n_all, 3), "lift": lift, "example": ref(ex) if ex else ""})
    R["hooks"] = sorted(hooks, key=lambda x: -(x["lift"] or 0))
    lens = [ci_len(n["title"]) for n in notes]
    R["title_len_median"] = median(lens)
    R["title_keywords"] = [{"word": w, "notes": c} for w, c in ci.keywords([n["title"] for n in notes], ci.load_stopwords(), 12)]

    # 形式
    forms = {}
    for f in ("图文", "视频"):
        g = [eng(n) for n in notes if n["type"] == f]
        if g:
            forms[f] = {"count": len(g), "median_engagement": median(g)}
    R["forms"] = forms
    # 收藏点赞比、评论点赞比（只统计有数据的笔记）：判断内容是被当资料收藏，还是引发讨论
    cl = [n["collects"] / n["likes"] for n in notes if n["likes"] and n["collects"]]
    cm = [n["comments"] / n["likes"] for n in notes if n["likes"] and n["comments"]]
    R["ratios"] = {"collect_like_median": round(median(cl), 2) if cl else None, "comment_like_median": round(median(cm), 2) if cm else None, "n": len(cl)}

    # 需求侧：语料自带评论 + 外部洞察
    embedded = [(c, 0) for n in notes for c in n.get("comment_list", [])]
    demand = None
    if insight:
        demand = insight
    elif len(embedded) >= 5:
        cleaned, seen = [], set()
        for t, l in embedded:
            t = ci.clean(t)
            if len(t) >= 2 and t not in seen:
                seen.add(t)
                cleaned.append((t, l))
        demand = ci.analyse(cleaned)
    gaps = []
    if demand:
        R["demand_comments"] = demand.get("total", 0)
        for name, c in demand.get("pain_clusters", {}).items():
            words = c.get("top_words", [])
            cover = [n for n in notes if any(w in n["title"] or w in n["desc"] for w in words)]
            in_title = [n for n in cover if any(w in n["title"] for w in words)]
            gaps.append({"pain": name, "mentions": c["count"], "words": words, "notes_covering": len(cover),
                         "notes_in_title": len(in_title), "coverage": round(len(cover) / n_all, 3),
                         "quotes": c.get("quotes", [])[:2],
                         "gap": bool(c["count"] >= 3 and len(in_title) / n_all <= 0.1)})
        gaps.sort(key=lambda x: (-x["gap"], -x["mentions"]))
        R["unanswered_questions"] = demand.get("questions_to_answer", [])[:6]
    R["gaps"] = gaps

    R["low_fan_hits"] = [brief(n) for n in notes if n["low_fan_hit"]][:top]
    R["top_notes"] = [brief(n) for n in notes[:top]]

    # 假设候选：每条都对应上面的一个计数结果
    H = []
    for g in gaps:
        if g["gap"]:
            H.append({"basis": "需求缺口", "hypothesis": "以「%s」痛点开头的笔记，评论率和收藏点赞比会高于泛卖点开头" % g["pain"],
                      "evidence": "评论中 %d 条提到，但仅 %d/%d 篇笔记在标题回应" % (g["mentions"], g["notes_in_title"], n_all), "metric": "评论率"})
            break
    for a in R["angles"]:
        if a["opportunity"]:
            H.append({"basis": "角度机会", "hypothesis": "用「%s」角度发布，互动率会高于常见的「%s」角度" % (a["angle"], R["angles"][0]["angle"]),
                      "evidence": "该角度仅占 %.0f%%，互动中位数是整体的 %.1f 倍" % (a["share"] * 100, a["vs_overall"]), "metric": "互动率"})
            break
    for h in R["hooks"]:
        if h["lift"] and h["lift"] >= 1.3:
            H.append({"basis": "标题钩子", "hypothesis": "标题使用「%s」会比不使用的点击率更高" % h["hook"],
                      "evidence": "%d 篇使用，互动中位数是未使用的 %.1f 倍" % (h["used"], h["lift"]), "metric": "点击率"})
            break
    if len(forms) == 2 and min(v["count"] for v in forms.values()) >= 5:
        b = max(forms, key=lambda k: forms[k]["median_engagement"])
        o = "图文" if b == "视频" else "视频"
        if forms[o]["median_engagement"] and forms[b]["median_engagement"] / forms[o]["median_engagement"] >= 1.3:
            H.append({"basis": "内容形式", "hypothesis": "同一角度用%s发布，互动率会高于%s" % (b, o),
                      "evidence": "%s互动中位数 %d，%s %d" % (b, forms[b]["median_engagement"], o, forms[o]["median_engagement"]), "metric": "互动率"})
    R["hypotheses"] = H
    return R


def ci_len(s):
    wide = len(re.findall(r"[^\x00-\x7f]", s))
    return wide + (len(re.findall(r"[\x21-\x7e]", s)) + 1) // 2


def brief(n):
    return {"title": n["title"], "url": n["url"], "author": n["author"], "likes": n["likes"], "collects": n["collects"],
            "comments": n["comments"], "followers": n["followers"], "like_fan_ratio": n["like_fan_ratio"],
            "date": n["date"], "angle": n["angle"], "score": n["score"], "low_fan_hit": n["low_fan_hit"]}


def fmt_note(b):
    fans = "粉丝 %d，赞粉比 %.2f" % (b["followers"], b["like_fan_ratio"]) if b["followers"] is not None else "粉丝未知"
    t = "[%s](%s)" % (b["title"], b["url"]) if b["url"] else "「%s」" % b["title"]
    return "%s｜赞 %d 藏 %d 评 %d｜%s｜%s｜%s｜评分 %d" % (t, b["likes"], b["collects"], b["comments"], fans, b["date"] or "日期未知", b["angle"], b["score"])


def to_markdown(R, topic):
    L = ["# 发布前调研：%s" % (topic or "未命名"), ""]
    L += ["## 数据说明", "",
          "- 输入 %d 篇，去重%s后分析 **%d** 篇；互动中位数 %d（赞 + 2×藏 + 3×评）。" % (R["total_input"], ("并剔除 %d 篇超过 %d 天的旧帖" % (R["dropped_old"], R["days"])) if R["dropped_old"] else "", R["analyzed"], R["median_engagement"]),
          "- 有粉丝数的 %d 篇，有日期的 %d 篇。缺粉丝数的笔记无法判断是否低粉爆款。" % (R["with_followers"], R["with_date"])]
    if not R["sample_sufficient"]:
        L.append("- **样本不足 20 篇**：以下结论只能当线索，不能当结论。请补充更多关键词下的笔记。")
    L += ["- 数据只来自已收集的笔记，存在推广帖和幸存者偏差；所有数字为脚本计数。", ""]

    L += ["## 1. 角度供给：大家都在发什么", "", "| 角度 | 篇数 | 占比 | 互动中位数 | 相对整体(倍) | 低粉爆款 | 代表笔记 | 机会 |", "|---|---|---|---|---|---|---|---|"]
    for a in R["angles"]:
        L.append("| %s | %d | %.0f%% | %d | %s | %d | %s | %s |" % (a["angle"], a["count"], a["share"] * 100, a["median_engagement"], a["vs_overall"] if a["vs_overall"] is not None else "—", a["low_fan_hits"], a["best"], "✅ 供给少互动高" if a["opportunity"] else ""))
    L += ["", "## 2. 标题钩子：哪种写法互动更高", "", "标题长度中位数 %d 字。提升度 = 使用该钩子的互动中位数 ÷ 未使用的；两边各少于 5 篇不计算。" % R["title_len_median"], "",
          "| 钩子 | 使用篇数 | 占比 | 提升度 | 代表标题 |", "|---|---|---|---|---|"]
    for h in R["hooks"]:
        L.append("| %s | %d | %.0f%% | %s | %s |" % (h["hook"], h["used"], h["share"] * 100, ("%.1f 倍" % h["lift"]) if h["lift"] else "样本不足", h["example"]))
    L += ["", "标题高频词：" + ("、".join("%s(%d)" % (k["word"], k["notes"]) for k in R["title_keywords"]) or "无")]
    if R["forms"]:
        L += ["", "形式：" + "；".join("%s %d 篇，互动中位数 %d" % (k, v["count"], v["median_engagement"]) for k, v in R["forms"].items())]

    if R.get("ratios", {}).get("n"):
        L += ["", "收藏点赞比中位数 %s，评论点赞比中位数 %s（%d 篇有数据）。收藏点赞比接近或超过 1 说明被当作资料保存。" % (R["ratios"]["collect_like_median"], R["ratios"]["comment_like_median"], R["ratios"]["n"])]
    L += ["", "## 3. 需求缺口：用户在问、但没人回答的", ""]
    if not R["gaps"]:
        L.append("没有评论数据，无法计算缺口。把竞品笔记的评论区粘贴保存后运行 `comment_insight.py 文件 --json insight.json`，再用 `--insight insight.json` 重跑。")
    else:
        L += ["基于 %d 条评论。缺口 = 评论提及不少于 3 条，且在标题回应它的笔记不超过 10%%。" % R.get("demand_comments", 0), "",
              "| 痛点 | 评论提及 | 正文或标题涉及 | 标题回应 | 判断 | 用户原话 |", "|---|---|---|---|---|---|"]
        for g in R["gaps"]:
            L.append("| %s | %d | %d 篇 | %d 篇 | %s | %s |" % (g["pain"], g["mentions"], g["notes_covering"], g["notes_in_title"], "🎯 缺口" if g["gap"] else ("提及较少" if g["mentions"] < 3 else "已有供给"), " / ".join("“%s”" % q for q in g["quotes"]).replace("|", " ")))
        if R.get("unanswered_questions"):
            L += ["", "评论区高频问题（可直接做选题）："] + ["- " + q for q in R["unanswered_questions"]]

    L += ["", "## 4. 低粉爆款：最值得模仿的", "", "条件：粉丝少于 5000 且点赞过千，或点赞不少于 300 且赞粉比不低于 1。说明靠的是内容而不是账号。", ""]
    L += (["- " + fmt_note(b) for b in R["low_fan_hits"]] or ["- 未发现（或缺少粉丝数据）。"])
    L += ["", "## 5. 综合评分 Top %d" % len(R["top_notes"]), "", "评分 = 互动分位 40% + 时效 25% + 赞粉比 35%（无粉丝数时为互动 60% + 时效 40%）。", ""]
    L += ["%d. %s" % (i + 1, fmt_note(b)) for i, b in enumerate(R["top_notes"])]

    L += ["", "## 6. 发布假设候选", ""]
    if not R["hypotheses"]:
        L.append("数据没有给出足够强的信号。补充笔记或评论后重跑，或由你根据上表提出假设。")
    for i, h in enumerate(R["hypotheses"], 1):
        L += ["%d. **%s**：%s" % (i, h["basis"], h["hypothesis"]), "   - 依据：%s" % h["evidence"], "   - 主指标：%s" % h["metric"]]
    L += ["", "只选一条登记：`python scripts/launch_log.py add --title \"…\" --angle \"…\" --hypothesis \"…\" --evidence \"…\"`"]
    return "\n".join(L)


def cmd_keywords(a):
    sp = lambda s: [x.strip() for x in (s or "").replace("，", ",").replace("、", ",").split(",") if x.strip()]
    c, aud, pains, comps = a.category, sp(a.audience), sp(a.pains), sp(a.competitors)
    G = [("品类基础（看整体供给）", [c + " 推荐", c + " 测评", c + " 怎么选"]),
         ("反面（看真实痛点）", [c + " 避雷", c + " 踩坑", c + " 缺点", c + " 后悔"]),
         ("教程与用法（看使用门槛）", [c + " 教程", c + " 怎么用", c + " 新手"]),
         ("对比与平替（看决策逻辑）", [c + " 对比", c + " 平替"] + ["%s vs %s" % (comps[i], comps[i + 1]) for i in range(len(comps) - 1)][:2]),
         ("人群与场景（找细分入口）", [("%s %s" % (x, c)) for x in aud[:3]]),
         ("竞品（逐个搜，看评论区）", comps[:5] + [x + " 缺点" for x in comps[:2]]),
         ("痛点直搜（验证缺口）", ["%s %s" % (c, p) for p in pains[:4]]),
         ("自家产品（已有口碑）", [a.product, a.product + " 真实测评"] if a.product else [])]
    print("# 搜索关键词矩阵：%s\n" % c)
    n = 0
    for name, ks in G:
        ks = [k for k in ks if k]
        if not ks:
            continue
        print("## %s" % name)
        for k in ks:
            n += 1
            print("%d. %s" % (n, k))
        print()
    print("用法：每个词取综合排序和最新排序的前 10 到 20 篇，至少覆盖「品类基础」「反面」两组；"
          "把结果保存为文件后用 `research.py add 文件 --keyword 该词` 入库。总量达到 30 篇以上再分析。")
    miss = [x for x, v in (("--audience", aud), ("--pains", pains), ("--competitors", comps)) if not v]
    if miss:
        print("\n提示：补充 %s 可以得到更细的关键词。" % " ".join(miss))


def cmd_add(a):
    if not os.path.exists(a.file):
        sys.exit("找不到文件：%s" % a.file)
    try:
        new = read_notes(a.file, a.keyword or "")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        sys.exit("文件解析失败（%s）。请确认是 UTF-8 编码的 json/jsonl/csv/txt。" % e)
    if not new:
        sys.exit("没有识别到笔记。txt 每行一篇，例如：标题 | 赞 1.2万 | 藏 800 | 评 56 | 粉丝 900 | 2026-11-01 | 链接")
    old = load_corpus(a.corpus)
    merged = dedupe(old + new)
    save_corpus(a.corpus, merged)
    print("读取 %d 篇，语料库 %d → %d 篇（已去重）。保存在 %s" % (len(new), len(old), len(merged), a.corpus))
    nf = sum(1 for n in new if n["followers"] is None)
    if nf:
        print("其中 %d 篇没有粉丝数：能补上的话可以识别低粉爆款。" % nf)
    if len(merged) < 20:
        print("当前不足 20 篇，建议继续补充后再 analyze。")


def cmd_status(a):
    notes = load_corpus(a.corpus)
    if not notes:
        print("语料库为空（%s）。先运行 keywords 生成搜索词，再用 add 入库。" % a.corpus)
        return
    kws = {}
    for n in notes:
        kws[n.get("keyword") or "未标注"] = kws.get(n.get("keyword") or "未标注", 0) + 1
    print("语料库 %d 篇｜有粉丝数 %d｜有日期 %d｜自带评论 %d 条" % (len(notes), sum(1 for n in notes if n["followers"] is not None),
          sum(1 for n in notes if n["date"]), sum(len(n.get("comment_list", [])) for n in notes)))
    print("按搜索词：" + "；".join("%s %d" % kv for kv in sorted(kws.items(), key=lambda x: -x[1])))


def cmd_analyze(a):
    notes = load_corpus(a.corpus)
    if not notes:
        sys.exit("语料库为空（%s）。先用 add 入库。" % a.corpus)
    insight = None
    if a.insight:
        if not os.path.exists(a.insight):
            sys.exit("找不到洞察文件：%s" % a.insight)
        with open(a.insight, encoding="utf-8") as f:
            insight = json.load(f)
    R = analyze(notes, a.days, a.top, insight)
    if R is None:
        sys.exit("时间窗内没有笔记，请加大 --days 或用 --days 0 关闭时间窗。")
    md = to_markdown(R, a.topic)
    jpath = a.json or os.path.join(os.path.dirname(os.path.abspath(a.corpus)), "analysis.json")
    os.makedirs(os.path.dirname(os.path.abspath(jpath)), exist_ok=True)
    with open(jpath, "w", encoding="utf-8") as f:   # 供阶段②的 content_plan.py 读取
        json.dump(R, f, ensure_ascii=False, indent=2)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    print(md)


def main():
    ap = argparse.ArgumentParser(description="小红书发布前调研")
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def sp(name, fn):
        s = sub.add_parser(name)
        s.add_argument("--corpus", default=argparse.SUPPRESS)
        s.set_defaults(fn=fn)
        return s

    s = sp("keywords", cmd_keywords)
    s.add_argument("--category", required=True); s.add_argument("--product"); s.add_argument("--audience"); s.add_argument("--pains"); s.add_argument("--competitors")
    s = sp("add", cmd_add)
    s.add_argument("file"); s.add_argument("--keyword")
    sp("status", cmd_status)
    s = sp("analyze", cmd_analyze)
    s.add_argument("--days", type=int, default=90, help="只分析最近 N 天，0 为不限"); s.add_argument("--top", type=int, default=10)
    s.add_argument("--insight"); s.add_argument("--out"); s.add_argument("--json"); s.add_argument("--topic", default="")
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

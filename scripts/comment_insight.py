#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书评论洞察：解析评论 → 意图分布、关注点（吐槽 / 疑问 / 好评）、高频问题、待回复清单。

用法:
  python3 comment_insight.py 评论文件 [更多文件…] [--research | --id L1] [--author 作者昵称] [--detail]
输入（自动识别，不需要手工整理）:
  - 从小红书 App / 网页评论区直接复制的文本（用户名、评论、时间属地、赞、回复 各占一行；作者回复会单独分出来）
  - 每行一条评论的文本；「昵称：评论」；Markdown 表格
  - csv / tsv（含 评论 / 内容 / content 列）；json（字符串数组，或含 content 字段的对象）
  - UTF-8 和 GBK 都可以；文件名写 - 表示从标准输入读
保存:
  --research  存为调研用的洞察（research.py analyze 会自动读取）
  --id L1     存为发布 L1 的反馈洞察（launch_log.py verdict 会自动读取）
  --json 路径 存到指定位置
词表: assets/ 里是通用词表；品类特有的词写进 数据目录/lexicon.json（自动加载），或用 --lexicon 指定。
只依赖 Python 3 标准库。所有条数由脚本计数。
"""
import argparse, json, math, os, re, sys
from collections import Counter, OrderedDict, defaultdict

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

MIN_COMMENTS = 20     # 少于这个数，结论只能当线索
MIN_MENTIONS = 3      # 少于这个数，不算一个痛点
TEXT_KEYS = ["评论内容", "评论", "内容", "content", "comment", "text", "comment_content", "note_comment"]
LIKE_KEYS = ["点赞数", "点赞", "赞", "likes", "like_count", "liked_count", "like"]
USER_KEYS = ["用户", "用户名", "昵称", "作者", "nickname", "user_name", "username", "user", "name"]
LABEL = {"C": "吐槽", "Q": "疑问", "P": "好评", "M": "提及"}

# ---------- 语法规则（与品类无关） ----------
CJK = "一-鿿"
MASK_CH = "\ue000"   # 私用区字符，用来遮住易混词
D_FILL = r"(?:也|还|真的?|是真|确实|实在|简直|都|就|有点|有些|比较|非常|特别|十分|相当|很|太|好|挺|蛮|超|巨|贼|略|稍|偏|过于|会|是|的|得)*"
DEG = (r"(?:太|好|很|挺|蛮|超级?|巨|真的?|真心|特别|非常|十分|有点儿?|有些|有一点|略微?|稍微?|偏|比较|那么|这么|贼|过于|更|最|越来越|又|也|还|都|实在|确实|简直"
       r"|相当|格外|怪|忒|齁|属实|死)$")
LIC = (r"(?:感觉|觉得|用着|用起来|涂着|涂上|涂完|涂起来|摸着|摸起来|吃着|吃起来|喝着|喝起来|闻着|闻起来|看着|看起来|穿着|穿上|穿起来|戴着|戴上|戴久了|用久了|穿久了"
       r"|上脸|上手|上身|上嘴|入口|会|就是|只是|可是|但是|但|还是|显得|变|发|除了|可惜|嫌|虽然|缺点是|缺点就是|问题是|毛病是|的确|而且|依然|依旧|仍然|略显|稍显|一直|老是|总是|有时候?)$")
EXCESS = r"(?:太|过于|过|偏|有点儿?|有些|有一点|略微?|稍微?|齁|忒)$"
NEG_PRE = (r"(?:不|没有?|无|未|(?<![特区分个告性级类差识鉴辨])别|甭)(?:会|是|算|太|很|怎么|咋|大|用|再|显|觉得|感觉|至于|那么|这么|是很|是太|会太|会很|算太|算很|会觉得|是特别|是那么|够"
           r"|(?:想象|传说|说|预期|以为|别人说|网上说)[中的]{0,2}(?:那么|这么)?)?$")
# 祈使句里的否定不是在夸：「别再涨价」是已经涨过（吐槽），「千万别漏」「希望别那么油」是担心（疑问）
IMPER = r"(?:(?<![特区分个告性级类差识鉴辨])别|甭|不要|勿)(再|又|老是?|总是?|一直)?(?:太|那么|这么)?$"
POST_STRONG = r"(?:死了?|爆了?|炸了?|哭了?|麻了|吐了|到不行|得不行|得很|得要命|得要死|得离谱|到离谱|得慌|得一批|到爆|到哭|得不得了|极了|透了|疯了)"
POST_DE = r"得(?!有道理|有理由|值|其所|刚好|刚刚好|恰到好处|合理|体|当)."      # 苦得像中药、卡得想砸手机：带补语，算吐槽；贵得有道理不算
POST_WEAK = r"(?:了|啊|呀|哦|吧|呢|嘛|吗|么|诶|哈|啦|哇|点|些|一点)*"
WEAK_PRE = r"(?:这个?|这款|它|那个?|东西|产品|这东西|这玩意)?"
POST_NEG = r"(?:几乎|基本|完全|其实|倒是|倒|也|都|并)?(?:不大|不明显|很小|不严重|还好|能接受|可以接受|不算|不存在|没有|不多|很少|不怎么|不太)"
# 形容词后面只能跟语气词、补语或句子结束：「好贵啊」「贵得离谱」「太贵买不起」算，「好苦恼」「太重要」不算
ADJ_POST = re.compile(r"$|[^%s]|[了的啊呀哦吧呢嘛哈啦哇诶点些得到死爆炸哭麻吐极透疯又还也且但却而就不没吗么呗嘞咯喔耶额呃欸啥]|一点|一些|[%s]不" % (CJK, CJK))
A_NOT_A = [(re.compile(r"([%s]{2})[不没]\1" % CJK), r"\1"), (re.compile(r"([%s])[不没]\1" % CJK), r"\1"), (re.compile(r"有没有|有无|有木有"), "有")]
# 「黏不黏主要看用量」「贵不贵不重要」是在下判断，不是在问
A_NOT_A_STMT = re.compile(r"(?:主要|完全|全|就|得|都|还是|还得|要)(?:看|取决)|取决于|在于|不重要|无所谓|另说|两说|因人而异|看个人|看人")
Q_STRIP = re.compile(r"没啥|没什么|不怎么|不咋|什么都|什么也|啥都|啥也|哪怕|哪里都|哪儿都|哪都|谁懂|谁用谁|谁买谁|无论什么|不管什么|没多久|不多久|多少有点|多少有些|怎么都|怎么也|再怎么")
Q_WORD = re.compile(r"吗|嘛$|(?<![这那多要怎什])么$|多少|哪|谁|怎么|咋|如何|为什么|为啥|为何|是否|请问|求问|想问|问一下|问下|请教|能否|可否|啥|什么|多久|多大|多重|多高|多长|多厚|几[号码岁点时]"
                    r"|同问|同求|求解|求答|真的假的|蹲(?:个|一个)?(?:回复|答案|后续|解答)|(?:行|能|可以|对|好|有|是|会|用|买|吃|喝)不$")
RHETORIC = re.compile(r"怎么这么|怎么那么|为什么这么|为什么那么|为啥这么|为啥那么|也太|未免太|凭什么|至于吗|有必要吗|好意思")
CONCERN = re.compile(r"听说|据说|(?<![可哪害恐])怕|担心|不知道|想知道|好奇|有人说|网上说|看评论说|纠结|犹豫")
# 「求平价的」「想找不油的」是在要东西，后面跟着的好评词不算夸；「求求别涨价」「要求」「追求」不算
SEEK = re.compile(r"求(?:推荐|安利|链接|教程|分享|同款|地址|店|出|带|问|助|科普|避雷|解答|告知)|有[^，。]{0,10}(?:推荐|平替|同款|类似|替代)吗?|推荐(?:一下|下|个|几个|点|些)|能推荐|有推荐|求一个|跪求|在线等|蹲蹲|蹲一个"
                  r"|(?<![要请追需寻谋祈乞恳哀苛讲力强征渴应求])求(?![求你您别不放改生职婚学之人己])|想找|在找")
TAI_OK = re.compile(r"^(?:[好有可想爱喜会懂棒赞美帅酷香萌强牛绝值顶稳准全妙神真像巧搞逗]|需要|及时|幸福|治愈|解压|上头|心动|感动|惊喜|惊艳|满意|开心|快乐|高级|漂亮|精致|温柔|丝滑|清爽|方便|舒服|划算|便宜|实用|厉害|优秀|贴心|良心|详细|用心|走心)")
CLAUSE = re.compile(r"([，,。！!？?~～…；;\n]+|\s+)")
ORDER = "CQPM"   # 一条评论对一个维度只算一种态度：吐槽 > 疑问 > 好评 > 提及
TRUST = "信任与真实性"   # 这个维度的吐槽单独算「质疑广告」，不算产品痛点


def _rx(term):
    """词表里的一项 → 正则源码。re: 开头是正则；{D} 是可有可无的程度词，{W3} 是最多 3 个不含否定词的字。"""
    if not term.startswith("re:"):
        return re.escape(term.lower())
    return re.sub(r"\{W(\d)\}", lambda m: "[^不没无别未]{0,%s}" % m.group(1), term[3:].replace("{D}", D_FILL))


def _compile(terms):
    terms = [t for t in terms if isinstance(t, str) and t]
    if not terms:
        return None
    plain = sorted((t for t in terms if not t.startswith("re:")), key=len, reverse=True)
    src = [_rx(t) for t in terms if t.startswith("re:")] + [_rx(t) for t in plain]
    try:
        return re.compile("|".join("(?:%s)" % s for s in src))
    except re.error:
        for t in terms:
            try:
                re.compile(_rx(t))
            except re.error as e:
                sys.exit("词表里这一项的正则写错了：%s（%s）" % (t, e))
        raise


def load_json_asset(name):
    with open(os.path.join(C.ASSETS, name), encoding="utf-8") as f:
        return json.load(f)


def load_stopwords():
    with open(os.path.join(C.ASSETS, "stopwords.txt"), encoding="utf-8") as f:
        return set(f.read().split())


def _merge_lex(base, extra, src):
    """把项目词表并进通用词表（格式见 references/feedback.md）。返回改动的词数。"""
    n = 0
    asp = extra.get("aspects") or {}
    if not isinstance(asp, dict):
        sys.exit("词表 %s 里的 aspects 应该是 {\"维度名\": {\"neg\": [...], \"pos\": [...]}} 这样的对象。" % src)
    for name, d in asp.items():
        if not isinstance(d, dict):
            sys.exit("词表 %s 里 aspects.%s 应该是 {\"neg\": [...], \"pos\": [...], \"topic\": [...]} 这样的对象。" % (src, name))
        tgt = base["aspects"].setdefault(name, {"neg": [], "pos": [], "good": [], "topic": [], "adj": "", "too": ""})
        for k in ("neg", "pos", "good", "topic"):
            add = [w for w in d.get(k) or [] if isinstance(w, str) and w and w not in tgt[k]]
            tgt[k] = tgt[k] + add
            n += len(add)
        for k in ("adj", "too"):
            add = "".join(ch for ch in "".join(d.get(k) or "") if ch not in tgt[k])
            tgt[k] += add
            n += len(add)
    for name, ws in (extra.get("intents") or {}).items():
        tgt = base["intents"].setdefault(name, [])
        add = [w for w in ws if isinstance(w, str) and w and w not in tgt]
        tgt += add
        n += len(add)
    spam = extra.get("spam") or {}
    for name, ws in (spam.items() if isinstance(spam, dict) else [("自定义", spam)]):
        tgt = base["spam"].setdefault(name, [])
        add = [w for w in ws if isinstance(w, str) and w and w not in tgt]
        tgt += add
        n += len(add)
    for k in ("positive", "negative", "mask"):
        add = [w for w in extra.get(k) or [] if isinstance(w, str) and w and w not in base[k]]
        base[k] = base[k] + add
        n += len(add)
    gone = set(w for w in extra.get("remove") or [] if isinstance(w, str))
    if gone:   # 通用词表里在这个品类会误判的词
        for d in base["aspects"].values():
            for k in ("neg", "pos", "good", "topic"):
                n += len([w for w in d[k] if w in gone])
                d[k] = [w for w in d[k] if w not in gone]
            for k in ("adj", "too"):
                n += len([ch for ch in d[k] if ch in gone])
                d[k] = "".join(ch for ch in d[k] if ch not in gone)
        for k in ("positive", "negative"):
            n += len([w for w in base[k] if w in gone])
            base[k] = [w for w in base[k] if w not in gone]
        for grp in (base["intents"], base["spam"]):
            for name in grp:
                n += len([w for w in grp[name] if w in gone])
                grp[name] = [w for w in grp[name] if w not in gone]
    return n


class Lexicon:
    """通用词表 + 项目词表，编译成匹配器。"""

    def __init__(self, extra_paths=()):
        il = load_json_asset("intent_lexicon.json")
        pl = load_json_asset("pain_lexicon.json")
        self.raw = {"aspects": OrderedDict((k, dict(v)) for k, v in pl.items() if not k.startswith("_")),
                    "intents": OrderedDict((k, list(v)) for k, v in il["intents"].items()), "positive": list(il["positive"]),
                    "negative": list(il["negative"]), "mask": list(il["mask"]), "spam": OrderedDict((k, list(v)) for k, v in il["spam"].items())}
        self.loaded = []
        for p in extra_paths:
            if p and os.path.exists(p):
                extra = C.read_json(p)
                if not isinstance(extra, dict):
                    sys.exit("词表 %s 应该是一个 JSON 对象。" % C.where(p))
                self.loaded.append((p, _merge_lex(self.raw, extra, p)))
        r = self.raw
        self.mask = _compile(r["mask"])
        self.intents = OrderedDict((k, _compile(v)) for k, v in r["intents"].items())
        self.pos, self.neg = _compile(r["positive"]), _compile(r["negative"])
        self.spam = OrderedDict((k, _compile(v)) for k, v in r["spam"].items())
        self.aspects = OrderedDict()
        for name, d in r["aspects"].items():
            self.aspects[name] = {k: _compile(d.get(k) or []) for k in ("neg", "pos", "good", "topic")}
            self.aspects[name].update(adj=set(d.get("adj") or ""), too=set(d.get("too") or ""))
        self.adj_of = {ch: name for name, a in self.aspects.items() for ch in a["adj"]}
        self.too_of = {ch: name for name, a in self.aspects.items() for ch in a["too"]}

    # ----- 单条评论 -----
    def spam_kind(self, text):
        t = text.lower()
        for kind, rx in self.spam.items():
            if rx and rx.search(t):
                return kind
        return None

    def analyse(self, text):
        """返回 {"intents": [...], "aspects": {维度: (C|Q|P|M, [命中词])}, "loose": [未归入维度的「太X了」]}"""
        t = text.lower()
        m = self.mask.sub(lambda x: MASK_CH * len(x.group(0)), t) if self.mask else t
        found, loose = OrderedDict(), []
        g_c = g_p = asked = False
        parts, raws = CLAUSE.split(m) + [""], CLAUSE.split(t) + [""]
        for i in range(0, len(parts) - 1, 2):
            c, delim, raw = parts[i], parts[i + 1], raws[i]
            if not c:
                continue
            anot = False
            for rx, rep in A_NOT_A:
                c2 = rx.sub(rep, c)
                if c2 != c:
                    anot, c = True, c2
            rh = bool(RHETORIC.search(raw))
            mark = "?" in delim or "？" in delim
            if anot and not mark and A_NOT_A_STMT.search(raw):
                anot, c = False, parts[i]
                for rx, _ in A_NOT_A:                          # 整个「X不X」遮掉，免得里面的词被当成好评或吐槽
                    c = rx.sub(lambda x: MASK_CH * len(x.group(0)), c)
            q_word = anot or bool(Q_WORD.search(Q_STRIP.sub("", raw)))
            res, excess, tai = self._clause(c, (q_word or mark) and not rh)
            q = (q_word or (mark and not excess)) and not rh
            asked = asked or q
            soft = q or bool(SEEK.search(raw)) or bool(CONCERN.search(raw))
            for name, (pol, words) in res.items():
                if name is None:
                    if not soft:
                        g_c, g_p = g_c or pol == "C", g_p or pol == "P"
                    continue
                lab = "Q" if (soft and pol != "M") or (q and pol == "M") else pol
                found.setdefault(name, {}).setdefault(lab, []).extend(words)
            if not soft:
                loose += tai
        aspects = OrderedDict()
        for name, labs in found.items():
            top = min(labs, key=ORDER.index)
            aspects[name] = (top, labs.get("C", []) + labs.get("Q", []) if top in "CQ" else labs[top])
        intents = []
        if asked:
            intents.append("提问")
        if g_c or any("C" in labs for name, labs in found.items() if name != TRUST):
            intents.append("痛点吐槽")
        if g_p or any("P" in labs for labs in found.values()):
            intents.append("好评认可")
        for name, rx in self.intents.items():
            if rx and rx.search(t):
                intents.append(name)
        if "C" in found.get(TRUST, {}) and "质疑广告" in self.intents and "质疑广告" not in intents:
            intents.append("质疑广告")
        return {"intents": intents or ["其他"], "aspects": aspects, "loose": loose}

    def _clause(self, c, asking=False):
        """一个分句里的命中。返回 ({维度或 None: (态度, [词])}, 有没有「太…了」这类过量表达, 没归入维度的过量词)"""
        hits = []   # (start, end, 维度, 类别, 词)
        for name, a in self.aspects.items():
            for kind in ("neg", "pos", "good", "topic"):
                if a[kind]:
                    hits += [(x.start(), x.end(), name, kind, x.group(0)) for x in a[kind].finditer(c) if x.end() > x.start()]
        for kind, rx in (("neg", self.neg), ("pos", self.pos)):
            if rx:
                hits += [(x.start(), x.end(), None, kind, x.group(0)) for x in rx.finditer(c) if x.end() > x.start()]
        # 重叠时保留更长的；一样长时 具体维度 > 通用词，吐槽 > 好评 > 功能词 > 话题。同一维度的话题词可以和别的词重叠。
        rank = {"neg": 0, "pos": 1, "good": 2, "topic": 3}
        hits.sort(key=lambda h: (-(h[1] - h[0]), h[2] is None, rank[h[3]], h[0]))
        kept = []
        for h in hits:
            if not any(h[0] < k[1] and k[0] < h[1] and not (h[2] == k[2] and (h[3] == "topic") != (k[3] == "topic")) for k in kept):
                kept.append(h)
        covered = set()
        for h in kept:
            if h[3] != "topic":
                covered.update(range(h[0], h[1]))
        topics = sorted((h for h in kept if h[3] == "topic"), key=lambda h: h[0])
        anchors = [h for h in kept if h[3] in ("topic", "good")]   # 通用好评 / 吐槽词可以挂靠的词
        topic_ends = {h[1] for h in topics}
        out, gens, excess = {}, [], False

        def put(name, pol, word):
            cur = out.setdefault(name, ["M", []])
            if ORDER.index(pol) < ORDER.index(cur[0]):
                cur[0] = pol
            cur[1].append(word)

        def owner(pos, own):
            """形容词归到它前面最近的话题词所属的维度（发货好慢 → 购买与售后）；没有话题词就用它自己的维度。"""
            cand = [h for h in topics if h[1] <= pos] or topics
            if not cand or any(h[2] == own for h in cand):
                return own
            return max(cand, key=lambda h: h[1])[2]

        for s, e, name, kind, w in kept:
            pre, post = c[:s], c[e:]
            negated = bool(re.search(NEG_PRE, pre)) and not w.startswith(("不", "没", "无"))
            imp = re.search(IMPER, pre)
            if kind == "topic":
                put(name, "M", w)
            elif imp and name is None:
                if kind == "neg":
                    gens.append((s, e, "C", w))
            elif imp:
                put(name, "C" if imp.group(1) and kind == "neg" else "Q", w)
            elif kind == "good":
                put(name, "C" if negated else ("P" if re.search(DEG, pre) else "M"), ("不" + w) if negated else w)
            elif name is None:
                if kind == "neg" and pre.endswith(("到", "得")):     # 好吃到不行、贵得离谱：是程度补语，不是吐槽
                    continue
                if kind == "pos" and pre.endswith("才"):             # 洗完手才舒服：有条件，不算好评
                    continue
                flip = negated or (kind == "neg" and bool(re.match(POST_NEG, post)))
                gens.append((s, e, ("P" if flip else "C") if kind == "neg" else ("C" if flip else "P"), ("不" + w) if flip else w))
            elif kind == "neg":
                flip = negated or bool(re.match(POST_NEG, post))
                put(name, "P" if flip else "C", ("不" + w) if flip else w)
            else:
                if pre.endswith("才"):
                    continue
                put(name, "C" if negated else "P", ("不" + w) if negated else w)
        for i, ch in enumerate(c):
            if i in covered or (ch not in self.adj_of and ch not in self.too_of):
                continue
            pre, post = c[:i], c[i + 1:]
            if not ADJ_POST.match(post):
                continue
            negated = bool(re.search(NEG_PRE, pre))
            deg = re.search(DEG, pre)
            bare = bool(re.fullmatch(WEAK_PRE, pre) and re.fullmatch(POST_WEAK, post))
            imp = re.search(IMPER, pre)
            if imp:
                put(owner(i, self.adj_of.get(ch) or self.too_of[ch]), "C" if imp.group(1) and ch in self.adj_of else "Q", ch)
            elif ch in self.adj_of:
                own = self.adj_of[ch]
                if negated:
                    put(owner(i, own), "P", "不" + ch)
                elif deg and deg.group(0) in ("最", "更") and post.startswith("的"):
                    continue                                         # 最贵的那款：只是在指代
                elif (deg or re.search(LIC, pre) or i in topic_ends or re.match(POST_STRONG, post) or re.match(POST_DE, post) or pre.endswith(ch) or bare
                      or re.match(r"了(?:点|些|一点|一丢丢)", post)):
                    if re.match(POST_NEG, post):
                        put(owner(i, own), "P", "不" + ch)
                    else:
                        excess = excess or bool(re.search(EXCESS, pre)) or bool(re.match(POST_STRONG, post))
                        put(owner(i, own), "C", (deg.group(0) if deg else "") + ch)
            else:
                own = self.too_of[ch]
                ex = re.search(EXCESS, pre)
                if pre.endswith("不够"):
                    put(owner(i, own), "C", "不够" + ch)
                elif negated:
                    put(owner(i, own), "M", "不" + ch)
                elif ex or re.match(r"了(?:点|些|一点|一丢丢)", post):
                    excess = True
                    put(owner(i, own), "C", (ex.group(0) + ch) if ex else (ch + "了点"))
                elif (deg and topics) or (asking and (bare or i in topic_ends)):
                    put(owner(i, own), "M", ch)
        # 「太X了」「不够X」里的 X 不在词表：分句里有话题词就记到那个维度，没有就只作为线索返回
        tai = []
        for x in re.finditer(r"(太|不够)([%s]{1,2}?)(?:了|啦|$|(?=%s))" % (CJK, MASK_CH), c):
            if any(p in covered for p in range(x.start(), x.end())) or x.group(2)[0] in self.adj_of or x.group(2)[0] in self.too_of:
                continue
            if x.group(1) == "太" and (TAI_OK.match(x.group(2)) or not c[x.end(2):].startswith(("了", "啦"))):
                continue
            excess = True
            if topics:
                put(owner(x.start(), topics[0][2]), "C", x.group(1) + x.group(2))
            else:
                tai.append(x.group(1) + x.group(2))
        # 通用好评 / 吐槽词：紧跟在话题词后面（或「不错的味道」这样紧贴在前面）时，算到那个话题头上
        for s, e, pol, w in gens:
            near = [h for h in anchors if 0 <= s - h[1] <= 3 or (h[0] >= e and c[e:h[0]] == "的")]
            put(min(near, key=lambda h: abs(s - h[1]))[2] if near else None, pol, w)
        return {k: (v[0], v[1]) for k, v in out.items()}, excess, tai


# ---------- 读取与解析 ----------

DATE_INLINE = re.compile(r"\s+(?:编辑于\s*)?%s(?:\s*[%s]{2,7})?(?:\s*回复)?\s*$" % (C.DATE, CJK))
UI_SURE = re.compile(r"^(?:共\s*\d+\s*条评论|全部评论|评论\s*\d+|说点什么.*|加载中.*|查看更多.*|展开更多.*|没有更多.*|到底了.*|已经到底.*|-+\s*the end\s*-+|the end"
                     r"|展开\s*\d+\s*条回复|查看\s*\d+\s*条回复|查看全部\s*\d+\s*条回复|共\s*\d+\s*条回复.*|收起回复|收起)$", re.I)
TAGS = {"作者": "author", "置顶评论": "pinned", "置顶": "pinned", "作者赞过": "liked", "作者回复过": "replied", "首评": "first", "你的关注": "", "朋友": ""}
LIKE_KW = re.compile(r"^(?:赞|点赞|喜欢|[♡❤♥👍]️?)\s*[:：]?\s*(%s)?$|^(%s)\s*(?:赞|点赞)$" % (C.COUNT, C.COUNT))
REPLY_KW = re.compile(r"^(?:回复|评论)\s*(?:%s)?$|^(?:%s)\s*(?:条)?回复$" % (C.COUNT, C.COUNT))
NUM_ONLY = re.compile(r"^%s$" % C.COUNT)


def clean(t):
    """去掉表情代码、@、回复前缀、行尾的时间属地。"""
    t = re.sub(r"\[[^\]\s]{1,8}R?\]", "", str(t))
    t = re.sub(r"^\s*回复\s*@?[^:：\s]{1,20}\s*[:：]\s*", "", t)
    t = re.sub(r"@[^\s@，,。:：]{1,20}", " ", t)
    t = DATE_INLINE.sub("", " " + t)
    return re.sub(r"\s+", " ", t).strip()


def _is_meta(s):
    return bool(LIKE_KW.match(s) or REPLY_KW.match(s) or NUM_ONLY.match(s) or UI_SURE.match(s) or s in TAGS)


def _block(lines, with_user, author):
    """一块（时间行之前的几行）→ 评论 dict。lines 已去掉空行。"""
    flags = {TAGS[l] for l in lines if l in TAGS}
    texts = [l for l in lines if l not in TAGS and not UI_SURE.match(l)]
    user = ""
    if with_user and texts:
        user, texts = texts[0], texts[1:]
        m = re.fullmatch(r"(.+?)\s+作者", user)
        if m:
            user, flags = m.group(1), flags | {"author"}
    if author and user and user.strip() == author.strip():
        flags.add("author")
    return {"text": " ".join(texts), "user": user, "likes": 0, "author": "author" in flags, "lines": len(texts)}


def parse_blocks(lines, author=""):
    """App / 网页复制的评论块。返回 (评论列表, 说明) 或 None（不是块格式）。"""
    n = len(lines)
    dates = [i for i, l in enumerate(lines) if C.is_date_line(l, lines[i + 1] if i + 1 < n else "")]
    kw = [i for i, l in enumerate(lines) if (LIKE_KW.match(l) and not NUM_ONLY.match(l)) or REPLY_KW.match(l)]
    texts = [l for i, l in enumerate(lines) if i not in set(dates) and not _is_meta(l)]
    few = bool(dates) and len(dates) >= len(texts) * 0.2 and not [l for l in lines[dates[-1] + 1:] if not _is_meta(l)]
    if len(dates) >= 3 or few:       # 只贴了一两条也按评论块读（单独成行的时间不可能是评论），前提是每条评论后面都有时间行
        anchors, mode = set(dates), "时间行"
    elif len(kw) >= 3 and len(kw) >= n * 0.15:
        anchors, mode = set(kw), "赞/回复行"
    else:
        return None
    raw, cur, i, tail = [], [], 0, 0
    while i < n:
        if i in anchors and (cur or mode == "时间行"):
            likes, j = None, i + (1 if mode == "时间行" else 0)
            while j < n and j not in dates and _is_meta(lines[j]) and not (mode != "时间行" and j != i and j in anchors and False):
                mk = LIKE_KW.match(lines[j])
                v = C.num(mk.group(1) or mk.group(2)) if mk else (C.num(lines[j]) if NUM_ONLY.match(lines[j]) else None)
                if likes is None and v is not None and not REPLY_KW.match(lines[j]):
                    likes = v
                j += 1
            raw.append((cur, likes or 0))
            cur, i = [], max(j, i + 1)
        else:
            cur.append(lines[i])
            i += 1
    tail = len([l for l in cur if not UI_SURE.match(l) and l not in TAGS])
    sizes = [len([l for l in b if l not in TAGS and not UI_SURE.match(l)]) for b, _ in raw]
    multi = sum(1 for s in sizes if s >= 2)
    with_user = multi >= max(1, len(sizes) * 0.5)
    out = []
    for b, likes in raw:
        cmt = _block(b, with_user, author)
        cmt["likes"] = likes
        out.append(cmt)
    info = {"format": "从 App / 网页复制的评论块（%s，按%s分隔）" % ("用户名 + 评论" if with_user else "只有评论，没有用户名", mode), "warnings": []}
    odd = sum(1 for s in sizes if s > 3) if with_user else sum(1 for s in sizes if s > 2)
    if tail:
        info["warnings"].append("末尾有 %d 行后面没有时间行，没有计入（可能是复制时截断了最后一条）。" % tail)
    if odd > max(1, len(sizes) * 0.2):
        info["warnings"].append("有 %d 块的行数比别的多，可能是几条评论粘在了一起，或者评论本身有换行。请核对条数。" % odd)
    if not with_user and multi:
        info["warnings"].append("多数块只有一行，按「没有用户名」处理；如果第一行其实是用户名，请用每行一条的格式重贴。")
    return out, info


def parse_lines(lines):
    """每行一条。识别「昵称：评论」，丢掉明显的界面文字。"""
    info = {"format": "每行一条评论", "warnings": []}
    rows = [l for l in lines if not UI_SURE.match(l)]
    ui = lambda l: bool(REPLY_KW.match(l) or (LIKE_KW.match(l) and l not in ("赞", "喜欢")) or C.is_date_line(l) or l in TAGS)   # 单独一个「赞」可能就是评论
    meta = sum(1 for l in rows if ui(l))
    rows = [l for l in rows if not ui(l)]
    if meta >= max(2, len(rows) * 0.2):
        info["warnings"].append("有 %d 行像是时间、点赞数或「回复」按钮，但没能按评论块识别。这些行已剔除，条数可能不准，请对照原文核对。" % meta)
    named = [re.match(r"^([^:：\s，,。？?！!]{1,16})\s*[:：]\s*(\S.*)$", l) for l in rows]
    hit = [x for x in named if x]
    out = []
    if len(rows) >= 4 and len(hit) >= len(rows) * 0.7 and len({x.group(1) for x in hit}) >= max(2, len(hit) * 0.5):
        info["format"] = "每行一条「昵称：评论」"
        for l, x in zip(rows, named):
            out.append({"text": x.group(2) if x else l, "user": x.group(1) if x else "", "likes": 0, "author": False})
    else:
        seq = [re.match(r"^\s*(\d{1,3})\s*[.、)）]\s*(?=\D)", l) for l in rows]
        nums = [int(x.group(1)) for x in seq if x]
        strip = len(nums) >= 3 and len(nums) >= len(rows) * 0.6 and sum(1 for a, b in zip(nums, nums[1:]) if b == a + 1) >= (len(nums) - 1) * 0.6
        for l, x in zip(rows, seq):
            l = re.sub(r"^\s*[-*•·]\s+", "", l[x.end():] if (strip and x) else l)
            out.append({"text": l, "user": "", "likes": 0, "author": False})
    return out, info


COMMENT_LISTS = ("comments", "comment_list", "sub_comments", "replies", "children", "评论", "评论列表", "子评论")
CONTAINERS = ("data", "items", "list", "notes", "note_list", "笔记", "result", "results")
NOTE_KEYS = ("title", "标题", "note_id", "desc", "display_title")


def _from_json(data, out, author, as_comments=True):
    """从 JSON 里取评论：字符串数组、评论对象数组，或者「笔记 → comments」这样的嵌套导出。笔记自己的正文不算评论。"""
    if isinstance(data, dict):
        data, as_comments = [data], False
    for it in data if isinstance(data, list) else []:
        if isinstance(it, str):
            if as_comments:
                out.append({"text": it, "user": "", "likes": 0, "author": False})
            continue
        if not isinstance(it, dict):
            continue
        is_note = any(k in it for k in NOTE_KEYS) or any(isinstance(it.get(k), list) for k in COMMENT_LISTS[:2] + COMMENT_LISTS[5:7])
        if as_comments and not is_note and any(k.lower() in [str(x).lower() for x in it] for k in TEXT_KEYS):
            user = it.get("user_info") or it.get("user") or {}
            name = C.pick(user, ["nickname", "name", "nick_name"]) if isinstance(user, dict) else (user if isinstance(user, str) else "")
            name = name or C.pick(it, USER_KEYS[:-2]) or ""
            tags = it.get("show_tags") or []
            is_author = bool(it.get("is_author")) or "is_author" in tags or bool(author and name == author)
            text = C.pick(it, TEXT_KEYS)
            out.append({"text": "" if text is None else str(text), "user": str(name), "likes": C.num(C.pick(it, LIKE_KEYS)) or 0, "author": is_author})
        for k in COMMENT_LISTS:
            if isinstance(it.get(k), list):
                _from_json(it[k], out, author, True)
        for k in CONTAINERS:
            if isinstance(it.get(k), (list, dict)):
                _from_json(it[k], out, author, as_comments and not is_note)


def read_comments(path, author=""):
    """读一个评论文件，返回 (评论 dict 列表, 说明)。"""
    text, enc = C.read_text(path)
    ext = os.path.splitext(path)[1].lower()
    info = {"format": "", "warnings": [], "encoding": enc}
    out = []
    if ext in (".json", ".jsonl"):
        try:
            data = [json.loads(l) for l in text.splitlines() if l.strip()] if ext == ".jsonl" else json.loads(text)
        except ValueError as e:
            sys.exit("%s 不是合法的 JSON（%s）。" % (path, e))
        _from_json(data, out, author)
        info["format"] = "JSON"
    else:
        rows = C.table_rows(text, ext)
        if rows and any(C.pick(r, TEXT_KEYS) for r in rows):
            for r in rows:
                name = str(C.pick(r, USER_KEYS) or "")
                out.append({"text": str(C.pick(r, TEXT_KEYS) or ""), "user": name, "likes": C.num(C.pick(r, LIKE_KEYS)) or 0,
                            "author": bool(author and name == author) or str(C.pick(r, ["是否作者", "is_author"]) or "").strip() in ("是", "1", "true", "True", "作者")})
            info["format"] = "表格（%d 行，评论列：%s）" % (len(rows), next(k for k in rows[0] if k and str(k).strip().lower() in [x.lower() for x in TEXT_KEYS]))
        else:
            if rows or ext in (".csv", ".tsv"):
                info["warnings"].append("表格里没有找到评论列（评论 / 内容 / content）。已把每一行当作一条评论，请确认表头。")
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            got = parse_blocks(lines, author) or parse_lines(lines)
            out, info2 = got
            info.update(format=info2["format"], warnings=info["warnings"] + info2["warnings"])
    if enc != "UTF-8":
        info["format"] += "，编码 %s" % enc
    return out, info


def prepare(raw, lex, sources=1):
    """清洗、去重、分出作者回复和无关评论。返回 (有效评论 [(text, likes)], 统计)。"""
    stat = {"raw": len(raw), "author_replies": [], "spam": defaultdict(list), "no_text": 0, "duplicates": 0}
    seen, out = set(), []
    for c in raw:
        t = clean(c["text"])
        if len(re.sub(r"[\W_]+", "", t)) < 1:
            stat["no_text"] += 1
            continue
        if c.get("author"):
            stat["author_replies"].append(t)
            continue
        key = (c.get("user") or "", t)
        if key in seen and (c.get("user") or len(t) >= 8):   # 同一个人的同一句，或很长的同一句：重复粘贴
            stat["duplicates"] += 1
            continue
        seen.add(key)
        kind = lex.spam_kind(c["text"])
        if kind:
            stat["spam"][kind].append(t)
            continue
        out.append((t, c.get("likes") or 0))
    return out, stat


# ---------- 统计 ----------

def keywords(texts, stop, top):
    """无分词依赖的中文关键词：统计 2 到 6 字片段出现在多少条里，去掉停用词和被更长片段覆盖的片段。"""
    df = Counter()
    for t in texts:
        grams = OrderedDict()       # 按出现顺序记，保证次数相同的词每次运行排在同样的位置
        for seg in re.findall(r"[一-鿿]+|[A-Za-z][A-Za-z0-9]+", t):
            if re.match(r"[A-Za-z]", seg):
                grams[seg.lower()] = 1
                continue
            for n in (2, 3, 4, 5, 6):
                for i in range(len(seg) - n + 1):
                    g = seg[i:i + n]
                    if g in stop or g[0] in stop and g[-1] in stop:
                        continue
                    if any(ch in "的了吗呢吧啊呀哦么" for ch in (g[0], g[-1])) or g[0] in "个一是我你就都也还" or g[-1] in "我你他她它们":
                        continue
                    if any(ch in "的了吗呢吧啊呀哦么是" for ch in g[1:-1]):      # 跨过虚词的片段不是一个词（出差党的便携 → 差党的便）
                        continue
                    grams[g] = 1
        df.update(grams.keys())
    least = max(2, int(math.ceil(len(texts) * 0.03)))          # 至少出现在 2 条里；条数多时按 3% 提高，免得只出现两三次的词也算「高频」
    is_long = lambda g: len(g) >= 5 and re.match("[%s]" % CJK, g)
    cand = [(g, c) for g, c in df.items() if c >= max(least, 3 if is_long(g) else 2)]     # 5 到 6 字的短语要出现 3 次以上才算
    cand.sort(key=lambda x: (-x[1], -len(x[0])))
    # 没达到次数的长短语不算关键词，但它的切片也不能冒出来（「自由搭配千年白噪音」出现 2 次，不该报出「配千年白」）
    kept, dropped = [], [(g, c) for g, c in df.items() if c >= 2 and is_long(g) and c < max(least, 3)]
    for g, c in cand:
        if any(g in k and kc >= c * 0.8 for k, kc in kept + dropped if len(k) > len(g)):      # 被更长的片段覆盖（包括已经被判为「长词切片」的那些）
            continue
        if any(kc >= c and ((k in g and len(g) - len(k) == 1 and c < kc * 0.8) or (k not in g and _partial(k, g, 1 if kc > c else 2))) for k, kc in kept):
            dropped.append((g, c))
            continue
        kept = [(k, kc) for k, kc in kept if not (k in g and c >= kc * 0.8 and len(g) > len(k))]
        kept.append((g, c))
    kept.sort(key=lambda x: (-x[1], -len(x[0])))
    return kept[:top]


def _partial(k, g, least=1):
    """两个片段首尾相接地重叠（「亚特兰大」和「兰大不来」）：多半是同一个长词被切开了。"""
    for n in range(least, min(len(k), len(g))):
        if g.startswith(k[-n:]) or g.endswith(k[:n]):
            return True
    return False


def analyse(comments, top=15, lex=None, stat=None, parse=None):
    """comments: [(text, likes)]，已清洗。返回洞察 dict。"""
    lex = lex or Lexicon()
    stat = stat or {"raw": len(comments), "author_replies": [], "spam": {}, "no_text": 0, "duplicates": 0}
    stop = load_stopwords()
    n = len(comments)
    rows = [(t, likes, lex.analyse(t)) for t, likes in comments]
    intent_count, intent_samples = Counter(), defaultdict(list)
    asp = OrderedDict((name, {"C": [], "Q": [], "P": [], "M": [], "words": Counter()}) for name in lex.aspects)
    loose, unclassified, suggestions = Counter(), [], []
    for t, likes, r in rows:
        for it in r["intents"]:
            intent_count[it] += 1
            intent_samples[it].append((likes, t))
        for name, (lab, words) in r["aspects"].items():
            asp[name][lab].append((likes, t))
            if lab in "CQ":
                ws = list(OrderedDict.fromkeys(words))      # 去重但保持出现顺序，次数相同的词每次运行排在同样的位置
                asp[name]["words"].update(w for w in ws if not any(w != o and w in o for o in ws))
        loose.update(r["loose"])
        if r["intents"] == ["其他"] and not r["aspects"]:
            unclassified.append(t)
        if "建议期待" in r["intents"]:
            suggestions.append((likes, t))

    def quotes(lst, k=3):
        return [t for _, t in sorted(lst, key=lambda x: -x[0])[:k]]

    aspects = []
    for name, d in asp.items():
        concern = len(d["C"]) + len(d["Q"])
        if concern + len(d["P"]) + len(d["M"]) == 0:
            continue
        aspects.append({"aspect": name, "complaints": len(d["C"]), "questions": len(d["Q"]), "praises": len(d["P"]), "mentions": len(d["M"]),
                        "concern": concern, "top_words": [w for w, _ in d["words"].most_common(5)],
                        "complaint_quotes": quotes(d["C"]), "question_quotes": quotes(d["Q"]), "praise_quotes": quotes(d["P"], 2)})
    aspects.sort(key=lambda a: (-a["concern"], -a["complaints"], -a["praises"]))
    # 兼容旧字段：pain_clusters 只含吐槽
    clusters = OrderedDict()
    for a in sorted(aspects, key=lambda a: -a["complaints"]):
        if a["complaints"]:
            clusters[a["aspect"]] = {"count": a["complaints"], "share": round(a["complaints"] / n, 3) if n else 0, "enough": a["complaints"] >= MIN_MENTIONS,
                                     "top_words": a["top_words"][:4], "quotes": a["complaint_quotes"]}
    # 问题按主题计数
    # 一条提问归到它问的那个维度：先看标成疑问的维度；没有就看它提到的别的维度（「续航真有 45 小时吗，我朋友的两天就没电」问的是性能）；都没有才算其他问题
    q_by, q_other = OrderedDict((a["aspect"], list(asp[a["aspect"]]["Q"])) for a in aspects if a["questions"]), []
    for t, likes, r in rows:
        if "提问" not in r["intents"] or any(lab == "Q" for lab, _ in r["aspects"].values()):
            continue
        about = [k for k in r["aspects"] if k != TRUST]
        for k in about:
            q_by.setdefault(k, []).append((likes, t))
        if not about:
            q_other.append((likes, t))
    qtopics = [{"topic": k, "count": len(v), "examples": quotes(v, 2)} for k, v in q_by.items()]
    if q_other:
        qtopics.append({"topic": "其他问题", "count": len(q_other), "examples": quotes(q_other, 2)})
    qtopics.sort(key=lambda x: (x["topic"] == "其他问题", -x["count"]))
    all_q = sorted(((likes, t) for t, likes, r in rows if "提问" in r["intents"]), key=lambda x: -x[0])

    def share(k):
        return intent_count.get(k, 0) / n if n else 0

    def strong(k, th):
        return intent_count.get(k, 0) >= MIN_MENTIONS and share(k) >= th

    actions = []
    if strong("购买意向", 0.15):
        actions.append("购买意向 %d 条：在首评或正文末尾补充购买方式，并准备一篇「怎么选 / 怎么买」的跟进笔记。" % intent_count["购买意向"])
    if strong("提问", 0.25):
        actions.append("提问 %d 条：按上面的「问题主题」整理一篇答疑笔记，并在 24 小时内逐条回复。" % intent_count["提问"])
    if strong("求教程", 0.1):
        actions.append("求教程 %d 条：下一次发布改用教程体，或出视频版分步演示。" % intent_count["求教程"])
    if strong("质疑广告", 0.08):
        actions.append("广告质疑 %d 条：下一篇增加真实使用细节和缺点，减少卖点罗列，并写明你和产品的关系。" % intent_count["质疑广告"])
    if strong("建议期待", 0.08):
        actions.append("用户在提需求（%d 条）：把「建议期待」的原话登记进产品改进清单。" % intent_count["建议期待"])
    big = [a for a in aspects if a["complaints"] >= MIN_MENTIONS]
    if big:
        a = big[0]
        actions.append("最集中的吐槽是「%s」（%d 条）：先判断是产品问题还是预期管理问题，再决定进产品改进清单，还是做下一篇的开头。" % (a["aspect"], a["complaints"]))
    else:
        thin = [a for a in aspects if a["complaints"]]
        if thin:
            actions.append("没有哪个痛点达到 %d 条。「%s」只有 %d 条，只能当线索，不要据此定下一篇的角度。" % (MIN_MENTIONS, thin[0]["aspect"], thin[0]["complaints"]))
    asked = [a for a in aspects if a["questions"] >= MIN_MENTIONS]
    if asked and (not big or asked[0]["aspect"] != big[0]["aspect"]):
        actions.append("「%s」被问了 %d 次：说明这项信息没给够，在正文或首评里直接回答。" % (asked[0]["aspect"], asked[0]["questions"]))
    low_conf = bool(parse and parse.get("warnings") and not parse.get("checked"))
    if n < MIN_COMMENTS:
        actions.insert(0, "有效评论只有 %d 条，不到 %d 条：以上只能当线索，不能当结论。" % (n, MIN_COMMENTS))
    if low_conf:
        actions.insert(0, "解析有疑点（见报告开头的 ⚠️），请先核对条数，再使用下面的数字。")
    un_kw = keywords(unclassified, stop, 8) if len(unclassified) >= 3 else []
    return {
        "total": n, "sample_sufficient": n >= MIN_COMMENTS and not low_conf,
        "parse": {"format": (parse or {}).get("format", ""), "warnings": (parse or {}).get("warnings", []), "checked": bool((parse or {}).get("checked")), "raw_entries": stat["raw"],
                  "author_replies": len(stat["author_replies"]), "spam": sum(len(v) for v in stat["spam"].values()),
                  "no_text": stat["no_text"], "duplicates": stat["duplicates"]},
        "intent_distribution": [{"intent": k, "count": c, "share": round(c / n, 3), "examples": quotes(intent_samples[k], 2)} for k, c in intent_count.most_common()],
        "keywords": [{"word": w, "comments": c} for w, c in keywords([t for t, _ in comments], stop, top)],
        "aspects": aspects, "pain_clusters": clusters,
        "question_topics": qtopics, "questions_to_answer": [t for _, t in all_q[:10]],
        "suggestions": quotes(suggestions, 8), "author_replies": stat["author_replies"][:20],
        "filtered": {k: {"count": len(v), "examples": v[:2]} for k, v in stat["spam"].items()},
        "unclassified": {"count": len(unclassified), "share": round(len(unclassified) / n, 3) if n else 0,
                         "keywords": [w for w, _ in un_kw], "examples": unclassified[:5], "loose_complaints": [w for w, _ in loose.most_common(6)]},
        "lexicons": [os.path.basename(p) for p, _ in lex.loaded],
        "actions": actions,
    }


def cut(s, n=60):
    s = str(s).replace("|", " ").replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def to_markdown(r, detail=None):
    p = r["parse"]
    L = ["# 评论洞察报告", ""]
    bits = ["有效评论 **%d** 条" % r["total"]]
    for k, name in (("author_replies", "作者回复"), ("spam", "引流或无关"), ("no_text", "无文字"), ("duplicates", "重复")):
        if p[k]:
            bits.append("%s %d 条" % (name, p[k]))
    L.append("解析：识别为「%s」。读到 %d 条，其中%s%s。" % (p["format"], p["raw_entries"], "，".join(bits), "（后几类不计入统计）" if len(bits) > 1 else ""))
    for w in p["warnings"]:
        L.append("- ⚠️ %s%s" % (w, "（已人工核对条数）" if p.get("checked") else ""))
    if p["warnings"] and not p.get("checked"):
        L.append("- 对照原文数一下条数。条数对，加 --checked 重跑；条数不对，把评论整理成每行一条再跑。")
    if not r["sample_sufficient"]:
        L.append("- ⚠️ %s，下面的结果只能当线索。" % ("解析有疑点" if p["warnings"] and r["total"] >= MIN_COMMENTS else "有效评论不到 %d 条" % MIN_COMMENTS))
    if r["lexicons"]:
        L.append("- 已加载项目词表：%s" % "、".join(r["lexicons"]))
    L += ["", "## 意图分布", "", "一条评论可以同时属于多种意图。", "", "| 意图 | 条数 | 占比 | 代表评论 |", "|---|---|---|---|"]
    for it in r["intent_distribution"]:
        L.append("| %s | %d | %.0f%% | %s |" % (it["intent"], it["count"], it["share"] * 100, " / ".join(cut(x, 40) for x in it["examples"])))
    L += ["", "## 关注点", "", "吐槽和疑问都说明用户在意这一点；达到 %d 条吐槽才算一个痛点。" % MIN_MENTIONS, "",
          "| 维度 | 吐槽 | 疑问 | 好评 | 高频词 | 判断 |", "|---|---|---|---|---|---|"]
    for a in r["aspects"]:
        if a["concern"] + a["praises"] == 0:
            continue
        verdict = "痛点" if a["complaints"] >= MIN_MENTIONS else ("信息没给够" if a["questions"] >= MIN_MENTIONS else ("亮点" if a["praises"] >= MIN_MENTIONS and a["praises"] > a["concern"] else "线索"))
        L.append("| %s | %d | %d | %d | %s | %s |" % (a["aspect"], a["complaints"], a["questions"], a["praises"], "、".join(a["top_words"][:4]) or "—", verdict))
    if not any(a["concern"] + a["praises"] for a in r["aspects"]):
        L.append("| （没有命中任何维度） | 0 | 0 | 0 | — | — |")
    shown = [a for a in r["aspects"] if a["complaints"]]
    if shown:
        L += ["", "吐槽原话："]
        for a in sorted(shown, key=lambda a: -a["complaints"]):
            L.append("- **%s**（%d 条）：%s" % (a["aspect"], a["complaints"], " / ".join("“%s”" % cut(q) for q in a["complaint_quotes"])))
    L += ["", "## 问题主题（按条数）", ""]
    for q in r["question_topics"]:
        L.append("- **%s** %d 条：%s" % (q["topic"], q["count"], " / ".join(cut(x) for x in q["examples"])))
    if not r["question_topics"]:
        L.append("没有提问。")
    if r["questions_to_answer"]:
        L += ["", "待回复（按点赞排序）："] + ["- " + cut(q, 100) for q in r["questions_to_answer"]]
    if r["suggestions"]:
        L += ["", "## 用户建议", ""] + ["- " + cut(s, 100) for s in r["suggestions"]]
    if r["author_replies"]:
        L += ["", "## 作者回复（%d 条，不计入统计）" % p["author_replies"], "", "回复里的说法要和笔记正文、卖点一致，写下一篇前核对一遍。", ""] + ["- " + cut(s, 100) for s in r["author_replies"][:8]]
    if r["filtered"]:
        L += ["", "## 已过滤的无关评论", ""] + ["- %s %d 条，例：%s" % (k, v["count"], " / ".join(cut(x, 40) for x in v["examples"])) for k, v in r["filtered"].items()]
    L += ["", "## 高频关键词", "", "、".join("%s(%d)" % (k["word"], k["comments"]) for k in r["keywords"]) or "无（评论过少）"]
    u = r["unclassified"]
    L += ["", "## 词表覆盖", "", "%d 条评论里有 %d 条（%.0f%%）没有归入任何意图或维度。" % (r["total"], u["count"], u["share"] * 100)]
    if u["keywords"] or u["loose_complaints"]:
        L.append("其中的高频词：%s。" % "、".join(u["keywords"] + u["loose_complaints"]))
    if u["examples"]:
        L.append("例：" + " / ".join(cut(x, 40) for x in u["examples"][:4]))
    if u["count"] >= 3 and u["share"] >= 0.25:
        L.append("如果里面有这个品类特有的痛点词或好评词，把它们写进项目词表 `%s` 后重跑（格式见 references/feedback.md 第 5 节）；改不了的少量误判，人工计数并注明「人工计数」。" % os.path.join(C.DATA_DIRNAME, "lexicon.json"))
    L += ["", "## 行动建议", ""] + (["- " + a for a in r["actions"]] or ["- 暂无明确信号，继续积累评论。"])
    if detail:
        L += ["", "## 逐条归类", "", "| 评论 | 意图 | 关注点 |", "|---|---|---|"]
        for t, _, x in detail:
            L.append("| %s | %s | %s |" % (t.replace("|", " ")[:60], "、".join(x["intents"]), "；".join("%s:%s" % (k, LABEL[v[0]]) for k, v in x["aspects"].items()) or "—"))
    return "\n".join(L)


def build_parser():
    ap = argparse.ArgumentParser(description="小红书评论洞察")
    ap.add_argument("files", nargs="+", metavar="文件", help="评论文件（可多个；- 表示标准输入）")
    ap.add_argument("--research", action="store_true", help="存为调研洞察：数据目录/research/insight.json")
    ap.add_argument("--id", help="存为某次发布的反馈洞察：数据目录/feedback/<编号>_insight.json")
    ap.add_argument("--json", help="把结构化结果写到这个路径")
    ap.add_argument("--author", default="", help="笔记作者的昵称：这个昵称发的评论按作者回复处理")
    ap.add_argument("--lexicon", action="append", default=[], help="额外的词表 json（可多次）")
    ap.add_argument("--top", type=int, default=15, help="关键词数量")
    ap.add_argument("--detail", action="store_true", help="列出每条评论的归类结果，便于核对")
    ap.add_argument("--checked", action="store_true", help="已对照原文核对过条数：保留解析提示，但不再因此降低可信度")
    C.add_dir_arg(ap)
    return ap


def main():
    a = build_parser().parse_args()
    lex = Lexicon([C.P(a, "lexicon.json")] + a.lexicon)
    raw, infos = [], []
    for f in a.files:
        if f != "-" and not os.path.exists(f):
            sys.exit("找不到文件：%s（当前目录 %s）" % (f, os.getcwd()))
        rows, info = read_comments(f, a.author)
        raw += rows
        infos.append(info)
    parse = {"format": "；".join(sorted({i["format"] for i in infos})), "warnings": [w for i in infos for w in i["warnings"]], "checked": a.checked}
    comments, stat = prepare(raw, lex, len(a.files))
    if not comments:
        sys.exit("没有解析到有效评论（读到 %d 条，作者回复 %d，无关 %d，无文字 %d）。txt 每行一条，或直接粘贴评论区复制的内容；csv / json 需要有 评论 / content 字段。"
                 % (stat["raw"], len(stat["author_replies"]), sum(len(v) for v in stat["spam"].values()), stat["no_text"]))
    r = analyse(comments, a.top, lex, stat, parse)
    out = a.json or (C.P(a, "research", "insight.json") if a.research else (C.P(a, "feedback", "%s_insight.json" % a.id.upper()) if a.id else None))
    detail = [(t, likes, lex.analyse(t)) for t, likes in comments] if a.detail else None
    print(to_markdown(r, detail))
    print()
    if out:
        if not a.json:
            C.check_cwd()
        C.write_json(out, r)
        print("已保存：%s" % C.where(out))
        if a.research:
            print("下一步：%s" % C.cmd("research.py", "analyze"))
        elif a.id:
            print("下一步：录入数据 %s，再用 verdict 下结论。" % C.cmd("launch_log.py", "metrics", "--id", a.id.upper(), "--impressions", "N", "--views", "N", "--likes", "N", "--collects", "N", "--comments", "N"))
    else:
        print("没有保存结构化结果。调研用的评论加 --research，某次发布的反馈加 --id L1。")


if __name__ == "__main__":
    C.run(main)

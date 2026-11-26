#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""各脚本共用的工具：编码容错读取、数字与日期解析、数据目录、可直接复制的命令提示。

约定：脚本可以从任何目录调用（用脚本的绝对路径），数据写在「当前工作目录/xhs_launch/」，
也可以用 --dir 或环境变量 XHS_LAUNCH_DIR 指定。只依赖 Python 3 标准库。
"""
import argparse, csv, io, json, math, os, re, shutil, sys
from datetime import datetime, timedelta

sys.dont_write_bytecode = True
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(SCRIPTS)
ASSETS = os.path.join(SKILL, "assets")
DATA_DIRNAME = "xhs_launch"
_state = {"extra": []}   # 本次调用用到的 --dir / --log，命令提示里原样带上

# 「1.2万」「3k」「1,024」「10万+」这类计数
COUNT = r"\d+(?:[.,]\d+)*\s*(?:万|w|W|千|k|K)?\+?"
# 评论区和搜索结果里出现的时间写法
DATE = (r"(?:刚刚|\d+\s*(?:秒|分钟|小时|天|周|个月|年)前|(?:今天|昨天|前天)(?:\s*\d{1,2}[:：]\d{2})?"
        r"|\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?|\d{1,2}[-/月]\d{1,2}日?)(?:\s+\d{1,2}[:：]\d{2})?")
# 小红书显示的 IP 属地：省级行政区和常见国家地区
PLACES = set("""北京 天津 上海 重庆 河北 山西 辽宁 吉林 黑龙江 江苏 浙江 安徽 福建 江西 山东 河南 湖北 湖南 广东 海南 四川 贵州 云南
陕西 甘肃 青海 台湾 内蒙古 广西 西藏 宁夏 新疆 香港 澳门 中国香港 中国澳门 中国台湾 美国 日本 韩国 英国 法国 德国 加拿大 澳大利亚 新加坡
马来西亚 泰国 越南 印度尼西亚 菲律宾 印度 俄罗斯 意大利 西班牙 荷兰 瑞士 瑞典 新西兰 爱尔兰 比利时 丹麦 芬兰 挪威 奥地利 葡萄牙 波兰
土耳其 阿联酋 沙特阿拉伯 巴西 墨西哥 阿根廷 南非 埃及 柬埔寨 老挝 缅甸 蒙古 哈萨克斯坦 匈牙利 捷克 希腊 以色列 卡塔尔 未知""".split())


def setup_io():
    """中文和表情在任何终端都不报错：终端里只替换打不出的字符，管道和重定向统一用 UTF-8。"""
    for s in (sys.stdout, sys.stderr):
        try:
            if s.isatty():
                s.reconfigure(errors="replace")
            elif not os.environ.get("PYTHONIOENCODING"):
                s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def run(main):
    """各脚本的统一入口：先让脚本把文件写完，再一次性输出文字。输出被 head 之类的命令截断时不会丢数据，也不会报 BrokenPipe。"""
    setup_io()
    real, buf, code = sys.stdout, io.StringIO(), 0
    sys.stdout = buf
    try:
        main()
    except SystemExit as e:
        code = e.code
    finally:
        sys.stdout = real
        try:
            real.write(buf.getvalue())
            real.flush()
        except BrokenPipeError:
            try:
                os.dup2(os.open(os.devnull, os.O_WRONLY), real.fileno())
            except (OSError, ValueError, AttributeError):
                pass
        except (OSError, ValueError):
            pass
    if code not in (None, 0):
        sys.exit(code)


def read_text(path):
    """读文本，返回 (文本, 编码)。依次尝试 UTF-8、UTF-16、GB18030（含 GBK，中文 Windows 的 Excel 默认导出）。path 为 - 时读标准输入。"""
    if path == "-":
        data = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as f:
            data = f.read()
    if data[:3] == b"\xef\xbb\xbf":
        text, enc = data[3:].decode("utf-8", "replace"), "UTF-8"
    elif data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text, enc = data.decode("utf-16", "replace"), "UTF-16"
    else:
        for enc in ("utf-8", "gb18030"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text, enc = data.decode("utf-8", "replace"), "utf-8?"
        enc = {"utf-8": "UTF-8", "gb18030": "GBK"}.get(enc, "无法确定（已跳过乱码字节）")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub("[\u200b-\u200f\u2028\u2029\u202a-\u202e\ufeff\ufffc\x00]", "", text).replace("\u00a0", " ").replace("\u3000", " ")
    return text, enc


def num(v):
    """'1.2万' '3k' '1,024' '10万+' -> int；认不出返回 None。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().lower().replace(",", "").replace("+", "").replace(" ", "")
    m = re.match(r"^(\d+(?:\.\d+)?)(万|w|千|k)?$", s)
    if not m:
        return None
    return int(round(float(m.group(1)) * {"万": 1e4, "w": 1e4, "千": 1e3, "k": 1e3, None: 1}[m.group(2)]))


def parse_date(v, today=None):
    """把各种时间写法转成 YYYY-MM-DD；认不出返回 None。支持「编辑于 11-02 上海」「3天前」「昨天 21:15」和时间戳。"""
    if v in (None, "") or isinstance(v, bool):
        return None
    today = today or datetime.now()
    s = str(v).strip()
    if isinstance(v, (int, float)) or re.fullmatch(r"\d{10}|\d{13}", s):
        t = float(v)
        try:
            return datetime.fromtimestamp(t / 1000 if t > 1e11 else t).strftime("%Y-%m-%d")
        except (ValueError, OSError, OverflowError):
            return None
    m = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return "%04d-%02d-%02d" % (y, mo, d) if 1 <= mo <= 12 and 1 <= d <= 31 else None
    back = None
    m = re.search(r"(\d+)\s*(秒|分钟|小时|天|周|个月|年)前", s)
    if m:
        back = int(m.group(1)) * {"秒": 0, "分钟": 0, "小时": 0, "天": 1, "周": 7, "个月": 30, "年": 365}[m.group(2)]
    elif re.search(r"刚刚|今天", s):
        back = 0
    elif "昨天" in s:
        back = 1
    elif "前天" in s:
        back = 2
    if back is not None:
        return (today - timedelta(days=back)).strftime("%Y-%m-%d")
    m = re.search(r"(?<![\d.])(\d{1,2})[-/月](\d{1,2})日?(?![\d.])", s)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            y = today.year - (1 if (mo, d) > (today.month, today.day + 1) else 0)   # 不带年份的日期不会在未来
            return "%04d-%02d-%02d" % (y, mo, d)
    return None


def is_date_line(s, nxt=""):
    """这一整行是不是「时间 + 属地」（评论和搜索结果里的元信息行）。属地不在词表里时，要求下一行是点赞数或「回复」才算。"""
    m = re.fullmatch(r"(?:编辑于\s*)?%s\s*([一-鿿]{2,7})?\s*(回复)?" % DATE, s.strip())
    if not m:
        return False
    place = m.group(1)
    if not place or place in PLACES or m.group(2):
        return True
    return bool(re.fullmatch(r"(?:赞|回复|[♡❤👍]\s*)?\s*(?:%s)?" % COUNT, nxt.strip())) and bool(nxt.strip())


def xhs_len(s):
    """小红书的计数习惯：中文和全角算 1，英文数字两个算 1。"""
    wide = len(re.findall(r"[^\x00-\x7f]", s))
    return wide + (len(re.findall(r"[\x21-\x7e]", s)) + 1) // 2


# ---------- 百分比、数字和单位 ----------

def pct(part, whole, digits=0):
    """part / whole 写成百分比。直接从原始条数算，四舍五入（5 进 1），不经过中间的小数。whole 为 0 时返回「—」。"""
    if not whole:
        return "—"
    scale = 10 ** digits
    q = (200 * scale * int(part) + int(whole)) // (2 * int(whole))
    return "%d%%" % q if not digits else "%d.%0*d%%" % (q // scale, digits, q % scale)


def rate_pct(v, digits=1):
    """比率（0.125）写成百分比（12.5%）。四舍五入，不用「五成双」。"""
    scale = 10 ** digits
    q = int(math.floor(abs(v) * 100 * scale + 0.5 + 1e-9))
    body = "%d" % q if not digits else "%d.%0*d" % (q // scale, digits, q % scale)
    return ("-" if v < 0 and q else "") + body + "%"


_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_CH = "一二两三四五六七八九十百半"


def cn_num(s):
    """「三」「十二」「二十」「两百」「半」→ 数；认不出返回 None。只管一千以内的常见写法。"""
    if s == "半":
        return 0.5
    if not s or any(ch not in _CN and ch not in "十百" for ch in s):
        return None
    total = cur = 0
    for ch in s:
        if ch in _CN:
            cur = _CN[ch]
        else:
            total, cur = total + (cur or 1) * (10 if ch == "十" else 100), 0
    return total + cur


# (写法, 归一后的单位, 换算系数, 是不是硬数字)。硬数字是价格、规格、时长、比例：写错一个就是虚假宣传。软数字是次数、人数、件数。
# 归一后的单位是 None 时用原来的量词（支、片、盒…）。
_UNITS = [
    (r"元|块钱|rmb|块(?=$|[^一-鿿a-z0-9]|[的和跟与或就都也还能买左上不出多包以内一差起到了吗呢吧啊呀嘛])", "元", 1, True),
    (r"kg|公斤|千克", "g", 1000, True), (r"斤", "g", 500, True), (r"克|g(?![a-z0-9])", "g", 1, True),
    (r"ml|毫升", "ml", 1, True), (r"升|l(?![a-z0-9])", "ml", 1000, True),
    (r"秒钟?", "分钟", 1.0 / 60, True), (r"分钟|min(?![a-z])", "分钟", 1, True), (r"个?小时|h(?![a-z0-9])", "分钟", 60, True),
    (r"天", "天", 1, True), (r"个?星期|个?礼拜|周(?![年期末岁边围到全])", "天", 7, True),
    (r"个月", "天", 30, True), (r"年(?![级代轻纪龄货夜])", "天", 365, True),      # 月和年只能约等于天数，比对时放宽一成
    (r"%|％", "%", 1, True), (r"折", "折", 1, True), (r"倍", "倍", 1, True),
    (r"mah|毫安时?", "mAh", 1, True), (r"cm|厘米", "cm", 1, True), (r"mm|毫米", "cm", 0.1, True), (r"英寸|寸", "寸", 1, True),
    (r"次", "次", 1, False), (r"个人|人(?![民生类气间工们])|位", "人", 1, False),
    (r"支|瓶|盒|包(?!邮)|片|粒|杯|袋|罐|颗|双|套|枚|贴", None, 1, False),
]
_UNIT_RX = "|".join("(?P<u%d>%s)" % (i, u[0]) for i, u in enumerate(_UNITS))
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_QTY = re.compile(r"(?<![\d.a-z第])(?:(?P<lo>%s)\s*(?:-|~|～|—|到|至)\s*)?(?P<num>%s)\s*(?:%s)" % (_NUM, _NUM, _UNIT_RX))
_QTY_PRE = re.compile(r"(?:[¥￥]|rmb)\s*(?P<num>%s)(?!\s*(?:元|块|%%|％))" % _NUM)
# 「到手 59」「39.9 包邮」：没写单位，但说的是价格
_QTY_PRICE = re.compile(r"(?:到手价?|只要|仅需|券后价?|折后价?|价格|售价|原价|现价|单价|定价|活动价|秒杀价?)\s*(?:是|为|才)?\s*[:：]?\s*(?P<a>%s)(?![\d.]|\s*(?:[a-z%%％一-鿿]))|(?<![\d.a-z第])(?P<b>%s)\s*包邮" % (_NUM, _NUM))
_QTY_KUAI = re.compile(r"(?<![\d.a-z第])(\d+)\s*块\s*(\d)(?![\d个支片条只盒袋瓶罐颗粒件毛分a-z])|(?<![第%s])([%s]+)块([一二三四五六七八九])(?![一-鿿])" % (_CN_CH, _CN_CH[:-1]))
_QTY_HALF = re.compile(r"(?<![\d.a-z第%s])(\d+|[%s]+)\s*(?:个半\s*(小时|月)|(年|个月|天|个?小时)半(?![一-鿿]))" % (_CN_CH, _CN_CH[:-1]))
_HALF = {"小时": ("分钟", 60), "个小时": ("分钟", 60), "月": ("天", 30), "个月": ("天", 30), "年": ("天", 365), "天": ("天", 1)}
_CN_UNITS = [u for u in _UNITS if u[1] in ("分钟", "天")] + [(r"块钱|元", "元", 1, True)]
_IDIOM = re.compile(r"三天两头|一年四季|十年如一日|三年五载|一日三餐|三天打鱼|两天晒网|一天到晚|一年到头|百年")
_QTY_CN = re.compile(r"(?<![第零%s])(?P<num>[%s]+)(?:%s)" % (_CN_CH, _CN_CH, "|".join("(?P<c%d>%s)" % (i, u[0]) for i, u in enumerate(_CN_UNITS))))
_ONE_OK = "了用涂吃喝戴穿过等放泡敷满共约近续持试"
# 宽松模式：中文数字配任何单位都认（每天涂三次、五十克、打八折）。只用在「出处」那一边，认多了只会让比对更宽，不会多报
_LOOSE_UNITS = [(r"块钱|元", "元", 1, True)] + _UNITS[1:]
_QTY_LOOSE = re.compile(r"(?<![第零%s])(?P<num>[%s]+)\s*(?:%s)" % (_CN_CH, _CN_CH[:-1], "|".join("(?P<c%d>%s)" % (i, u[0]) for i, u in enumerate(_LOOSE_UNITS))))


def quantities(text, loose=False):
    """找出文字里「数字 + 单位」的说法，换算成同一种单位，便于比对两段文字里的数字是不是同一个。
    返回 [{"value": 数, "unit": 归一后的单位, "raw": 原文, "start": 位置, "hard": 是不是硬数字, "approx": 是不是约数}]，按出现顺序。
    认「39 元」「¥39」「9块9」「50g」「30 秒」「两周」「半小时」「30-40 分钟」「8 个人」；不认序数（第 3 天）、年份（2026 年）、5G。
    中文数字默认只认时长和价格（两周、九块九）；loose=True 时配任何单位都认（三次、五十克），给「用户说过的话」那一边用。"""
    t = str(text)
    low = t.lower()
    out, taken = [], [x.span() for x in _IDIOM.finditer(low)]

    def add(value, unit, hard, a, b, approx=False):
        if value is None or any(a < y and x < b for x, y in taken) or low[:a].rstrip().endswith("第"):
            return
        taken.append((a, b))
        out.append({"value": round(float(value), 4), "unit": unit, "raw": t[a:b].strip(), "start": a, "hard": hard, "approx": approx})

    for m in _QTY_KUAI.finditer(low):
        if m.group(1):
            add(float(m.group(1)) + int(m.group(2)) / 10.0, "元", True, m.start(), m.end())
        else:
            head = cn_num(m.group(3))
            add(None if head is None else head + _CN[m.group(4)] / 10.0, "元", True, m.start(), m.end())
    for m in _QTY_HALF.finditer(low):
        head = float(m.group(1)) if m.group(1).isdigit() else cn_num(m.group(1))
        unit, k = _HALF[m.group(2) or m.group(3)]
        add(None if head is None else (head + 0.5) * k, unit, True, m.start(), m.end(), k >= 30)
    for m in _QTY_PRE.finditer(low):
        add(float(m.group("num").replace(",", "")), "元", True, m.start(), m.end())
    for m in _QTY_PRICE.finditer(low):
        g = "a" if m.group("a") else "b"
        add(float(m.group(g).replace(",", "")), "元", True, m.start(g), m.end(g))
    for m in _QTY.finditer(low):
        i = next(i for i in range(len(_UNITS)) if m.group("u%d" % i))
        _, unit, k, hard = _UNITS[i]
        word = m.group("u%d" % i)
        v = float(m.group("num").replace(",", ""))
        if word.startswith("年") and v >= 1900:                           # 2026 年：年份
            continue
        if unit == "g" and word == "g" and t[m.end("u%d" % i) - 1] == "G" and v in (2, 3, 4, 5, 6):   # 5G 网络
            continue
        if m.group("lo"):
            add(float(m.group("lo").replace(",", "")) * k, unit or word, hard, m.start("lo"), m.end("lo"), k >= 30)
        add(v * k, unit or word, hard, m.start("num"), m.end(), k >= 30)
    for rx, units in ((_QTY_CN, _CN_UNITS),) + (((_QTY_LOOSE, _LOOSE_UNITS),) if loose else ()):
        for m in rx.finditer(low):
            i = next(i for i in range(len(units)) if m.group("c%d" % i))
            _, unit, k, hard = units[i]
            raw, word = m.group("num"), m.group("c%d" % i)
            v = cn_num(raw)
            if v is None or v == 0 or (raw == "半" and word == "天"):          # 等了半天：不是时长
                continue
            prev = low[m.start() - 1] if m.start() else ""
            if raw == "一" and "一" <= prev <= "鿿" and prev not in _ONE_OK:      # 有一天、每一年：不是在报数
                continue
            add(v * k, unit or word, hard, m.start(), m.end(), k >= 30)
    out.sort(key=lambda q: q["start"])
    return out


def same_quantity(a, b):
    """两个说法是不是同一个数。带「月」「年」的是约数（一个月 ≈ 30 天 ≈ 4 周），放宽一成；其余要完全相等。"""
    if a["unit"] != b["unit"]:
        return False
    tol = 0.1 if a.get("approx") or b.get("approx") else 1e-6
    return abs(a["value"] - b["value"]) <= tol * max(abs(a["value"]), abs(b["value"]), 1e-9)


def table_rows(text, ext=""):
    """把 csv / tsv / Markdown 表格 / 从 Excel 粘贴出来的制表符文本读成 [dict]。不是表格时返回 []。"""
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) >= 2 and lines[0].lstrip().startswith("|") and re.fullmatch(r"[\s|:\-]+", lines[1]):
        split = lambda l: [c.strip() for c in l.strip().strip("|").split("|")]
        head = split(lines[0])
        return [dict(zip(head, split(l))) for l in lines[2:] if l.lstrip().startswith("|")]
    head = lines[0] if lines else ""
    if ext in (".csv", ".tsv"):
        delim = "\t" if head.count("\t") >= max(1, head.count(",")) else (";" if head.count(";") > head.count(",") else ",")
    elif head.count("\t") >= 1 and len(lines) >= 2 and len({l.count("\t") for l in lines}) == 1:
        delim = "\t"
    else:
        return []
    return [r for r in csv.DictReader(io.StringIO(text), delimiter=delim)]


def pick(d, keys):
    """按候选列名（不分大小写）取第一个非空值。"""
    low = {str(k).strip().lower(): v for k, v in d.items() if k is not None}
    for k in keys:
        v = low.get(k.lower())
        if v not in (None, ""):
            return v
    return None


# ---------- 数据目录与命令提示 ----------

def add_dir_arg(parser):
    parser.add_argument("--dir", default=argparse.SUPPRESS, help="数据目录，默认是当前目录下的 xhs_launch；不同产品用不同目录")
    parser.add_argument("--log", default=argparse.SUPPRESS, help=argparse.SUPPRESS)   # 旧版参数：发布日志的路径，数据目录取它所在的目录


def data_dir(a=None):
    """数据目录：--dir > 旧参数 --log 所在目录 > 环境变量 XHS_LAUNCH_DIR > ./xhs_launch。"""
    if getattr(a, "dir", None):
        _state["extra"] = ["--dir", quote(a.dir)]
        return a.dir
    if getattr(a, "log", None):
        _state["extra"] = ["--log", quote(a.log)]
        return os.path.dirname(a.log) or "."
    return os.environ.get("XHS_LAUNCH_DIR") or DATA_DIRNAME


def P(a, *parts):
    return os.path.join(data_dir(a), *parts)


def log_path(a):
    return getattr(a, "log", None) or P(a, "launch_log.json")


def quote(s):
    s = str(s)
    return '"%s"' % s if re.search(r"[\s()&;'$]", s) or not s else s


def py():
    """当前环境里能直接用的 Python 命令名。"""
    exe = os.path.realpath(sys.executable) if sys.executable else ""
    for n in (("python", "py") if os.name == "nt" else ("python3", "python")):
        w = shutil.which(n)
        if w and (os.name != "nt" or os.path.realpath(w).lower() == exe.lower()):
            return n
    return quote(sys.executable) if sys.executable else "python3"


def cmd(script, *args):
    """生成一条在任何目录都能直接运行的命令（脚本用绝对路径；本次用了 --dir 时自动带上）。"""
    return " ".join([py(), quote(os.path.join(SCRIPTS, script))] + [str(x) for x in args] + _state["extra"])


def where(path):
    """给用户看的路径：统一成绝对路径，免得分不清文件写到了哪。"""
    return os.path.abspath(path)


def check_cwd():
    """在技能目录里运行会把用户数据写进技能目录：提醒换到自己的工作目录。"""
    if _state["extra"] or os.environ.get("XHS_LAUNCH_DIR"):
        return
    cwd, sk = os.path.realpath(os.getcwd()), os.path.realpath(SKILL)
    if cwd == sk or cwd.startswith(sk + os.sep):
        sys.stderr.write("注意：当前目录在技能目录里，数据会写到 %s 。请先 cd 到你自己的工作目录再运行（脚本用绝对路径调用），或用 --dir 指定数据目录。\n" % where(DATA_DIRNAME))


def write_text(path, text):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError as e:
        sys.exit("无法写入 %s（%s）。请在可写的工作目录运行，或用 --dir 指定一个可写的数据目录。" % (where(path), e.strerror or e))


def write_json(path, obj, indent=2):
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=indent))


def read_json(path):
    """读 JSON；文件不存在返回 None，内容损坏时给出能看懂的提示。"""
    if not os.path.exists(path):
        return None
    try:
        return json.loads(read_text(path)[0])
    except ValueError as e:
        sys.exit("文件不是合法的 JSON：%s（%s）。如果是手工编辑过，请检查逗号和引号。" % (where(path), e))

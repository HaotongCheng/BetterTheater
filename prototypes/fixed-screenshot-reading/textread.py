"""PROTOTYPE — page localisation and text-field reading from OCR tokens.

Every parser returns an Observation-like dict {"value", "raw", "fixed"} or None (未读)。
"fixed" marks a value that needed a documented character normalisation (O→0 等)，原文保留在 raw。
"""
import re

DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1"})


class Tok:
    __slots__ = ("text", "x0", "y0", "x1", "y1")

    def __init__(self, text, x0, y0, x1, y1):
        self.text, self.x0, self.y0, self.x1, self.y1 = text, x0, y0, x1, y1

    @property
    def cx(self): return (self.x0 + self.x1) / 2
    @property
    def cy(self): return (self.y0 + self.y1) / 2
    @property
    def h(self): return self.y1 - self.y0
    @property
    def w(self): return self.x1 - self.x0

    def __repr__(self): return f"{self.text}@{int(self.cx)},{int(self.cy)}"


def norm(s):
    return (s.replace(" ", "").replace("：", ":").replace("・", "·").replace("•", "·")
             .replace("．", ".").replace("x", "×").replace("X", "×"))


def tokens_rapid(entry, offset=(0, 0), scale=1.0):
    out = []
    for it in entry["items"]:
        xs = [p[0] for p in it["box"]]; ys = [p[1] for p in it["box"]]
        out.append(Tok(norm(it["text"]), offset[0] + min(xs) * scale, offset[1] + min(ys) * scale,
                       offset[0] + max(xs) * scale, offset[1] + max(ys) * scale))
    return out


def tokens_win(entry):
    # Windows OCR 中文按字切词、行内带空格；按行合并为一个 token，bbox 取词框并集。
    out = []
    for line in entry["lines"]:
        ws = line["words"]
        if not ws:
            continue
        x0 = min(w["rect"]["x"] for w in ws); y0 = min(w["rect"]["y"] for w in ws)
        x1 = max(w["rect"]["x"] + w["rect"]["width"] for w in ws)
        y1 = max(w["rect"]["y"] + w["rect"]["height"] for w in ws)
        # 同一“行”有时横跨整屏（例如顶栏与余额被并成一行）；按大间距再切开
        cur = [ws[0]]
        groups = [cur]
        for a, b in zip(ws, ws[1:]):
            gap = b["rect"]["x"] - (a["rect"]["x"] + a["rect"]["width"])
            if gap > 1.5 * max(a["rect"]["height"], b["rect"]["height"]):
                cur = [b]; groups.append(cur)
            else:
                cur.append(b)
        for g in groups:
            out.append(Tok(norm("".join(w["text"] for w in g)),
                           min(w["rect"]["x"] for w in g), min(w["rect"]["y"] for w in g),
                           max(w["rect"]["x"] + w["rect"]["width"] for w in g),
                           max(w["rect"]["y"] + w["rect"]["height"] for w in g)))
    return out


def find(toks, pat):
    r = re.compile(pat)
    return [t for t in toks if r.search(t.text)]


def first(toks, pat):
    f = find(toks, pat)
    return f[0] if f else None


def obs(value, raw, fixed=False):
    return {"value": value, "raw": raw, "fixed": fixed}


def to_int(s):
    fixed = s != s.translate(DIGIT_FIX)
    s2 = s.translate(DIGIT_FIX)
    return (int(s2), fixed) if s2.isdigit() else (None, False)


# ---------------------------------------------------------------- page localisation
# 规则只使用页面上的固定文案锚点，不用坐标；按“更特殊的先判”排序。
PAGE_RULES = [
    ("rewind_result", [r"已回溯至"]),
    ("paused_resume", [r"回溯机会"]),
    ("battle_failed", [r"演出失败"]),
    ("blessing_acquired", [r"祝福已升级"]),
    ("battle_result_lineup", [r"演出阵容"]),
    ("post_battle_recruit", [r"待命角色转变为可出战"]),
    ("companion_select", [r"伙伴事件", r"转变为可出战角色"]),
    ("details_roster", [r"可出战角色", r"^待命角色$"]),
    ("details_blessing", [r"^辉彩祝福$", r"祝福等级\d+"]),
    ("battle_preview", [r"舞台效果", r"敌人详情", r"确认选择"]),
    ("event_select", [r"第\d+幕$", r"重置事件"]),
]
# 局前配置页含“待命角色/可出战角色”等相同词汇；出现这些词时拒判。
REJECT = [r"队伍配置", r"存在尚未进行的圣牌挑战", r"获得基础的", r"额外编入"]


def classify(toks):
    if any(find(toks, p) for p in REJECT):
        return "unknown", "命中拒判词"
    for page, pats in PAGE_RULES:
        if all(find(toks, p) for p in pats):
            return page, " + ".join(pats)
    return "unknown", "无规则命中"


# ---------------------------------------------------------------- field parsers
def top_bar(toks):
    """顶栏：同一行 ≥4 个 Lv 记号，按 x 排序 = 皇冠/绽放/激化/感电；其右侧纯数字 = 余额。"""
    lv = [t for t in toks if re.fullmatch(r"L[vV]?\.?[0-9OoIl]{1,2}", t.text)]
    rows = []
    for t in sorted(lv, key=lambda t: t.cy):
        for r in rows:
            if abs(r[0].cy - t.cy) < 0.6 * r[0].h:
                r.append(t); break
        else:
            rows.append([t])
    rows = [r for r in rows if len(r) >= 4]
    res = {}
    if rows:
        row = sorted(min(rows, key=lambda r: r[0].cy), key=lambda t: t.cx)[:4]
        for name, t in zip(["crown", "bloom", "quicken", "electro"], row):
            v, fx = to_int(re.sub(r"^L[vV]?\.?", "", t.text))
            res[name] = obs(v, t.text, fx) if v is not None else None
        y, h, xr = row[0].cy, row[0].h, row[-1].x1
        nums = [t for t in toks if re.fullmatch(r"\d{1,4}", t.text) and abs(t.cy - y) < h and t.x0 > xr]
        if nums:
            t = min(nums, key=lambda t: t.x0)
            res["balance"] = obs(int(t.text), t.text)
    return res, (rows[0][0] if rows else None)


def balance_corner(toks, W, H):
    """战斗准备页：右上角唯一的纯数字。"""
    c = [t for t in toks if re.fullmatch(r"\d{1,4}", t.text) and t.cy < 0.08 * H and t.cx > 0.75 * W]
    return obs(int(c[0].text), c[0].text) if c else None


def parse_event(toks, W, H):
    f, _ = top_bar(toks)
    a = first(toks, r"第(\d+)幕$")
    f["act"] = obs(int(re.search(r"第(\d+)幕", a.text).group(1)), a.text) if a else None
    r = first(toks, r"^重置事件$")
    f["refresh"] = None
    if r:
        c = [t for t in toks if re.fullmatch(r"[0-9OoIl]", t.text) and r.y0 - 4 * r.h < t.cy < r.y0
             and abs(t.cx - r.cx) < 1.5 * r.w]
        if c:
            v, fx = to_int(c[0].text); f["refresh"] = obs(v, c[0].text, fx)
    f["cards"] = read_cards(toks, H)
    return f


TITLE_RE = r"(战斗|伙伴|激化|绽放|感电|神秘收获)(·\S+)?"
PRICE_RE = r"[+\-]\d{1,3}|免费"


def read_cards(toks, H):
    """以卡片标题为锚（比价格稳），在标题正上方找价格。读不出价格时保留最近的原文供检视。"""
    titles = sorted([t for t in toks if re.fullmatch(TITLE_RE, t.text) and 0.35 * H < t.cy < 0.8 * H], key=lambda t: t.cx)
    cards, raws = [], []
    for ti in titles:
        above = [t for t in toks if 0 < ti.cy - t.cy < 3 * ti.h and abs(t.cx - ti.cx) < ti.w and t is not ti]
        price = [t for t in above if re.fullmatch(PRICE_RE, t.text)]
        p = min(price, key=lambda t: ti.cy - t.cy) if price else None
        raw = p.text if p else (min(above, key=lambda t: ti.cy - t.cy).text if above else "∅")
        cards.append([p.text if p else None, ti.text]); raws.append(f"{raw}/{ti.text}")
    return {"value": cards, "raw": " | ".join(raws), "fixed": False, "_titles": titles} if cards else None


def parse_preview(toks, W, H):
    f = {}
    t = first(toks, r"^(战斗|月谕圣牌)·")
    f["title"] = obs(t.text, t.text) if t and t.cy < 0.3 * H else None
    goal = first(toks, r"^(击败所有敌人|「圣牌挑战」)")
    f["reward"] = None
    if goal:
        n = [x for x in toks if re.fullmatch(r"\d{2,3}", x.text) and abs(x.cy - goal.cy) < goal.h and x.x1 <= goal.x0 + 2]
        if n:
            n = max(n, key=lambda x: x.x1); f["reward"] = obs(int(n.text), n.text)
    s = first(toks, r"明星挑战")
    if s:
        m = re.search(r"(\d+)秒", s.text)
        f["star_seconds"] = obs(int(m.group(1)) if m else None, s.text)
    else:
        f["star_seconds"] = None
    f["balance"] = balance_corner(toks, W, H)
    return f


def parse_result(toks, W, H):
    f = {}
    r = first(toks, r"演出(成功|失败)")
    f["result"] = obs(re.search(r"演出(成功|失败)", r.text).group(1), r.text) if r else None
    t = first(toks, r"\d{2}[:：]\d{2}")
    f["time"] = obs(re.search(r"(\d{2})[:：](\d{2})", t.text).group(0).replace("：", ":"), t.text) if t else None
    return f


def parse_result_lineup(toks, W, H):
    f = parse_result(toks, W, H)
    goals = sorted(find(toks, r"击败"), key=lambda t: t.cy)
    f["reward"] = None
    if goals:
        g = goals[0]
        n = [x for x in toks if re.fullmatch(r"\d{2,3}", x.text) and abs(x.cy - g.cy) < g.h and x.x0 > g.x1]
        if n:
            f["reward"] = obs(int(n[0].text), n[0].text)
    f["_goal_toks"] = goals[:2]
    return f


def cand_levels(toks, anchor_pat):
    a = first(toks, anchor_pat)
    if not a:
        return None
    lv = sorted([t for t in toks if re.fullmatch(r"L[vV]?\.?[0-9OoIl]{2,3}", t.text) and t.cy > a.cy], key=lambda t: t.cx)
    vals = [to_int(re.sub(r"^L[vV]?\.?", "", t.text))[0] for t in lv]
    return obs(vals, " ".join(t.text for t in lv))


def parse_recruit(toks, W, H):
    f = parse_result(toks, W, H)
    f["cand_levels"] = cand_levels(toks, r"转变为可出战")
    return f


def parse_companion(toks, W, H):
    return {"cand_levels": cand_levels(toks, r"转变为可出战")}


def parse_roster(toks, W, H):
    f, _ = top_bar(toks)
    a = first(toks, r"^可出战角色$"); s = first(toks, r"^待命角色$")
    lv = [t for t in toks if re.fullmatch(r"L[vV]?\.?[0-9OoIl]{2,3}", t.text)]
    if a and s:
        av = sorted([t for t in lv if a.cy < t.cy < s.cy], key=lambda t: t.cx)
        f["avail_levels"] = obs([to_int(t.text.split(".")[-1])[0] for t in av], " ".join(t.text for t in av))
        f["standby_visible_levels"] = obs(len([t for t in lv if t.cy > s.cy]), "count")
        st = sorted([t for t in toks if re.fullmatch(r"×?\d{1,2}", t.text) and abs(t.cy - s.cy) < s.h], key=lambda t: t.cx)
        f["standby_stats"] = obs([int(t.text.lstrip("×")) for t in st], " ".join(t.text for t in st))
    return f


def parse_blessing(toks, W, H):
    f, _ = top_bar(toks)
    h = first(toks, r"当前持有:?\d+")
    f["held"] = obs(int(re.search(r"(\d+)", h.text).group(1)), h.text) if h else None
    mh = first(toks, r"^神秘收获$"); bh = first(toks, r"^辉彩祝福$")
    if mh:
        lim = bh.cy if bh else H
        b = sorted([t for t in toks if "·" in t.text and mh.cy < t.cy < lim and len(t.text) <= 8], key=lambda t: t.cx)
        f["boons"] = obs([t.text for t in b], " ".join(t.text for t in b))
    else:
        f["boons"] = None
    tl = first(toks, r"^祝福等级(\d+)")
    f["blessing_total"] = obs(int(re.search(r"(\d+)", tl.text).group(1)), tl.text) if tl else None
    lv = {}
    for t in find(toks, r"^等级[0-9OoIl]+"):
        name = [x for x in toks if re.fullmatch(r"(绽放|激化|感电)祝福", x.text) and abs(x.cy - t.cy) < t.h and x.x0 > t.x0]
        joined = re.search(r"(绽放|激化|感电)祝福", t.text)
        nm = name[0].text[:2] if name else (joined.group(1) if joined else None)
        if nm:
            lv[nm] = to_int(re.match(r"等级([0-9OoIl]+)", t.text).group(1))[0]
    f["branch_levels"] = obs(lv, str(lv)) if lv else None
    return f


def parse_failed(toks, W, H):
    f = parse_result(toks, W, H)
    c = first(toks, r"(\d+)秒后自动退出")
    f["countdown"] = obs(int(re.search(r"(\d+)秒", c.text).group(1)), c.text) if c else None
    return f


def parse_paused(toks, W, H):
    a = first(toks, r"正于第(\d+)幕"); r = first(toks, r"剩余(\d+)次")
    return {"act": obs(int(re.search(r"第(\d+)幕", a.text).group(1)), a.text) if a else None,
            "rewind_left": obs(int(re.search(r"剩余(\d+)次", r.text).group(1)), r.text) if r else None}


def parse_rewind(toks, W, H):
    a = first(toks, r"已回溯至第(\d+)幕")
    lv = sorted([t for t in toks if re.fullmatch(r"L[vV]?\.?[0-9OoIl]{2,3}", t.text)], key=lambda t: t.cx)
    return {"act": obs(int(re.search(r"第(\d+)幕", a.text).group(1)), a.text) if a else None,
            "visible_levels": obs([to_int(t.text.split(".")[-1])[0] for t in lv], " ".join(t.text for t in lv)) if lv else None}


def parse_acquired(toks, W, H):
    a = first(toks, r"(\S{2})祝福已升级"); t = first(toks, r"^(绽放|激化|感电)·")
    return {"branch": obs(re.search(r"(\S{2})祝福已升级", a.text).group(1), a.text) if a else None,
            "title": obs(t.text, t.text) if t else None}


PARSERS = {
    "event_select": parse_event, "battle_preview": parse_preview,
    "battle_result_lineup": parse_result_lineup, "post_battle_recruit": parse_recruit,
    "companion_select": parse_companion, "details_roster": parse_roster,
    "details_blessing": parse_blessing, "battle_failed": parse_failed,
    "paused_resume": parse_paused, "rewind_result": parse_rewind, "blessing_acquired": parse_acquired,
}

# 体力头像带的锚点文案
ROSTER_ANCHOR = {
    "battle_preview": r"^可出战角色$", "battle_result_lineup": r"^演出阵容$",
    "post_battle_recruit": r"^可出战角色$", "companion_select": r"^可出战角色$",
    "details_roster": r"^可出战角色$", "rewind_result": r"^可出战角色$",
}

"""PROTOTYPE — image fields: stamina slots, head identity, objective ✓/✗.

所有区域都相对 OCR 文案锚点（“可出战角色”“演出阵容”等）定位，尺度用锚点文字高度换算；
没有写死 2560×1440 坐标，所以用户裁切过的 E1 图也走同一路径。
"""
import itertools
import cv2
import numpy as np

# 参考图库：每条 (名称, 亮/灰, 来源图, 框, 来源图的锚点文字高度)。匹配时按 当前锚点高度/来源锚点高度 缩放。
# V1/V2 只用前两条（S15）；V3 用全部。来源图自身不算诚实测试：S23 测卡片式、E1 最终战测深色全灰都被污染，只有 S10 是诚实的卡片式测试。
TEMPLATE_SRC = "S15"
LIT_BOX = (1112, 684, 1132, 712)    # S15 头像式亮格
GREY_BOX = (1140, 683, 1158, 711)   # S15 头像式灰格（深色底）
LIBRARY = [
    ("head_lit", "lit", "S15", LIT_BOX),
    ("head_grey", "grey", "S15", GREY_BOX),
    ("card_lit", "lit", "S23", (777, 980, 795, 1007)),        # 卡片式亮格（橙色卡面）
    ("card_grey", "grey", "S23", (1536, 979, 1556, 1008)),    # 卡片式灰格（浅色卡面）
    ("dark_grey", "grey", "E1:final-battle", (445, 425, 459, 443)),  # 深色底全灰格
]


class Template:
    def __init__(self, name, kind, img, box, ref_h):
        self.name, self.kind, self.ref_h = name, kind, ref_h
        x0, y0, x1, y1 = box
        self.gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)[y0:y1, x0:x1]
        self.sat = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[y0:y1, x0:x1, 1]


class Templates:
    """保持旧接口：T.lit / T.grey / T.lit_sat / T.ref_h 指向 S15 模板；T.lib 为全部模板。"""
    def __init__(self, img_s15, anchor_h, lib=None):
        self.ref_h = anchor_h
        g = cv2.cvtColor(img_s15, cv2.COLOR_BGR2GRAY)
        sat = cv2.cvtColor(img_s15, cv2.COLOR_BGR2HSV)[..., 1]
        self.lit = g[LIT_BOX[1]:LIT_BOX[3], LIT_BOX[0]:LIT_BOX[2]]
        self.grey = g[GREY_BOX[1]:GREY_BOX[3], GREY_BOX[0]:GREY_BOX[2]]
        self.lit_sat = sat[LIT_BOX[1]:LIT_BOX[3], LIT_BOX[0]:LIT_BOX[2]]
        self.lib = lib or []


def edges(gray):
    # 形状比亮度更稳：头像页背景有深色、浅色和橙色卡底三种
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    return cv2.magnitude(gx, gy)


def is_lit(bgr_patch):
    hsv = cv2.cvtColor(bgr_patch, cv2.COLOR_BGR2HSV)
    m = (hsv[..., 0] >= 12) & (hsv[..., 0] <= 35) & (hsv[..., 1] > 60) & (hsv[..., 2] > 200)
    core = (hsv[..., 2] > 235) & (hsv[..., 1] < 140)
    return float(m.mean() + core.mean())


def band_for(anchor, page, W, H):
    """头像页：图标在锚点下 ~2.6h–3.6h；卡片页（演出详情/回溯）更靠下。x 只取锚点附近，避免页面其他图形。"""
    h = anchor.h
    if page in ("details_roster", "rewind_result"):
        y0, y1 = anchor.y1 + 2.5 * h, anchor.y1 + 7.5 * h
    else:
        y0, y1 = anchor.y1 + 1.8 * h, anchor.y1 + 4.4 * h
    if page in ("battle_preview", "details_roster"):
        x0, x1 = anchor.x0 - 1.5 * h, anchor.x0 + (34 if page == "details_roster" else 26) * h   # 左对齐列表
    elif page == "rewind_result":
        x0, x1 = anchor.cx - 19 * h, anchor.cx + 19 * h        # 卡片更宽
    else:
        x0, x1 = anchor.cx - 15 * h, anchor.cx + 15 * h        # 居中列表
    return int(max(0, y0)), int(min(H, y1)), int(max(0, x0)), int(min(W, x1))


def detect_slots(img, anchor, page, T, thr=0.7, thr_lit=0.5, mode="sat"):
    """mode='sat'：亮格在饱和度图上匹配；mode='edge'：亮格也用边缘图（对照基线）。"""
    H, W = img.shape[:2]
    y0, y1, bx0, bx1 = band_for(anchor, page, W, H)
    s = anchor.h / T.ref_h
    band = img[y0:y1, bx0:bx1]
    if band.shape[0] < 10:
        return [], (y0, y1, bx0, bx1, s)
    e = edges(cv2.cvtColor(band, cv2.COLOR_BGR2GRAY))
    sat = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)[..., 1]
    dets = []
    # V1：亮/灰都在边缘图上匹配；V2：亮格改在饱和度图上；V3：参考图库全部模板（亮→饱和度，灰→边缘）
    if mode == "lib":
        plan = [(t.kind, t.sat if t.kind == "lit" else t.gray, sat if t.kind == "lit" else e,
                 thr_lit if t.kind == "lit" else thr, anchor.h / t.ref_h, t.name) for t in T.lib]
    else:
        plan = [(("lit", T.lit_sat, sat, thr_lit) if mode == "sat" else ("lit", T.lit, e, thr)) + (s, "head_lit"),
                ("grey", T.grey, e, thr, s, "head_grey")]
    for kind, t, chan, th, sc, tname in plan:
        tt = cv2.resize(t, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
        if tt.shape[0] >= chan.shape[0] or tt.shape[1] < 4:
            continue
        te = tt if (kind == "lit" and mode in ("sat", "lib")) else edges(tt)
        r = cv2.matchTemplate(chan.astype(np.float32), te.astype(np.float32), cv2.TM_CCOEFF_NORMED)
        if te is not tt:
            # 平坦区域的归一化相关会退化成 ±1；要求窗口内边缘能量与模板相当
            energy = cv2.boxFilter(chan, -1, (te.shape[1], te.shape[0]), normalize=True)
            energy = energy[te.shape[0] // 2: te.shape[0] // 2 + r.shape[0], te.shape[1] // 2: te.shape[1] // 2 + r.shape[1]]
            r[energy < 0.35 * float(te.mean())] = 0
        r[~np.isfinite(r)] = 0
        ys, xs = np.where(r >= th)
        for y, x in zip(ys, xs):
            dets.append((float(r[y, x]) + (0.5 if kind == "lit" else 0), int(x + bx0), int(y + y0), tt.shape[1], tt.shape[0], kind, tname))
    # NMS
    dets.sort(reverse=True)
    keep = []
    for d in dets:
        if all(abs(d[1] - k[1]) > 0.6 * d[3] or abs(d[2] - k[2]) > 0.6 * d[4] for k in keep):
            keep.append(d)
    # 只保留主行：多数检测所在的 y
    if keep:
        ys = np.array([k[2] for k in keep])
        med = np.median(ys[np.argsort([-k[0] for k in keep])][:max(2, len(keep) // 2)])
        keep = [k for k in keep if abs(k[2] - med) < 0.5 * k[4]]
    out = []
    for sc, x, y, w, h, kind, tname in sorted(keep, key=lambda k: k[1]):
        lit = is_lit(img[y:y + h, x:x + w])
        out.append({"x": x, "y": y, "w": w, "h": h, "score": sc - (0.5 if kind == "lit" else 0), "tmpl": tname, "litness": lit, "lit": lit > 0.18})
    return out, (y0, y1, bx0, bx1, s)


def group_avatars(slots):
    """相邻两格 = 一名角色。间距用格宽归一，不写死像素。"""
    avs, cur = [], []
    for sl in slots:
        if cur and (sl["x"] - (cur[-1]["x"] + cur[-1]["w"]) > 0.9 * sl["w"] or len(cur) == 2):
            avs.append(cur); cur = []
        cur.append(sl)
    if cur:
        avs.append(cur)
    return [{"slots": a, "lit": sum(s["lit"] for s in a), "cx": (a[0]["x"] + a[-1]["x"] + a[-1]["w"]) / 2,
             "y": min(s["y"] for s in a), "sw": a[0]["w"], "n": len(a)} for a in avs]


# ------------------------------------------------------------------ identity
def head_crop(img, av):
    w = av["sw"]
    x0, x1 = int(av["cx"] - 2.2 * w), int(av["cx"] + 2.2 * w)
    y0, y1 = int(av["y"] - 3.6 * w), int(av["y"] + 0.2 * w)
    H, W = img.shape[:2]
    return img[max(0, y0):min(H, y1), max(0, x0):min(W, x1)]


def desc_hist(crop):
    c = cv2.resize(crop, (64, 64), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 1] > 50) & (hsv[..., 2] > 50)).astype(np.uint8)   # 去掉低饱和背景
    h = cv2.calcHist([hsv], [0, 1], mask, [24, 8], [0, 180, 0, 256])
    return cv2.normalize(h, h).flatten()


def desc_gray(crop):
    c = cv2.resize(crop, (48, 48), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return (g - g.mean()) / (g.std() + 1e-6)


def sim_hist(a, b):
    return 1 - cv2.compareHist(a, b, cv2.HISTCMP_BHATTACHARYYA)


def sim_gray(a, b):
    return float((a * b).mean())


def assign(A, B, sim):
    """A 每个头像在 B 中找唯一对应；|A|<=|B|，穷举最优排列（≤8 人可接受）。"""
    S = np.array([[sim(a, b) for b in B] for a in A])
    best, bp = -1e9, None
    for perm in itertools.permutations(range(len(B)), len(A)):
        v = sum(S[i, j] for i, j in enumerate(perm))
        if v > best:
            best, bp = v, perm
    margins = []
    for i, j in enumerate(bp):
        others = [S[i, k] for k in range(len(B)) if k != j]
        margins.append(float(S[i, j] - max(others)) if others else 0.0)
    return list(bp), margins, S


# ------------------------------------------------------------------ objective marks
def objective_mark(img, goal_tok):
    h = goal_tok.h
    x0, x1 = int(goal_tok.x0 - 2.2 * h), int(goal_tok.x0 - 0.1 * h)
    y0, y1 = int(goal_tok.y0 - 0.2 * h), int(goal_tok.y1 + 0.2 * h)
    patch = img[max(0, y0):y1, max(0, x0):x1]
    if patch.size == 0:
        return None, patch
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    sat = (hsv[..., 1] > 90) & (hsv[..., 2] > 120)
    green = (sat & (hsv[..., 0] > 35) & (hsv[..., 0] < 90)).mean()
    red = (sat & ((hsv[..., 0] < 10) | (hsv[..., 0] > 165))).mean()
    if max(green, red) < 0.02:
        return None, patch
    return ("✓" if green > red else "✗"), patch

"""PROTOTYPE — run every candidate method on the fixed screenshots, score against labels.py,
write out/results.json and out/report.html (both gitignored: the report embeds screenshot crops).

    .venv\\Scripts\\python ocr_cache.py   # once: full-frame OCR for both engines
    .venv\\Scripts\\python run.py
"""
import base64, html, json, re, time
from collections import Counter, defaultdict

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from labels import LABELS, NV, IDENTITY_PAIRS
from samples import SAMPLES
import textread as tr
import vision as vi

CACHE = json.load(open("out/ocr_cache.json", encoding="utf-8"))
rapid = RapidOCR()
IMG = {}


def img(k):
    if k not in IMG:
        IMG[k] = cv2.imread(str(SAMPLES[k]))
    return IMG[k]


def b64(bgr, maxw=900):
    if bgr is None or bgr.size == 0:
        return ""
    if bgr.shape[1] > maxw:
        bgr = cv2.resize(bgr, (maxw, int(bgr.shape[0] * maxw / bgr.shape[1])))
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


# ------------------------------------------------------------------ scoring
def status(truth, o):
    if o and o.get("_unread"):
        o = None
    v = o["value"] if o else None
    if truth is None:   # 真值是“该处没有此项”（例如明星条件没有秒数）
        return "正确" if o is not None and v is None else ("未读" if o is None else "误读")
    if truth == NV:
        return "正确(不可见)" if v is None else "误读"
    if v is None:
        return "未读"
    if v == truth:
        return "正确(经纠正)" if o.get("fixed") else "正确"
    return "误读"


def expand(field, truth, o):
    """卡片、列表逐项评分；其余整体评分。"""
    if field == "cards" and truth != NV:
        got = o["value"] if o else []
        rows = []
        for i, (tp, tt) in enumerate(truth):
            g = got[i] if i < len(got) else [None, None]
            rows.append((f"cards[{i}].price", tp, {"value": g[0], "raw": o["raw"] if o else ""} if g[0] else
                         ({"value": None, "raw": o["raw"], "_unread": True} if o else None)))
            rows.append((f"cards[{i}].title", tt, {"value": g[1], "raw": o["raw"] if o else ""} if g[1] else None))
        return rows
    return [(field, truth, o)]


# ------------------------------------------------------------------ text methods
def toks_for(engine, k):
    e = CACHE[k][engine]
    return tr.tokens_rapid(e) if engine == "rapid" else tr.tokens_win(e)


def ocr_crop(bgr, up=3, use_cls=False):
    # 局部小图关闭方向分类：全屏默认开启时，“+90”被转 180° 读成“06+”
    c = cv2.resize(bgr, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
    t = time.perf_counter(); res, _ = rapid(c, use_cls=use_cls); dt = time.perf_counter() - t
    return [(tr.norm(s), float(sc)) for _, s, sc in (res or [])], dt


def local_reread(k, page, toks, fields):
    """方法 R2：全屏一次后，只对“未读”的字段按锚点裁小图放大再读一次。"""
    im = img(k); H, W = im.shape[:2]; extra = 0.0; notes = []
    if page == "event_select":
        r = tr.first(toks, r"^重置事件$")
        if r and fields.get("refresh") is None:
            x0, x1 = int(r.cx - 1.2 * r.w), int(r.cx + 1.2 * r.w); y0, y1 = int(r.y0 - 4 * r.h), int(r.y0)
            got, dt = ocr_crop(im[max(0, y0):y1, max(0, x0):x1]); extra += dt
            d = [s for s, _ in got if re.fullmatch(r"[0-9OoIl]", s)]
            if d:
                v, fx = tr.to_int(d[0]); fields["refresh"] = tr.obs(v, d[0], fx); notes.append("refresh")
        c = fields.get("cards")
        if c:
            for i, (ti, (p, _)) in enumerate(zip(c["_titles"], c["value"])):
                if p is None:
                    y0, y1 = int(ti.y0 - 2.6 * ti.h), int(ti.y0 - 0.1 * ti.h); x0, x1 = int(ti.x0), int(ti.x1)
                    got, dt = ocr_crop(im[max(0, y0):y1, max(0, x0):x1]); extra += dt
                    pr = [m.group(0) for m in (re.search(tr.PRICE_RE, s) for s, _ in got) if m]   # 花朵图标常读成 β/@
                    if pr:
                        c["value"][i][0] = pr[0]; c["raw"] += f" ‖补读:{','.join(s for s, _ in got)}"; notes.append(f"cards[{i}].price")
                    else:
                        c["raw"] += f" ‖补读:{','.join(s for s, _ in got) or '∅'}"
    return fields, extra, notes


def run_text(engine, k, reread=False):
    W, H = CACHE[k]["size"]
    toks = toks_for(engine, k)
    t = time.perf_counter()
    page, why = tr.classify(toks)
    fields = tr.PARSERS[page](toks, W, H) if page in tr.PARSERS else {}
    parse_dt = time.perf_counter() - t
    extra, notes = 0.0, []
    if reread and page == LABELS[k]["page"]:
        fields, extra, notes = local_reread(k, page, toks, fields)
    return {"page": page, "why": why, "fields": fields, "ocr_sec": CACHE[k][engine]["sec"],
            "parse_sec": parse_dt, "reread_sec": extra, "reread": notes, "toks": toks}


# 方法 R0：固定比例坐标（以 S09 的 2560×1440 版面量出），不找锚点。
FIXED_ROI = {  # x0,y0,x1,y1 as fraction of W,H
    "crown": (.33, .05, .40, .11), "bloom": (.43, .05, .50, .11), "quicken": (.53, .05, .60, .11),
    "electro": (.63, .05, .70, .11), "balance": (.83, .05, .90, .11), "act": (.44, .80, .56, .86),
    "refresh": (.935, .79, .97, .84),
    **{f"cards[{i}].price": (x - .05, .57, x + .05, .63) for i, x in enumerate([.23, .41, .59, .77])},
    **{f"cards[{i}].title": (x - .08, .62, x + .08, .67) for i, x in enumerate([.23, .41, .59, .77])},
}


def run_fixed_roi(k):
    im = img(k); H, W = im.shape[:2]; out = {}; dt = 0.0
    for f, (a, b, c, d) in FIXED_ROI.items():
        got, t = ocr_crop(im[int(b * H):int(d * H), int(a * W):int(c * W)], up=2); dt += t
        s = "".join(x for x, _ in got)
        v = None
        if f in ("crown", "bloom", "quicken", "electro"):
            m = re.search(r"L[vV]?\.?([0-9OoIl]{1,2})", s); v = tr.to_int(m.group(1))[0] if m else None
        elif f in ("balance", "refresh"):
            m = re.fullmatch(r"\d{1,4}", s); v = int(s) if m else None
        elif f == "act":
            m = re.search(r"第(\d+)幕", s); v = int(m.group(1)) if m else None
        elif f.endswith("price"):   # 小图常把花朵图标读成 @ 等符号，去掉后再判
            m = re.search(tr.PRICE_RE, s); v = m.group(0) if m else None
        else:                       # 小图常丢“·”，按已知前缀补回
            m = re.fullmatch(r"(战斗|伙伴|激化|绽放|感电|神秘收获)·?(\S*)", s)
            v = (m.group(1) + ("·" + m.group(2) if m.group(2) else "")) if m else None
        out[f] = {"value": v, "raw": s or "∅"}
    return out, dt


# ------------------------------------------------------------------ image methods
A15 = tr.first(toks_for("rapid", "S15"), tr.ROSTER_ANCHOR["battle_result_lineup"])
LIB = [vi.Template(n, kind, img(src), box, tr.first(toks_for("rapid", src), tr.ROSTER_ANCHOR[LABELS[src]["page"]]).h)
       for n, kind, src, box in vi.LIBRARY]
TPL = vi.Templates(img("S15"), A15.h, LIB)
CONTAMINATED = {src for _, _, src, _ in vi.LIBRARY}   # 模板来源图：V3 在这些图上的成绩不算


def stamina(k, page, toks, mode):
    pat = tr.ROSTER_ANCHOR.get(page)
    a = tr.first(toks, pat) if pat else None
    if not a:
        return None
    t = time.perf_counter()
    slots, (y0, y1, x0, x1, s) = vi.detect_slots(img(k), a, page, TPL, mode=mode)
    avs = vi.group_avatars(slots)
    dt = time.perf_counter() - t
    dbg = img(k).copy()
    cv2.rectangle(dbg, (x0, y0), (x1, y1), (255, 120, 0), 2)
    for sl in slots:
        cv2.rectangle(dbg, (sl["x"], sl["y"]), (sl["x"] + sl["w"], sl["y"] + sl["h"]), (0, 220, 255) if sl["lit"] else (200, 200, 200), 2)
    top = max(0, y0 - int(4 * a.h))
    return {"value": [v["lit"] for v in avs], "raw": f"{len(avs)}人/{len(slots)}格", "avatars": avs, "sec": dt,
            "crop": dbg[top:y1 + 10, max(0, x0):x1]}


# ------------------------------------------------------------------ main
def main():
    R = {"samples": {}, "identity": [], "synthetic": []}
    engines = [("rapid", False, "R1 Rapid全屏"), ("rapid", True, "R2 Rapid全屏+局部补读"), ("win", False, "W1 WinOCR全屏")]
    for k, lab in LABELS.items():
        rec = {"truth_page": lab["page"], "methods": {}, "rows": []}
        for eng, rr, name in engines:
            res = run_text(eng, k, rr)
            m = {"page": res["page"], "page_ok": res["page"] == lab["page"], "why": res["why"],
                 "ocr_sec": res["ocr_sec"], "reread_sec": res["reread_sec"], "reread": res["reread"], "fields": {}}
            if res["page"] == lab["page"]:
                for f, truth in lab.items():
                    if f in ("page", "stamina", "ids", "marks"):
                        continue
                    for fn, tv, o in expand(f, truth, res["fields"].get(f)):
                        m["fields"][fn] = {"truth": tv, "value": o["value"] if o else None,
                                           "raw": o.get("raw") if o else None, "status": status(tv, o)}
                if "marks" in lab:
                    goals = res["fields"].get("_goal_toks", [])
                    for i, tv in enumerate(lab["marks"]):
                        mk = vi.objective_mark(img(k), goals[i])[0] if i < len(goals) else None
                        m["fields"][f"marks[{i}]"] = {"truth": tv, "value": mk, "raw": "颜色", "status": status(tv, {"value": mk} if mk else None)}
            else:
                for f, truth in lab.items():
                    if f != "page":
                        for fn, tv, o in expand(f, truth, None):
                            m["fields"][fn] = {"truth": tv, "value": None, "raw": "页面未定位", "status": "未读(页面)"}
            if eng == "rapid" and not rr:
                rec["_toks"] = res["toks"]
            rec["methods"][name] = m
        # 固定坐标基线，只做事件页
        if lab["page"] == "event_select":
            fx, dt = run_fixed_roi(k)
            m = {"page": "(不判页)", "page_ok": None, "ocr_sec": dt, "fields": {}}
            for f, truth in lab.items():
                if f == "page":
                    continue
                for fn, tv, _ in expand(f, truth, None):
                    o = fx.get(fn)
                    if o is None:
                        continue
                    m["fields"][fn] = {"truth": tv, "value": o["value"], "raw": o["raw"], "status": status(tv, o if o["value"] is not None else None)}
            rec["methods"]["R0 固定坐标ROI"] = m
        # 体力
        if "stamina" in lab:
            rec["stamina"] = {}
            for mode, name in (("edge", "V1 边缘模板"), ("sat", "V2 饱和度+边缘模板"), ("lib", "V3 参考图库")):
                if k == vi.TEMPLATE_SRC and mode != "lib":
                    continue
                st = stamina(k, lab["page"], rec["_toks"], mode)
                stt = status(lab["stamina"], st)
                if mode == "lib" and k in CONTAMINATED:
                    stt += "(模板来源，不计)"
                rec["stamina"][name] = {"truth": lab["stamina"], "value": st["value"] if st else None,
                                        "raw": st["raw"] if st else "无锚点", "sec": st["sec"] if st else None,
                                        "status": stt, "img": b64(st["crop"]) if st else "",
                                        "_avs": st["avatars"] if st else []}
        R["samples"][k] = rec

    # 身份关联（V2 检测结果上做）
    for a, b in IDENTITY_PAIRS:
        ra, rb = R["samples"][a], R["samples"][b]
        def avs(k, rec):
            if "stamina" in rec and "V2 饱和度+边缘模板" in rec["stamina"]:
                return rec["stamina"]["V2 饱和度+边缘模板"]["_avs"]
            st = stamina(k, LABELS[k]["page"], toks_for("rapid", k), "sat")   # 模板来源图：只取位置，不评分
            return st["avatars"] if st else []
        avA, avB = avs(a, ra), avs(b, rb)
        ida, idb = LABELS[a]["ids"], LABELS[b]["ids"]
        entry = {"a": a, "b": b, "methods": {}}
        if len(avA) != len(ida) or len(avB) != len(idb):
            entry["note"] = f"检测人数与真值不符（{len(avA)}/{len(ida)}，{len(avB)}/{len(idb)}），无法评估"
            R["identity"].append(entry); continue
        ca = [vi.head_crop(img(a), v) for v in avA]; cb = [vi.head_crop(img(b), v) for v in avB]
        for name, desc, sim in (("I1 颜色直方图", vi.desc_hist, vi.sim_hist), ("I2 灰度相关", vi.desc_gray, vi.sim_gray)):
            t = time.perf_counter()
            perm, margins, _ = vi.assign([desc(c) for c in ca], [desc(c) for c in cb], sim)
            dt = time.perf_counter() - t
            ok = [ida[i] == idb[j] for i, j in enumerate(perm)]
            entry["methods"][name] = {"correct": sum(ok), "n": len(ok), "ok": ok, "perm": perm,
                                      "margins": [round(x, 3) for x in margins], "sec": dt}
        entry["crops_a"] = [b64(c, 120) for c in ca]; entry["crops_b"] = [b64(c, 120) for c in cb]
        R["identity"].append(entry)

    # 合成缩放（不是实测环境）：同一截图缩到 1920×1080 / 1280×720 再走 R1 + V2
    for k in ("S09", "S20", "S14", "S16", "S19"):
        lab = LABELS[k]
        for (w, h) in ((1920, 1080), (1280, 720)):
            small = cv2.resize(img(k), (w, h), interpolation=cv2.INTER_AREA)
            t = time.perf_counter(); res, _ = rapid(small); dt = time.perf_counter() - t
            toks = [tr.Tok(tr.norm(s), min(p[0] for p in b), min(p[1] for p in b), max(p[0] for p in b), max(p[1] for p in b)) for b, s, _ in (res or [])]
            page, _ = tr.classify(toks)
            fields = tr.PARSERS[page](toks, w, h) if page in tr.PARSERS else {}
            cnt = Counter()
            for f, truth in lab.items():
                if f in ("page", "stamina", "ids", "marks"):
                    continue
                for fn, tv, o in expand(f, truth, fields.get(f) if page == lab["page"] else None):
                    cnt[status(tv, o)] += 1
            st = None
            if "stamina" in lab:
                IMG[f"{k}@{w}"] = small
                s2 = stamina(f"{k}@{w}", lab["page"], toks, "sat")
                st = status(lab["stamina"], s2)
            R["synthetic"].append({"k": k, "size": f"{w}×{h}", "page_ok": page == lab["page"], "fields": dict(cnt),
                                   "stamina": st, "ocr_sec": dt})

    for rec in R["samples"].values():
        rec.pop("_toks", None)
        for s in rec.get("stamina", {}).values():
            s.pop("_avs", None)
    json.dump(R, open("out/results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    write_report(R)
    print_summary(R)


def summarize(R):
    page, field = defaultdict(Counter), defaultdict(Counter)
    for k, rec in R["samples"].items():
        for name, m in rec["methods"].items():
            if m["page_ok"] is not None:
                page[name]["正确" if m["page_ok"] else "错误"] += 1
            for f in m["fields"].values():
                field[name][f["status"]] += 1
    stam = defaultdict(Counter)
    for rec in R["samples"].values():
        for name, s in rec.get("stamina", {}).items():
            stam[name][s["status"]] += 1
    ident = defaultdict(Counter)
    for e in R["identity"]:
        for name, m in e["methods"].items():
            ident[name]["正确"] += m["correct"]; ident[name]["错误"] += m["n"] - m["correct"]
        if "note" in e:
            ident["(未评估对数)"]["对"] += 1
    return page, field, stam, ident


def print_summary(R):
    page, field, stam, ident = summarize(R)
    for title, d in (("页面定位", page), ("文本/勾叉字段", field), ("体力（整帧完全一致）", stam), ("身份关联（逐人）", ident)):
        print("==", title)
        for k, v in d.items():
            print("  ", k, dict(v))
    print("== 合成缩放")
    for s in R["synthetic"]:
        print("  ", s)


# ------------------------------------------------------------------ report
CSS = """
:root{--bg:#fbfaf7;--fg:#1f2328;--mut:#667085;--line:#e4e1da;--ok:#1a7f37;--bad:#c62828;--warn:#9a6700;--card:#fff;--chip:#f1efe9}
@media (prefers-color-scheme:dark){:root{--bg:#16181c;--fg:#e6e6e6;--mut:#9aa3ae;--line:#30343b;--ok:#4ac26b;--bad:#ff6b6b;--warn:#e3b341;--card:#1d2026;--chip:#262a31}}
body{background:var(--bg);color:var(--fg);font:14px/1.55 system-ui,"Microsoft YaHei",sans-serif;margin:0;padding:24px 16px;max-width:1200px;margin:auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
.mut{color:var(--mut)}table{border-collapse:collapse;width:100%;margin:6px 0 14px;font-size:13px}
td,th{border-bottom:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}th{color:var(--mut);font-weight:600}
.s-ok{color:var(--ok)}.s-bad{color:var(--bad);font-weight:600}.s-un{color:var(--warn)}
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:10px 0}
img{max-width:100%;border-radius:4px}.heads img{width:64px;height:auto;margin:2px}
code{background:var(--chip);padding:0 4px;border-radius:3px}.wrap{overflow-x:auto}
details summary{cursor:pointer;font-weight:600}
"""


def cls(s):
    return "s-ok" if s.startswith("正确") else ("s-bad" if s == "误读" else "s-un")


def esc(x):
    return html.escape(json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x)


def write_report(R):
    page, field, stam, ident = summarize(R)
    H = [f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>固定截图读取原型</title><style>{CSS}</style>",
         "<h1>固定截图：页面定位与字段读取原型</h1>",
         "<p class=mut>可抛弃原型。真值为代理逐图人工标注，<b>待用户复核</b>；阈值与锚点偏移在同一批样本上调过，没有留出集，所以下表是“这批图上能否做到”，不是可靠性估计。"
         "样本：S01–S23（2560×1440，用户截图）与 E1 旧合作局 13 张（用户裁切过、尺寸各异）。全部本地运行，未外传图像。</p>"]

    def tbl(d, cols):
        rows = "".join(f"<tr><td>{html.escape(k)}</td>" + "".join(f"<td>{v.get(c, 0)}</td>" for c in cols) + "</tr>" for k, v in d.items())
        return "<div class=wrap><table><tr><th>方法</th>" + "".join(f"<th>{c}</th>" for c in cols) + f"</tr>{rows}</table></div>"

    H.append("<h2>汇总</h2><p class=mut>页面定位（按页面判定；未支持的页面应拒判为 unknown）</p>" + tbl(page, ["正确", "错误"]))
    H.append("<p class=mut>文本与勾叉字段（逐字段；“未读(页面)”= 页面没定位上导致整页字段没读）</p>" +
             tbl(field, ["正确", "正确(经纠正)", "正确(不可见)", "误读", "未读", "未读(页面)"]))
    H.append("<p class=mut>体力：整帧所有人的亮格数都对才算正确。V3 在模板来源图（S15/S23/E1 最终战）上的成绩单列、不计。</p>" + tbl(stam, ["正确", "误读", "未读", "正确(模板来源，不计)", "误读(模板来源，不计)"]))
    H.append("<p class=mut>跨页身份关联：逐人是否配对到同一角色</p>" + tbl(ident, ["正确", "错误", "对"]))

    H.append("<h2>体力格检测</h2><p class=mut>图为 V3 的检测：蓝框 = 由锚点文字推出的搜索带；黄框 = 判为亮格；灰框 = 判为灰格。</p>")
    for k, rec in R["samples"].items():
        if "stamina" not in rec:
            continue
        H.append(f"<div class=box><b>{html.escape(k)}</b> <span class=mut>{rec['truth_page']}</span>")
        for name, s in rec["stamina"].items():
            H.append(f"<div>{html.escape(name)}：真值 <code>{s['truth']}</code> 读出 <code>{s['value']}</code> "
                     f"<span class={cls(s['status'])}>{s['status']}</span> <span class=mut>{s['raw']}</span></div>")
        H.append(f"<img src='{rec['stamina']['V3 参考图库']['img']}'></div>")

    H.append("<h2>跨页身份关联</h2><p class=mut>第一行为 A 页头像，第二行为按方法配到的 B 页头像（I1）；✗ 为配错。margin = 最佳与次佳相似度差，越小越不可靠。</p>")
    for e in R["identity"]:
        H.append(f"<div class=box><b>{html.escape(e['a'])} → {html.escape(e['b'])}</b>")
        if "note" in e:
            H.append(f"<div class=s-un>{html.escape(e['note'])}</div></div>"); continue
        for name, m in e["methods"].items():
            H.append(f"<div>{name}：{m['correct']}/{m['n']} 正确，margin {m['margins']}</div>")
        m = e["methods"]["I1 颜色直方图"]
        H.append("<div class=heads>" + "".join(f"<img src='{c}'>" for c in e["crops_a"]) + "</div><div class=heads>" +
                 "".join(f"<span><img src='{e['crops_b'][j]}'>{'' if ok else '✗'}</span>" for j, ok in zip(m["perm"], m["ok"])) + "</div></div>")

    H.append("<h2>合成缩放（非实测）</h2><p class=mut>把 2560×1440 截图缩小后再跑 R1 + V2，只说明锚点相对定位不依赖绝对像素；不代表真实 1080p 渲染。</p><div class=wrap><table><tr><th>样本</th><th>尺寸</th><th>页面</th><th>字段</th><th>体力</th><th>OCR秒</th></tr>")
    for s in R["synthetic"]:
        H.append(f"<tr><td>{s['k']}</td><td>{s['size']}</td><td>{'✓' if s['page_ok'] else '✗'}</td><td>{esc(s['fields'])}</td><td>{s['stamina'] or '—'}</td><td>{s['ocr_sec']:.2f}</td></tr>")
    H.append("</table></div>")

    H.append("<h2>逐图明细</h2>")
    for k, rec in R["samples"].items():
        names = list(rec["methods"])
        H.append(f"<details class=box><summary>{html.escape(k)} · {rec['truth_page']}</summary>")
        H.append("<div>" + " · ".join(f"{html.escape(n)}：页面 <code>{m['page']}</code> OCR {m['ocr_sec']:.2f}s" +
                                      (f" 补读 {m['reread_sec']:.2f}s {m['reread']}" if m.get('reread') else "") for n, m in rec["methods"].items()) + "</div>")
        fields = []
        for m in rec["methods"].values():
            fields += [f for f in m["fields"] if f not in fields]
        H.append("<div class=wrap><table><tr><th>字段</th><th>真值</th>" + "".join(f"<th>{html.escape(n)}</th>" for n in names) + "</tr>")
        for f in fields:
            truth = next((m["fields"][f]["truth"] for m in rec["methods"].values() if f in m["fields"]), "")
            H.append(f"<tr><td>{f}</td><td>{esc(truth)}</td>")
            for n in names:
                x = rec["methods"][n]["fields"].get(f)
                H.append("<td>—</td>" if not x else
                         f"<td><span class={cls(x['status'])}>{x['status']}</span> {esc(x['value'])}<br><span class=mut>{esc(x['raw'] or '')}</span></td>")
            H.append("</tr>")
        H.append("</table></div></details>")
    open("out/report.html", "w", encoding="utf-8").write("".join(H))


if __name__ == "__main__":
    main()

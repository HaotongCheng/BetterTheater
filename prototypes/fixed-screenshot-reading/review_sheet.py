"""PROTOTYPE — 生成真值复核页 out/review.html（本地文件，内嵌截图裁片，不入库）。

每一项：裁片 + 我的标注 + 要确认的问题 + 对/错/不确定 + 备注；页底"生成答复"把选择汇总成文本，复制到对话里即可。
裁片都避开右下角 UID 区域；仍然只在本地使用。
"""
import base64, html, json, re

import cv2
import numpy as np

from labels import LABELS
from samples import SAMPLES
import textread as tr
import vision as vi

CACHE = json.load(open("out/ocr_cache.json", encoding="utf-8"))
IMG = {}


def img(k):
    if k not in IMG:
        IMG[k] = cv2.imread(str(SAMPLES[k]))
    return IMG[k]


def toks(k):
    return tr.tokens_rapid(CACHE[k]["rapid"])


def b64(bgr, maxw=1000):
    if bgr is None or bgr.size == 0:
        return ""
    if bgr.shape[1] > maxw:
        bgr = cv2.resize(bgr, (maxw, int(bgr.shape[0] * maxw / bgr.shape[1])), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


def crop_box(k, x0, y0, x1, y1, up=1.0):
    im = img(k); H, W = im.shape[:2]
    c = im[max(0, int(y0)):min(H, int(y1)), max(0, int(x0)):min(W, int(x1))]
    if up != 1.0 and c.size:
        c = cv2.resize(c, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
    return c


def crop_toks(k, ts, padx=1.0, pady=0.6, up=1.0):
    """按一组 token 的并集框裁，pad 以 token 高度为单位。"""
    h = max(t.h for t in ts)
    return crop_box(k, min(t.x0 for t in ts) - padx * h, min(t.y0 for t in ts) - pady * h,
                    max(t.x1 for t in ts) + padx * h, max(t.y1 for t in ts) + pady * h, up)


A15 = tr.first(toks("S15"), tr.ROSTER_ANCHOR["battle_result_lineup"])
TPL = vi.Templates(img("S15"), A15.h)


def roster_strip(k, letters=None):
    """头像/卡片带：从锚点文字到体力格下沿；有身份字母时标在每人上方。"""
    lab = LABELS[k]; page = lab["page"]
    a = tr.first(toks(k), tr.ROSTER_ANCHOR[page])
    im = img(k); H, W = im.shape[:2]
    y0, y1, x0, x1 = vi.band_for(a, page, W, H)
    top = int(a.y0 - 0.3 * a.h)
    c = im[top:y1 + int(0.3 * a.h), x0:x1].copy()
    if letters:
        slots, _ = vi.detect_slots(im, a, page, TPL, mode="sat")
        avs = vi.group_avatars(slots)
        if len(avs) == len(letters):
            for L, av in zip(letters, avs):
                cx = int(av["cx"] - x0); cy = int(av["y"] - top - 3.0 * av["sw"])
                cv2.putText(c, L, (cx - 8, max(18, cy)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
                cv2.putText(c, L, (cx - 8, max(18, cy)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 230, 255), 2, cv2.LINE_AA)
        else:
            cv2.putText(c, f"(检测人数 {len(avs)} != 标注 {len(letters)}，未标字母)", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return c


def top_bar_strip(k):
    f, row0 = tr.top_bar(toks(k))
    if row0 is None:
        im = img(k); return im[0:int(0.08 * im.shape[0]), :]
    ts = [t for t in toks(k) if abs(t.cy - row0.cy) < row0.h]
    return crop_toks(k, ts, padx=3, pady=0.8)


def refresh_corner(k):
    r = tr.first(toks(k), r"^重置事件$")
    return crop_box(k, r.cx - 2 * r.w, r.y0 - 4.5 * r.h, r.cx + 2 * r.w, r.y1 + 0.5 * r.h, up=1.5) if r else None


def cards_strip(k):
    ts = [t for t in toks(k) if re.fullmatch(tr.TITLE_RE, t.text) or re.fullmatch(tr.PRICE_RE, t.text)]
    H = img(k).shape[0]
    ts = [t for t in ts if 0.4 * H < t.cy < 0.8 * H]
    return crop_toks(k, ts, padx=2.5, pady=1.2)


ITEMS = []  # (id, group, title, [images], my_label, question)


def add(group, title, images, label, question):
    ITEMS.append((f"{len(ITEMS) + 1:02d}", group, title, [b64(i) for i in images if i is not None and i.size], label, question))


# ---------------------------------------------------------------- A. 体力与身份（最需要你看）
add("A 体力与身份", "E1 最终战结算：本场阵容 4 人体力",
    [roster_strip("E1:final-battle")],
    "从左到右 [0, 0, 0, 1]：前三人两格全灰，第四人亮一格。",
    "前三人是否确实两格都是灰的（耐力归零但仍显示）？这一条决定“全灰格”到底存不存在。")
add("A 体力与身份", "S15 本场阵容 4 人体力 + 身份字母",
    [roster_strip("S15", list("SRUV"))],
    "体力 [1, 1, 1, 1]；身份字母 S R U V（与 S14/S16 同字母 = 同一角色）。",
    "四人是否各亮一格？字母对应是否与下面 S14/S16 一致？")
add("A 体力与身份", "S14 精锐战前 8 人体力 + 身份字母",
    [roster_strip("S14", list("PQRSTUVW"))],
    "体力全部 2；身份 P Q R S T U V W。",
    "八人是否都两格亮？")
add("A 体力与身份", "S16 战后选人 8 人体力 + 身份字母（顺序已变）",
    [roster_strip("S16", list("PQTWRSUV"))],
    "体力 [2, 2, 2, 2, 1, 1, 1, 1]；身份 P Q T W R S U V。即 S15 出战的 S R U V 各掉一格，排到了后面。",
    "前四人两格、后四人一格？字母是否与 S14 中同一角色对应（同字母 = 同人）？")
add("A 体力与身份", "S11 普通战前 6 人、S12 伙伴事件 6 人",
    [roster_strip("S11", list("PQRSTW")), roster_strip("S12", list("PQRSTW"))],
    "两页都是体力全 2，身份都是 P Q R S T W（S14 的 8 人里少了 U、V）。",
    "两页六人是否同一批、顺序一致、都两格亮？")
add("A 体力与身份", "E1 第一幕：战前 8 人 / 伙伴事件 7 人 / 战后 8 人",
    [roster_strip("E1:act-1-battle-before", list("ABCDEFGH")),
     roster_strip("E1:act-1-recruitment-before", list("BCDEFGH")),
     roster_strip("E1:act-1-battle-after", list("ACEFBDGH"))],
    "战前 [2]*8，字母 A–H；伙伴事件 [2]*7，字母 B–H（没有 A）；战后 [2,2,2,2,1,1,1,1]，字母 A C E F B D G H（B D G H 出战各掉一格）。",
    "三页字母是否指向同一角色？战后后四人是否各一格？")
add("A 体力与身份", "E1 第五幕后选人 7 人",
    [roster_strip("E1:act-5-recruitment")],
    "体力 [2, 2, 2, 2, 2, 1, 1]。",
    "是否前五人两格、后两人一格？")
add("A 体力与身份", "S23 回溯结果：卡片式列表",
    [roster_strip("S23")],
    "可见 7 张完整卡 + 第 8 张被右边截断（不计）；Lv [90,90,90,90,90,90,80]；体力 [2,2,2,2,2,2,1]。",
    "第 7 张（Lv.80）是否只亮一格？前六张都两格？被截断的第 8 张我没有计入，对吗？")
add("A 体力与身份", "S10 演出详情：可出战区体力 + 待命区数量",
    [roster_strip("S10"), crop_box("S10", 540, 560, 2150, 1230)],
    "可出战 6 人体力全 2；待命区可见两整行共 16 张带 Lv 的卡，第三行 8 张半卡（Lv 被裁掉，不计）；统计 ×7 ×10 ×6。",
    "可出战六人都两格？待命可见整卡是否 16 张？统计三个数字对吗？")

# ---------------------------------------------------------------- B. 事件页：顶栏、刷新、卡片
for k, note in [("S09", ""), ("S17", ""), ("S20", "左侧有裂隙入口，卡片整体右移"),
                ("E1:act-1-bloom-after", ""), ("E1:act-2-events", ""), ("E1:act-9-refresh-before", ""),
                ("E1:act-9-refresh-after", "顶栏被裁掉，皇冠/三类等级/余额标为不可见(NV)")]:
    lab = LABELS[k]
    tb = f"皇冠 {lab['crown']}，绽放 {lab['bloom']}，激化 {lab['quicken']}，感电 {lab['electro']}，余额 {lab['balance']}"
    cards = "；".join(f"{p} {t}" for p, t in lab["cards"])
    add("B 事件页", f"{k}：顶栏 / 刷新次数 / 卡片",
        [top_bar_strip(k), refresh_corner(k), cards_strip(k)],
        f"第 {lab['act']} 幕；{tb}；刷新 {lab['refresh']}；卡片：{cards}。{note}",
        "数字与标题是否逐项正确？")

# ---------------------------------------------------------------- C. 战斗准备 / 结算 / 选人
for k in ["S11", "S14", "E1:act-1-battle-before", "E1:chariot-challenge", "E1:moon-challenge"]:
    lab = LABELS[k]; T = toks(k)
    ts = [t for t in T if re.search(r"击败|明星挑战|圣牌挑战|^\d{2,3}$|^(战斗|月谕圣牌)·", t.text) and t.cy < 0.45 * img(k).shape[0]]
    im = img(k); corner = im[0:int(0.09 * im.shape[0]), int(0.72 * im.shape[1]):]
    add("C 战斗准备", f"{k}：标题 / 奖励 / 明星秒数 / 右上余额",
        [crop_toks(k, ts, padx=2, pady=1), corner],
        f"标题 {lab['title']}；奖励 {lab['reward']}；明星秒数 {lab['star_seconds']}；余额 {lab['balance']}（NV = 画面里没有/被裁掉；None = 明星条件不是秒数）。",
        "逐项是否正确？右上角是否确实没有余额（NV 的那几张）？")
for k in ["S15", "E1:final-battle"]:
    lab = LABELS[k]; T = toks(k)
    ts = [t for t in T if re.search(r"演出(成功|失败)|消耗时间|击败|^\d{2,3}$", t.text)]
    add("C 结算", f"{k}：结果 / 用时 / 奖励 / 勾叉",
        [crop_toks(k, ts, padx=3, pady=1)],
        f"{lab['result']}，{lab['time']}，奖励 {lab['reward']}，两条目标 {lab['marks']}。",
        "是否正确？")
for k in ["S16", "E1:act-1-battle-after", "E1:act-5-recruitment", "S12", "E1:act-1-recruitment-before"]:
    lab = LABELS[k]; T = toks(k)
    ts = [t for t in T if re.search(r"演出(成功|失败)|消耗时间|L[vV]\.", t.text)]
    add("C 选人", f"{k}：结果 / 用时 / 候选等级",
        [crop_toks(k, ts, padx=3, pady=1)],
        f"结果 {lab.get('result', '—')}，用时 {lab.get('time', '—')}，候选等级 {lab['cand_levels']}（NV = 被裁掉）。",
        "是否正确？")

# ---------------------------------------------------------------- D. 详情页与其他
add("D 详情与其他", "S18 演出详情：神秘收获 + 祝福上部",
    [crop_box("S18", 520, 220, 2180, 1200)],
    "当前持有 2；标题「伙伴·即兴特邀」「惊喜·近价交换」；祝福等级 10；绽放等级 0（激化/感电在下方未显示）。",
    "是否正确？")
add("D 详情与其他", "S19 演出详情：祝福汇总下部",
    [crop_box("S19", 520, 220, 2180, 1180)],
    "祝福等级 10；绽放 0、激化 2、感电 0；神秘收获区已滚出画面（NV）。",
    "是否正确？")
add("D 详情与其他", "S13 / S21 / S22 / S23 文本",
    [crop_box("S13", 1000, 250, 1560, 900), crop_box("S21", 600, 300, 1960, 1000),
     crop_box("S22", 900, 180, 1660, 1200), crop_box("S23", 1000, 260, 1560, 380)],
    "S13：激化祝福已升级，激化·原态。S21：演出失败，24 秒后自动退出。S22：正于第 4 幕战斗，回溯剩余 2 次。S23：已回溯至第 4 幕。",
    "是否正确？")
add("D 详情与其他", "拒判页面（本原型不支持、应输出 unknown）",
    [cv2.resize(img(k)[: int(0.5 * img(k).shape[0])], None, fx=0.3, fy=0.3) for k in
     ["S03", "S06", "S07", "E1:act-1-bloom-before", "E1:unfinished-challenge-warning"]],
    "S01–S08（主菜单、模式说明、队伍配置、祝福树预览、名单确认、额外编入奖励）、E1 祝福购买确认弹层、圣牌未完成提示：都标为“unknown”。",
    "这些页面本票不读字段，只要求不被误判成局内页面。你是否同意这个范围？（S07/S08 的“获得 8 级祝福 / 获得 120 花朵”以后可能要读。）")

# ---------------------------------------------------------------- HTML
CSS = """
:root{--bg:#fbfaf7;--fg:#1f2328;--mut:#667085;--line:#e4e1da;--card:#fff;--acc:#1a5fb4}
@media (prefers-color-scheme:dark){:root{--bg:#16181c;--fg:#e6e6e6;--mut:#9aa3ae;--line:#30343b;--card:#1d2026;--acc:#79b8ff}}
body{background:var(--bg);color:var(--fg);font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif;margin:0;padding:20px 16px 80px;max-width:1100px;margin:auto}
h1{font-size:21px;margin:0 0 6px}h2{font-size:17px;margin:30px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
.mut{color:var(--mut)}.item{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:12px 0}
.item h3{font-size:15px;margin:0 0 8px}.item img{max-width:100%;display:block;margin:6px 0;border-radius:4px;border:1px solid var(--line)}
.lab{margin:8px 0 4px}.q{color:var(--acc);margin:4px 0 8px}
label.r{margin-right:14px}textarea{width:100%;box-sizing:border-box;min-height:40px;font:inherit;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:4px;padding:6px}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);padding:10px 16px;display:flex;gap:10px;align-items:center}
button{font:inherit;padding:6px 14px;border-radius:6px;border:1px solid var(--line);background:var(--bg);color:var(--fg);cursor:pointer}
#out{position:fixed;left:50%;transform:translateX(-50%);bottom:60px;width:min(900px,95vw);height:260px;display:none}
"""
H = [f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>真值复核</title><style>{CSS}</style>",
     "<h1>固定截图读取原型：真值复核</h1>",
     "<p class=mut>下面每一项是我标的真值和要你确认的点。A 组最要紧（体力格与身份），B–D 组多是明文数字，扫一眼即可。"
     "每项选“对 / 错 / 不确定”，错的请在备注里写正确值；最后点底部“生成答复”，把文本复制到对话里。本页只在本地，不要上传。</p>"]
cur = None
for iid, group, title, imgs, label, q in ITEMS:
    if group != cur:
        H.append(f"<h2>{html.escape(group)}</h2>"); cur = group
    H.append(f"<div class=item data-id='{iid}' data-title='{html.escape(title)}'><h3>#{iid} {html.escape(title)}</h3>")
    H += [f"<img src='{s}'>" for s in imgs]
    H.append(f"<div class=lab><b>我的标注：</b>{html.escape(label)}</div><div class=q>要确认：{html.escape(q)}</div>")
    H.append("".join(f"<label class=r><input type=radio name='r{iid}' value='{v}'> {v}</label>" for v in ("对", "错", "不确定")))
    H.append("<textarea placeholder='备注 / 正确值'></textarea></div>")
H.append("""<div class=bar><button onclick="gen()">生成答复</button><button onclick="document.getElementById('out').style.display='none'">收起</button>
<span class=mut>未选的项会按“未看”输出</span></div><textarea id=out></textarea>
<script>
function gen(){let L=[];document.querySelectorAll('.item').forEach(it=>{const r=it.querySelector('input:checked');const n=it.querySelector('textarea').value.trim();
L.push('#'+it.dataset.id+' '+(r?r.value:'未看')+(n?'：'+n:'')+'  ('+it.dataset.title+')');});
const o=document.getElementById('out');o.value=L.join('\\n');o.style.display='block';o.select();}
</script>""")
open("out/review.html", "w", encoding="utf-8").write("".join(H))
print(len(ITEMS), "items")

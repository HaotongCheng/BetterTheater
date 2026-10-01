"""BWIKI 快照 -> 候选规则包（原型，可抛弃）。只用标准库。

用法：
    python import_bwiki.py                        # 读快照，写 rulepack.json
    python import_bwiki.py --inject demo.html     # 同时把规则包注入单文件演示页

来源目录默认取主检出的 docs/research/sources/bwiki-2026-09-17（未入库），可用环境变量 BT_SOURCES 覆盖。
导入结果一律是“候选”（candidate）；只有 verification.json 里登记过的条目才标为已核验。
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT_DIR_NAME = "bwiki-2026-09-17"
SNAPSHOT_DATE = "2026-09-17"
SOURCE_URL = "https://wiki.biligame.com/ys/幻想真境剧诗"

# 当期（2026-09，水/雷/草；来源：官方 7.0 更新说明 O1，见 #13 报告）能出现的反应族。
# 其余反应族仍导入，作为同名/历史反例，in_period=false。
PERIOD = {"period": "2026-09", "elements": ["水", "雷", "草"], "families": ["绽放", "激化", "感电"]}

# 声明的适用范围。这是“声明”，不是核验结果；核验状态在每个条目上。
CLAIMED_SCOPE = {"server": "北美服（用户样本）", "client_version": "7.0", "language": "zh-CN", "period": PERIOD["period"]}

BOON_CATEGORIES = ("伙伴", "惊喜", "助益", "礼物")


def find_sources() -> Path:
    env = os.environ.get("BT_SOURCES")
    cands = [Path(env)] if env else []
    cands += [
        HERE.parents[1] / "docs/research/sources" / SNAPSHOT_DIR_NAME,  # 本工作树
        HERE.parents[3] / "docs/research/sources" / SNAPSHOT_DIR_NAME,  # 主检出（.research-worktrees/<name>/../..）
    ]
    for c in cands:
        if (c / "theater.html").exists():
            return c
    sys.exit("找不到 BWIKI 快照目录；请设置 BT_SOURCES=<.../bwiki-2026-09-17>")


class Walker(HTMLParser):
    """按文档顺序产出 heading / text / table 事件，只看 #mw-content-text。"""

    HEADINGS = {"h2", "h3", "h4", "h5"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_content = False
        self.div_depth = 0
        self.skip = 0
        self.events: list[tuple] = []
        self.heading = None
        self.hbuf: list[str] = []
        self.table = None
        self.row = None
        self.cell = None
        self.prose: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div":
            if self.in_content:
                self.div_depth += 1
            elif a.get("id") == "mw-content-text":
                self.in_content, self.div_depth = True, 1
        if not self.in_content:
            return
        if tag in ("script", "style"):
            self.skip += 1
            return
        if self.skip:
            return
        if tag in self.HEADINGS:
            self.heading, self.hbuf = tag, []
            return
        if tag == "table" and "wikitable" in (a.get("class") or ""):
            self.events.append(("text", "".join(self.prose)))
            self.prose = []
            self.table = []
            return
        if self.table is not None:
            if tag == "tr":
                self.row = []
            elif tag in ("td", "th"):
                self.cell = {"tag": tag, "colspan": int(a.get("colspan") or 1), "parts": []}
            elif tag == "br" and self.cell is not None:
                self.cell["parts"].append(" ")
        elif tag in ("p", "br", "li"):
            self.prose.append("\n")

    def handle_endtag(self, tag):
        if not self.in_content:
            return
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        if tag in self.HEADINGS and self.heading == tag:
            text = re.sub(r"\s+", " ", "".join(self.hbuf)).replace("[编辑]", "").strip()
            self.events.append(("heading", tag, text))
            self.heading = None
            self.prose = []
            return
        if self.table is not None:
            if tag in ("td", "th") and self.cell is not None:
                self.cell["text"] = "".join(self.cell["parts"])
                self.row.append(self.cell)
                self.cell = None
            elif tag == "tr" and self.row is not None:
                if self.row:
                    self.table.append(self.row)
                self.row = None
            elif tag == "table":
                self.events.append(("table", self.table))
                self.table = None
        if tag == "div":
            self.div_depth -= 1
            if self.div_depth <= 0:
                self.in_content = False

    def handle_data(self, data):
        if not self.in_content or self.skip:
            return
        if self.heading:
            self.hbuf.append(data)
        elif self.cell is not None:
            self.cell["parts"].append(data)
        elif self.table is None:
            self.prose.append(data)


NORMALIZATION = [
    "去掉图片（元素/反应图标），只保留文字",
    "模板渲染导致的重复词（如“月绽放 月绽放”）折叠为一次",
    "去掉所有空白（包括不换行空格）",
]


def clean(text: str) -> str:
    t = text.replace("\xa0", " ")
    t = re.sub(r"(\S{2,8})[ ]+\1(?=[ ]|$)", r"\1", t)  # 折叠“X X”重复
    t = re.sub(r"\s+", "", t)
    return t


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


BRANCH_RE = re.compile(r"^分支(\d)([AB])?[:：]\s*(.+)$")


def parse_tree(rows, ruleset_id, context):
    """一张祝福树表 -> 9 个节点。表形状固定：原态/原态文/分支1,2/文,文/进阶/进阶文/1A..2B/文×4。"""

    def cells(i, tag, n):
        r = rows[i]
        if len(r) != n or any(c["tag"] != tag for c in r):
            raise ValueError(f"表形状不符 @row{i}: 期待 {n}×{tag}，得到 {[c['tag'] for c in r]}（{context}）")
        return [clean(c["text"]) for c in r]

    if len(rows) != 8:
        raise ValueError(f"祝福树表应有 8 行，得到 {len(rows)}（{context}）")
    (root_title,) = cells(0, "th", 1)
    (root_text,) = cells(1, "td", 1)
    l2_titles = cells(2, "th", 2)
    l2_texts = cells(3, "td", 2)
    (l3_title,) = cells(4, "th", 1)
    (l3_text,) = cells(5, "td", 1)
    l4_titles = cells(6, "th", 4)
    l4_texts = cells(7, "td", 4)

    family = root_title.split("·")[0]
    nodes = []

    def node(level, path, title, text, parent):
        nid = f"{ruleset_id}/{family}/L{level}" + (f"/{path}" if path else "")
        nodes.append({
            "id": nid, "ruleset_id": ruleset_id, "family": family, "level": level, "path": path,
            "parent_id": parent, "title": title, "text": text, "text_hash": sha(text),
            "in_period": ruleset_id == "current" and family in PERIOD["families"],
            "verification": {"status": "candidate"},
        })
        return nid

    root = node(1, "", root_title, root_text, None)
    l2_ids = {}
    for t, x in zip(l2_titles, l2_texts):
        m = BRANCH_RE.match(t)
        if not m:
            raise ValueError(f"分支标题无法解析：{t}（{context}）")
        l2_ids[m.group(1)] = node(2, m.group(1), m.group(3), x, root)
    # “进阶”按父分支各一个节点：同名同文，但继承的 2 级分支不同
    l3_ids = {p: node(3, p, l3_title, l3_text, pid) for p, pid in l2_ids.items()}
    for t, x in zip(l4_titles, l4_texts):
        m = BRANCH_RE.match(t)
        if not m or not m.group(2):
            raise ValueError(f"末级分支标题无法解析：{t}（{context}）")
        node(4, m.group(1) + m.group(2), m.group(3), x, l3_ids[m.group(1)])
    return nodes


def parse_boons(rows, ruleset_id, category, context):
    header = [clean(c["text"]) for c in rows[0]]
    if header[:2] != ["名称", "内容"]:
        raise ValueError(f"神秘收获表头不符：{header}（{context}）")
    out = []
    for r in rows[1:]:
        if len(r) < 2:
            continue
        title, text = clean(r[0]["text"]), clean(r[1]["text"])
        flags = []
        if "奇妙助益" in text or category == "助益":
            # 奇妙助益已被辉彩祝福替代（见 #13 报告对 W1 的说明），这些词条是否仍会出现需当期核验
            flags.append("mentions-legacy-system")
        out.append({
            "id": f"{ruleset_id}/boon/{title}", "ruleset_id": ruleset_id, "category": category,
            "title": title, "text": text, "text_hash": sha(text), "flags": flags,
            "verification": {"status": "candidate"},
        })
    return out


LEGACY_RE = re.compile(r"（(\d{4})年(\d{1,2})月前）")


def build(src: Path) -> dict:
    html = (src / "theater.html").read_text(encoding="utf-8")
    w = Walker()
    w.feed(html)

    rev = re.search(r'"wgRevisionId":(\d+)', html) or re.search(r'"wgCurRevisionId":(\d+)', html)
    h = {"h2": "", "h3": "", "h4": "", "h5": ""}
    last_text = ""
    in_history = False
    blessings, boons, rulesets = [], [], {}
    rulesets["current"] = {
        "id": "current", "label": "现行表（快照时点）", "status": "candidate",
        "source_section": "5.0新增：辉彩祝福 / 神秘收获",
    }

    for ev in w.events:
        if ev[0] == "heading":
            _, tag, text = ev
            h[tag] = text
            for lower in [k for k in h if k > tag]:
                h[lower] = ""
            if tag == "h2":
                in_history = False
            if tag == "h3" and text == "加强历史":
                in_history = True
            continue
        if ev[0] == "text":
            last_text = ev[1]
            continue
        rows = ev[1]
        if not rows or not rows[0]:
            continue
        first = clean(rows[0][0]["text"])
        ctx = f"{h['h2']}/{h['h3']}/{h['h4']} first={first[:12]}"
        if first.endswith("·原态"):
            ruleset_id = "current"
            if in_history:
                m = LEGACY_RE.search(last_text) or LEGACY_RE.search(h["h4"]) or LEGACY_RE.search(h["h5"])
                if not m:
                    raise ValueError(f"历史表缺少“（YYYY年M月前）”标记（{ctx}）")
                ruleset_id = f"legacy-pre-{m.group(1)}-{int(m.group(2)):02d}"
                rulesets.setdefault(ruleset_id, {
                    "id": ruleset_id, "label": f"加强历史（{m.group(1)}年{int(m.group(2))}月前）", "status": "retired",
                    "retired_before": f"{m.group(1)}-{int(m.group(2)):02d}", "source_section": f"加强历史 / {h['h4']}",
                    "note": "只含被调整的反应族，不是完整期次快照",
                })
            blessings += parse_tree(rows, ruleset_id, ctx)
        elif h["h2"] == "神秘收获" and h["h3"] in BOON_CATEGORIES and first == "名称":
            boons += parse_boons(rows, "current", h["h3"], ctx)

    pack = {
        "pack_format": 1,
        "pack_id": f"bwiki-theater-rev{rev.group(1) if rev else 'unknown'}",
        "source": {
            "name": "BWIKI 幻想真境剧诗（社区维护，CC BY-NC-SA 4.0）", "url": SOURCE_URL,
            "revision_id": int(rev.group(1)) if rev else None, "snapshot_file": "theater.html",
            "snapshot_date": SNAPSHOT_DATE, "sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
            "trust": "第三方候选目录；不是官方注册表，不证明当期全集",
        },
        "scope": {
            "claimed": CLAIMED_SCOPE, "period_families": PERIOD["families"],
            "note": "scope 是声明，不是核验结果；每个条目各自带 verification",
        },
        "imported_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "importer": "prototypes/rulepack-title-matching/import_bwiki.py",
        "normalization": NORMALIZATION,
        "identity": {
            "blessing": "ruleset_id / family / level / path（path：L1 空，L2/L3 为 1|2，L4 为 1A|1B|2A|2B）；标题与文字是证据，不是主键",
            "boon": "ruleset_id / boon / title（标题在同一规则集内须唯一，由 check_rulepack.py 保证）",
        },
        "rulesets": list(rulesets.values()),
        "blessings": blessings,
        "boons": boons,
    }
    return pack


def apply_verification(pack: dict, reg_path: Path) -> int:
    if not reg_path.exists():
        return 0
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in pack["blessings"] + pack["boons"]}
    n = 0
    for item in reg["entries"]:
        e = by_id.get(item["id"])
        if not e:
            print(f"[verification] 未找到条目 {item['id']}，跳过", file=sys.stderr)
            continue
        e["verification"] = {
            "status": "verified", "verified_text_hash": e["text_hash"], "verified_on": item["verified_on"],
            "evidence": item["evidence"], "verified_fields": item["fields"], "note": item.get("note", ""),
        }
        n += 1
    return n


def inject(demo: Path, pack_json: str) -> None:
    s = demo.read_text(encoding="utf-8")
    start, end = "<!--RULEPACK-START-->", "<!--RULEPACK-END-->"
    a, b = s.find(start), s.find(end)
    if a < 0 or b < 0:
        sys.exit(f"{demo} 缺少注入标记 {start}/{end}")
    s = s[: a + len(start)] + "\n" + pack_json + "\n" + s[b:]
    demo.write_text(s, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "rulepack.json"))
    ap.add_argument("--inject", help="把规则包注入到这个单文件演示页")
    args = ap.parse_args()

    src = find_sources()
    pack = build(src)
    n = apply_verification(pack, HERE / "verification.json")
    text = json.dumps(pack, ensure_ascii=False, indent=1)
    Path(args.out).write_text(text + "\n", encoding="utf-8")
    fam = sorted({(b["ruleset_id"], b["family"]) for b in pack["blessings"]})
    print(f"来源：{src}")
    print(f"规则包 {pack['pack_id']}：规则集 {len(pack['rulesets'])}，祝福树 {len(fam)} 棵 / 节点 {len(pack['blessings'])}，"
          f"神秘收获 {len(pack['boons'])}，已核验条目 {n}")
    print(f"写入 {args.out}")
    if args.inject:
        inject(Path(args.inject), text)
        print(f"已注入 {args.inject}")


if __name__ == "__main__":
    main()

"""规则包结构校验与跨版本差异（原型，可抛弃）。只用标准库。

用法：
    python check_rulepack.py rulepack.json            # 结构校验 + 同名报告（Markdown 输出）
    python check_rulepack.py old.json --diff new.json # 两个规则包按身份比对：新增/删除/文字变化
结构校验失败时退出码非 0；同名只报告不判错，因为同名本身就是要暴露的事实。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load(p: str) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def structural(pack: dict) -> list[str]:
    errors = []
    ids = Counter(e["id"] for e in pack["blessings"] + pack["boons"])
    for i, n in ids.items():
        if n > 1:
            errors.append(f"身份重复：{i} ×{n}")
    by_id = {e["id"]: e for e in pack["blessings"]}
    trees = defaultdict(list)
    for b in pack["blessings"]:
        trees[(b["ruleset_id"], b["family"])].append(b)
    for (rs, fam), nodes in sorted(trees.items()):
        levels = Counter(n["level"] for n in nodes)
        if dict(levels) != {1: 1, 2: 2, 3: 2, 4: 4}:
            errors.append(f"树形不完整：{rs}/{fam} 各级数量 {dict(levels)}")
        for n in nodes:
            if n["level"] == 1 and n["parent_id"]:
                errors.append(f"原态不应有父节点：{n['id']}")
            if n["level"] > 1:
                p = by_id.get(n["parent_id"])
                if not p:
                    errors.append(f"父节点缺失：{n['id']} -> {n['parent_id']}")
                elif p["level"] != n["level"] - 1 or not n["path"].startswith(p["path"] or ""):
                    errors.append(f"父子路径不一致：{n['id']} 父 {p['id']}")
            if n["level"] == 3 and n["title"] != f"{fam}·进阶":
                errors.append(f"3 级标题不是“{fam}·进阶”：{n['id']} = {n['title']}")
    rs_ids = {r["id"] for r in pack["rulesets"]}
    for e in pack["blessings"] + pack["boons"]:
        if e["ruleset_id"] not in rs_ids:
            errors.append(f"条目引用未登记的规则集：{e['id']}")
    boon_titles = Counter((b["ruleset_id"], b["title"]) for b in pack["boons"])
    for (rs, t), n in boon_titles.items():
        if n > 1:
            errors.append(f"神秘收获标题在同一规则集内重复：{rs}/{t} ×{n}")
    return errors


def duplicate_report(pack: dict) -> list[str]:
    out = []
    by_title = defaultdict(list)
    for b in pack["blessings"]:
        by_title[b["title"]].append(b)
    same_ruleset, cross = [], []
    for title, nodes in sorted(by_title.items()):
        if len(nodes) < 2:
            continue
        rs = defaultdict(list)
        for n in nodes:
            rs[n["ruleset_id"]].append(n)
        for r, ns in rs.items():
            if len(ns) > 1 and not title.endswith("·进阶"):
                same_text = len({n["text_hash"] for n in ns}) == 1
                same_ruleset.append((title, r, [n["path"] for n in ns], same_text))
        if len(rs) > 1:
            texts = {n["text_hash"] for n in nodes}
            path_sets = {frozenset(n["path"] for n in ns) for ns in rs.values()}
            cross.append((title, sorted(rs), len(texts) > 1, len(path_sets) > 1))
    n_adv = sum(1 for t in by_title if t.endswith("·进阶"))
    out.append(f"- “X·进阶”标题 {n_adv} 个：每个反应族都有 2 个同名同文的 3 级节点（按父分支各一个），只能靠路径区分。")
    out.append(f"- 同一规则集内、同名不同路径的末级节点：{len(same_ruleset)} 组")
    for title, r, paths, same_text in same_ruleset:
        out.append(f"  - {title}（{r}）：路径 {'/'.join(paths)}，{'文字相同' if same_text else '文字不同'}；继承的 2 级分支不同，身份不能合并")
    out.append(f"- 跨规则集同名（现行表与加强历史）：{len(cross)} 个标题")
    for title, rss, text_diff, path_diff in cross:
        out.append(f"  - {title}：{' / '.join(rss)}；{'文字有变化' if text_diff else '文字相同'}，{'路径/位置有变化' if path_diff else '路径相同'}")
    flagged = [b for b in pack["boons"] if b.get("flags")]
    out.append(f"- 神秘收获共 {len(pack['boons'])} 条，标题在快照内无重名；带 mentions-legacy-system 标记（疑似旧系统“奇妙助益”）{len(flagged)} 条：{'、'.join(b['title'] for b in flagged)}")
    ver = [e for e in pack["blessings"] + pack["boons"] if e["verification"]["status"] == "verified"]
    out.append(f"- 已核验条目 {len(ver)} / {len(pack['blessings']) + len(pack['boons'])}；其余为候选，发布前不得标为“可出现”。")
    return out


def diff(old: dict, new: dict) -> list[str]:
    o = {e["id"]: e for e in old["blessings"] + old["boons"]}
    n = {e["id"]: e for e in new["blessings"] + new["boons"]}
    added = sorted(set(n) - set(o))
    removed = sorted(set(o) - set(n))
    changed = sorted(i for i in set(o) & set(n) if o[i]["text_hash"] != n[i]["text_hash"])
    out = [f"旧包 {old['pack_id']} → 新包 {new['pack_id']}", f"- 新增 {len(added)}：" + "、".join(added),
           f"- 删除 {len(removed)}：" + "、".join(removed), f"- 文字变化 {len(changed)}：" + "、".join(changed)]
    invalid = [i for i in changed if o[i]["verification"]["status"] == "verified"]
    out.append(f"- 其中旧包已核验、因文字变化而核验失效：{len(invalid)}：" + "、".join(invalid))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pack")
    ap.add_argument("--diff")
    args = ap.parse_args()
    pack = load(args.pack)
    errors = structural(pack)
    trees = {(b["ruleset_id"], b["family"]) for b in pack["blessings"]}
    print(f"## 规则包 {pack['pack_id']}")
    print(f"- 规则集：{', '.join(r['id'] for r in pack['rulesets'])}")
    print(f"- 祝福树 {len(trees)} 棵 / 节点 {len(pack['blessings'])}；神秘收获 {len(pack['boons'])}")
    print(f"- 结构校验：{'通过' if not errors else '失败'}")
    for e in errors:
        print(f"  - {e}")
    print("\n### 同名与核验状态")
    for line in duplicate_report(pack):
        print(line)
    if args.diff:
        print("\n### 跨版本差异")
        for line in diff(pack, load(args.diff)):
            print(line)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()

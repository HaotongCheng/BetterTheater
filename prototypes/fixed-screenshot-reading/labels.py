"""PROTOTYPE — ground truth for the fixed-screenshot experiment.

来源：代理逐图人工查看后标注，用户于 2026-09-30 逐项复核（32 项：31 项确认，S23 体力由用户纠正，“拒判页面范围”用户标不确定）；不是自动识别结果，也不是客户端实测之外的推断。
- NV = 画面中该字段不可见（被裁切/不在本页）。方法应输出“未读”，输出任何值都算误读。
- 未列出的字段 = 本次不评分。
- 角色身份用批内中性代号（S 批：P..W；E1 批：A..J），只表示“同一角色”，不对应角色名。
"""
NV = "NV"

# 本原型支持的页面类型；其余页面真值为 "unknown"，方法应拒判。
PAGE_TYPES = [
    "event_select", "details_roster", "details_blessing", "battle_preview",
    "battle_result_lineup", "post_battle_recruit", "companion_select",
    "battle_failed", "paused_resume", "rewind_result", "blessing_acquired",
]

LABELS = {
    # ---- 局前与其他页面：应拒判 ----
    "S01": {"page": "unknown"}, "S02": {"page": "unknown"}, "S03": {"page": "unknown"},
    "S04": {"page": "unknown"}, "S05": {"page": "unknown"}, "S06": {"page": "unknown"},
    "S07": {"page": "unknown"}, "S08": {"page": "unknown"},
    "E1:act-1-bloom-before": {"page": "unknown"},          # 祝福购买确认弹层
    "E1:unfinished-challenge-warning": {"page": "unknown"},  # 圣牌未完成提示弹层

    # ---- 事件页 ----
    "S09": {"page": "event_select", "act": 1, "crown": 8, "bloom": 0, "quicken": 0, "electro": 0,
            "balance": 280, "refresh": 3,
            "cards": [["+90", "战斗·普通"], ["+90", "战斗·普通"], ["-80", "伙伴·随机"], ["-60", "激化·原态"]]},
    "S17": {"page": "event_select", "act": 2, "crown": 10, "bloom": 0, "quicken": 2, "electro": 0,
            "balance": 135, "refresh": 3,
            "cards": [["+90", "战斗·普通"], ["-80", "伙伴·随机"], ["-60", "绽放·原态"], ["免费", "神秘收获"]]},
    "S20": {"page": "event_select", "act": 4, "crown": 11, "bloom": 0, "quicken": 2, "electro": 1,
            "balance": 140, "refresh": 2,   # 左侧裂隙入口使卡片整体右移
            "cards": [["+90", "战斗·守护桥段"], ["-70", "感电·分支"], ["-70", "激化·进阶"], ["-70", "绽放·原态"]]},
    "E1:act-1-bloom-after": {"page": "event_select", "act": 1, "crown": 9, "bloom": 1, "quicken": 0, "electro": 0,
            "balance": 85, "refresh": 3,
            "cards": [["+90", "战斗·普通"], ["+90", "战斗·普通"], ["-60", "感电·原态"], ["-60", "绽放·分支"]]},
    "E1:act-2-events": {"page": "event_select", "act": 2, "crown": 9, "bloom": 1, "quicken": 0, "electro": 0,
            "balance": 175, "refresh": 3,
            "cards": [["+90", "战斗·普通"], ["+90", "战斗·普通"], ["-60", "激化·原态"], ["免费", "神秘收获"]]},
    "E1:act-9-refresh-before": {"page": "event_select", "act": 9, "crown": 14, "bloom": 2, "quicken": 1, "electro": 3,
            "balance": 135, "refresh": 1,
            "cards": [["+90", "战斗·普通"], ["-80", "伙伴·水元素"], ["-60", "绽放·进阶"], ["-40", "神秘收获·珍贵"]]},
    "E1:act-9-refresh-after": {"page": "event_select", "act": 9, "crown": NV, "bloom": NV, "quicken": NV, "electro": NV,
            "balance": NV, "refresh": 0,    # 顶栏被用户裁掉
            "cards": [["+90", "战斗·普通"], ["+90", "战斗·普通"], ["-80", "伙伴·随机"], ["-80", "伙伴·水元素"]]},

    # ---- 演出详情 ----
    "S10": {"page": "details_roster", "crown": 8, "bloom": 0, "quicken": 0, "electro": 0, "balance": 280,
            "avail_levels": [90, 90, 90, 80, 80, 70], "stamina": [2, 2, 2, 2, 2, 2],
            "standby_visible_levels": 16,  # 另有一行8张半卡被裁切、Lv不可见；右侧有滚动条
            "standby_stats": [7, 10, 6]},   # 画面为 ×7 ×10 ×6
    "S18": {"page": "details_blessing", "crown": 10, "bloom": 0, "quicken": 2, "electro": 0, "balance": 135,
            "held": 2, "boons": ["伙伴·即兴特邀", "惊喜·近价交换"], "blessing_total": 10,
            "branch_levels": {"绽放": 0}},   # 激化/感电在滚动区下方，本帧不可见
    "S19": {"page": "details_blessing", "crown": 10, "bloom": 0, "quicken": 2, "electro": 0, "balance": 135,
            "held": NV, "boons": NV, "blessing_total": 10,
            "branch_levels": {"绽放": 0, "激化": 2, "感电": 0}},

    # ---- 战斗准备 ----
    "S11": {"page": "battle_preview", "title": "战斗·普通", "balance": 280, "reward": 90, "star_seconds": 80,
            "stamina": [2, 2, 2, 2, 2, 2], "ids": list("PQRSTW")},
    "S14": {"page": "battle_preview", "title": "战斗·精锐来袭", "balance": 25, "reward": 110, "star_seconds": 75,
            "stamina": [2] * 8, "ids": list("PQRSTUVW")},
    "E1:act-1-battle-before": {"page": "battle_preview", "title": NV, "balance": NV, "reward": 90, "star_seconds": 80,
            "stamina": [2] * 8, "ids": list("ABCDEFGH")},
    "E1:chariot-challenge": {"page": "battle_preview", "title": "月谕圣牌·七·战车", "balance": NV, "reward": 90,
            "star_seconds": 65},
    "E1:moon-challenge": {"page": "battle_preview", "title": "月谕圣牌·十八·月亮", "balance": NV, "reward": 90,
            "star_seconds": None},  # 明星条件是“击败18名敌人”，没有秒数

    # ---- 结算：本场阵容 ----
    "S15": {"page": "battle_result_lineup", "result": "成功", "time": "02:08", "reward": 110,
            "marks": ["✓", "✗"], "stamina": [1, 1, 1, 1], "ids": list("SRUV")},
    "E1:final-battle": {"page": "battle_result_lineup", "result": "成功", "time": "00:40", "reward": 125,
            "marks": ["✓", "✓"], "stamina": [0, 0, 0, 1]},   # 3人两格均灰仍显示

    # ---- 结算后选人 / 伙伴事件 ----
    "S16": {"page": "post_battle_recruit", "result": "成功", "time": "02:08", "cand_levels": [80, 71],
            "stamina": [2, 2, 2, 2, 1, 1, 1, 1], "ids": list("PQTWRSUV")},
    "E1:act-1-battle-after": {"page": "post_battle_recruit", "result": "成功", "time": "00:48", "cand_levels": [90, 71],
            "stamina": [2, 2, 2, 2, 1, 1, 1, 1], "ids": list("ACEFBDGH")},
    "E1:act-5-recruitment": {"page": "post_battle_recruit", "result": NV, "time": NV, "cand_levels": [90, 70],
            "stamina": [2, 2, 2, 2, 2, 1, 1]},
    "S12": {"page": "companion_select", "cand_levels": [71, 90, 80],
            "stamina": [2] * 6, "ids": list("PQRSTW")},
    "E1:act-1-recruitment-before": {"page": "companion_select", "cand_levels": [90, 80, 95],
            "stamina": [2] * 7, "ids": list("BCDEFGH")},

    # ---- 失败 / 暂离 / 回溯 / 获得结果 ----
    "S21": {"page": "battle_failed", "result": "失败", "countdown": 24},
    "S22": {"page": "paused_resume", "act": 4, "rewind_left": 2},
    "S23": {"page": "rewind_result", "act": 4, "visible_levels": [90, 90, 90, 90, 90, 90, 80],
            "stamina": [2, 2, 2, 2, 2, 1, 1]},   # 第8张卡被右侧截断，不计；用户复核时纠正第6张为1格
    "S13": {"page": "blessing_acquired", "branch": "激化", "title": "激化·原态"},
}

# 跨页身份关联测试：同一批次、头像样式（非卡片样式）页面之间。
IDENTITY_PAIRS = [
    ("S11", "S14"), ("S12", "S14"), ("S14", "S16"), ("S15", "S16"),
    ("E1:act-1-battle-before", "E1:act-1-battle-after"),
    ("E1:act-1-recruitment-before", "E1:act-1-battle-before"),
]

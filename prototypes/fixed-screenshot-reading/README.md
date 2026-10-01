# 固定截图读取原型（可抛弃）

对应票：[用固定截图验证页面定位与字段读取的方法](https://github.com/HaotongCheng/BetterTheater/issues/15)。
这是决策材料，不是产品架构；阈值与锚点偏移都在同一批样本上调过，没有留出集。

## 运行

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install opencv-python-headless numpy pillow rapidocr_onnxruntime winocr
.venv\Scripts\python ocr_cache.py   # 全屏 OCR 一次（Rapid + Windows OCR），写 out/ocr_cache.json
.venv\Scripts\python run.py         # 跑全部候选方法，写 out/results.json 与 out/report.html
```

截图从主检出的 `docs/research/assets/`（未入库）读取，可用环境变量 `BT_ASSETS` 改路径。
`out/` 已忽略：报告内嵌截图裁片与 UID，不要提交。

## 文件

- `samples.py`：样本登记。S01–S23 为 2560×1440 用户截图；`E1:*` 为旧合作局 13 张用户裁切图。
- `labels.py`：真值。代理逐图人工标注，**待用户复核**；`NV` 表示画面不可见、方法应输出未读。
- `textread.py`：按固定文案锚点判页（11 种页面 + 拒判），再按锚点相对位置读字段；不写死坐标。
- `vision.py`：体力格模板匹配（模板取自 S15 一张图）、头像身份直方图配对、目标勾叉颜色判定。
- `run.py`：跑 R0/R1/R2/W1、V1/V2、I1/I2，评分并生成报告。

## 候选方法

| 代号 | 方法 |
|---|---|
| R0 | 固定比例坐标 ROI + 局部 OCR（对照基线，只跑事件页） |
| R1 | RapidOCR（PaddleOCR v4 ONNX，本地）全屏一次 → 锚点判页 → 相对位置读字段 |
| R2 | R1 + 对“未读”字段按锚点裁小图放大补读一次 |
| W1 | Windows 内置 OCR（zh-Hans）全屏一次 → 同一套判页与解析 |
| V1 / V2 | 体力格：边缘模板 / 饱和度模板找亮格 + 边缘模板找灰格，再按间距分人 |
| I1 / I2 | 跨页身份：头像 HSV 直方图 / 灰度相关，穷举最优配对 |

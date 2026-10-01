# BetterGI 对小字数字与局部文本的识别路径

日期：2026-09-30。对应[核实 BetterGI 对小字数字与局部文本的识别路径](https://github.com/HaotongCheng/BetterTheater/issues/26)。源码固定于 [`42e1c0e745670eb4443c1e0357fba963eb24dfcd`](https://github.com/babalae/better-genshin-impact/tree/42e1c0e745670eb4443c1e0357fba963eb24dfcd)，所有源码链接均指向该提交。本票只读公开源码与 `Docs/`，未运行 BetterGI、未登录、未复制代码（根许可证 GPL v3，只归纳与链接）。

本笔记接续 [BetterGI 画面识别参考调研](https://github.com/HaotongCheng/BetterTheater/blob/9816fda/docs/research/bettergi-reference.md)（捕获、ROI 坐标体系、`ImageRegion` 的识别类型、调度与稳定性组件、剧诗模块不存在等已写明，不再重复）。本票只深入 OCR 的局部路径与预处理：`OcrWithoutDetector` 的使用条件与输入尺寸处理、裁剪放大、颜色范围提取、方向分类、替换词典与白名单、数字专用路径与后处理、整屏与局部的取舍、耗时与准确率说明。

标记约定：**【已证实】**来自固定提交源码或 Docs 的静态阅读；**【推断】**是由源码推出但上游没有明说的结论；**【未实测】**是本票没有运行或测量的事项。

## 结论

1. **【已证实】上游有两条 OCR 入口，但没有"整屏一次再派发字段"的用法。**`PaddleOcrService` 提供完整路径（Det 检测 + Rec 识别，`OcrResult`/`Ocr`）与仅识别路径（`OcrWithoutDetector`，直接把整张输入图当作一行文字送 Rec）。所调研的所有调用点都先用模板/锚点定位，再裁出 1080p 坐标系下几十像素高的小区域送 OCR；整张截图在进入任何识别前已缩到宽 1920。
2. **【已证实】`OcrWithoutDetector` 用于"已知位置、单行、短文本/数字"的字段**：拾取物名、树脂当前/上限、浓缩树脂数量、背包格数量、技能 CD 秒数、骰子数、任务距离、便携营养袋数量判定、快捷使用数量。输入高度一律归一到 48，宽度按原比例 `ceil(w/h×48)`，不补边、不裁宽；配置里的 320 只是名义值。
3. **【已证实】上游没有方向分类（cls）模型。**模型注册表只有 Det/Rec；完整路径对高宽比 ≥1.5 的检测框逆时针旋 90°，没有 180° 判断；仅识别路径不做任何旋转。
4. **【已证实】"读数字"没有专用模型或字符白名单，靠的是裁剪 + 预处理 + 正则/范围校验。**预处理分三类：灰度阈值二值化后反色（树脂）、颜色范围 `InRange`（白色 CD 数字、HLS 高亮选项文字、HSV 深灰数量）、放大后连通域紧裁再归一化（背包数量，放大 3 倍）。后处理有全角转半角、去非数字、分隔符容错正则、圈数字替换、按笔画结构修正 1/7、范围校验；失败返回 null/-2/0 而非硬改。
5. **【已证实】替换词典是字段级字符串替换，白名单是业务词表**：`RecognitionObject.ReplaceDictionary`（键为正确文本，值为误识别列表）在去空格后逐项 `Replace`；`Recognition.json` 暴露 `replace`/`allContains`/`oneContains`/`regex`。拾取白/黑名单是 JSON+TXT 词表，精确匹配。
6. **【未实测】上游没有任何耗时或准确率的数字说明。**计时代码存在但只在 Debug 输出或被注释；单元测试用合成字图与 1080p 截图做"是否正确"断言，不记录耗时；README 只说"图像识别比较吃性能"并推荐 1920×1080。

## 范围与方法

- 读取的核心文件：`PaddleOcrService.cs`、`Rec.cs`、`Det.cs`、`DbPostProcessor.cs`、`OcrUtils.cs`、`OcrVersionConfig.cs`、`OcrFactory.cs`、`IOcrService.cs`、`OcrResult.cs`、`BgiOnnxModel.cs`、`OtherConfig.cs`、`ImageRegion.cs`、`RecognitionObject.cs`、`RecognitionTypes.cs`、`OpenCvCommonHelper.cs`、`AutoPickTrigger.cs`、`TextRectExtractor.cs`、`PickTextInference.cs`、`CaptureContent.cs`、`GameCaptureRegion.cs`、`SystemInfo.cs`、`StringUtils.cs`、`RegexHelper.cs`，以及 `Docs/technical/recognition-json.md`、根 README。
- 数字/短文本用例：`ResinStatus.cs`、`ResinRecognition.cs`、`AutoBossTask.cs`、`GridItemCountRecognizer.cs`、`GridScreenExtensions.cs`、`AutoEatTask.cs`、`AutoDomainTask.cs`、`SkillCdTrigger.cs`、`Avatar.cs`、`AutoLeyLineOutcropTask.cs`、`GeniusInvokationControl.cs`、`AutoTrackTask.cs`、`BvOcr.cs`、`BvStatus.cs`、`AutoArtifactSalvageTask.cs`、`AutoWoodTask.cs`、`TpTask.cs`、`QuickTeleportTrigger.cs`。
- 用 GitHub code search 枚举 `OcrWithoutDetector`、`ColorRangeAndOcr`、`ReplaceDictionary`、`RotateFlags`、`DropScore` 的调用文件，再逐一在固定提交取回核对。code search 只反映调研时的默认分支索引，文件内容以固定提交为准。
- 单元测试目录只看了 `OCRTests/` 与 `ResinStatusTests.cs`，用于判断上游有没有记录准确率/耗时。

## OCR 核心路径

### 两条入口

**【已证实】**`IOcrService` 只有三个方法：`Ocr`（返回拼接文本）、`OcrResult`（返回带框和分数的区域列表）、`OcrWithoutDetector`（返回字符串）。[1] 完整路径 `RunAll`：Det 出框 → 按 y/x 排序 → 对每个框做透视裁剪 → Rec 批量识别 → 过滤 `Score < DropScore(0.5)`。[2] `OcrWithoutDetector` 直接 `Rec.Run(mat)`，不经过 Det、不过滤分数、不返回分数。[3] 这意味着仅识别路径的调用方必须自己校验结果（上游所有用例都配了正则或范围校验）。

### Det 的输入尺寸处理

**【已证实】**`Det` 按 PaddleOCR 的 `DetResizeForTest` 规则缩放：`LimitSideLen = 960`、`LimitType = "max"`、`MaxSideLimit = 4000`；长边超过 960 时按比例缩小，宽高各自取整到 32 的倍数；`w + h < 64` 的超小图先补黑边到至少 32×32。[4] 后处理阈值 `BoxThreshold = 0.3`、`BoxScoreThreshold = 0.6`、`UnclipRatio = 1.5`、`MinSize = 3`、不开膨胀。[5]

**【推断】**上游截图先缩到 1920×1080（见下文"捕获整体缩放"），整屏送 Det 时再缩到 960×544，即原 1080p 画面的 0.5 倍；若把 2560×1440 原图直接送同样参数的 Det，则是 0.375 倍。1080p 下 20 px 高的数字在 Det 输入里只剩 10 px，接近 `MinSize` 与 unclip 的下限。这是上游不整屏 OCR 的一个结构性原因，但上游没有明说。

### Rec 的输入尺寸处理

**【已证实】**`OcrVersionConfig` 为 V4/V5/V6 都声明 `OcrShape(3, 320, 48)`，但 `Rec.RunMulti` 不用 320：它先按批内最大的 `w/h × 48` 算出 `maxWidth`，再把每张图按自身比例缩到 `(ceil(w/h×48), 48)`，没有补边到统一宽度，也没有把宽度截断到 320；插值为 Linear；像素归一到约 [-1, 1]。[6][7] 批处理只是把同宽度的图排在一起，推理仍逐张进行，且 Det/Rec 的 session 都加了锁（注释说多线程推理会出问题），所以 OCR 调用在进程内是串行的。[6][4]

**【已证实】**单通道输入会被转成三通道（GRAY2BGR），四通道转 BGR；注释说三通道最快。[6][3] 解码为 CTC 贪心：取每列最大概率的字符，跳过空白与重复，分数是所选字符概率的平均。[6]

**【推断】**由于 Rec 总会把输入重采样到高 48，调用方在送入前把裁片放大 N 倍，对 Rec 本身只影响插值质量（Linear 上采样一次与先放大再下采样的差别），真正的收益来自放大后更稳的前景提取与连通域过滤（见 `GridItemCountRecognizer`），以及全路径时 Det 不再漏掉单字符。

### 方向分类

**【已证实】**模型注册表里只有 Det V4/V5/V6 与 Rec V4/V4En/V5/V5Latin/V5Eslav/V5Korean/V6，没有 cls 模型；固定提交文件树中也没有 `cls` 相关资源。[8] 完整路径对透视裁剪后 `h/w ≥ 1.5` 的框逆时针旋 90°，这是唯一的旋转逻辑；没有 180° 判断。[2] `OcrWithoutDetector` 不做任何旋转。[3] GitHub code search `RotateFlags` 只命中 OCR 服务、小地图相机朝向与一个占位 trigger。

### 模型与语言选择

**【已证实】**`OtherConfig.Ocr.PaddleOcrModelConfig` 默认 `V4Auto`：游戏语言为 zh-Hans 时用 V4 中文 Det+Rec；为 en 时用 `V4En`（`en_PP-OCRv4_mobile_rec` 英文/数字识别模型，预热图是 `test_pp_ocr_number.png`）；繁体走 V5；其他语言按拉丁/斯拉夫/韩文选 V5 子模型。V5/V6 需手动切换。[9][10] 没有"中文界面但数字字段改用英文/数字模型"的路径。

### 捕获整体缩放到 1080p

**【已证实】**`CaptureContent` 构造时对截图 `DeriveTo1080P()`：宽 > 1920 时整张缩到宽 1920（高按比例）；任务层 `TaskControl.CaptureToRectArea()` 同样经过这一步。[11][12] `SystemInfo.AssetScale` 不会大于 1（宽 < 1920 时按比例缩小素材），`ScaleMax1080PCaptureRect` 在宽 > 1920 时固定为 1920 宽。[13] 因此所有 ROI 常量都是 1080p 坐标乘 `AssetScale(≤1)`；在 2560×1440 窗口下，上游 OCR 看到的是降采样后的 1920×1080 图，而不是原生分辨率。README 也声明只支持 16:9，推荐 1920×1080 窗口化。[14]

## 局部路径的具体用法

下表汇总所有找到的数字/短文本用例。尺寸为 1080p 坐标（实际乘 `AssetScale`）。"极性"指送入 OCR 的图是白字黑底还是黑字白底。

| 用例 | 定位 | 裁片尺寸 | 预处理 | 入口 | 后处理 / 校验 | 来源 |
|---|---|---|---|---|---|---|
| 拾取物名（AutoPick） | 模板找 F 键，文字区 = F 键右 115～400 px、同高 | 285×F 键高 | Sobel 梯度判断是否正在拾取；灰度阈值 160 二值 + 腐蚀/膨胀 + 列投影（允许 30 列空隙）求文字右边界，右边再留 5 px；原图彩色裁到该宽度 | `OcrWithoutDetector`；找不到有效区域回退 `Ocr` | 去空白、`【[`→`「`、`】]`→`」`、裁掉两端非中文/非引号字符、补配对引号；单字不拾取；白/黑名单精确匹配、模糊黑名单 Contains | [15][16][17] |
| 拾取物名（Yap 引擎，可选） | 同上 | 同上 | 灰度，强制缩到 221×32 后补黑边到 384×32 | 独立 SVTR 模型 | 同上 | [18][19] |
| F 键文字（`Bv.FindFKeyText`） | 同上 | 同上 | `InRange` 取 RGB 254～255 的纯白，开运算 + 膨胀，取外接矩形，右边留 3 px | `OcrWithoutDetector`，否则 `Ocr` | 无 | [20] |
| 原粹树脂当前/上限（秘境） | 模板找树脂图标，数字区 = 图标右 +25 px | 110×24 | 无（彩色原图） | `OcrWithoutDetector` | 正则 `(\d+)\s*[/17]\s*(2|20|200)`：斜杠可能被读成 1 或 7，所以把 `/`、`1`、`7` 都当分隔符 | [21] |
| 浓缩树脂数量（秘境） | 原粹图标左 180 px 内再找浓缩图标，数字区 = 图标右 +20 px | 30×图标高 | 灰度阈值 180 二值 → 反色（黑字白底） | `OcrWithoutDetector` | 去非数字后 `int.TryParse` | [21] |
| 树脂（大地图顶栏） | 同上 | 105×25 / 30×图标高 | 两处都阈值 180 + 反色 | `OcrWithoutDetector` | 全角转半角；`(\d{1,3})\s*[/17]\s*(200)`；浓缩数限 0～5，否则 null | [22] |
| 树脂上限 / 恢复时间（AutoBoss） | 同上 | 120×24；详情弹窗 | 无 | 上限用 `OcrWithoutDetector`，弹窗用 `OcrResult` 后按中心点排序拼接 | 去非数字取末三位；`\d{1,3}:\d{2}:\d{2}` | [23] |
| 快捷使用数量（AutoBoss） | 固定 ROI | 72×29；93×81 | 无 | `OcrWithoutDetector`；`OcrResult` | 全角转半角、去空白、取最大数字 / `使用数量\D*(\d+)` | [23] |
| 背包格数量（`GridItemCountRecognizer`） | 格子固定比例裁底部 | 格子高的 128/153～150/153 | 放大 3 倍 → HSV `InRange(S≤140, V≤210)` 取深灰数字 → 外轮廓过滤（高 ≥12、面积 ≥20、底边 ≥ 区域高 55%）→ 合并紧裁 → 反色 → 等比缩到高 48（Nearest）→ 白底画布左右各留 24 px、上下各留 6 px | `OcrWithoutDetector` | 全角转半角、严格纯数字；单连通域且宽高比 ≤0.45 判为 1；单连通域宽高比 ≥0.65 却读成 1 则改 7；失败 -2 并带原因 | [24] |
| 背包格数量（旧路径，AutoEat） | 同上 | 同上 | 放大 2 倍 | `Ocr`（完整路径） | 全角转半角、`int.TryParse` | [25][26] |
| 便携营养袋判定（AutoEat/AutoDomain） | 固定 ROI (1800,845) | 40×20 | 灰度 | `OcrWithoutDetector` | 能 `int.TryParse` 即视为装备了营养袋 | [26][27] |
| 元素战技 CD（SkillCd / Avatar / LeyLine） | 右下固定 ROI | 41×18 | `InRange` 取白：BGR 230～255，或 HSV S≤25、V≥235 | `OcrWithoutDetector` | `\d+(\.\d+)?` 或 `TryParseDouble`；SkillCd 减去两帧补偿并限 (0,60)；Avatar 限 ≤ 角色技能 CD | [28][29][30][31] |
| 骰子数（七圣召唤） | 固定 ROI (68,642) | 25×31 | 灰度 | `OcrWithoutDetector` | 去空格、①～⑮ 替换成 1～15、`^[0-9]+$` 全数字才接受，否则 -10 并在 Debug 保存图片 | [32][33] |
| 角色 HP（七圣召唤） | 卡片位置偏移 | 配置矩形 | 无 | `Ocr`（完整路径） | `^[0-9]+$` | [32] |
| 任务距离（AutoTrack） | 先对派蒙菜单右侧 300×100 做 `Ocr` FindMulti，取长度 <8 且含 `m` 的区域作为后续 ROI | 该区域 | 灰度 | 之后反复 `OcrWithoutDetector` | 去非数字，≤3 即到达 | [34] |
| 树脂计数（LeyLine） | 模板找图标 | 200×40 / 90×40 | 灰度 | `OcrWithoutDetector` | `(\d{1,3})\s*/\s*\d+`；浓缩读不出时**回退到 0～5 的白色数字模板匹配** | [35] |
| UID | 固定 ROI (1683,1051) | 234×28 | 无 | `RecognitionObject.Ocr`（完整路径） | 拼接所有 `\d+` | [36] |
| 圣遗物词条 | 卡片固定比例 | 多块 | 灰度；主词条 TopHat(15×15) + 阈值 30；副词条不处理（注释：不处理效果最好） | `OcrResult` | `Score > 0.5`、副词条必须贴左边、`^\+(\d*)$` 且 0～20 | [37] |
| 传送候选 / 区域名 | 模板找图标，右侧 200～220 宽 | 图标高 +16 | `ColorRangeAndOcr`：BGR2HLS，L 245～255、S ≤15，只取高亮白字 | 完整路径（`ImageRegion.Find`） | 去 `>`；长度 ≤1 视为误匹配；区域名用 `ReplaceDictionary`（渊下宮→渊下宫、蒙徳→蒙德、娜塔→纳塔） | [38][39] |
| 伐木统计 | 固定 ROI | 300×250 | 无 | `Ocr` | `([^\d\n]+)[×x](\d+)`；多帧 OCR 取最佳结果 | [40] |

**【已证实】**`ImageRegion.Find` 的 `ColorRangeAndOcr` 分支：按 `ColorConversionCode` 转色彩空间后 `InRange` 得到单通道掩膜（白字黑底），直接送完整路径；`Ocr`/`OcrMatch` 分支都是完整路径，`ImageRegion` 本身不调用 `OcrWithoutDetector`。[41] 仅识别路径只在具体任务代码里出现。

**【推断】**从用例看，`OcrWithoutDetector` 的启用条件是三个同时满足：位置已由模板/锚点/固定比例确定；内容是单行短文本或数字；裁片内除目标外没有其他文字。满足前两条但裁片可能含多行或含图标时，上游改用完整路径再按位置筛选区域（圣遗物、树脂详情弹窗、任务文字第一次定位）。

**【已证实】**上游两种极性都有：树脂与背包数量反色成黑字白底送 Rec；`ColorRangeAndOcr`、CD 数字、F 键文字是白字黑底掩膜。没有注释说明哪种更好。**【未实测】**两种极性对 PP-OCR Rec 的影响。

## 替换词典、白名单与正则

- **【已证实】替换词典。**`RecognitionObject.ReplaceDictionary` 类型为 `Dictionary<string, string[]>`，键是正确文本，值是误识别形式列表；`ImageRegion.ApplyTextReplacements` 在 `RemoveAllSpace` 之后对整段文本逐项 `string.Replace`；`FindMulti` 对每个区域文本单独替换。[41][42] `Recognition.json` 的 `replace` 字段与之对应，文档示例为 `"播放": ["播故", "搰放"]`。[43]
- **【已证实】匹配规则。**`OcrMatch` 需要 `allContains` 全部命中、`oneContains` 任一命中、`regex` 列表全部命中；三者可组合。[41][43] `ColorMatch`/`ColorRangeAndOcr` 的 `colorCode`、`lowerColor`、`upperColor` 支持 1～4 个数字。[43]
- **【已证实】白名单/黑名单。**拾取名单来自 `Assets\Config\Pick\default_pick_*.json` 与 `User\pick_*.txt`，按行读入 `HashSet` 精确匹配，模糊黑名单用 `Contains`。[15] 这是业务词表，不是 OCR 字符白名单。
- **【已证实】没有字符级白名单或数字专用模式。**Rec 的字典来自模型目录 `inference.yml` 的 `character_dict`，全量加载；没有把输出限制在 0～9 的参数。[2][6] 唯一偏数字的模型是 `V4En`，且只在游戏语言为 en 时启用。[9]
- **【已证实】数字后处理工具。**`StringUtils.ConvertFullWidthNumToHalfWidth`（全角数字转半角）、`TryExtractPositiveInt`（去掉所有非数字再解析）、`RegexHelper.FullNumberRegex`（`^[0-9]+$`）。[44][45] 具体用例的容错见上表：分隔符 `[/17]`、圈数字替换、`+`/`%` 的正则、按连通域宽高比修正 1/7。

## 整屏一次 vs 局部多次

**【已证实】**

- 所有找到的 OCR 调用都带 ROI（`RegionOfInterest`、`DeriveCrop` 或 `new Mat(src, rect)`）；`RecognitionObject.OcrThis` 在相册任务里也是对已裁出的区域使用。没有对整帧跑一次 OCR 再从结果里取多个字段的代码。
- 每帧的默认工作是模板匹配定位（例如拾取先找 F 键，没找到就不 OCR）；OCR 只在定位命中后执行，且拾取还用 Sobel 梯度跳过"正在拾取"的帧。[15]
- 整帧先缩到 1080p；Det 再缩到长边 960；Det/Rec session 加锁串行。[11][4][6]
- `GridItemCountRecognizer` 的注释直接给出选择仅识别路径的理由："固定区域已经完成前景定位，直接调用无检测器 OCR，避免单字符 1 被检测阶段漏掉"。[24]
- `AutoPick` 对仅识别路径失败时回退完整路径，`LeyLine` 对浓缩树脂 OCR 失败时回退数字模板匹配。[15][35]

**【推断】**上游"局部多次"的取舍依据是：位置能由更便宜且更稳的模板匹配先确定；小字在 Det 下采样后容易漏检；仅识别路径没有检测开销且对单字符更稳；每个字段可以配自己的预处理与校验。上游没有写下这些理由，也没有比较数据。

**【未实测】**上游在 2560×1440 原生分辨率下的小字表现（上游根本不在该分辨率下跑 OCR）。

## 耗时与准确率说明

**【已证实】**

- `PaddleOcrService` 两条入口都有 `Stopwatch` 计时，但输出语句被注释；`AutoPickTrigger` 用 `SpeedTimer` 记录"识别到拾取键/识别聊天图标/文字识别/白名单判断"各阶段，只在 Debug 打印；Yap 推理有 Debug 耗时输出。[2][3][15][18] 没有任何文档或注释给出毫秒数或准确率。
- `BgiOnnxFactory` 支持 CPU、DirectML、CUDA/TensorRT、OpenVINO 多种 provider（注释称 OpenVINO 目前比 DML 强），耗时随设备不同，上游未给基准。[46]
- 单元测试：`PaddleOcrServiceTests` 用 Arial 12pt 在白底上画多语言词再断言识别结果；`ResinStatusTests` 用四张 1080p 截图断言树脂数量（V4/V5 各有用例）。两者都是"是否正确"的断言，不含耗时与错误率统计。[47][48]
- `GridItemCountRecognizer` 的默认参数注释为"经实测使用的默认预处理参数"，但没有附实测数据。[24]
- README 只说明"图像识别比较吃性能，低配置电脑可能无法正常使用部分功能"，并推荐 1920×1080 窗口化。[14]

**【未实测】**本票没有测量 PP-OCR Det/Rec 任一路径的耗时，也没有验证上游参数在剧诗界面上的准确率。

## 对 BetterTheater 的可借鉴点

本项目只读画面、不模拟输入、不读内存。以下按原型遇到的具体问题逐条给出上游做法的适用性判断，不替项目做最终选型。

### 全屏一次中位 1.7 s、最大 3.2 s（2560×1440，RapidOCR）

- **上游做法：**不整屏 OCR；整帧先缩到 1920 宽；每帧只做模板定位，OCR 只对命中后的几十像素高裁片执行。
- **适用性判断：**原型已经用固定文案锚点判页，锚点本身仍来自整屏 OCR，所以每张图至少付一次全屏 Det 的代价。可以借鉴的拆分是：页面判定改用模板/颜色等更便宜的方法或只对少数固定锚点区域 OCR；字段读取改为"锚点 → 偏移裁片 → 仅识别"。**【推断】**若保留整屏 Det，先把 2560×1440 缩到 1920 宽不会损失 Det 可见的信息（Det 内部还会缩到 960），只省掉一次缩放成本；收益大小**【未实测】**。**【未实测】**RapidOCR 的 det `limit_side_len`/`limit_type` 是否与上游一致（本票未读 RapidOCR 源码）；若也是 960/max，则全屏输入的小字在 Det 里只剩原图 0.375 倍，这与"刷新次数角标全屏读不出"相符，但需要核对。

### 价格前的花朵图标被读成 "@"/"β"

- **上游做法：**用模板匹配定位图标，再从图标右边缘加固定偏移裁出纯文字区（树脂数字区 = 图标右 +25 px），把图标排除在 OCR 输入之外；或用颜色范围只保留文字颜色（HLS 高亮白、HSV 深灰），让图标在掩膜里消失。
- **适用性判断：**适用。花朵图标形状固定，可以当作锚点模板；价格文字颜色若与图标不同，颜色范围提取也能去掉图标。两种方法都不依赖输入模拟。需要注意上游 `ColorRangeAndOcr` 输出白字黑底掩膜走完整路径，而树脂路径是反色黑字白底走仅识别，上游没有说明哪种更好，需在本项目样本上比较（**【未实测】**）。

### "+90" 在方向分类开启时偶尔被转 180° 读成 "06+"

- **上游做法：**没有 cls 模型；仅识别路径不做任何旋转；完整路径只按高宽比 ≥1.5 旋 90°。
- **适用性判断：**关闭方向分类与上游一致；对已知水平的短文本，仅识别路径天然不会出现 180° 翻转。`+` 号本身能否稳定识别，上游没有对应用例（圣遗物的 `+` 是在完整路径下用正则 `^\+(\d*)$` 匹配的），需要本项目样本验证（**【未实测】**）。

### 刷新次数角标（单个数字、带圆底）全屏读不出、裁小放大 3 倍后可读

- **上游做法：**最接近的是 `GridItemCountRecognizer`：固定比例裁片 → 放大 3 倍 → HSV 范围取数字前景 → 连通域过滤与紧裁 → 反色 → 等比缩到高 48 → 白底画布四周留白 → 仅识别 → 严格纯数字 + 按宽高比修正 1/7。另有 `LeyLine` 对 0～5 的白色单数字用模板匹配兜底。
- **适用性判断：**适用，且解释了原型"放大后可读"的机制：Rec 会把输入重采样到高 48，放大本身不是关键；关键是全屏 Det 漏掉了单字符，而裁小后要么 Det 能检出、要么直接走仅识别。圆底可以用颜色范围去掉（上游用低饱和低明度取深灰数字，本项目角标颜色需自定阈值）；留白与极性是上游明确处理过的细节。候选值只有个位数时，单数字模板匹配是另一条可比较的路径。放大倍数对本项目字段的实际影响**【未实测】**。

### Windows 内置 OCR 0.1 s，但中文按字切、顶栏多个 "Lv.N" 并成一行、"Lv.0" 读成 "Lv.O"

- **上游做法：**没有 Windows OCR 路径。相关的是：每个字段单独裁片仅识别，天然不会把多个 `Lv.N` 并到一行；`ReplaceDictionary` 做字段级字符串替换（设计用途正是 "播故→播放" 这类固定误读）；数字字段去非数字、全角转半角、分隔符容错正则、范围校验。
- **适用性判断：**原型的 `DIGIT_FIX`（O→0、I/l/|→1）与上游替换词典思路一致，建议把替换限定在具体字段解析器内并保留原文（原型已这样做）。按字段裁片后，无论用哪种引擎，"并成一行"的问题都转为"裁片是否只含一个字段"。Windows OCR 本身能否接受仅识别式的裁片输入，上游没有可借鉴的证据（**【未实测】**）。

### 共通原则

- **【已证实】**上游每条数字路径都有范围校验（浓缩树脂 0～5、圣遗物等级 0～20、CD <60、树脂上限 200）与失败值（null/-2/0/-10），不把不合法结果硬改成合法值；仅识别路径没有分数，校验必须由调用方完成。这与已有笔记的建议一致。
- **【已证实】**上游参数（阈值 160/180、HSV/HLS 范围、留白像素、放大倍数）都是针对原神特定 UI 调出来的，没有通用性说明；本项目应把它们当作"要试的候选"而不是直接采用的常量。
- 许可证：以上只借鉴流程与参数，不复制实现；若后续要引入上游代码或模型，需按已有笔记的提醒逐项核对许可证。

## 未实测与未证实项

- 未运行 BetterGI，未测量任一路径的耗时与错误率。
- 未读 RapidOCR 源码；RapidOCR 的 Det 缩放参数、是否默认启用 cls、Rec 输入高度是否同为 48，均未核对。
- 未验证两种极性（白字黑底 / 黑字白底）、放大倍数、留白像素对本项目字段的实际影响。
- 未验证 `+`、`×`、`·` 等符号在仅识别路径下的稳定性。
- Yap/SVTR 拾取模型的精度与适用范围未知，且它是为单一场景训练的。
- GitHub code search 结果为调研时索引，可能遗漏固定提交中的其他调用点；本票已对命中的文件逐一在固定提交核对。

## 主要一手来源

- [1] [IOcrService](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/IOcrService.cs#L5-L12)
- [2] [PaddleOcrService：DropScore、RunAll、GetRotateCropImage、模型类型与语言选择](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/PaddleOcrService.cs#L31-L32)（[RunAll L313-L333](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/PaddleOcrService.cs#L313-L333)、[旋转 L369-L372](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/PaddleOcrService.cs#L369-L372)、[字典加载 L48-L89](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/PaddleOcrService.cs#L48-L89)）
- [3] [PaddleOcrService.OcrWithoutDetector](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/PaddleOcrService.cs#L289-L299)
- [4] [Det：缩放参数与 MatResizeForDetection](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/Det.cs#L16-L41)（[缩放实现 L130-L190](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/Det.cs#L130-L190)、[session 锁 L101](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/Det.cs#L101)）
- [5] [DbPostProcessor](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/DbPostProcessor.cs#L25-L90)
- [6] [Rec：高度/宽度计算、通道转换、锁、CTC 解码](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/Rec.cs#L50-L194)
- [7] [OcrUtils.ResizeNormImg](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Engine/OcrUtils.cs#L111-L164)、[OcrVersionConfig](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Engine/OcrVersionConfig.cs#L28-L36)、[OcrShape](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Engine/data/OcrShape.cs#L6)
- [8] [BgiOnnxModel：模型注册表](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/ONNX/BgiOnnxModel.cs#L76-L134)、[固定提交文件树](https://github.com/babalae/better-genshin-impact/tree/42e1c0e745670eb4443c1e0357fba963eb24dfcd)
- [9] [PaddleOcrService.PaddleOcrModelType.V4En 与 FromCultureInfoV4](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/PaddleOcrService.cs#L117-L249)
- [10] [OcrFactory.CreatePaddleOcrInstance](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/OcrFactory.cs#L88-L124)、[OtherConfig.Ocr 默认 V4Auto](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Config/OtherConfig.cs#L105-L112)
- [11] [CaptureContent：DeriveTo1080P](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/CaptureContent.cs#L24-L32)、[GameCaptureRegion.DeriveTo1080P](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Model/Area/GameCaptureRegion.cs#L64-L78)
- [12] [TaskControl.CaptureToRectArea](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Common/TaskControl.cs#L311-L316)
- [13] [SystemInfo：AssetScale 与 ScaleMax1080PCaptureRect](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Model/SystemInfo.cs#L83-L101)
- [14] [README：性能与分辨率说明](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/README.md#L84-L95)
- [15] [AutoPickTrigger：名单加载、文字区、Sobel、引擎切换与回退、ProcessOcrText](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoPick/AutoPickTrigger.cs#L278-L339)（[名单 L80-L99](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoPick/AutoPickTrigger.cs#L80-L99)、[文本清理 L513-L611](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoPick/AutoPickTrigger.cs#L513-L611)、[计时 L189-L403](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoPick/AutoPickTrigger.cs#L189-L403)）
- [16] [TextRectExtractor：二值化、形态学、列投影](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoPick/TextRectExtractor.cs#L18-L121)
- [17] [AutoPickConfig：文字区偏移与引擎选项](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoPick/AutoPickConfig.cs#L24-L45)
- [18] [PickTextInference（Yap/SVTR）](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/ONNX/SVTR/PickTextInference.cs#L38-L87)
- [19] [OcrUtils.ToTensorYapDnn：221×32 与 384×32](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Engine/OcrUtils.cs#L21-L47)
- [20] [Bv.FindFKeyText 与 GetWhiteTextBoundingRect](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Common/BgiVision/BvOcr.cs#L18-L50)、[白字提取](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoPick/AutoPickTrigger.cs#L450-L463)
- [21] [ResinStatus.RecogniseFromRegion](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoDomain/Model/ResinStatus.cs#L35-L93)
- [22] [ResinRecognition（大地图顶栏）](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Common/ResinRecognition.cs#L40-L159)
- [23] [AutoBossTask：树脂上限、恢复时间、快捷使用数量](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoBoss/AutoBossTask.cs#L311-L345)（[数量 L645-L659](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoBoss/AutoBossTask.cs#L645-L659)、[L729-L813](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoBoss/AutoBossTask.cs#L729-L813)）
- [24] [GridItemCountRecognizer：参数、流程、结构修正](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Model/GameUI/GridItemCountRecognizer.cs#L10-L238)
- [25] [GridScreenExtensions.GetGridItemIconText](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Model/GameUI/GridScreenExtensions.cs#L15-L20)
- [26] [AutoEatTask：数量读取与营养袋判定](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoEat/AutoEatTask.cs#L107-L118)（[L201-L210](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoEat/AutoEatTask.cs#L201-L210)）
- [27] [AutoDomainTask.IsTakeFood](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoDomain/AutoDomainTask.cs#L1028-L1037)
- [28] [SkillCdTrigger.RecognizeSkillCd](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/SkillCd/SkillCdTrigger.cs#L561-L589)
- [29] [Avatar.GetSkillCurrentCd](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoFight/Model/Avatar.cs#L590-L602)
- [30] [AutoLeyLineOutcropTask：长 E 的 CD 读取](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoLeyLineOutcrop/AutoLeyLineOutcropTask.cs#L1027-L1044)
- [31] [AutoFightAssets.ECooldownRect（41×18）](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoFight/Assets/AutoFightAssets.cs#L69-L70)
- [32] [GeniusInvokationControl：HP 与骰子数 OCR](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoGeniusInvokation/GeniusInvokationControl.cs#L1240-L1381)
- [33] [AutoGeniusInvokationConfig.MyDiceCountRect](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoGeniusInvokation/AutoGeniusInvokationConfig.cs#L29)
- [34] [AutoTrackTask：距离文字定位与读取](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoSkip/AutoTrackTask.cs#L257-L298)
- [35] [AutoLeyLineOutcropTask：树脂计数与数字模板回退](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoLeyLineOutcrop/AutoLeyLineOutcropTask.cs#L2373-L2490)
- [36] [BvStatus.Uid](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Common/BgiVision/BvStatus.cs#L370-L393)
- [37] [AutoArtifactSalvageTask.GetArtifactStat](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoArtifactSalvage/AutoArtifactSalvageTask.cs#L528-L560)（[等级正则 L722-L733](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoArtifactSalvage/AutoArtifactSalvageTask.cs#L722-L733)）
- [38] [TpTask：ColorRangeAndOcr 候选文字与 ReplaceDictionary](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoTrackPath/TpTask.cs#L3376-L3391)（[替换表 L2531-L2549](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoTrackPath/TpTask.cs#L2531-L2549)）
- [39] [QuickTeleportTrigger：ColorRangeAndOcr](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/QuickTeleport/QuickTeleportTrigger.cs#L149-L161)
- [40] [AutoWoodTask：伐木统计 OCR 与正则](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoWood/AutoWoodTask.cs#L159-L160)（[L233-L245](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoWood/AutoWoodTask.cs#L233-L245)）
- [41] [ImageRegion.Find：OcrMatch、Ocr/ColorRangeAndOcr、FindMulti、ApplyTextReplacements](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Model/Area/ImageRegion.cs#L223-L368)（[FindMulti L490-L541](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Model/Area/ImageRegion.cs#L490-L541)、[替换 L568-L579](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Model/Area/ImageRegion.cs#L568-L579)）
- [42] [RecognitionObject：颜色与 OCR 字段](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/RecognitionObject.cs#L169-L222)、[RecognitionTypes](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/RecognitionTypes.cs#L3-L12)
- [43] [Docs/technical/recognition-json.md：ColorMatch/ColorRangeAndOcr 与 OCR/OcrMatch 字段](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/Docs/technical/recognition-json.md#L256-L349)
- [44] [StringUtils：全角转半角、TryExtractPositiveInt](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Helpers/StringUtils.cs#L74-L125)
- [45] [RegexHelper](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Helpers/RegexHelper.cs#L7-L11)
- [46] [BgiOnnxFactory：执行 provider 选择](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/ONNX/BgiOnnxFactory.cs#L104-L192)
- [47] [PaddleOcrServiceTests](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/Test/BetterGenshinImpact.UnitTest/CoreTests/RecognitionTests/OCRTests/PaddleOcrServiceTests.cs)
- [48] [ResinStatusTests](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/Test/BetterGenshinImpact.UnitTest/GameTaskTests/AutoDomainTests/ResinStatusTests.cs)
- 根 [LICENSE](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/LICENSE)（GPL v3）

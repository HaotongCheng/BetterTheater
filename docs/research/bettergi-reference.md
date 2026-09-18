# BetterGI 画面识别参考调研

本笔记服务于 [核实局内动态状态的页面覆盖与读取可行性](https://github.com/HaotongCheng/BetterTheater/issues/12) 开始全面可行性调查前的参考学习。它说明 BetterGI 如何组织视觉识别，以及哪些思路值得后续验证；不构成 BetterTheater 的识别覆盖、准确率、性能结论，也不决定语言、桌面框架或 OCR 引擎。

调研日期：2026-09-18。源码固定于 [`42e1c0e745670eb4443c1e0357fba963eb24dfcd`](https://github.com/babalae/better-genshin-impact/tree/42e1c0e745670eb4443c1e0357fba963eb24dfcd)（调研时 `main`）。以下“已证实”来自静态阅读，未在本机运行 BetterGI 或测量其性能。文末列出主要源码入口，均为固定提交链接。

## 核心发现

最值得借鉴的是“识别界面和锚点 → 裁剪局部 → 按字段选择识别器 → 校验结果”的组合，而非对整屏反复 OCR，也不是直接采用 BetterGI 的整个技术栈。

| 环节 | 已证实的 BetterGI 实现 | 对 BetterTheater 的启发（待验证） |
|---|---|---|
| 捕获 | `GameCaptureFactory` 提供 BitBlt、DWM shared surface、Windows Graphics Capture 及 HDR/V2 变体。[1] | 将捕获能力与识别逻辑分开；实际选哪种需比较本项目目标窗口条件。 |
| 缩放与 ROI | `CaptureContent` 派生处理图像；`SystemInfo` 以 1920 宽为参考，大图计算缩小后的画布、小图计算素材比例；素材加载按分辨率缓存，并回退到 1920×1080 素材。[2] | 明确原图、参考画布、字段 ROI 三套坐标；不要把一张示例图上的绝对坐标当通用方案。 |
| 定位后读字 | 自动拾取先找交互键模板、判断相邻图标，再按锚点偏移裁出文本区域；有效文字框可直接调用识别模型，找不到则回退到检测加识别。[3] | 先判断剧诗页面，再读取标题、价格、花朵等对应字段；固定单行和复杂多行文本可以走不同流程。 |
| OCR | 通用服务使用 Paddle OCR 的检测/识别模型，经 ONNX Runtime 推理；工厂提供 V4/V5/V6 及语言模型选择，拾取还保留独立的 Yap/SVTR 路径。[3][4] | OCR 是可替换能力；不同字段未必适合同一模型，当前不选定 Paddle、ONNX 或 C#。 |
| 模板与文本混合 | `ImageRegion` 支持模板匹配、OCR、OCR 文本匹配、颜色范围后 OCR；模板可带阈值与 mask，OCR 匹配支持包含、正则、替换词典。[5] | 标题适合词表匹配；头像、耐力点和完成标记应比较模板/颜色/分类方法，不能默认全部交给 OCR。 |
| 调度 | 定时器默认间隔参数为 50 ms，但上一轮未完成时直接跳过；最小化时停止本轮，背景执行取决于 trigger 配置；共享一张截图，按界面类别和 trigger 状态调度。[6] | 借鉴避免重复捕获和任务积压，而非照搬频率。读取时机应围绕本项目结算、开战前、招募/购买/刷新后及手动重读。 |
| 稳定性 | 存在缩到 320×180、用归一化相关系数比较并累计稳定次数的组件。[7] | 可把“动画结束再读”作为候选实验；这里仅确认组件存在，未证明所有 OCR 调用都经过它。 |

上述实现不能直接证明剧诗可读：拾取的一行浅色文字与剧诗卡片、叠层弹窗、小数字、头像列表不是同一分布。

## OCR 的具体处理与边界

`PaddleOcrService` 会将四通道输入转为 BGR；完整路径先检测文本框、排序、透视裁剪，再调用识别模型，竖长框另作旋转。完整检测识别路径默认过滤识别分数低于 `0.5` 的结果；这个阈值是上游实现参数，并非本项目可直接采用的正确率保证。`OcrWithoutDetector` 返回字符串，不保留这一完整路径的过滤及结果结构，不能把两条路径当作等价的置信度接口。[4]

`Rec` 按模型高度与文字图比例计算宽度，通过 `ResizeNormImg` 缩放和归一化到约 `[-1, 1]`，再做模型推理和字符解码。业务层还有可选的颜色范围提取、去空格及替换表。因此，预处理要区分模型必需的输入变换与某类游戏 UI 才适用的图像处理，不能统一“灰度加二值化”后认为会更准确。[4][5]

自动拾取的文字清理会归一化括号并裁去不符合其中文拾取场景的边缘字符；它还结合白名单、黑名单及图标规则判断。这说明领域词表和结构约束有价值，但该清理方法不能直接用于需要保留数字的花朵、价格、等级或层数。[3]

**对 BetterTheater 的技术验证建议，尚未实现或确认为产品设计：**识别结果至少保留原始文字/图块、候选值、来源页面、时间与状态；词表匹配失败或数值矛盾应输出未知/待重读，而不是硬改成一个合法值。已有跨幕状态可以协助校验，但不应替代实际观测，例如不能仅根据购买动作推算余额或默认挑战消耗。

## 可维护性与只读边界

BetterGI 将许多静态模板、ROI、阈值、替换词典放进 `Recognition.json`，支持参考画布与锚点搜索，同时明确复杂预处理和依赖业务状态的定位仍留在代码中。[8] 可借鉴的是把“素材/界面描述”与“局内状态规则”分离，使游戏 UI 变化时更容易定位要更新哪部分。

调度器记录截图及 trigger 耗时；`ImageRegion` 可绘制识别区域；截图功能支持保存画面并遮挡 UID。[5][6] 对本项目，可参考可回放样本、字段框及失败原因，方便判断是捕获、定位、OCR 还是状态更新出了问题。这里不要求用户现在补采样，也不引入上传服务。

上游 README 声明不修改游戏文件或读写游戏内存，依靠视觉算法与模拟操作；源码中的自动拾取确实直接调用键鼠模拟。[3][9] **BetterTheater 的边界更窄：只读画面、不读内存、不模拟输入。** 因此只借鉴捕获、定位、识别及调试思路；不能直接引入上游任务执行器或含输入动作的整条自动化流程。上游 README 关于管理员权限的解释也与模拟鼠标点击有关，不能据此认定我们的只读程序必需管理员权限。[9]

## 幻想真境剧诗是否已有支持

在固定提交的递归文件树中，没有发现以 `Theater`、`Theatre`、`Imagin` 命名的专用模块；README 列出的功能未列出剧诗。另对上游仓库执行 GitHub code search，关键词 `幻想真境`、`剧诗`、`Imaginarium` 均返回空结果。树与 README 的证据可固定到本提交；GitHub 搜索结果只代表调研时索引状态。[9][10]

因此准确表述是：**本次未找到可以直接对接的剧诗识别或局内状态模块**，不是断言 BetterGI 的所有历史版本、独立脚本仓库或社区脚本均不支持剧诗。没有据此证明角色耐力、花朵、祝福等目标字段已被上游验证。

## 后续页面覆盖与读取可行性研究应验证什么

以下是后续研究问题与样本类别，尚未执行全面覆盖调查，也不是新增用户前置任务：

1. **页面与定位：**准备界面、候选卡片、购买/招募弹层、开战前和结算页面能否区分；在已有图上先验证可用锚点，防止同一位置跨页面误读。
2. **字段方法：**标题/角色名用 OCR 加词表是否足够；头像和耐力点是否更适合图像方法；花朵、价格、等级/层数、刷新次数等数字要分别测，不能以标题成功代表整体成功。
3. **变化前后：**优先利用已有招募前后、购买前后、刷新前后和战后样本；验证“旧值→新值”确实来自新画面，尤其防止动画中间态覆盖稳定状态。
4. **技术异常与重读：**至少覆盖遮挡、过渡画面、识别失败、字段暂不可见、手动重读和跨幕保留；验证不可见不是零值，重读不是清空整局。这仅是识别与状态更新的测试边界，不重开地图中已暂缓的资料缺失降级、补问或拒绝推荐设计。
5. **环境与成本：**在明确的目标分辨率/窗口模式先建立基线，再决定是否扩大；记录字段正确率、误识别、未识别、单次耗时及游戏并行资源占用。上游 16:9/1920×1080 推荐和滤镜限制是上游说明，不等于我们的支持承诺。[9]

可先定义捕获图像、页面定位、字段观测、状态更新的接口，再用同一批样本比较候选实现。这个顺序保留了技术选型空间；没有理由仅因 BetterGI 成熟就提前绑定其框架。

## 复用注意

固定提交的根许可证是 GPL v3。[11] 当前笔记只归纳设计和链接源码，没有复制其实现。若之后计划复制代码、分发其二进制或携带模型/素材，应逐项核对相应许可证及来源，再决定复用方式；根许可证本身不能代替模型、图像及第三方子组件的逐项核查。本轮不作许可证兼容性结论。

## 主要一手来源

所有源码链接固定到同一提交，避免后续 `main` 变化造成解释漂移。

- [1] [GameCaptureFactory：捕获后端](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/Fischless.GameCapture/GameCaptureFactory.cs)
- [2] [CaptureContent](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/CaptureContent.cs)、[SystemInfo](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Model/SystemInfo.cs)、[RecognitionAssets](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/RecognitionAssets.cs)
- [3] [AutoPickTrigger：锚点、局部文字、识别回退、文本清理及输入动作](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/AutoPick/AutoPickTrigger.cs)
- [4] [PaddleOcrService](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/PaddleOcrService.cs)、[Rec](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Paddle/Rec.cs)、[OcrUtils](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/Engine/OcrUtils.cs)、[OcrFactory](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OCR/OcrFactory.cs)
- [5] [ImageRegion：ROI、模板/OCR/颜色识别和调试框](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/Model/Area/ImageRegion.cs)
- [6] [TaskTriggerDispatcher：调度、跳帧、窗口状态、耗时与截图](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/TaskTriggerDispatcher.cs)
- [7] [TemplateMatchStabilityDetector：稳定性组件](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/Core/Recognition/OpenCv/TemplateMatchStabilityDetector.cs)
- [8] [Recognition.json 官方技术说明](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/Docs/technical/recognition-json.md)
- [9] [README：功能、环境说明与运行方式声明](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/README.md)
- [10] [固定提交文件树](https://github.com/babalae/better-genshin-impact/tree/42e1c0e745670eb4443c1e0357fba963eb24dfcd)
- [11] [根 LICENSE](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/LICENSE)


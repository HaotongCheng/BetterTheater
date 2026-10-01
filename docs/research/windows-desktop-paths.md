# Windows 画面采集与置顶建议窗口：集成约束

核查日期：2026-10-01 UTC（用户当地 2026-09-30）。对应[核实 Windows 画面采集与置顶建议窗口的集成约束](https://github.com/HaotongCheng/BetterTheater/issues/18)。

## 结论与证据边界

**建议先用 Windows Graphics Capture（WGC）的单窗口采集，验证“快捷键重读 → 获得可追溯的画面 → 更新不抢焦点的小窗口”这一条最短链路。** 这是原型起点，不是确定 C#、WPF 或最终产品技术栈。另保留 DXGI Desktop Duplication 和 Electron 两条候选，按实际失败原因或工程接入成本选择对照。

本报告仅查官方 API 文档及固定版本源码，没有运行捕获程序、游戏工具或性能测试。下文分别标明：**文档事实**是 API 声明的能力与约束；**源码事实**是具体版本采取的做法；**推导/建议**是供原型验证的判断。三者均不能证明本机《原神》的窗口、全屏、HDR 或提升权限环境已经可用。

承接已有[BetterGI 参考](https://github.com/HaotongCheng/BetterTheater/blob/9816fda/docs/research/bettergi-reference.md)和[核实局内动态状态的页面覆盖与读取可行性](https://github.com/HaotongCheng/BetterTheater/issues/12)，不重新调查剧诗字段。本票不安装工具、不登录账号、不读游戏内存、不模拟输入、不调用付费服务；没有上传私人截图。文档中的远程桌面用途也不意味着本项目要传输整屏。

## 三条候选组合

| 候选 | 文档支持的接入方式 | 对本项目的取舍（推导） | 仍需本机验证 |
|---|---|---|---|
| A：WGC + .NET/WPF 小窗口 + Win32 快捷键 | WGC 可选窗口或显示器；桌面互操作 `CreateForWindow(HWND)` 从 Windows 10 1903 起提供。现代 .NET 可通过 Windows 目标框架接入 WinRT；WPF 提供 `Topmost`、`ShowActivated`。[W1]、[W2]、[N1]、[U1]、[U2] | 单窗口源与目标游戏匹配；原型仍须处理 Direct3D 纹理和 WinRT/Win32 互操作，不能把几行 UI 属性当成完整采集实现。适合先隔离采集风险。 | 目标窗口可捕获性、边框/客户区、最小化、HDR、CPU 拷贝成本、普通权限运行。 |
| B：DXGI Desktop Duplication + C++/Win32 小窗口 + Win32 快捷键 | 按显示器输出复制桌面；官方明确覆盖全屏 DirectX 内容。`SetWindowPos` 可控制置顶与激活；`RegisterHotKey` 接收系统快捷键。[D1]、[U3]、[H1] | 可作窗口采集失败时的显示器级对照；必须自行裁剪游戏区域、处理遮挡、输出/适配器、像素格式和恢复。C++ 是这里的原型组合，不代表 DXGI 只能由 C++ 使用。 | 整屏其他窗口污染、全屏切换恢复、混合显卡、HDR 转换、游戏被遮挡时的拒用规则。 |
| C：Electron `desktopCapturer`/媒体流 + `BrowserWindow` + `globalShortcut` | 官方提供 `screen`/`window` 源和媒体流示例，窗口置顶/非激活显示及失焦快捷键 API。[E1]、[E2]、[E3] | 若后续采用 Web 界面，可验证 JavaScript/TypeScript 接入成本；捕获仍需从媒体流取得真实图像，源列表缩略图不能代替帧采集。官方这些页面没有承诺固定 Windows 后端或暴露 WGC 的 QPC 时间语义，不能默认其等价于 A。 | 实际帧尺寸、色彩、延迟、隐藏窗口节流、最小化游戏、全屏及采集源重新连接。 |

捕获后端、识别器和建议窗口可以分别替换；上表只是三种可测试组合。没有证据支持先用框架“成熟度”推断本项目准确率或游戏并行性能。

## 必须带入原型的约束

### 目标窗口、全屏、权限与焦点

- **文档事实：**WGC 的系统选择器让用户选择目标，并显示采集边框；开始前应调用 `IsSupported()`。`CreateForWindow` 是另一个按 HWND 建立目标的桌面入口；它的存在不能解释为对所有游戏窗口、权限层级或最小化状态的保证。[W1]、[W2]
- **文档事实：**Desktop Duplication 捕获的是显示器桌面，而非指定 HWND。Direct3D 设备必须来自该输出所属适配器；权限不足、安全桌面和会话断开均有明确失败返回。安全桌面的 `LOCAL_SYSTEM` 条件不是本助手申请更高权限的理由。[D1]、[D2]
- **推导：**整屏方案中，被别的窗口遮住的游戏区域不能直接当成完整游戏画面；最小化后复制到的桌面也不能当成游戏现状。单窗口方案则需实测遮挡和最小化后究竟返回新帧、旧帧、空帧还是停止更新，不能由“支持 window”推断。
- **未测：**普通权限助手与提升权限游戏的组合、游戏窗口切换/重建后的识别、原神实际使用的全屏路径。游戏设置中的“全屏”名称不证明独占呈现模式。能采集全屏与建议窗口能显示在其上方是两项独立验证。

### 缩放、尺寸与 HDR

**文档事实：**WGC 在内容尺寸与帧池尺寸不同时可能裁切或留下未定义区域，应依据 `ContentSize` 取有效区域并在尺寸变化后重建帧池。HDR 场景官方建议整个采集链采用 `R16G16B16A16_FLOAT`，按输出用途再做色调映射。[W1] 传统 DXGI 复制路径使用 BGRA8；`DuplicateOutput1` 可接受高色深格式并避免部分全屏格式转换，不能把传统 BGRA8 路径等同于保留 HDR。[D3]、[D4]

**文档事实：**Windows 的 DPI 感知模式影响坐标和缩放；Electron 也明确区分物理像素与 DIP 并提供转换接口。[P1]、[E4] **推导：**采集像素、游戏内容区域、识别参考画布、建议窗口位置应有明确转换关系。不能拿 UI 布局坐标直接裁图，也不能因同为 2560×1440 就认为渲染比例、系统缩放和 HDR 相同。原型记录实际像素格式和转换步骤；换 HDR 模式后重测文字、耐力点等局部图像，不用“看起来正常”代替核对。

### 帧时间、忙时处理与恢复

| 文档事实 | 对原型的直接要求（建议） |
|---|---|
| WGC `SystemRelativeTime` 表示合成器渲染该帧的 QPC 时间；`CreateFreeThreaded` 在内部工作线程发出 `FrameArrived`，无需依赖 UI 的 `DispatcherQueue`。[W3]、[W4] | 分别记录源时间、收到帧时间、重读请求时间和识别完成时间。后台回调只接收/复制必要数据，重计算与 UI 更新分开；具体线程边界待原型测量。 |
| WGC 帧归还帧池后不能继续持有原帧/底层 surface；`Recreate` 会丢弃旧帧。[W1] | 异步识别需拥有仍有效的数据；尺寸或设备重建后不得让旧请求结果覆盖新来源。 |
| DXGI `AcquireNextFrame` 可能超时，也可能因仅鼠标变化而返回；桌面/模式/全屏切换可能产生 `DXGI_ERROR_ACCESS_LOST`，需重建接口。[D5] | 收到回调不等于游戏内容变化；超时与接口失效分别处理，恢复后重新核对目标和尺寸。 |
| DXGI `LastPresentTime` 是桌面图像更新时间；仅鼠标变化时为零，`AccumulatedFrames` 说明处理期间积累的更新。[D6] | 不把鼠标更新当新页面；用来源时间和积压信息诊断延迟，避免排队处理大量过期帧。 |
| Electron 的 `backgroundThrottling` 默认启用，影响后台页面的动画和计时器。[E5] | 若采集消费/识别调度放在 renderer，需测助手失焦、隐藏和最小化后的行为；不能靠页面计时器频率证明实际采集频率。 |

**推导：**上述时间戳证明的只是图像生产或接收时点，不证明招募、购买或结算已经完成。静止页面可以多次重读，画面相同也不必然陈旧；反之动画中的“新帧”不必然可用。原型需要把“帧有效/来源可用”和“页面稳定/字段可确认”分开记录。快捷键触发不能直接重复提交上次缓存并标成新观测；是否允许复用已确认静态帧及其时效规则，留给后续状态设计。

### 置顶、输入与快捷键

**文档事实：**WPF 的 `Topmost` 是 Z 顺序属性；`ShowActivated=false` 仅控制首次显示，用户点击后仍正常激活。Win32 的 `HWND_TOPMOST` 与 `SWP_NOACTIVATE` 分别控制置顶和不激活。Electron 同样需要区分 `setAlwaysOnTop`、`showInactive`、`setFocusable`；忽略鼠标也不等于不接收键盘焦点。[U1]、[U2]、[U3]、[E2] **推导：**建议小窗展示、刷新和重新定位时不抢游戏焦点；用户主动点击设置的交互应另测。置顶本身不构成独占全屏覆盖保证。

**文档事实：**`RegisterHotKey` 通过 `WM_HOTKEY` 通知窗口/线程，`MOD_NOREPEAT` 可避免按住键时重复触发；冲突可能使注册失败，F12 保留给调试器。Electron `globalShortcut` 在失焦时也可用，但被占用的组合会注册失败，必须检查返回值。[H1]、[E3] **建议：**只让热键请求本助手重读，不向游戏发送输入；原型检查冲突、长按、连按及退出后注销，不提前指定用户最终按键。

**文档事实：**自有顶层窗口可用 `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` 从捕获中排除，完整语义从 Windows 10 2004 起提供，且不是安全隔离保证。[U4] **建议：**显示器级候选至少验证小窗遮住 ROI 时是否被捕获；可对比移到 ROI 外与排除捕获两种办法。不能假设一次属性调用就已消除当前帧污染，也不通过修改游戏窗口来解决。

## 既有源码证据的正确用途

**源码事实：**重新检查 BetterGI 固定提交 `42e1c0e745670eb4443c1e0357fba963eb24dfcd`，其[捕获工厂](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/Fischless.GameCapture/GameCaptureFactory.cs)提供 WGC/HDR/V2、BitBlt 等后端；[调度器](https://github.com/babalae/better-genshin-impact/blob/42e1c0e745670eb4443c1e0357fba963eb24dfcd/BetterGenshinImpact/GameTask/TaskTriggerDispatcher.cs)在上一轮忙时跳过，在游戏最小化时直接退出该轮。它说明可替换后端、限制积压和检查窗口状态是已有做法；**不能据此声称 WGC 官方保证最小化失败，也不能照搬其频率、权限需求或输入执行器。** 本报告没有复制该项目实现或增加第四条候选。

## 最小原型与未测清单

**建议起点：**A 的 WGC 单窗口采集，先用普通本地测试窗口验证身份、尺寸、计时、小窗显示和热键，再在后续授权的真实游戏环境复核。语言选择只服务这次可丢弃原型。起步不接 OCR、推荐或云 API；用时间变化标记及本地局部画面核对采集链本身。已有剧诗样本可用于后续比较局部内容，但静态样本无法验证实时捕获。

以下全部**尚未实测**。原型不必穷举硬件；先记录用户实际 OS build、GPU/驱动、显示器、游戏窗口模式、分辨率、缩放、HDR、助手/游戏权限和所用框架版本，再按实际环境执行。

| 最少场景 | 保存的证据与判断 |
|---|---|
| 正常游戏页面，快捷键一次与连续多次重读 | 请求/帧/完成时间，源身份、实际尺寸、黑帧/空帧/重复帧统计；重读是否得到来源有效的画面，是否产生任务积压。 |
| 游戏失焦、被普通窗口和建议小窗分别遮挡 | 采集内容差异、可见性、当前焦点；建议更新不得自动切走游戏焦点，被污染图像不得当作正常字段来源。 |
| 游戏最小化再恢复、关闭再打开 | 停帧/旧帧/错误的实际表现、捕获会话恢复过程；旧 HWND/旧帧不得继续绑定为当前游戏。 |
| 窗口化与用户实际全屏模式切换 | 采集是否继续、模式切换错误/恢复耗时、小窗是否可见；对失败模式明确支持边界。 |
| 当前分辨率/缩放，再改变一档；有第二屏时移屏 | 物理像素、DIP、客户区和 ROI 对应是否仍正确；尺寸变化不裁掉有效内容或引入未定义边缘。没有第二屏则标记未测。 |
| SDR/HDR（设备实际支持时） | 输入格式、转换后局部图与人工可见内容的对照；没有 HDR 硬件则保留未测，不能宣称支持。 |
| 普通权限助手与实际游戏权限组合 | 是否可选中、是否有帧、热键是否触发及明确错误；失败不自动提高权限或尝试安全桌面捕获。 |
| 热键冲突、长按、连按、助手退出 | 注册结果、每次触发数、去重/排队行为、注销；助手隐藏与最小化也测一次，尤其是候选 C。 |
| 游戏并行运行、一次捕获恢复 | 端到端延迟分布（中位数、P95、最大值）、CPU/GPU/内存及游戏帧时间变化；记录观察值，不预设达标或推断 OCR 正确率。 |

**报告接口建议，尚非架构定案：**每个捕获结果保留目标身份、后端、会话/尺寸版本、像素尺寸、有效内容区域、像素/色彩格式、来源时间（注明时钟语义）、接收时间、请求 ID 和不可用原因；后续识别与状态更新只消费这一边界。这样可以更换捕获或 UI，而不把屏幕坐标、框架对象和“当前角色状态”混在一起。

完成这组原型后，才有依据决定 A 是否足够、是否需要 B 的显示器路径或 C 的 UI 集成对照，以及首版支持哪些显示环境。本票交付的是候选和约束证据，不是“Windows 集成已通过”或最终选型。

## 一手来源

官方页面均于上述日期核查；`latest` 文档可能继续变化，执行原型时应固定实际依赖版本。源码证据已固定提交。

- [W1：Microsoft，Screen capture][W1]
- [W2：Microsoft，CreateForWindow][W2]
- [W3：Microsoft，SystemRelativeTime][W3]
- [W4：Microsoft，CreateFreeThreaded][W4]
- [N1：Microsoft，桌面应用调用 WinRT][N1]
- [D1：Microsoft，Desktop duplication 概览][D1]
- [D2：Microsoft，DuplicateOutput 的适配器、权限与会话约束][D2]
- [D3：Microsoft，Desktop Duplication API 的格式与处理][D3]
- [D4：Microsoft，DuplicateOutput1 的高色深格式][D4]
- [D5：Microsoft，AcquireNextFrame][D5]
- [D6：Microsoft，DXGI_OUTDUPL_FRAME_INFO][D6]
- [P1：Microsoft，Windows 高 DPI 桌面应用][P1]
- [U1：Microsoft，WPF Topmost][U1]
- [U2：Microsoft，WPF ShowActivated][U2]
- [U3：Microsoft，SetWindowPos][U3]
- [U4：Microsoft，SetWindowDisplayAffinity][U4]
- [H1：Microsoft，RegisterHotKey][H1]
- [E1：Electron，desktopCapturer][E1]
- [E2：Electron，BaseWindow][E2]
- [E3：Electron，globalShortcut][E3]
- [E4：Electron，screen 坐标转换][E4]
- [E5：Electron，BrowserWindow][E5]

[W1]: https://learn.microsoft.com/en-us/windows/apps/develop/media-authoring-processing/screen-capture
[W2]: https://learn.microsoft.com/en-us/windows/win32/api/windows.graphics.capture.interop/nf-windows-graphics-capture-interop-igraphicscaptureiteminterop-createforwindow
[W3]: https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.direct3d11captureframe.systemrelativetime?view=winrt-26100
[W4]: https://learn.microsoft.com/en-us/uwp/api/windows.graphics.capture.direct3d11captureframepool.createfreethreaded?view=winrt-26100
[N1]: https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/winrt-apis-desktop-apps
[D1]: https://learn.microsoft.com/en-us/windows-hardware/drivers/display/desktop-duplication-api
[D2]: https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_2/nf-dxgi1_2-idxgioutput1-duplicateoutput
[D3]: https://learn.microsoft.com/en-us/windows/win32/direct3ddxgi/desktop-dup-api
[D4]: https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_5/nf-dxgi1_5-idxgioutput5-duplicateoutput1
[D5]: https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_2/nf-dxgi1_2-idxgioutputduplication-acquirenextframe
[D6]: https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_2/ns-dxgi1_2-dxgi_outdupl_frame_info
[P1]: https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows
[U1]: https://learn.microsoft.com/en-us/dotnet/api/system.windows.window.topmost?view=windowsdesktop-9.0
[U2]: https://learn.microsoft.com/en-us/dotnet/api/system.windows.window.showactivated?view=windowsdesktop-9.0
[U3]: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos
[U4]: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity
[H1]: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey
[E1]: https://www.electronjs.org/docs/latest/api/desktop-capturer
[E2]: https://www.electronjs.org/docs/latest/api/base-window
[E3]: https://www.electronjs.org/docs/latest/api/global-shortcut
[E4]: https://www.electronjs.org/docs/latest/api/screen
[E5]: https://www.electronjs.org/docs/latest/api/browser-window

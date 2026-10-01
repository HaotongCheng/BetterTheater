# 账号档案导入候选：字段契约与更新限制

核查日期：2026-09-30（America/New_York）。对应[核实账号档案导入候选的字段契约与更新限制](https://github.com/HaotongCheng/BetterTheater/issues/19)。承接[账号与实际可借角色数据：获取边界](https://github.com/HaotongCheng/BetterTheater/blob/cc5e3d87d7cbba4ac9c4f5eb44dc2dcf84bc81b8/docs/research/account-data.md)，本次只比较三个输入候选，供后续适配原型使用，不决定登录方案。

本次读取了公开文档与一手源码，没有登录、读取浏览器凭据、调用任何账号资料接口、取得用户样本或使用付费服务。以下“存在”均指源码/格式存在；真实账号的可访问性、完整性和更新延迟尚未实测。

## 结论

三条候选都能表达部分或全部所需的角色配置，但完整性与新鲜度的含义不同：

| 候选输入 | 已证实的具体入口 | 最适合验证的内容 | 原型必须保留的限制 |
| --- | --- | --- | --- |
| **A：用户选择的 GOOD JSON 文件** | Genshin Optimizer 的数据库下载按钮调用 `exportGOOD()`，输出 JSON；当前导出为 GOOD v3 | 不接触游戏登录会话的文件适配、字段校验、装备与角色关联 | 是用户工具数据库的快照；标准不保证全账号、当前穿戴、账号归属或采集时间。不能拿文件名时间当换装同步时间。[G1][G2][G3] |
| **B：genshin.py 战绩角色详情** | `character/list` → `character/detail`；提供 `return_raw_data=True` | 列表与详情核对、数值解析、未来本人授权后的全账号配置候选 | 查询范围可人为限制；接口权限、风控、返回完整性和同步延迟待授权实测。没有证实第三方稳定性承诺。[H1][H2][H5] |
| **C：Enka UID 响应或保存配装 JSON** | `/api/uid/{uid}/`；公开已验证账号的 `/builds/` | 公共字段映射、配装快照导入、缓存与缺失处理 | 必须记录是展柜还是某一保存配装；`live` 不代表实时；不能由多个历史配装合成一个“现在的全账号”。[E1][E2] |

**建议的原型顺序（推论，待接入决策）：**先做 A 的严格原始文件校验与本地归一化；用获授权的 B/C 快照验证同一份字段契约是否足够。B 的登录集成独立决策。A 能降低原型对在线会话的依赖，但不能保证用户已经有合格的 GOOD 数据库；若没有，生成文件所需工具与操作负担仍须另评估。本票没有审核或选择扫描器。

三条输入均只更新**账号角色档案**。它们不直接产生**本局参演名单**或**当前角色状态**，也没有在本次研究中证明能枚举当前**可借角色**。历史助演、朋友展柜和保存配装都不能单独证明当前借用资格；后者仍需游戏内核对。

## 1. 字段映射候选

以下路径优先写原始 JSON；不是把包装库的模型属性名误作接口原字段。`?` 表示允许缺失或尚需验证，不是零值。GOOD 的键采用该格式的英文稳定键；不以中文显示名称联表。[G1]

| 档案概念 | A：GOOD 文件 | B：战绩详情原始响应 | C：Enka 角色对象 |
| --- | --- | --- | --- |
| 角色身份 | `characters[].key`；需版本化字典转内部角色 ID | `list[].base.id`；原始 `element` 一并保留 | `avatarId`，并保留 `skillDepotId` 区分技能组；不能只按名字合并 |
| 等级 / 命座 | `level` / `constellation`（0–6） | `base.level` / `base.actived_constellation_num`；还可核对 `constellations[].is_actived` | `propMap["4001"].val` / `talentIdList` 中已解锁命座数 |
| 角色突破 | `ascension`（0–6，区分 80/80 与 80/90） | 目前所审模型没有直接角色突破字段，记未知，不从等级独断 | `propMap["1002"].val` |
| 武器归属 / 身份 | `weapons[].location` 关联角色；`key` 为武器类型键 | 当前 `list[].weapon.id` | `equipList[]` 中武器的 `itemId` |
| 武器等级 / 突破 / 精炼 | `level` / `ascension` / `refinement`（1–5） | `weapon.level` / `promote_level` / `affix_level`；包装模型命名为 refinement，边界样本仍需核对 | `weapon.level` / `promoteLevel` / `affixMap` 的值（0–4，归一化为 1–5） |
| 天赋 | `talent.auto/skill/burst`，文档明确**不包含命座提升** | `skills[].skill_id/skill_type/level/is_unlock`；需按 ID 映射技能类型 | `skillLevelMap[skill_id]`，结合 `skillDepotId` 做技能映射 |
| 天赋加成口径 | 已明确为基础等级 | 所审源码未规定 level 是否已含命座等加成：未知 | 所审 API 文档未完整规定加成口径：未知；不能与 GOOD 直接相等比较 |
| 圣遗物归属 / 槽位 / 套装 | `artifacts[].location/slotKey/setKey` | `relics[].pos/set.id`；`pos_name` 只作显示参考 | `equipList[].flat.equipType/setNameTextMapHash`；需版本化套装字典 |
| 圣遗物等级 / 星级 | `level`（0–20） / `rarity` | `relics[].level/rarity`；边界数值待样本核对 | `reliquary.level`（1–21，归一化减 1） / `flat.rankLevel` |
| 圣遗物主词条 | `mainStatKey`；**不直接包含主词条数值**，需由匹配版本的星级/等级表推导并标记为推导值 | `main_property.property_type/value/times`；通过顶层 `property_map` 解释属性 | `flat.reliquaryMainstat.mainPropId/propValue`；另有 `reliquary.mainPropId`，两者不能混用为同一命名空间 |
| 圣遗物副词条 | `substats[].key/value`；v3 可有 `initialValue`、`unactivatedSubstats` | `sub_property_list[].property_type/value/times` | `flat.reliquarySubstats[].appendPropId/propValue`；文档表的 `appendPropID` 大小写需以获授权原始样本确认，适配不能仅照抄文档拼写 |
| 面板与单位 | 核心 GOOD 格式无当前角色完整面板；不得凭缺省值冒充采集 | `base_properties/selected_properties/extra_properties/element_properties`；`base/add/final` 是字符串 | `fightPropMap` 有独立属性编号；与装备 `propValue` 的单位分别校验，不统一套一个百分比转换 |

映射依据：[GOOD 官方格式页面源码][G1]、[GOOD 模式与角色/武器/圣遗物模式][G4]、[战绩详情模型及展开逻辑][H2]、[Enka 字段文档][E2]。Enka 文档同时出现 `avatarID` 表格拼写和 `avatarId` 用例；后续适配以样本及服务实际字段验证，不把文档拼写差异悄悄吞掉。

这张表没有声明技能等级、圣遗物值和角色身份转换已经验证。尤其旅行者的身份、元素/技能组与装备归属需要同时保留原始键，避免多元素档案相互覆盖；GOOD 的 `location` 应按该版本角色位置字典解析，不凭字符串相等猜测所有角色变体。[G1][G4][E2]

## 2. 缺字段、空集合与完整性

### A：GOOD 的“有效 JSON”不等于“完整实测档案”

标准顶层 `characters`、`weapons`、`artifacts` 均可省略。武器/圣遗物的 `location: ""` 明确表示未装备；省略 location 或缺少整份装备数组则不能推断角色没有装备。标准角色键标识角色类型，武器 `key` 标识武器类型，不是账号内每一把武器的唯一实例；核心圣遗物格式同样没有必须提供的实例 ID。[G1][G4]

当前 Optimizer 模式接受 v1、v2、v3；v2 新增材料，v3 新增圣遗物标记、初始词条与未激活副词条。核心角色/武器字段保持兼容。TheaterLens 若暂时不用这些扩展，可保留原始数据并明确不参与计算，不把 `unactivatedSubstats` 加入当前有效副词条。[G1][G4]

**不能直接复用上游宽容校验当作采集可信度判定。**当前实现可对缺失或非法数值使用 fallback、限制范围，并为部分属性提供默认值：例如命座可变为 0，天赋可变为 1，圣遗物主属性可变为 hp，副词条值可变为 0。这是 Optimizer 的输入处理行为，不能证明用户实际持有该配置。原型应先检查原始字段是否存在/合法，再决定转换；缺失保留未知，非法值报告问题，不静默“修好”。[G4][G5]

GO 下载的是数据库内容，可能来自手动输入、旧导入或用户编辑。即使三个数组都存在且有条目，仍须用户声明导出的范围，并对照角色总数和抽样配装；不能推断角色列表覆盖整个自有角色池。文件缺失某角色时，默认不删除已有档案。[G1][G2][G3]（最后两句是本项目的适配建议。）

### B：战绩列表与详情必须分别验收

`get_genshin_detailed_characters` 未传 characters 时先取拥有角色 ID 列表，再请求这些 ID 的详情；显式传入 characters 则只查询指定子集。原型须保存“请求 ID 集合”和“返回详情 ID 集合”，逐项核对缺漏/重复，而不只检查 HTTP 成功。列表→详情并非源码承诺的原子快照，两个请求之间改装会产生一致性问题。[H1]

原始详情以 `list[].base` 嵌套基础信息；包装模型把 base 展开、跳过 base 的简化 weapon，并用顶层 `property_map` 补充每条属性的名称/类型信息。缺少词条映射时可能直接查键失败。保留 raw 与归一化结果各自的验证状态，不能把解析异常转成空角色池。[H2]

模型允许 `weapon.sub_property` 为 null（武器无副属性的表达候选）；其他关键配置缺失、空 relics、空 skills 的精确服务端语义，本次未取得真实样本证实。只在来源有明确含义时写“没有”；其余写“未读取/无法确认”。此外 `BaseCharacter` 会用角色数据库自动补全/修正 id、name、element、rarity，必须区分接口观测值与静态元数据补全值。[H2][H6]

### C：Enka 对部分缺失有明确语义

服务文档明确：`avatarInfoList` 缺失表示展柜关闭或没有角色；不是全账号无角色。角色详情中 C0 的 `talentIdList` 可以没有数据，因此只有在角色详情对象自身有效时，才按文档把这一特定缺失解释为零命。不能把这条规则推广到缺武器、缺技能等级或整个角色对象。[E1][E2]

保存配装按 avatarId 分组，每组可有多个配装，数组没有确定顺序，`order` 仅用于显示排序。必须让用户指定采用哪一套，或明确导入每个独立快照；不能靠“第一个”“最后一个”猜当前配装。[E1]

## 3. 地区、认证与失效边界

| 候选 | 已核实边界 | 仍未知 / 失败应如何表达 |
| --- | --- | --- |
| GOOD 文件 | 本地读取已由用户选择的文件无需游戏登录，也没有网络地区路由；核心格式不要求 UID、服务器或账号证明。[G1][G2] | 文件身份必须由用户绑定到本地档案；不能声称已验证账号归属。导出来源本身如何获取资料不是 GOOD 格式的保证。 |
| genshin.py | 战绩调用根据游戏 UID 选服务器并分国服/国际服路由。源码将 UID 去掉末 8 位后的前缀映射为 `1/2/3→cn_gf01`、`5→cn_qd01`、`6→os_usa`、`7→os_euro`、`8/18→os_asia`、`9→os_cht`，不能仅看第一位导致 `18` 错路由。[H3] | 映射存在不证明每个地区/渠道账号目前可访问。先验证本人实际地区，不把其他地区默认为已支持。 |
| genshin.py 认证 | 库文档以服务登录 cookies 为主要身份认证，列举 `ltuid/ltoken`，另有 v2 cookie/令牌更新路径；cookie 是敏感会话，不能当公开 UID。库可能更新 cookies，提供 `on_cookie_update` 钩子；这不是固定会话有效期承诺。[H4] | 本次未确认各地区今天最小 cookie 组合、会话期限及无交互续期保证；不选登录流程、不索取会话。抽卡 authkey 不等同于角色战绩授权。 |
| genshin.py 错误 | 库区分 InvalidCookies（含 `-100`、`10001`）、未绑定社区账户、DataNotPublic（`10102`）、访问频繁和 GeetestError；战绩设置还分别控制战绩可见和角色详情可见。[H5][H7] | 会话无效、权限不足、需人类验证、暂时限流分别呈现；均不当“账号无角色”。不得为读取自动开启公开设置。具体错误码可能随服务变化，保留原始码和安全消息用于诊断。 |
| Enka | UID 查询是公开服务；公开 profile 枚举只返回 `verified` 且 `public` 的游戏账号。绑定验证通过用户在游戏签名放置验证信息，读取文档所示公开端点未要求传游戏 cookie。[E1] | 本次所查服务文档没有完整的国服/渠道/国际服支持矩阵，保持按实际地区待验证；不推导全部服务器可用。公开隐藏/删除导致不可见不等于账号或角色消失。 |

战绩当前源码的国际服基址为 `sg-public-api.hoyolab.com/event/game_record/genshin/api`，国服为 `api-takumi-record.mihoyo.com/game_record/app/genshin/api`。这些是非官方包装库记录的一手实现，不能包装成 HoYoverse 对第三方开发者的稳定接口契约。[H3]

后续即使选择 B，也应把“本人在本机授权采样”与“把脱敏响应交给适配器”分开；原型不需要 cookie、请求头或登录日志作为测试 fixture。这是本项目建议，不是本次已获授权的登录工作。

## 4. 缓存、换装与文件时间

- **GOOD：**JSON 是静态文件。GO 导出按钮把当前时间放在文件名中，但不证明数据库刚从游戏同步；标准顶层也没有必须的采集时间、装备生效时间或完整性标记。需要分别记录用户声明的采集/核对时间与导入时间。[G1][G2]
- **战绩：**`_request_genshin_record` 的本地 cache 参数默认 false，所审列表/详情调用没有开启它；这只说明该调用路径没有使用该可选客户端缓存，不代表上游没有缓存。所审字段模型没有提供每件装备的更新时间，也没有找到可据此承诺换装刷新时延的 SLA。[H1][H2]
- **Enka UID：**响应 `ttl` 是距离下一次向展柜请求的秒数；未到期会返回缓存，再次请求仍消耗限流额度。要尊重 ttl 并使用自定义 User-Agent。服务列出 400、404、424、429、500、503；维护/限流/服务异常都不能转成空档案。[E1]
- **Enka 配装：**`live: true` 仅为用户上次点击 refresh 时的展柜；刷新会删除旧 live 配装并建立新的。保存配装长期不变是合法情况。获取时间新不代表配置新。[E1]

因此适配原型的归一化结果至少应保存来源类型、来源版本/导出工具、原始角色/装备键、导入时间、来源采集时间（可未知）、游戏内核对时间（可未知）、范围声明及字段可信状态。未知或可能过期的关键配置必须在原型证据中保留该状态，不能转换为最低练度或默认装备，更不能宣称该字段已验证。这是由上述差异得出的技术证据边界；本地图仍以所需资料齐全为前提，不在此决定缺资料时的推荐交互、降级、补问或拒绝流程。

## 5. 用户控制的文件交接可行性

**A 有现成的用户导出入口。**Genshin Optimizer 的下载功能直接把 `database.exportGOOD()` 序列化为 `.json`，也提供复制数据功能。本票已在源码确认路径，尚未对用户真实数据库执行导出。TheaterLens 可读取用户主动选定的文件并展示导入摘要：声明范围、角色数、缺字段、未识别键、装备归属冲突、待核对时间。[G2][G3]

**B/C 可形成响应快照文件，但不是本票已验证的官方导出按钮。**B 的 raw 返回选项和 C 的 JSON 响应足够让未来获授权的本机采样器保存数据；文件应只含响应正文与必要来源元数据，不含 cookies、Authorization、签名验证信息或无关昵称/签名。读取文件本身不需要再向原服务提交数据。是否提供这类采样器、采用哪个登录方法，需要后续人类决定。[H1][E1]（文件裁剪和保存方式为适配建议。）

三个候选都不能在缺少范围声明时做破坏性全量替换。建议默认合并已证实字段，并展示冲突；只有用户明确确认“本次完整账号快照”且核对通过，才允许替换档案范围。档案文件里出现好友角色也不能据此登记为本人的自有角色。

## 6. 后续获授权样本的最小验证计划

以下是后续执行票的验收输入，本票没有执行采样。先选择本人实际使用地区、输入路径与可保留字段；不为验证本票而申请所有地区账号。

1. **一份范围明确的基线快照。**用户给出当前角色总数与需要规划的角色范围；A 由用户导出，B 由后来获授权的本机流程取得列表和详情，C 只读取用户指定展柜/配装。保留只含必要配置的本地原始样本及采样时间，逐项列明哪些字段是人工声明。
2. **最少三类角色覆盖。**选择能覆盖零命与带天赋提升命座、两种武器精炼、已知基础天赋、旅行者技能组的少量角色（若账号具备）；核对角色 ID、等级、命座、武器身份/等级/精炼、天赋基础与显示等级。未能覆盖的边界记“未测”，不要求用户为测试抽卡或培养。
3. **装备与单位对照。**核对已装备五个槽位、至少一个百分比及一个固定值副词条；有未满级、空槽、无副属性武器时一并覆盖。明确 Enka 等级/精炼偏移、B 字符串值及百分号解析、GOOD 主词条推导版本。把命座天赋的重复加成与百分比乘百/除百错误列为必失败项。
4. **完整性和缺失处理。**B 比较请求 ID 与返回 ID 并对照游戏角色数；A 试省略一个顶层数组、缺天赋、重复装备归属、未知键；C 试缺 `avatarInfoList`、有效 C0 详情和多个保存配装。可以用脱敏 fixture 制造异常，不需要修改真实账号隐私设置。必须区分“确认为无”与“未知/未返回”，失败不能清空已知档案。
5. **一次受控换装。**用户记录游戏内换装的 t0；在限流允许范围刷新或重新导出，记录何时首次反映新配置、是否还有旧字段混入。Enka 按 ttl 等待；B 同时复核列表/详情一致性；A 只有用户重新同步并导出后才期待改变。测不到更新则报告本次窗口内未观察到，不能据一次成功发布同步 SLA。
6. **恢复与身份隔离。**用模拟响应先覆盖会话无效、权限不足、验证码、限流、维护和网络错误；若后续自然遇到真实失效，再记录实际行为。不得为测试主动注销全部设备或搜集凭据。旧档案保留且标过期；切换账号/服务器不互相覆盖；导入、诊断与报告均无敏感会话字段。

通过标准：上述已覆盖样本的关键字段与游戏内核对一致；所有必需转换可解释；缺失、过期、非完整范围不被伪装成完整事实；错误不删除已有档案。原型通过只证明**该路径、该地区、该样本**的适配可用，不证明全地区或未来版本兼容，更不证明能取得实际可借名单。

## 7. 待人类决定与未证实项

- 首轮原型用用户已有 GOOD 文件，还是之后允许本机战绩采样；若两者都没有，获取样本的人工投入是否可接受。
- 是否接受 GOOD 样本的来源时间/账号归属由用户确认；适配验证中缺天赋、未知装备或旧配装只标为未知/过期，不能列入已验证字段。本票不决定缺资料时的推荐交互。
- 若选 B，单独决定地区、登录交互、会话保管/清除方式与采样范围；本报告没有替用户选定这些方案。
- B 的最小当前凭据组合、会话寿命、换装延迟、各服务器真实完整性，以及 B/C 天赋加成精确口径均未证实；C 的完整服务器矩阵也未证实。它们阻塞相应能力的上线声明，**不阻塞无凭据的文件校验原型**。
- 未装备库存、当前可借好友资格与助演配置同步不在本次已证实字段中；不得在后续工程票里隐含补齐。

## 一手证据索引

本次通过 GitHub API 读取固定版本源码；网页渲染器未能读取部分 raw 地址，引用仍指向已实际读取的公开源码版本。来源为格式/服务所有者或实现维护者的一手资料，不以二手教程作为契约。上游版本固定不等于在线服务状态固定。

### G：Genshin Optimizer / GOOD

固定版本：`16292c0e2d72983be0e32a0fe50b931b2004640a`（提交时间 2026-09-29）。

- [G1：GOOD 格式、版本历史、字段与键约定][G1]
- [G2：用户数据库下载与复制入口][G2]
- [G3：exportGOOD 实际构造][G3]
- [G4：顶层版本/可选集合模式][G4]；[角色模式](https://github.com/frzyc/genshin-optimizer/blob/16292c0e2d72983be0e32a0fe50b931b2004640a/libs/gi/schema/src/character/schema.ts)、[武器模式](https://github.com/frzyc/genshin-optimizer/blob/16292c0e2d72983be0e32a0fe50b931b2004640a/libs/gi/schema/src/weapon/schema.ts)、[圣遗物模式](https://github.com/frzyc/genshin-optimizer/blob/16292c0e2d72983be0e32a0fe50b931b2004640a/libs/gi/schema/src/artifact.ts)
- [G5：校验帮助函数的 fallback、catch 与钳制行为][G5]

### H：genshin.py

固定版本：`86193a8c46e4175864808d4874c6d0d8bec61f32`（提交时间 2026-09-28）。

- [H1：角色列表、详情与 raw 选项；可选缓存][H1]
- [H2：角色详情、装备、属性、技能模型及 base 展开][H2]
- [H3：地区路由][H3]；[UID 前缀与服务器映射](https://github.com/seriaati/genshin.py/blob/86193a8c46e4175864808d4874c6d0d8bec61f32/genshin/utility/uid.py)
- [H4：认证说明、更新 cookies 回调与 authkey 区别][H4]
- [H5：错误分类与返回码映射][H5]
- [H6：角色基础字段及静态数据库补全][H6]
- [H7：战绩请求与公开设置区分][H7]

### E：Enka 服务所有者文档

固定版本：`19eb305c51e9371270d8b67a462c501a5320ee83`（提交时间 2026-09-30）。

- [E1：UID/profile 端点、ttl、可见性、保存配装与 HTTP 错误][E1]
- [E2：原神角色、属性、技能和装备字段][E2]

[G1]: https://github.com/frzyc/genshin-optimizer/blob/16292c0e2d72983be0e32a0fe50b931b2004640a/libs/gi/page-doc/src/index.tsx
[G2]: https://github.com/frzyc/genshin-optimizer/blob/16292c0e2d72983be0e32a0fe50b931b2004640a/libs/gi/ui/src/components/database/DatabaseCard.tsx
[G3]: https://github.com/frzyc/genshin-optimizer/blob/16292c0e2d72983be0e32a0fe50b931b2004640a/libs/gi/db/src/Database/ArtCharDatabase.ts
[G4]: https://github.com/frzyc/genshin-optimizer/blob/16292c0e2d72983be0e32a0fe50b931b2004640a/libs/gi/good/src/schemas/good-format.ts
[G5]: https://github.com/frzyc/genshin-optimizer/blob/16292c0e2d72983be0e32a0fe50b931b2004640a/libs/common/database/src/lib/zodSchemas.ts
[H1]: https://github.com/seriaati/genshin.py/blob/86193a8c46e4175864808d4874c6d0d8bec61f32/genshin/client/components/chronicle/genshin.py
[H2]: https://github.com/seriaati/genshin.py/blob/86193a8c46e4175864808d4874c6d0d8bec61f32/genshin/models/genshin/chronicle/characters.py
[H3]: https://github.com/seriaati/genshin.py/blob/86193a8c46e4175864808d4874c6d0d8bec61f32/genshin/client/routes.py
[H4]: https://github.com/seriaati/genshin.py/blob/86193a8c46e4175864808d4874c6d0d8bec61f32/docs/authentication.md
[H5]: https://github.com/seriaati/genshin.py/blob/86193a8c46e4175864808d4874c6d0d8bec61f32/genshin/errors.py
[H6]: https://github.com/seriaati/genshin.py/blob/86193a8c46e4175864808d4874c6d0d8bec61f32/genshin/models/genshin/character.py
[H7]: https://github.com/seriaati/genshin.py/blob/86193a8c46e4175864808d4874c6d0d8bec61f32/genshin/client/components/chronicle/base.py
[E1]: https://github.com/EnkaNetwork/API-docs/blob/19eb305c51e9371270d8b67a462c501a5320ee83/api.md
[E2]: https://github.com/EnkaNetwork/API-docs/blob/19eb305c51e9371270d8b67a462c501a5320ee83/docs/gi/api.md

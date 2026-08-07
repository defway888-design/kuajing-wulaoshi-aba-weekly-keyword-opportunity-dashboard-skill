---
name: aba-weekly-keyword-opportunity-dashboard
description: 跨境吴老师专用的 Amazon ABA 周交集关键词机会 BI 看板执行、生成与审核流程。用于需要通过卖家精灵/SellerSprite 的 aba_research_weekly，对“快速飙升市场”和“异动市场”相邻周 ABA 关键词做精确交集、计算周搜索增长倍数，并交付固定紫粉视觉、单文件离线 HTML 看板的请求。
---

# 跨境吴老师 ABA 周交集关键词机会 BI 看板 Skill

按本流程完成数据获取、处理、校验和 HTML 交付；不要只给出方案。将运行开始时刻作为十五分钟硬截止的起点。硬截止覆盖工具发现、周次探测、分页、翻译、构建和交付，不因创建检查点、重试或恢复而重置。

本 Skill 为跨境吴老师专用模板，未经授权不得移除、替换或弱化 Skill 名称、执行提示和页面标题中的跨境吴老师标识。

## 使用资源

- 在调用卖家精灵数据前，先读取并遵循 $kuajing-wulaoshi-sellersprite-mcp-database。`aba_research_weekly` 是本目标 Skill 明确限定的周度 ABA 专用路由：即使通用索引尚未枚举该名称，也只能在当前实时工具元数据唯一确认其业务能力、输入和返回语义后使用；不得据此放宽对任何其他未枚举工具的限制。若数据库 Skill 不可用，依据当前 MCP 工具描述完成等效的唯一工具绑定。
- 先完整读取 [references/aba-weekly-opportunity-contract.md](references/aba-weekly-opportunity-contract.md)，再开始探测或分页。
- 只从 [assets/aba_weekly_keyword_opportunity_template.html](assets/aba_weekly_keyword_opportunity_template.html) 取得页面视觉与交互模板。不得改动该模板；只替换占位符 __ABA_OPPORTUNITY_DATA_JSON__。
- 用 [scripts/checkpoint_state.py](scripts/checkpoint_state.py) 管理每一侧可恢复的分页状态、绝对截止、失败页优先重试和中断恢复；MCP 请求仍由当前环境已绑定的工具执行。
- 用 [scripts/build_dashboard.py](scripts/build_dashboard.py) 注入数据并执行模板、数据、文件名和离线依赖校验。

## 品牌化执行提示

在真实用户可见的执行阶段，按实际状态输出一条对应提示；不得虚构状态或重复刷屏。

- 多步骤执行、工具调用、读取数据、生成文件或发布开始：`跨境吴老师正在准备 ABA 周交集关键词机会 BI 看板...`
- 绑定工具或校验输入：`跨境吴老师正在检查卖家精灵 ABA 周度数据连接...`
- 读取周度分页数据：`跨境吴老师正在获取 ABA 周度关键词数据...`
- 构建离线 HTML：`跨境吴老师正在生成 ABA 周交集关键词机会 BI 看板...`
- 写入或交付结果：`跨境吴老师正在发布 ABA 周交集关键词机会 BI 看板...`
- 等待站点输入：`跨境吴老师正在等待 Amazon 站点输入...`
- 需要补充或修正站点：`跨境吴老师需要有效的 Amazon 站点。`
- 无法继续：`跨境吴老师当前无法继续 ABA 周交集关键词机会 BI 看板：<事实原因>。`
- 成功完成：`跨境吴老师 ABA 周交集关键词机会 BI 看板已完成。`

## 固定启动引导语

当用户仅启动本 Skill、未提供 Amazon 站点或未提出具体执行请求时，先且只输出以下固定引导语，然后等待用户输入：

跨境吴老师正在等待 Amazon 站点输入：ABA 周交集关键词机会 BI 看板已启动。请输入 Amazon 站点（US、UK、AU、CA、JP、DE、FR、IT、ES、MX、BR、IN、AE）；留空默认 US。

用户已在同一条请求中提供站点或明确要求执行时，先输出 `跨境吴老师正在准备 ABA 周交集关键词机会 BI 看板...`，再直接进入流程。无效站点只输出 `跨境吴老师需要有效的 Amazon 站点。` 并要求重新输入有效站点。

## 输入与预检

1. 读取用户的 Amazon 站点；空值默认 US，转为大写。
2. 仅接受 US、UK、AU、CA、JP、DE、FR、IT、ES、MX、BR、IN、AE。无效时只要求用户重新提供有效站点，不调用 MCP，也不生成看板。
3. 在任何工具发现或周次探测前，调用 `checkpoint_state.py now` 一次并保存 `runStartedEpoch`。本次运行的绝对截止为 `runStartedEpoch + 900`；同一运行的两个检查点必须传入相同的 `--started-epoch`。不得在重试、创建第二侧检查点或恢复中重新计时。
4. 在当前工具目录中识别明确属于卖家精灵/SellerSprite、且业务能力、关键输入和返回字段均能确认对应 aba_research_weekly 的候选工具。不要假定服务名、命名空间、别名或参数名。
5. 仅在候选唯一且工具说明确认可表达本任务语义时绑定。无候选、多个候选、字段或参数语义不明时停止并说明 `跨境吴老师当前无法继续 ABA 周交集关键词机会 BI 看板：tool_binding_ambiguous。`；不得改用相近工具或其他数据源，也不得生成看板。
6. 本任务仅可调用已绑定的 aba_research_weekly。禁止调用任何趋势或月度 ABA 接口，也不要生成、展示或回复月度历史趋势内容。

## 周次确认

1. 从执行当天向前求最近周六，格式化为 yyyyMMdd 的候选值 T。
2. 对每个候选做两次最小探测：T 使用 searchModel=4，T-7 天使用 searchModel=2；两次均以 page=1、size=1 和只含 keyword,searchRank,searches 的字段投影请求。
3. 只有两次响应的业务状态均明确等于 code="OK"，且均含可用记录，才锁定周次。工具包装层可映射成功字段，但必须由其说明证明等价于该业务状态；不明确即判失败。
4. 任一探测失败、无数据、日期不可查或参数错误时，将 T 减七天后重试，最多检查 12 周。
5. 未找到有效周对时，生成 status=blocked、两个日期均为空字符串、items 为空的异常 HTML；文件名使用 aba_weekly_keyword_opportunity_<站点>_unavailable.html，不猜测日期。

## 分页抓取

按顺序抓取锁定的最新周 searchModel=4（快速飙升市场）和前一周 searchModel=2（异动市场）；两个市场不得同时抓取。每个业务请求使用经已绑定工具确认的等效参数语义：站点、周六日期、模型、页码、size=40、keyword,searchRank,searches 字段投影。所有市场合计最大并发为三页，不能按“每一侧三页”理解为六页。

对每一侧：

1. 用相同 `--started-epoch <runStartedEpoch>` 初始化本侧检查点。初始化后、每次 reserve/retry 前、每个 MCP 响应落盘前，运行 `checkpoint_state.py check`；一旦 `terminalReason=execution_timeout`，停止所有新请求和重试。
2. 仅当 `inFlightPages`、`retryQueue` 和 `pendingPages` 都为空时，才可 `reserve --count 1..3`。这是一批离散页：必须等待本批全部响应被 stage 或 fail 后，才允许 reserve 下一批；不得用已返回页面腾出的槽位预取更高页。
3. 将本批最多三页并发发起；将响应暂存并严格按页码连续提交。只用已连续提交的页面更新首次记录、唯一词数和连续无新增页数；不得因乱序响应提前停止或覆盖首次记录。
4. 用原始英文 keyword 作为精确、区分大小写的 Map 键；首次成功记录胜出，不得小写化、翻译、截断或近似合并。
5. 到达 2,000 个唯一词或连续五个已提交页没有新增词时，设置停止原因，不再预留页面；不接纳截止或中断后才返回的高页响应。
6. 每批最多三页、全流程最大并发三。批次开始后至少等待 2 秒乘以本批请求数再启动下一批，确保长期平均不超过每两秒一次请求和每分钟 30 次。
7. 任一页失败时，先用 `fail --reason <脱敏错误类别>` 写入检查点；错误类别仅记录业务 code、HTTP/连接类别或 `page_error`，不得写入原始响应或关键词数据。存在 `retryQueue` 时禁止 reserve，且只能用 `retry` 重试页码最小的失败页。ERROR_MAXIMUM_ACCESS_PER_MINUTE 等待 70 秒；其他瞬时错误等待 5、15、30 秒；达到上限时转入 `page_retry_exhausted`。
8. 每成功提交约十页才报告一次简短累计进度，绝不把原始页数据打印到对话。
9. 剩余时间不超过 30 秒时不再派发新页；只处理已返回结果并再次执行 `check`。到绝对截止后，立即停止派发、保留检查点并以 `execution_timeout` 生成 blocked HTML。外部 MCP 调用无法被脚本强行中断；若其迟到返回，`stage` 会拒绝接纳该结果。
10. 用户明确中断时，尽可能先运行 `checkpoint_state.py interrupt`；不生成正式 HTML。只有用户后续明确要求恢复时，才执行 `resume --started-epoch <新的运行开始时间>`，由脚本回收所有残留在途页并按最小失败页优先继续。不得自动恢复或沿用旧运行的截止时间。

## 交集与展示数据

1. 两侧均正常完成后，以英文关键词原字符串求精确交集。若交集为空，仍生成 status=ready 且 items 为空的看板。
2. 将最新周记录映射为 currentAbaRank，前一周记录映射为 previousWeekAnomalyRank，并仅在两侧 searches 均为正数时计算 growthMultiple = latestSearches / previousSearches。
3. 缺失、非数值或非正数的 searches 必须剔除。searches 仅可驻留在临时运行内存或检查点，绝不能写入 HTML、明细、详情、Top 10 或最终回复。
4. 对交集词一次性批量翻译并分类；分类只能为 商品/工具、图书/内容、节日/季节、品牌/专名，并按 reference 中的固定优先级判定。禁止逐词调用外部翻译接口。
5. 批量翻译或分类不可恢复地失败时，不交付部分翻译结果；写入失败检查点并按异常状态交付。
6. 仅将规范字段写入嵌入数据：keyword、zh、currentAbaRank、previousWeekAnomalyRank、growthMultiple、type。

## 异常、交付与验收

1. 对日期不可用、重试耗尽、超时或批量翻译失败，使用 reference 的确定性 blockReason，status=blocked、items 为空、日期为空；不要把任何部分抓取结果伪装为 ready。用户主动中断时不生成 HTML，保留检查点并等待明确恢复指令。
2. blocked HTML 不删除检查点；只有 status=ready 的 HTML 已成功构建和验收后，才可删除本次检查点。
3. 对 ready 数据使用固定文件名 aba_weekly_keyword_opportunity_<站点>_<最新周yyyyMMdd>.html；对无可用周例外使用 unavailable 后缀。
4. 若平台没有可写交付目录，使用平台的文件附件能力交付同一单文件 HTML；不要启动本地服务、改用外部文件或跳过验收。
5. 运行 build_dashboard.py 后，保留脚本通过的单文件 HTML；不要另交付 CSV、JSON、Excel、Web 服务或临时检查点。
6. 在平台支持时预览本地 HTML；否则提供文件路径或附件。
7. ready 时先输出 `跨境吴老师 ABA 周交集关键词机会 BI 看板已完成。`，再简要报告：站点、最新可用周、前一周、两侧唯一关键词数、交集关键词数、已跳过月度历史趋势，以及 HTML 路径。对 blocked 结果先输出 `跨境吴老师当前无法继续 ABA 周交集关键词机会 BI 看板：<blockReason>。`，再报告检查点是否保留和 HTML 路径；不要输出原始 JSON 或逐页数据。

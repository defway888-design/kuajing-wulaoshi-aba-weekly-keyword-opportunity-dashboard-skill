---
name: aba-weekly-keyword-opportunity-dashboard
description: 生成、执行、审核 Amazon ABA 周交集关键词机会 BI 看板。用于需要通过卖家精灵/SellerSprite 的 aba_research_weekly，对“快速飙升市场”和“异动市场”相邻周 ABA 关键词做精确交集、计算周搜索增长倍数，并交付固定紫粉视觉、单文件离线 HTML 看板的请求。
---

# ABA 周交集关键词机会看板

按本流程完成数据获取、处理、校验和 HTML 交付；不要只给出方案。将运行开始时刻作为十五分钟硬截止的起点。

## 使用资源

- 在调用卖家精灵数据前，先读取并遵循 $kuajing-wulaoshi-sellersprite-mcp-database。若该 Skill 不可用，依据当前 MCP 工具描述完成等效的唯一工具绑定。
- 先完整读取 [references/aba-weekly-opportunity-contract.md](references/aba-weekly-opportunity-contract.md)，再开始探测或分页。
- 只从 [assets/aba_weekly_keyword_opportunity_template.html](assets/aba_weekly_keyword_opportunity_template.html) 取得页面视觉与交互模板。不得改动该模板；只替换占位符 __ABA_OPPORTUNITY_DATA_JSON__。
- 用 [scripts/checkpoint_state.py](scripts/checkpoint_state.py) 管理每一侧可恢复的分页状态和当前页重试；MCP 请求仍由当前环境已绑定的工具执行。
- 用 [scripts/build_dashboard.py](scripts/build_dashboard.py) 注入数据并执行模板、数据、文件名和离线依赖校验。

## 固定启动引导语

当用户仅启动本 Skill、未提供 Amazon 站点或未提出具体执行请求时，先且只输出以下固定引导语，然后等待用户输入：

跨境吴老师 ABA 周交集关键词机会 BI 看板已启动。请输入 Amazon 站点（US、UK、AU、CA、JP、DE、FR、IT、ES、MX、BR、IN、AE）；留空默认 US。

用户已在同一条请求中提供站点或明确要求执行时，不输出该引导语，直接进入流程。无效站点仍仅要求重新输入有效站点。

## 输入与预检

1. 读取用户的 Amazon 站点；空值默认 US，转为大写。
2. 仅接受 US、UK、AU、CA、JP、DE、FR、IT、ES、MX、BR、IN、AE。无效时只要求用户重新提供有效站点，不调用 MCP，也不生成看板。
3. 在当前工具目录中识别明确属于卖家精灵/SellerSprite、且业务能力、关键输入和返回字段均能确认对应 aba_research_weekly 的候选工具。不要假定服务名、命名空间、别名或参数名。
4. 仅在候选唯一且工具说明确认可表达本任务语义时绑定。无候选、多个候选、字段或参数语义不明时停止并说明 blocked: tool_binding_ambiguous；不得改用相近工具或其他数据源，也不得生成看板。
5. 本任务仅可调用已绑定的 aba_research_weekly。禁止调用任何趋势或月度 ABA 接口，也不要生成、展示或回复月度历史趋势内容。

## 周次确认

1. 从执行当天向前求最近周六，格式化为 yyyyMMdd 的候选值 T。
2. 对每个候选做两次最小探测：T 使用 searchModel=4，T-7 天使用 searchModel=2；两次均以 page=1、size=1 和只含 keyword,searchRank,searches 的字段投影请求。
3. 只有两次响应的业务状态均明确等于 code="OK"，且均含可用记录，才锁定周次。工具包装层可映射成功字段，但必须由其说明证明等价于该业务状态；不明确即判失败。
4. 任一探测失败、无数据、日期不可查或参数错误时，将 T 减七天后重试，最多检查 12 周。
5. 未找到有效周对时，生成 status=blocked、两个日期均为空字符串、items 为空的异常 HTML；文件名使用 aba_weekly_keyword_opportunity_<站点>_unavailable.html，不猜测日期。

## 分页抓取

分别抓取锁定的最新周 searchModel=4（快速飙升市场）和前一周 searchModel=2（异动市场）。每个业务请求使用经已绑定工具确认的等效参数语义：站点、周六日期、模型、页码、size=40、keyword,searchRank,searches 字段投影。

对每一侧：

1. 先用 checkpoint_state.py 初始化检查点，再一次预留不超过三页；只对预留页发起 MCP 请求。
2. 允许最多三页并发，但将响应暂存并严格按页码连续提交。只用已连续提交的页面更新首次记录、唯一词数和连续无新增页数；不得因乱序响应提前停止或覆盖首次记录。
3. 用原始英文 keyword 作为精确、区分大小写的 Map 键；首次成功记录胜出，不得小写化、翻译、截断或近似合并。
4. 到达 2,000 个唯一词或连续五个已提交页没有新增词时，设置停止原因，不再预留页面；已在飞的高页响应可以丢弃，不得覆盖已提交页。
5. 每批最多三页、最大并发三。批次开始后至少等待 2 秒乘以本批请求数再启动下一批，确保长期平均不超过每两秒一次请求和每分钟 30 次。
6. 遇到 ERROR_MAXIMUM_ACCESS_PER_MINUTE 时等待 70 秒，只重试当前失败页。其他瞬时错误仅重试当前页三次，等待 5、15、30 秒；达到上限时写入失败检查点并转入 blocked。
7. 每成功提交约十页才报告一次简短累计进度，绝不把原始页数据打印到对话。
8. 到十五分钟硬截止时，停止派发，写入检查点并转入 blocked。只检查串行抓取、聊天输出原始页、错误调用趋势接口、频繁限流、未并发和未使用五页停止条件；不要继续重试。

## 交集与展示数据

1. 两侧均正常完成后，以英文关键词原字符串求精确交集。若交集为空，仍生成 status=ready 且 items 为空的看板。
2. 将最新周记录映射为 currentAbaRank，前一周记录映射为 previousWeekAnomalyRank，并仅在两侧 searches 均为正数时计算 growthMultiple = latestSearches / previousSearches。
3. 缺失、非数值或非正数的 searches 必须剔除。searches 仅可驻留在临时运行内存或检查点，绝不能写入 HTML、明细、详情、Top 10 或最终回复。
4. 对交集词一次性批量翻译并分类；分类只能为 商品/工具、图书/内容、节日/季节、品牌/专名，并按 reference 中的固定优先级判定。禁止逐词调用外部翻译接口。
5. 批量翻译或分类不可恢复地失败时，不交付部分翻译结果；写入失败检查点并按异常状态交付。
6. 仅将规范字段写入嵌入数据：keyword、zh、currentAbaRank、previousWeekAnomalyRank、growthMultiple、type。

## 异常、交付与验收

1. 对日期不可用、重试耗尽、超时或批量翻译失败，使用 reference 的确定性 blockReason，status=blocked、items 为空、日期为空；不要把任何部分抓取结果伪装为 ready。
2. blocked HTML 不删除检查点；只有 status=ready 的 HTML 已成功构建和验收后，才可删除本次检查点。
3. 对 ready 数据使用固定文件名 aba_weekly_keyword_opportunity_<站点>_<最新周yyyyMMdd>.html；对无可用周例外使用 unavailable 后缀。
4. 若平台没有可写交付目录，使用平台的文件附件能力交付同一单文件 HTML；不要启动本地服务、改用外部文件或跳过验收。
5. 运行 build_dashboard.py 后，保留脚本通过的单文件 HTML；不要另交付 CSV、JSON、Excel、Web 服务或临时检查点。
6. 在平台支持时预览本地 HTML；否则提供文件路径或附件。
7. 最终只简要报告：站点、最新可用周、前一周、两侧唯一关键词数、交集关键词数、已跳过月度历史趋势，以及 HTML 路径。对 blocked 结果只报告 blockReason、检查点是否保留和 HTML 路径；不要输出原始 JSON 或逐页数据。

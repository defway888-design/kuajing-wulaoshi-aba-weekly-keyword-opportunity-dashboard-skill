---
name: aba-weekly-keyword-opportunity-dashboard
description: 跨境吴老师专用的 Amazon ABA 异动需求机会BI看板执行、生成与审核流程。用于通过卖家精灵/SellerSprite 的 aba_research_weekly，对“快速飙升市场”和“异动市场”相邻周关键词做精确交集，为每个共同英文关键词生成 AI 中文翻译，并以本地 Runner 或受控 MCP 编排交付单文件离线 HTML 看板。
---

# 跨境吴老师异动需求机会BI看板 Skill

按本流程完成数据获取、处理、校验和 HTML 交付。单次执行持续至两侧数据正常结束、出现确定性阻塞或用户明确中断；不得以总执行时长终止、阻塞或否定结果。

本 Skill 为跨境吴老师专用模板，未经授权不得移除、替换或弱化 Skill 名称、执行提示和页面标题中的跨境吴老师标识。

## 使用资源

- 调用卖家精灵数据前，先读取并遵循 `$kuajing-wulaoshi-sellersprite-mcp-database`。`aba_research_weekly` 仅在当前实时工具元数据唯一确认其业务能力、输入和返回语义后使用；不得据此放宽其他未枚举工具的边界。
- 先完整读取 [references/aba-weekly-opportunity-contract.md](references/aba-weekly-opportunity-contract.md)。
- 使用 [scripts/aba_local_runner.py](scripts/aba_local_runner.py) 作为一次性本地执行器。它只能通过显式提供的本地适配器访问已绑定工具，绝不读取 Codex 配置、猜测服务别名、地址或密钥。
- 使用 [scripts/checkpoint_state.py](scripts/checkpoint_state.py) 管理分页状态、失败页优先重试和中断恢复；Runner 已直接复用它。
- 只从 [assets/aba_weekly_keyword_opportunity_template.html](assets/aba_weekly_keyword_opportunity_template.html) 取得视觉模板，并用 [scripts/build_dashboard.py](scripts/build_dashboard.py) 生成和验收单文件 HTML。

## 品牌化执行提示

在真实用户可见的阶段各输出一条对应提示，不虚构状态或重复刷屏。

- 开始：`跨境吴老师正在准备异动需求机会BI看板...`
- 绑定工具：`跨境吴老师正在检查卖家精灵 ABA 周度数据连接...`
- 读取分页：`跨境吴老师正在获取 ABA 周度关键词数据...`
- 构建文件：`跨境吴老师正在生成异动需求机会BI看板...`
- 交付文件：`跨境吴老师正在发布异动需求机会BI看板...`
- 等待站点：`跨境吴老师正在等待 Amazon 站点输入...`
- 站点无效：`跨境吴老师需要有效的 Amazon 站点。`
- 阻塞：`跨境吴老师当前无法继续异动需求机会BI看板：<事实原因>。`
- 完成：`跨境吴老师异动需求机会BI看板已完成。`

## 固定启动引导语

当用户仅启动本 Skill、未提供站点或具体执行请求时，只输出以下内容并等待输入：

跨境吴老师正在等待 Amazon 站点输入：异动需求机会BI看板已启动。请输入 Amazon 站点（US、UK、AU、CA、JP、DE、FR、IT、ES、MX、BR、IN、AE）；留空默认 US。

用户已提供站点或明确要求执行时，先输出准备提示后进入流程。站点仅接受 US、UK、AU、CA、JP、DE、FR、IT、ES、MX、BR、IN、AE；空值默认为 US。

## 工具绑定与本地 Runner

1. 唯一绑定当前环境中属于卖家精灵、且能确认对应 `aba_research_weekly` 的工具。关键语义必须包括：站点、周六日期、`searchModel`、页码、每页数量和字段投影；候选不唯一或语义不明时以 `tool_binding_ambiguous` 停止。
2. 只向卖家精灵请求 `keyword,searchRank`。周度接口未明确提供“周搜索量”语义，因此不得请求、保存、计算或展示 searches、周搜索增长倍数或机会类型；中文翻译只能在精确交集确定后由 AI 独立补全，绝不是卖家精灵原始字段。
3. 优先使用本地 Runner。适配器命令必须由当前环境明确提供，并以标准输入接收一条：

   ```json
   {"operation":"aba_research_weekly","request":{"marketplace":"US","date":"yyyyMMdd","searchModel":4,"page":1,"size":40,"returnFields":"keyword,searchRank"}}
   ```

   适配器标准输出只能是：

   ```json
   {"code":"OK","items":[{"keyword":"english keyword","searchRank":1}]}
   ```

   不得把原始工具响应、密钥或未请求字段输出给 Runner。以 JSON 字符串数组传入 `--adapter-command`；在 Windows shell 中优先使用 UTF-8 JSON 文件的 `--adapter-command-file`，不使用 shell 字符串拼接。
4. 本地 Runner 如需生成正式看板，还必须有当前环境明确提供的翻译适配器。它一次接收全部精确交集词：

   ```json
   {"operation":"translate_keywords","sourceLanguage":"en","targetLanguage":"zh-CN","keywords":["english keyword"]}
   ```

   并只返回：

   ```json
   {"items":[{"keyword":"english keyword","keywordZh":"中文翻译"}]}
   ```

   翻译适配器必须一词一译、覆盖全部交集、输出含中文字符的非空 `keywordZh`；不得返回解释、来源、原始模型响应或额外字段。
5. 一次性调用示例：

   ```text
   aba_local_runner.py --marketplace US --adapter-command-file <显式ABA命令数组文件> --translation-command-file <显式翻译命令数组文件> --output-dir <交付目录> --work-dir <临时检查点目录>
   ```

   Runner 在一个本地进程内完成周次探测、两个市场的顺序分页、精确交集、中文翻译和 HTML 构建；ready 后删除其检查点，只输出脱敏汇总。缺少翻译适配器且交集非空时，受控输出 `translation_adapter_unavailable`，不得伪造翻译。
6. 若当前环境没有明确的 ABA 或翻译适配器，不得伪造本地接口。改用一次连续的 Codex MCP 编排执行同一规则：保持状态在当前执行中、按批次调用已绑定工具；精确交集完成后一次性生成中文翻译，不得逐页向用户输出或把脚本命令误称为数据调用。

## 周次与分页规则

1. 从执行当天向前找最近周六 T。探测 T 的 `searchModel=4` 与 T-7 的 `searchModel=2`，均使用 page=1、size=1；两次 `code="OK"` 且各有记录才锁定。失败时每次回退七天，最多 12 组。
2. 最新周固定为快速飙升市场（4），前一周固定为异动市场（2）；两个市场必须顺序抓取。
3. 每页 size=40；每批最多三页，全流程并发最多三页。整批结果都 stage 或 fail 后才能申请下一批。
4. 仅以原始英文 `keyword` 的区分大小写精确值去重；首次成功记录胜出。到 2,000 个唯一词，或五个连续已提交页均无新增词时停止该市场。
5. 失败页必须先写入检查点，只重试页码最小的失败页。限流错误等待 70 秒；其他瞬时错误按 5、15、30 秒等待；非限流错误第三次失败后 `page_retry_exhausted`。
6. 每批完成后至少等待该批请求数 × 2 秒；不得跨越失败页预取。该等待和单次适配器通信超时只用于限流与失联识别，不构成总时长判定。
7. 用户明确中断时标记 `execution_interrupted`，不生成正式 HTML；只有用户明确要求恢复时才使用 Runner 的 `--resume` 继续，Runner 只会读取其 work-dir 中唯一的保留检查点。

## 数据、交付与验收

1. 两侧正常结束后，计算英文关键词精确交集。每项仅包含 `keyword`、`keywordZh`、`currentAbaRank`、`previousWeekAnomalyRank`；交集可为空。
2. `keywordZh` 必须为该英文关键词的非空中文 AI 翻译，保持与 `keyword` 一对一对应；品牌、人物、书影视名称、型号或尺寸可使用中文译名、音译或中文说明，但不得改写英文原词、捏造卖家精灵指标或宣称为官方翻译。页面必须标注“中文翻译（AI）”。
3. 不得计算或展示搜索量、增长倍数、机会类型、趋势、月度历史或任何未由本次周度工具确认的字段。
4. ready HTML 文件名为 `aba_weekly_anomaly_demand_opportunity_<站点>_<最新周yyyyMMdd>.html`；blocked 文件名为 `aba_weekly_anomaly_demand_opportunity_<站点>_unavailable.html`。
5. 可用 blocked 原因为 `no_valid_week_pair`、`page_retry_exhausted`、`runner_adapter_failed`、`translation_adapter_unavailable`、`translation_adapter_failed`。blocked 数据日期和 items 必须为空；中断不生成 HTML。
6. 只交付通过构建脚本校验的单文件 HTML，不交付原始响应、检查点、JSON、CSV、Excel、服务地址或临时文件。
6. 完成时简要报告：站点、两个周次、两侧唯一关键词数、交集数、耗时和 HTML 路径；不输出逐页数据。

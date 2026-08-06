# ABA 周交集机会看板数据与交付契约

## 数据范围与周次锁定

- 只使用已唯一绑定的 aba_research_weekly 业务能力。
- 最新可用周固定代表“快速飙升市场”，使用 searchModel=4；前一周固定代表“异动市场”，使用 searchModel=2。
- 只请求并使用 keyword、searchRank、searches。若工具将字段投影参数命名为其他名称，仅在工具描述明确表达相同语义时映射。
- 两次周次探测必须同时满足：业务响应 code="OK"，并且返回至少一条可用记录。包装层只能在字段语义已文档化时映射到这个判断。
- 禁止调用 ABA 趋势、月度 ABA、近 24 个月月度历史及任何会返回月度趋势字段的能力。

## 检查点和页序提交

对每个市场建立独立检查点。使用 checkpoint_state.py 的 init、reserve、stage、fail 和 retry 命令，检查点只用于本次运行恢复，不得随 ready HTML 交付。

    version, marketplace, date, searchModel
    nextPage, nextCommitPage, inFlightPages, pendingPages, committedPages
    keywordMap, noNewPages, retryQueue, stopReason, terminalReason

请求语义：

    marketplace = 用户站点
    date        = 经验证的周六（yyyyMMdd）
    searchModel = 4 或 2
    page        = 当前页
    size        = 40
    fields      = keyword,searchRank,searches

reserve 一次最多分配三页，最大并发三。页面可以乱序返回，但 stage 只能从 nextCommitPage 起连续提交；每次提交才计算唯一词、连续无新增页和停止条件。这样既保留并发，又保证“首次成功记录”和“五页连续无新增”按页码语义成立。

若提交后达到 2,000 个唯一词或五页连续无新增，立即设置 stopReason；不再 reserve，且忽略已经在飞的高页结果。批次开始后等待至少 2 秒乘本批页数再发下一批，确保平均不高于每两秒一次请求、每分钟不超过 30 次。

## 失败和恢复决策

| 条件 | 行动 | HTML 状态 | 检查点 |
| --- | --- | --- | --- |
| 站点无效 | 仅要求重新输入；不调用工具 | 不生成 | 不创建 |
| 工具绑定不唯一或不明确 | 返回 blocked: tool_binding_ambiguous；不生成 | 不生成 | 不创建 |
| 12 周内无有效周对 | 停止，不猜日期 | blocked，日期为空 | 不创建 |
| ERROR_MAXIMUM_ACCESS_PER_MINUTE | 等待 70 秒，仅重试当前页 | 继续 | 保留 |
| 其他瞬时错误 | 当前页等待 5、15、30 秒重试 | 继续 | 保留 |
| 瞬时错误三次仍失败 | 写 terminalReason=page_retry_exhausted | blocked，日期为空 | 保留 |
| 全流程满 15 分钟 | 停止派发并性能排查 | blocked，日期为空 | 保留 |
| 批量翻译或分类不可恢复失败 | 不交付部分结果 | blocked，日期为空 | 保留 |
| 两侧完成但交集为空 | 交付空表看板 | ready | 成功后删除 |

blocked 数据必须为：

    {
      "status": "blocked",
      "blockReason": "<deterministic reason>",
      "marketplace": "US",
      "latestWeek": "",
      "previousWeek": "",
      "items": []
    }

可用的确定性原因只使用：no_valid_week_pair、page_retry_exhausted、execution_timeout、batch_enrichment_failed。不要在 blockReason 中附原始响应或 searches。

## 转换规则

1. 仅保留两侧均存在的英文关键词。
2. 两侧 searches 都是正数时，计算 growthMultiple = latestSearches / previousSearches；否则剔除。
3. 显示增长倍数时使用两位小数和 ×，但数据保存为数值。
4. 批量补充中文翻译并按以下优先级一次性分类：
   1. 品牌/专名
   2. 图书/内容
   3. 节日/季节
   4. 商品/工具
5. 明显品牌词、书名、作者名、角色名或无法可靠翻译的专名，英文保留，中文写为 品牌词/书名/专名。

## 嵌入数据

ready 数据仅接受以下顶层字段：

    {
      "status": "ready",
      "blockReason": "",
      "marketplace": "US",
      "latestWeek": "2026年07月18日",
      "previousWeek": "2026年07月11日",
      "items": [
        {
          "keyword": "example keyword",
          "zh": "示例中文",
          "currentAbaRank": 1,
          "previousWeekAnomalyRank": 2,
          "growthMultiple": 2.5,
          "type": "商品/工具"
        }
      ]
    }

items 的每一项只能含示例所列六个字段，最多 2,000 项。不得携带 searches、调试信息或原始 API 字段。ready 的两个日期必须是中文格式，且相差七天；items 允许为空。

## 文件名、附件与验收

- ready 文件名严格为 aba_weekly_keyword_opportunity_<站点>_<最新周yyyyMMdd>.html。
- 仅当没有可验证的最新周时，blocked 文件名严格为 aba_weekly_keyword_opportunity_<站点>_unavailable.html。
- 没有可写本地目录时，通过平台附件交付同一 HTML；不得以 CSV、外部 JSON、固定端口或 localhost 服务替代。
- 模板 SHA-256 由构建脚本锁定，且只接受一个数据占位符。生成时只允许替换该占位符。
- 构建脚本会拒绝 fetch、XHR、WebSocket、EventSource、远程 URL、外部资源标签、@import、localhost 和月度趋势字段。
- 模板哈希验证通过后，页面固定包含标题、站点与两个周次卡片、搜索框、三种固定排序、四种固定类型筛选、六列表格、详情与 Top 10；前一周卡片只能标注“异动市场”。
- 明细表、详情和 Top 10 均不得展示 searches 原值。

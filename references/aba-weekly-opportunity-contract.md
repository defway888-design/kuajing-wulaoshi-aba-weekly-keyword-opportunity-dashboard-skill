# 跨境吴老师异动需求机会BI看板数据与交付契约

本 Skill 为跨境吴老师专用模板，未经授权不得移除、替换或弱化 Skill 名称、执行提示和页面标题中的跨境吴老师标识。

## 数据范围

- 唯一数据业务是已唯一绑定的 `aba_research_weekly`。
- 最新可用周使用 `searchModel=4`（快速飙升市场），前一周使用 `searchModel=2`（异动市场）。
- 每个业务请求只使用 `marketplace`、周六 `date`、`searchModel`、`page`、`size=40` 与字段投影 `keyword,searchRank`。
- 周度接口元数据未确认“周搜索量”字段语义；不得请求、保存、计算或展示 searches、增长倍数、机会类型、趋势或月度数据。`keywordZh` 是交集确定后由 AI 独立生成的中文翻译，不属于卖家精灵返回字段。
- 探测周对时，两次 page=1、size=1 响应均须为 `code="OK"` 且各含一条记录；最多向前检查 12 组周六。

## 本地 Runner 适配器

`scripts/aba_local_runner.py` 是单进程执行器。它不读取 Codex 配置、不发现服务、不保存密钥，也不能替代 MCP 工具绑定。

只有当前环境明确提供适配器命令时才可调用 Runner。适配器的单次输入、输出均固定为 UTF-8 JSON：

```json
{"operation":"aba_research_weekly","request":{"marketplace":"US","date":"yyyyMMdd","searchModel":4,"page":1,"size":40,"returnFields":"keyword,searchRank"}}
```

```json
{"code":"OK","items":[{"keyword":"english keyword","searchRank":1}]}
```

- 适配器负责将实际 MCP 包装层规范为上述输出；不得附加原始响应、密钥、错误正文或多余字段。
- Runner 只通过无 shell 的 JSON 命令数组启动适配器；Windows shell 优先传入 UTF-8 JSON 命令数组文件。
- 未提供适配器时，使用一次连续的 Codex MCP 编排，而非伪造 HTTP、别名或本地服务。

## 中文翻译适配器

本地 Runner 生成正式 ready HTML 时，翻译适配器也必须由当前环境明确提供；它不读取 Codex 配置、服务地址或密钥。单次输入、输出固定为 UTF-8 JSON：

```json
{"operation":"translate_keywords","sourceLanguage":"en","targetLanguage":"zh-CN","keywords":["english keyword"]}
```

```json
{"items":[{"keyword":"english keyword","keywordZh":"中文翻译"}]}
```

- 翻译输出必须与最终英文交集一一对应、无重复、无遗漏，且每个 `keywordZh` 非空并包含中文字符。
- 页面中必须以“中文翻译（AI）”标注该字段；它仅用于理解词义，不是卖家精灵原始字段或官方翻译。
- 没有明确翻译适配器时，不得为本地 Runner 编造翻译；交集非空则输出 `translation_adapter_unavailable`。受控 MCP 编排可由当前任务中的 AI 在精确交集完成后一次性生成同一字段。

## 检查点与分页

每个市场独立保存：

    version, marketplace, date, searchModel
    nextPage, nextCommitPage, inFlightPages, pendingPages, committedPages
    keywordMap, noNewPages, retryQueue, stopReason, terminalReason

- 每批最多三页，整批返回都 stage 或 fail 后才可 reserve 下一批；两个市场顺序执行，所有市场合计并发最多三。
- `keywordMap` 只以原始英文关键词区分大小写去重；只在页码连续提交时更新唯一词数、连续无新增页数与停止条件。
- 达到 2,000 个唯一词或连续五页无新增后停止 reserve。不得接受中断后返回的页。
- 每批完成后至少等待 `2 × 本批请求数` 秒，确保平均不超过每分钟 30 次。
- 失败时只重试最小页码。`ERROR_MAXIMUM_ACCESS_PER_MINUTE` 等待 70 秒；其他瞬时错误等待 5、15、30 秒，第三次仍失败则 `page_retry_exhausted`。
- 不设置全流程时长上限。单次适配器通信超时只用于识别失联的本地适配器，不得作为正常分页或周次探测的总时长判定。用户中断为 `execution_interrupted`，不生成 HTML。只有显式 `--resume` 才能使用 work-dir 中唯一的保留检查点。

## 嵌入数据

ready 只接受：

```json
{
  "status":"ready",
  "blockReason":"",
  "marketplace":"US",
  "latestWeek":"2026年07月25日",
  "previousWeek":"2026年07月18日",
  "items":[
    {"keyword":"example keyword","keywordZh":"示例关键词","currentAbaRank":1,"previousWeekAnomalyRank":2}
  ]
}
```

- items 最多 2,000 项，仅以上四个字段；`keywordZh` 必须为非空中文 AI 翻译，两侧排名必须为正整数。
- 两个 ready 周次必须相差七天；交集为空仍可 ready。
- blocked 只允许 `no_valid_week_pair`、`page_retry_exhausted`、`runner_adapter_failed`、`translation_adapter_unavailable` 或 `translation_adapter_failed`，且日期和 items 必须为空。

## 文件与验收

- ready 文件名：`aba_weekly_anomaly_demand_opportunity_<站点>_<最新周yyyyMMdd>.html`。
- blocked 文件名：`aba_weekly_anomaly_demand_opportunity_<站点>_unavailable.html`。
- 模板哈希由构建脚本锁定，只替换唯一的数据占位符。
- 成品必须离线可用，且不得包含外部请求、服务地址、临时检查点或未确认的数据字段。

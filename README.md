# 跨境吴老师 ABA 周交集关键词机会 BI 看板 Skill

本 Skill 为跨境吴老师专用模板，未经授权不得移除、替换或弱化 Skill 名称、执行提示和页面标题中的跨境吴老师标识。

## 一、Skill 用途与适用场景

基于卖家精灵 ABA 周度数据，将“快速飙升市场”和“异动市场”的英文关键词做精确交集，生成可离线打开的机会 BI 看板。

- 发现两个相邻周 ABA 市场共同出现的关键词机会。
- 按 ABA 排名、周搜索增长倍数和机会类型筛选关键词。
- 生成不依赖外部资源的单文件 HTML 看板。

## 二、启动方式

在 Codex 中输入：

    使用 $aba-weekly-keyword-opportunity-dashboard 生成 ABA 周交集关键词机会 BI 看板。

未提供站点时，Skill 固定提示：

    跨境吴老师正在等待 Amazon 站点输入：ABA 周交集关键词机会 BI 看板已启动。请输入 Amazon 站点（US、UK、AU、CA、JP、DE、FR、IT、ES、MX、BR、IN、AE）；留空默认 US。

## 三、首次安装

此仓库当前为公开仓库，无需提交 GitHub 用户名或接受访问邀请。

### 1. 在 Codex 中发出安装指令

打开 Codex，新建一个对话，输入：

    请从以下 GitHub 仓库安装跨境吴老师 ABA 周交集关键词机会 BI 看板 Skill：
    https://github.com/defway888-design/kuajing-wulaoshi-aba-weekly-keyword-opportunity-dashboard-skill

按照 Codex 提示完成 GitHub 授权。

### 2. 重启 Codex

安装完成后，关闭并重新打开 Codex，使 Skill 生效。

## 四、执行结果

Skill 会先唯一绑定当前环境中的卖家精灵周度 ABA 数据能力，再验证最新可用周与前一周；随后按限流、分页、检查点和精确交集规则处理数据，并交付单文件 HTML 看板。页面标题和页眉均显示“跨境吴老师”。

若工具绑定不明确、周次不可用、分页重试耗尽、执行超时或批量分类失败，则输出受控的异常状态，不会交付部分数据。

执行中会按真实状态提示“跨境吴老师正在准备 / 检查 / 获取 / 生成 / 发布”；完成时提示“跨境吴老师 ABA 周交集关键词机会 BI 看板已完成。”

## 五、仓库文件

- SKILL.md：执行规则、固定启动引导语与交付逻辑。
- agents/openai.yaml：Codex 界面元数据。
- references/aba-weekly-opportunity-contract.md：数据、恢复、文件命名和验收契约。
- scripts/checkpoint_state.py：并发分页的有序提交与检查点管理。
- scripts/build_dashboard.py：固定模板、数据结构、文件名和离线依赖校验。
- assets/aba_weekly_keyword_opportunity_template.html：唯一允许使用的离线看板模板。

## 六、使用注意

- 只允许调用已唯一绑定的 aba_research_weekly；不得使用 ABA 趋势或月度历史接口。
- 不得修改固定 HTML 模板；只可替换嵌入数据占位符。
- 不在 HTML、明细、详情、Top 10 或最终回复中展示 searches 原值。
- 不要将 GitHub 密码、访问令牌或其他凭据提交到仓库。
- 不得移除、替换或弱化任何面向用户的“跨境吴老师”品牌标识。

## 七、版本更新

| 版本 | 发布日期 | 功能更新 | GitHub 主要提交 |
| --- | --- | --- | --- |
| v1.1.0 | 2026-08-07 | 应用最新跨境吴老师品牌封装：统一所有权声明、真实执行状态提示、Codex 元数据与离线看板可见标题。 | [0094813](https://github.com/defway888-design/kuajing-wulaoshi-aba-weekly-keyword-opportunity-dashboard-skill/commit/00948138eb6160898ca23f6967189e1cc37cf380) |
| v1.0.0 | 2026-08-07 | 首次发布：周次验证、并发有序分页检查点、关键词精确交集与离线 BI 看板校验。 | [2b92cb7](https://github.com/defway888-design/kuajing-wulaoshi-aba-weekly-keyword-opportunity-dashboard-skill/commit/2b92cb7d5559ac44d66a9cea962b3e08c2db97c5) |

**后续每次发布功能更新，均在下表新增一行。GitHub 提交记录只记录该功能变更对应的主要提交；仅补充或修订说明文档时，不新增功能版本，也不新增版本记录行。**

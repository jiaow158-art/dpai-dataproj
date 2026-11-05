---
name: ar-analyst
description: 应收分析工作流。当用户询问应收账龄、逾期应收、回款率、应收账款周转、坏账减值、客户信用风险等需要执行分析的场景时自动激活。依赖 ar-knowledge 提供数据模型知识。
---

# 应收分析 — 工作流程

## 角色

你是一位资深财务分析师，熟悉 SAP FI-AR 模块和公司数仓 DWS (GaussDB) 体系。
在回答任何应收相关问题前，先按以下流程执行，不要跳过步骤。

## 分析流程（6 步法）

### 第 1 步：澄清需求

应收问题天然有歧义。在动手查数据之前，确认以下信息：

| 要澄清的 | 示例 |
|---|---|
| 时间范围 | "当前应收"是指最新快照还是某个月末？快照用 `query_date`，月末用 `edition_date` 或 `year`+`month` |
| 口径定义 | "应收"指本币余额(local_currency_balance_sum)、逾期金额(overdue_receivables) 还是含未逾期(n_overdue_receivables)？ |
| 账龄口径 | 应收账龄(ysyq=已收已清) / 应收未清(yswyq=已收未清) / 自然账龄(natural_receivables)？默认应收账龄 ysyq |
| 组织范围 | 哪个公司(comp_code)？哪个销售组(sales_grp/sales_group_master_file)？哪个 WBS？ |
| 客户范围 | 哪些客户(cust_code)？哪个客户组(cust_group_code)？ |
| 是否含特别总账 | `special_general_ledger` 是否过滤？ |

**关键问题清单**：
- "口径：本币余额 / 逾期金额 / 未逾期金额？"
- "账龄口径：标准 ysyq/yswyq 还是自然账龄 natural_receivables？"
- "时间口径：快照(query_date) 还是月末(edition_date/year+month)？"
- "是否含特别总账(special_general_ledger)？"
- "公司/销售组/WBS 范围？"

### 第 2 步：定位数据源

**必须先读语义层** `ar-knowledge/references/metrics.md`，按决策树选择表。

| 问题类型 | 首选用表 | 决策依据 |
|---|---|---|
| 应收账龄明细（客户+科目+WBS） | `dwrfin.dwr_ar_receivable_aging_2023_info_f` | 82列，13.4M行，最全最新 |
| 应收账龄（月度快照） | `dm.dm_ar_receivable_accage_t` | 45列，1.6M行，SAP 风格 |
| 应收余额 | `dwrfin.dwr_ar_receivable_balance_f` | 18列，6.5M行 |
| 票据级账龄 | `dwrfin.dwr_ar_bill_aging_f` | 63列，1万行 |
| 逾期应收监控 | `dm.dm_ar_overdue_receivables_t` | 32列，3.1M行 |
| 回款明细 | `dwrfin.dwr_ar_collection_detail_f` | 31列，12.9M行 |
| 坏账减值 | `dwrfin.dwr_ar_credit_devalue_f` | 129列，5.6M行 |
| 回款/付款 | `dm.dm_ar_return_payment_t` | 21列，1.8M行 |
| 综合分析报表 | `dm.dm_ar_analysis_rpt_f` | 208列，1.6M行 |
| 应收周转天数 | `dwrfin.dwr_ar_receivable_turnover_days_f` | 4列，484行 |
| 客户主数据 | `dwrdim.dwr_dim_cust_partner_d` | 79列，1.7M行 |

### 第 3 步：应用标准过滤

每条查询都必须带时间过滤。大表不带时间会全表扫描：

```sql
-- dwr_ar_receivable_aging_2023_info_f: query_date YYYY-MM-DD（带连字符）
WHERE query_date = '2026-06-08'

-- dm_ar_receivable_accage_t: edition_date YYYYMMDD（不带连字符）
WHERE edition_date = '20260608'

-- dwr_ar_receivable_balance_f: year + month
WHERE year = '2026' AND month = '2026-06'

-- dwr_ar_collection_detail_f: year + month
WHERE year = '2026' AND month = '2026-06'

-- dm_ar_analysis_rpt_f: calmonth YYYY-MM（带连字符，实测 '2025-08'）
WHERE calmonth = '2026-06'

-- dm_ar_overdue_receivables_t: ed_mon YYYYMM
WHERE ed_mon = '202606'
```

### 第 4 步：自检审查

生成 SQL 后，逐条检查：

- [ ] 时间字段格式（按表区分）：
      - `dwr_ar_receivable_aging_2023_info_f.query_date` = `'2026-06-08'` (YYYY-MM-DD 带连字符)
      - `dwr_ar_credit_devalue_f.query_date` = `'2026-06-08'` (YYYY-MM-DD 带连字符)
      - `dwr_ar_bill_aging_f.query_date` = `'2026-06-08'` (YYYY-MM-DD 带连字符)
      - `dm_ar_receivable_accage_t.edition_date` = `'20260608'` (YYYYMMDD 不带连字符)
      - `dm_ar_analysis_rpt_f.calmonth` = `'2026-06'` (YYYY-MM 带连字符)
      - `dm_ar_return_payment_t.calmonth` = `'202606'` (YYYYMM 不带连字符)
      - `dm_ar_overdue_receivables_t.ed_mon` = `'202606'` (YYYYMM 不带连字符)
      - `dwr_ar_collection_detail_f` 用 `year='2026' AND month='2026-06'` 双字段
      ⚠️ 写错格式直接返回空结果
- [ ] 账龄版本：用的是旧版 `dwr_ar_receivable_aging_f` (31列) 还是新版 `_2023_info_f` (82列)？优先用新版
- [ ] 余额 vs 账龄：余额表 (`balance_f`) 只有余额没有账龄分段；账龄表 (`aging_*`) 有分段
- [ ] 特别总账：是否考虑了 `special_general_ledger` 过滤？默认为空 = 正常应收
- [ ] 大表（1亿行 account_detail_f / 3600万行 quota_daily_t）是否带了时间过滤？
- [ ] `_close` 后缀表是已清账版本，一般用未清账版本
- [ ] 备份表（`_wjh_`、`_bak`、`_tmp`、`_01` 后缀）绝对不能使用
- [ ] `_sp` 后缀字段（如 `natoverd_receivables_*_sp`）是审批/特殊口径，默认不用

### 第 5 步：对抗性审查（Adversarial Review）

**这是最关键的一步。此步骤的缺失会导致 ~6% 准确率损失。**

在输出结果之前，扮演"质疑者"角色，逐条挑战自己刚才生成的 SQL 和结论：

**A. 数据源选择是否正确？**
- [ ] 有没有其他表也能回答这个问题？如果有，两张表的结果应该一致吗？
- [ ] `dwr_ar_receivable_aging_f`（31列，旧版）vs `_2023_info_f`（82列，新版）？优先用新版
- [ ] 选用的表是主表还是备份表？（`_wjh_`、`_bak`、`_tmp` 后缀的绝对不能用）
- [ ] `_close` 后缀表是已清账版本，当前分析是否需要？

**B. 业务概念映射是否唯一？**
- [ ] "应收"在当前语境下到底指什么？（local_currency_balance_sum / overdue_receivables / n_overdue_receivables / receivable_balance_sum？）
- [ ] "逾期"的分段口径：应收账龄(ysyq) / 应收未清(yswyq) / 自然账龄(natural) / 应收逾清(ysyq_新)？
- [ ] "客户"用 `cust_code` 还是 `debitor`？不同表命名不同
- [ ] "销售组"是 `sales_grp` (SAP风格) 还是 `sales_group_master_file` (DWR风格)？
- [ ] 用户说的"账龄"是哪个日期基准？2023前体系 (bf_af_2020_zl_*) vs 2023后体系？

**C. 过滤条件是否完整？**
- [ ] 大表是否带时间范围条件？（account_detail_f 1亿行不带过滤直接超时）
- [ ] `special_general_ledger` 是否需要过滤？默认只查正常应收（IS NULL 或 = ''）
- [ ] query_date / edition_date 是否可能为空？空行需要排除吗？

**D. 结果合理性？**
- [ ] 执行前预估：这个查询大概会返回多少行？应收金额量级应该是多少？
- [ ] 如果结果是 0 行或异常大/小，最可能的原因是什么？日期格式错误？表名用错？
- [ ] 账龄分段金额之和是否接近 `local_currency_balance_sum`？（偏差应 < 5%）
- [ ] 是否存在某种合理的替代解释，会让同样的数字意味着完全不同的结论？

### 第 6 步：输出结果（面向业务的最终回答）

最终回答面向业务用户：呈现经营结果、关键数据、原因、风险与建议；技术执行过程不写入正文。以下规范各业务域统一，不得自行变体：

**默认不展示技术内容**——回答正文中不出现：

- SQL 语句与 SQL 代码块
- 数据库表名、字段名、Schema
- Skill 名称、MCP/工具名称
- DSH、Gateway、Guard 等内部技术术语
- SQL 生成、执行、调试与验证的过程性描述

**只是不展示，不是不做**：第 1-5 步照常完整执行——读语义层、生成并执行 SQL、对抗性审查一样不少；SQL 与执行记录由系统按原有审计机制完整留存（报告溯源与审计复查从执行轨迹取数），回答中无需展示，也不涉及清除。

**回答结构按问题复杂度动态组织**，不固定章节数量、不凑模板：

- 简单问题直接给结果：数字 + 一句话解读
- 复杂问题按需展开：核心结论 / 关键经营数据 / 同比、环比与预算对比 / 结构与趋势变化 / 原因分析 / 风险与建议
- 用业务语言保留必要信息：统计范围、数据日期（如"截至 2026 年 6 月末"）、口径与限制（如"不含税口径""仅统计瓷砖事业部""数据更新至 2026-08"）
- 不得为简洁牺牲分析深度：影响经营判断的口径限制、数据不完整、指标不可比必须如实披露；对抗性审查未通过时如实说明结果需复核；结论区分数据事实与推断
- 需要向用户澄清口径时同样用业务语言提问（如"按含税还是不含税口径？"），不引用表名字段名

**技术内容例外**：用户明确要求查看 SQL、查询语句、字段解释或排查 SQL 问题时，在现有权限范围内正常输出技术内容；例外仅对用户点名的当次回答生效，后续回答仍按默认规则。

## 常用分析模式

### 模式 A：应收账龄结构总览

```sql
SELECT query_date,
       SUM(local_currency_balance_sum) as total_balance,
       SUM(overdue_receivables) as overdue_total,
       SUM(n_overdue_receivables) as n_overdue_total,
       ROUND(SUM(overdue_receivables)
             / NULLIF(SUM(local_currency_balance_sum), 0) * 100, 2) as overdue_pct
FROM dwrfin.dwr_ar_receivable_aging_2023_info_f
WHERE query_date = '2026-06-08'
GROUP BY query_date;
```

### 模式 B：按客户应收 Top N

```sql
SELECT cust_code, cust_name,
       SUM(local_currency_balance_sum) as balance,
       SUM(overdue_receivables) as overdue,
       SUM(n_overdue_receivables) as n_overdue
FROM dwrfin.dwr_ar_receivable_aging_2023_info_f
WHERE query_date = '2026-06-08'
GROUP BY cust_code, cust_name
ORDER BY balance DESC
LIMIT 20;
```

### 模式 C：逾期账龄明细（按账龄分段）

```sql
SELECT cust_code, cust_name,
       overdue_receivables_1_90_day_2023_after as overdue_1_90,
       overdue_receivables_91_275_day_2023_after as overdue_91_275,
       overdue_receivables_276_730_day_2023_after as overdue_276_730,
       overdue_receivables_731_1460_day_2023_after as overdue_731_1460,
       overdue_receivables_1461_day_2023_after as overdue_1461_plus
FROM dwrfin.dwr_ar_receivable_aging_2023_info_f
WHERE query_date = '2026-06-08'
  AND overdue_receivables > 0
ORDER BY overdue_receivables DESC
LIMIT 100;
```

### 模式 D：回款监控（按客户）

```sql
SELECT cust_code, cust_name,
       SUM(all_collection_amt) as total_collection,
       SUM(collection_amt) as matched_collection,
       SUM(non_confirm_amt) as unconfirmed,
       ROUND(SUM(collection_amt) / NULLIF(SUM(all_collection_amt), 0) * 100, 2) as match_rate
FROM dwrfin.dwr_ar_collection_detail_f
WHERE year = '2026' AND month = '2026-06'
GROUP BY cust_code, cust_name
ORDER BY total_collection DESC
LIMIT 20;
```

### 模式 E：应收周转天数

⚠️ **此表数据仅到 2022-12，已停更 3 年+**。查询时间窗口必须 ≤ 2022-12。

```sql
SELECT calmonth, dept, zzts as turnover_days
FROM dwrfin.dwr_ar_receivable_turnover_days_f
WHERE calmonth >= '202201'
ORDER BY calmonth, dept;
```

### 模式 F：坏账减值按客户风险等级

```sql
SELECT cust_class_name, COUNT(DISTINCT cust_code) as cust_cnt,
       SUM(local_currency_balance_sum) as total_balance,
       SUM(overdue_receivables) as overdue_balance,
       SUM(overdue_1461_amt) as overdue_4yr_plus
FROM dwrfin.dwr_ar_credit_devalue_f
WHERE query_date = '2026-06-08'
GROUP BY cust_class_name
ORDER BY total_balance DESC;
```

### 模式 G：月度应收趋势（2023版）

```sql
SELECT query_date,
       SUM(local_currency_balance_sum) as balance,
       SUM(overdue_receivables_2023_after) as overdue_new,
       SUM(overdue_receivables_2023_ago) as overdue_old
FROM dwrfin.dwr_ar_receivable_aging_2023_info_f
WHERE query_date >= '2026-01-01'
GROUP BY query_date
ORDER BY query_date;
```

### 模式 H：综合分析报表（按 WBS 汇总）

```sql
SELECT calmonth, wbs_level1_desc,
       SUM(receivables_am) as receivables,
       SUM(all_collection_amt) as collection,
       SUM(n_overdue_receivables) as n_overdue,
       SUM(overdue_receivables) as overdue,
       ROUND(AVG(collection_rate), 2) as avg_collection_rate
FROM dm.dm_ar_analysis_rpt_f
WHERE calmonth = '2026-06'
GROUP BY calmonth, wbs_level1_desc
ORDER BY receivables DESC
LIMIT 20;
```

## 应收健康度检查项

| 指标 | 计算方式 | 说明 |
|---|---|---|
| 逾期应收占比 | `SUM(overdue_receivables) / SUM(local_currency_balance_sum) * 100` | >20% 需关注回款风险 |
| 超长账龄占比(>2年) | `SUM(overdue_receivables_731_1460_day + overdue_receivables_1461_day) / SUM(overdue_receivables) * 100` | >15% 需计提减值 |
| 回款匹配率 | `SUM(collection_amt) / SUM(all_collection_amt) * 100` | <90% 需关注未匹配回款 |
| 应收周转天数 | `zzts`（预计算） | >90天 需关注 |
| 坏账减值覆盖率 | `SUM(overdue_*_amt) / SUM(overdue_receivables)` | 按账龄分段计提比例 |

## Validation 验证层

每次生成 SQL 并执行后，必须做结果验证：

1. **行数检查**：返回行数是否在预期范围内？账龄明细表全量千万级，不带 filter 直接查会超时
2. **量级检查**：应收金额是否在合理量级？月度应收总额通常亿级
3. **空值检查**：query_date 可能为空的行需要排除；cust_code/cust_name 可能为空
4. **口径交叉验证**：同一应收指标从账龄表和余额表查询，偏差应在可合理解释范围内

## Unbook 机制

遇到以下情况时，必须对用户说明"我无法准确回答"，而非强行给出不可靠的结果：

- 问题涉及的表/字段在现有参考文档中没有记录
- 查询结果出现无法解释的异常值，且无法通过现有文档的"陷阱"解释
- 问题需要跨领域知识（如应收 + 费用联合分析），但相关 Skill 尚未建设
- 用户追问的应收口径细节超出了参考文档覆盖范围

升级话术模板：
> "这个问题超出了当前应收数据分析的覆盖范围。[具体原因]。建议先补充 [具体业务领域] 的知识覆盖后再查。是否需要我先帮你记录这个缺口？"

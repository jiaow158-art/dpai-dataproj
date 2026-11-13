---
name: sales-performance-profit-composition
description: 利润组成/利润构成/营业利润拆解/净利润构成/利润来源/利润贡献/事业部利润结构的多口径路由；覆盖上市财报、内部经营利润表、事业部/阿米巴三套口径的候选表、已核实字段、不可比项与待业务确认项。只提供路由与核验线索，不限定 Agent 的探索路径。
---

# 利润组成 — 多口径路由与核验

## 0. 定位与边界

本文件回答的是“利润由哪些部分构成、各口径之间为什么对不上”，不是一套固定 SQL、固定表或固定指标。

- 下面的候选表是**起点**，不是白名单；Agent 仍可探索费用、成本、营收、组织、库存、OIT 等其他合法数据。
- 不同口径的利润**不能在没有依据时互相替代**；不能为了让公式闭合而调整业务数据。
- 标注“待业务确认”的字段/公式/口径，不得当作已确认结论输出；应先向业务确认，或在答案中明确披露。
- 本文件不提供可复制执行的固定 SQL 模板；字段、过滤和计算关系需结合实际问题与数据验证。

> **口径版本说明（2026-11-13）**：`dm_operat_profit_statement_t` 的 `flag`/`data_source`/单位/公式/锚点已由 [operat-profit-statement.md](operat-profit-statement.md) 实证。本文件保留上市口径字段清单、事业部/阿米巴路由、跨口径可比性与未决业务问题；若本文件旧段落与该实证文档冲突，以 `operat-profit-statement.md` 为准。

## 1. 先确认三个维度

在选表之前，先确认：

| 维度 | 需要确认的内容 | 未确认时的处理 |
|---|---|---|
| 口径 | 上市财报 / 内部经营利润表 / 事业部·阿米巴；用户要的是毛利、营业利润、利润总额还是净利润 | 说明假设；若多口径都合法，并列展示或比较，不静默选一个 |
| 期间 | 起止年月；当期还是累计；是否同比/环比 | 先查数据可用区间；不要假设“前三个季度”一定是某一年 |
| 实体 | 集团合并 / 单体法人 / 事业部；是否含内部交易、少数股东、关联交易 | 先确认 comp_code/dept/组织范围；不得把多个法人简单相加当集团合并净利润 |

## 2. 三套口径与候选表

### A. 上市财务报表口径

**候选表**：`dm.dm_fi_ambv2_profit_sum_listed_t`

**粒度（已核实的技术元数据）**：`stat_month`（年月）× `sales_grp`（销售组）× `comp_code`（公司代码）。

**已核实字段（来自 2026-11-06 `describe_table` 的列注释，属于技术元数据，不代表业务口径已确认）**：

| 组 | 字段 | 注释 |
|---|---|---|
| 收入 | `main_bus_income_amt` | 主营业务收入 |
| 收入 | `incld_point_amt` | 使用积分 |
| 收入 | `cur_reimburse_amt` | 本期报销 |
| 收入 | `cur_point_out_policy_amt` | 本期积分（政策外） |
| 收入 | `other_bus_income_amt` | 其他业务收入 |
| 成本/税金 | `main_bus_cost_amt` | 主营业务成本 |
| 成本/税金 | `lgstcs_cost_amt` | 物流成本 |
| 成本/税金 | `other_bus_cost_amt` | 其他业务支出 |
| 成本/税金 | `addl_tax_amt` | 税金及附加 |
| 期间费用 | `noincld_sale_fee_amt` | 销售费用 |
| 期间费用 | `mng_fee_amt` | 管理费用 |
| 期间费用 | `dev_fee_amt` | 研发费用 |
| 期间费用 | `fin_fee_amt` | 财务费用 |
| 其他损益 | `oth_income_amt` | 其他收益 |
| 其他损益 | `inv_income_amt` | 投资收益（损失） |
| 其他损益 | `fr_val_chg_income_amt` | 公允价值变动收益 |
| 其他损益 | `cre_impair_gain_loss_amt` | 信用减值利得（损失） |
| 其他损益 | `asset_impair_gain_loss_amt` | 资产减值利得（损失） |
| 其他损益 | `asset_disp_income_loss_amt` | 资产处置收益（损失） |
| 其他损益 | `incld_oth_income_prft_amt` | 营业外收入 |
| 其他损益 | `incld_oth_expd_prft_amt` | 营业外支出 |
| 其他损益 | `sharing_fee_amt` | 分成费用 |
| 所得税 | `income_tax_exp_amt` | 所得税费用 |

**已核实**：表名、列名、列注释、`stat_month` 时间粒度；该表在 `ambv2-profit.md` 与 `metrics.md` 中被标注为“上市口径”汇总表。

**待业务确认**：
- 各科目到“营业利润/利润总额/净利润”的精确 ETL 公式与符号方向（尤其是投资收益、减值、营业外收支、分成费用）。
- `comp_code` 的合并范围、内部交易抵销规则；能否直接对全部 `comp_code` 求和。
- 是否提供“归属于上市公司股东的净利润”及少数股东损益；本表列清单中未看到该字段。
- 单位（元/万元/亿元）与快照时点。

**禁止**：把全部 `comp_code` 简单相加后称为“集团合并净利润”；把列名当公式；在未确认合并口径时给出确定结论。

### B. 内部经营利润口径

见 [operat-profit-statement.md](operat-profit-statement.md)。该文档已实证 `flag`/`data_source`/单位/公式/锚点，并已覆盖预算/预测、集团内/外、`dept_name` 缺口等口径；本文件不再保留旧的“待业务确认”表述，避免与新文档冲突。
### C. 事业部/阿米巴利润口径

**候选表**：
- `dm.dm_fi_ambv2_profit_sum_t`：事业部/月度利润汇总（`stat_month`、`dept_name`、`flag`，列数较多）。
- `dm.dm_sw_fi_ambv2_profit_sum_t`：卫浴事业部阿米巴利润。
- `dm.dm_ambv2_profit_t`：收入成本明细底表（约 4600~5100 万行，列存）。常规月度构成优先用汇总表；单据/凭证/SKU 级追溯才下钻底表。

**已有的已验证知识**：
- 毛利三口径（阿米巴/实际成本/标A）及完整公式：见 [ambv2-profit.md](ambv2-profit.md)「毛利三口径」。
- 毛利率分母统一为 `notax_sales_net_amt` 的 2026-11-02 业务裁定：见 [metrics.md](metrics.md)「四-B」。
- `data_source` 的 S/D/U/W 语义与集团利润表 `IN ('S','T')` 口径：见 [ambv2-profit.md](ambv2-profit.md) 与 [metrics.md](metrics.md) 陷阱 20。
- 下游汇总表路由（上市/卫浴/品类）：见 [ambv2-profit.md](ambv2-profit.md)「下游表路由」。

**待业务确认**：
- `dept_name`/`flag` 的取值语义；汇总表是否已消除内部交易重复计算。
- 阿米巴利润与上市口径利润的勾稽关系；能否直接比较。
- 当月月中快照、成本读上期周期价等时点问题。
- 集团合并口径与事业部加总口径的差异。

**禁止**：把多个事业部/法人简单相加当集团净利润；忽略 `data_source` 直接 SUM；为简单月度构成扫描 5000 万行底表。

### D. 费用/成本域

利润组成不只有收入、成本、毛利。期间费用、减值、投资收益、营业外收支、所得税都可能改变结论。

- 费用/成本口径、毛利表选择、预算/预测：见 [fin-cost-knowledge/metrics.md](../../fin-cost-knowledge/references/metrics.md)。
- 销售毛利与毛利率：见 [fin-cost-knowledge/gross-profit.md](../../fin-cost-knowledge/references/gross-profit.md)。
- 费用明细、成本中心、科目、报销：见 `fin-cost-knowledge` 对应 reference。

跨域查询是允许的；不要因为使用了本路由就停止对费用/成本/组织维度的必要核验。

## 3. 已核实与待确认的边界

**已核实（可直接作为技术事实使用）**：
- 上述三张表的表名、列名、列注释、时间字段（`stat_month` / `calmonth`）。
- `ambv2-profit.md` 中以 ETL 源码为证据的毛利三口径公式。
- `metrics.md` 四-B 的毛利率分母裁定。
- 大表必须带时间过滤、备份/临时表禁用等既有规则。

**待业务确认（不得当作定论）**：
- （已解决）经营利润表 `flag`/`data_source`/`operating_profit` 由 `operat-profit-statement.md` 实证，不再列为待确认。
- 上市表的合并范围、内部抵销、归母净利润/少数股东损益。
- 三套口径之间的勾稽关系与可否比较。
- 单位、快照时点、跨年口径变更。

**处理原则**：如果公式对不上，记录差异、说明未解决的口径问题；不要调整数据去“凑平”，也不要把差异藏在答案之外。

## 4. 时间、过滤与单位

- 上市表：`stat_month`（YYYY-MM）。
- 经营利润表/阿米巴汇总：`calmonth`（YYYY-MM）。
- 费用毛利表：`months`（YYYYMM，无横杠，见 fin-cost metrics）。
- 聚合前先枚举 `flag`、`data_source`、`dept_name`、`node_name9` 的实际取值；不要凭经验硬编码。
- 大表必须带时间范围；备份/临时表（`_bak/_tmp/_wjh/_01/_close/_2024*` 等）禁用。
- 当月可能是月中快照；跨年比较注意 ETL 口径变更。
- 单位可能是元/万元/亿元；输出前确认单位并在答案中标注。

## 5. 可比与不可比

| 比较 | 是否可直接比较 | 说明 |
|---|---|---|
| 上市口径 vs 内部经营口径 | 否 | 范围、抵销、科目定义可能不同；要比较就并列展示并解释差异 |
| 上市口径 vs 事业部/阿米巴 | 否 | 组织范围、内部结算价、分成口径不同 |
| 毛利 vs 营业利润 vs 利润总额 vs 净利润 | 否 | 不同利润层级，不能混用 |
| 多个法人相加 vs 集团合并 | 否 | 内部交易、抵销、少数股东权益需确认 |
| 不同 `data_source` 行 | 需确认 | 可能是不同视角/分成方，不一定是重复行 |
| 当期 vs 累计 | 需确认 | `flag` 语义未确认前不要混用 |

## 6. 常见陷阱

1. **投资收益/减值/营业外收支的符号**：不同表注释写作“收益/损失”，正负方向需按实际数据和公式核验。
2. **投资收益双计**：利润表公式中若已含投资收益，再单独加一次会出现差额；不要为闭合差额调整业务数据。
3. **使用积分/预提积分/本期报销**：收入类调整项，是否已含在主营业务收入中需确认。
4. **分成费用/对外分成毛利额**：与普通费用不同，可能影响营业利润与阿米巴利润的勾稽。
5. **合并抵销**：`comp_code` 全量求和可能包含内部交易；上市表与事业部表的合并范围可能不同。
6. **`data_source` 语义**：在阿米巴表中 S/D/U/W 含义不同；在 Mix 体系中又不同，不能跨表套用。
7. **`flag` 语义**：经营利润表已由 `operat-profit-statement.md` 实证 20 个 flag 值；当期/累计/预算/预测/同期不可混用。
8. **`list_tables` 的 500 行上限**：`truncated=true` 时表清单可能不完整；不要因为没看到某张表就断言不存在。用 schema 过滤、`describe_table` 或既有 metrics 路由继续确认。
9. **元数据工具失败**：`list_tables`/`describe_table` 返回 `status=error` 时，不得当成“空表/无字段”；应按错误信息决定重试或换发现路径。
10. **表大小是估算**：修复后 `list_tables.size` 来自 `pg_class.relpages`，是近似值；0 可能表示未分析/分区表，不代表表不存在或没有数据。

## 7. 推荐分析路径（非强制）

1. 确认口径、期间、实体；未确认时说明假设。
2. 先查数据可用区间与关键维度取值（`stat_month`/`calmonth`、`flag`、`data_source`、`comp_code`/`dept_name`）。
3. 从候选表选一个与口径最匹配的；`describe_table` 核对字段与注释。
4. 计算核心利润组成：收入、成本、税金、期间费用、其他损益、所得税；按用户问题决定层级（毛利/营业利润/利润总额/净利润）。
5. 必要时做跨源核验（例如上市表 vs 经营表 vs 阿米巴汇总）；只在能解释差异时比较，不做没有新证据的重复扫描。
6. 输出时区分：已核实事实 / 合理推断 / 未解决口径；给出期间、实体、单位、口径假设。
7. 如果核心结论已成立，剩余的同比、趋势、事业部拆分等属于可选扩展；是否继续由 Agent 根据问题价值和数据情况判断，不设固定次数/轮次上限。

**再次强调**：以上是推荐路径，不是固定模板。Agent 可以探索其他表、跨知识域查询、继续追查口径差异；只要不伪造数据、不绕过 Guard、不把未确认口径当结论。

## 8. 待业务确认清单

- [x] 经营利润表 `flag`/`data_source`/`operating_profit`：已由 `operat-profit-statement.md` 实证（2026-11-12）。
- [ ] 上市表各科目到营业利润/利润总额/净利润的 ETL 公式与符号。
- [ ] 上市表合并范围、内部交易抵销、归母净利润/少数股东损益。
- [ ] 三套口径的勾稽关系与允许的比较方式。
- [ ] 集团合并 vs 事业部加总 vs 单体法人的实体边界。
- [ ] 单位、快照时点、跨年口径变更。
- [ ] 投资收益/减值/营业外收支/分成费用的正负方向与是否重复计入。

## 9. 相关文档

- [ambv2-profit.md](ambv2-profit.md)：阿米巴收入成本底表、毛利三口径、data_source 陷阱、下游表路由。
- [metrics.md](metrics.md)：销售业绩语义层、毛利率四-B、pattern 路由表。
- [operations-mix-sum.md](operations-mix-sum.md)：Mix 主事实表与月度业绩口径。
- [fin-cost-knowledge/metrics.md](../../fin-cost-knowledge/references/metrics.md)：费用/成本/毛利口径与表选择。
- [fin-cost-knowledge/gross-profit.md](../../fin-cost-knowledge/references/gross-profit.md)：销售毛利、预算 vs 实际、毛利率。

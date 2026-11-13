# 利润表平铺底表 — dm_operat_profit_statement_t

## 表概览

| 属性 | 值 |
|------|-----|
| Schema | `dm` |
| 表名 | `dm_operat_profit_statement_t` |
| 行数 | ~81 万（35 个月）；元数据快照实测 71.79 万——差异为快照时点/月份覆盖不同 |
| 粒度 | 月 × flag（比较期/数据系列）× data_source × 销售组单元（node_name9）；**费用族与利润预测只到事业部层（ETL 用 `node_name2 as node_name9`）** |
| 时间字段 | `calmonth` (YYYY-MM) |
| 存储与分布 | **行存**，`DISTRIBUTE BY calmonth`（非分区表）——按月过滤天然只命中少数 DN，跨多月扫全表代价高 |
| 列数 | 41 列（4 个维度 + 36 个数值/衍生 + `last_update_date`），**无分区字段、无 dept_name** |
| 口径层级 | 止于**阿米巴利润总额（税前）**：ETL 从利润上报数据表取了 `income_tax_expense`（减：所得税费用）但**未落表** → 本表**无所得税、无净利润** |
| 用途 | **组织×月粒度的利润表下半段**：费用构成 → 营业利润 → 阿米巴利润总额，含利润的预算/预测对比系列。mix 表只到"毛利以上"，本表补齐"毛利以下" |
| 更新方式 | 月级 DELETE + INSERT（ETL 循环 `TO_CHAR(PERIOD_ID_D,'YYYY-MM')` 与 `-6 days` 两个月：`delete ... where calmonth = P_DATE` 后整月重插） |
| 上游血缘（ETL 实测 11 张） | 实际族：`dm.dm_fi_ambv2_profit_sum_t`（阿米巴利润汇总，7.67 万行，提供 8 个实际系列的损益）+ `dm.dm_ambv2_zzt_xssr_t`（阿米巴集团业绩表，815 万行，提供**含税销售收入**）；预算族：`upload.upload_achievement_budget_t`（业绩预算）+ `upload.upload_amb_cost_rules_t`（阿米巴成本规则）+ `upload.upload_expense_group_t`（费用组）+ `upload.upload_profit_submit_data_t`（利润上报）+ `upload.upload_cost_adjustment_1037`（成本调整外挂）；预测族：`upload.upload_achievement_prediction_t`（收入预测）+ `dm.dm_profit_forecast_fill_t`（利润预测填报，仅 101 行）；组织：`dm.dm_rpt_sales_group_t`；成本中心：`DWIMD.DWI_MD_COST_CENTER_INFO_T` |
| ETL 脚本 | `huaweiclaude/DM/DM_CT/PJob_DWS_DM_OPERAT_PROFIT_STATEMENT_T.txt`（营业利润/阿米巴利润总额公式在 ETL 内算好落表） |

## 与本域其他表的分工

| 问题 | 走哪张表 |
|------|---------|
| 业绩达成/收入/毛利（毛利以上） | `dm_fin_operations_mix_sum_t` |
| 单据/凭证/SKU 级收入成本毛利下钻 | `dm_ambv2_profit_t`（5000 万行明细） |
| 明细粒度毛利（客户×物料×渠道） | `dm_so_org_perf_stat_t` |
| **费用构成/营业利润/阿米巴利润总额/利润预算预测**（组织×月） | **本表** |
| 上市口径利润表 / 净利润与所得税 | `dm_fi_ambv2_profit_sum_listed_t`（**仅当用户明确点名"上市口径"**，默认不走；本表不含所得税） |
| 阿米巴利润汇总（本表实际族上游，集团口径 `data_source IN ('S','T')`） | `dm_fi_ambv2_profit_sum_t` |
| 阿米巴集团业绩表（本表含税收入上游，815 万行） | `dm_ambv2_zzt_xssr_t` |
| 业绩预算 / 业绩预测填报（本表预算、预测收入上游） | `upload.upload_achievement_budget_t` / `upload.upload_achievement_prediction_t` |
| 利润预测填报（本表预测费用/利润上游，仅 101 行） | `dm.dm_profit_forecast_fill_t` |
| 费用预测明细（利润预测段走另一条链路，不读本表） | `dm.dm_expense_prediction_fsreclass_t`（JOIN `DWIMD.DWI_MD_COST_CENTER_INFO_T`、`DM.DM_RPT_SALES_GROUP_T`）——问费用预测明细别在本表找 |

## 维度列

| 列 | 说明 |
|----|------|
| `calmonth` | 'YYYY-MM' |
| `flag` | 比较期/数据系列，实测 20 值，三族（见下） |
| `data_source` | S/T/D/U/W/NULL（见下）；**预算/预测族还存在空串 `''`** |
| `node_name9` | ⚠️ **销售组单元编码**（如 R40），不是名称。名称与上级组织需 JOIN `dm_rpt_sales_group_t`（`ON node_name9`）取 `node_desc9`（单元名）/ `node_desc2`（事业部名，如 '瓷砖事业部'）。事业部级聚合必须先 JOIN 再 `GROUP BY node_desc2` |

> 组织树 `dm_rpt_sales_group_t` 有 `node_name1~9` / `node_desc1~9` 九层，本表落的最细层是第 9 层；**层级不落底表，任何层级聚合都靠 JOIN 树表按 `node_descN` 分组实现**（事业部= `node_desc2`，销售组= `node_desc3` 起）。但**预算/预测族只有事业部层数据**（ETL `node_name2 as node_name9`），此时第 9 层编码实际是事业部码，下钻到销售组单元必然为空。

> ⚠️ **口径缺口：`dept_name` 不存在**。已知的集团视角取数会在组织上叠加 `dept_name='11000000'` 过滤，但本表 41 列实测无 `dept_name` 列，ETL insert 列表亦无 —— 按集团视角口径过滤本表会直接报错，需确认该过滤对应的真实字段（组织树字段或另一版表结构）。

### flag 三族（实测 20 值）

| 族 | 值 | 用途 |
|----|-----|------|
| 实际（8） | 当期 / 累计 / 去年同期 / 去年同期累计 / 去年上期累计 / 去年下期 / 去年下期累计 /（ETL 还有'上期累计'分支，实测未见数据） | 问当月/累计利润、同比 |
| 预算（9） | 当期预算 / 累计预算 / 上期累计预算 / 下期预算 / 下期累计预算 / 去年同期预算 / 去年同期累计预算 / 去年上期累计预算 / 去年下期预算 | 问利润预算达成 |
| 预测（4） | 当期预测 / 累计预测 / 下期预测 / 下期累计预测 | 问利润预测 |

⚠️ 预算族仅 ~757 单元、预测族仅 ~81 单元有数（实际族 ~1400）——问小单元的预算/预测可能无数据，需按 P0 陷阱先 COUNT 验证。

**各系列的取数窗口（ETL 实测，`P_DATE` = 当月，字符串拼接实现）**

| flag | 取数窗口 |
|---|---|
| 当期 | `stat_month = P_DATE` |
| 累计 | `stat_month between 'YYYY-01' and P_DATE`（年初至今） |
| 上期累计 | 非 1 月：`'YYYY-01' ~ 上月` |
| 去年同期 | `stat_month = left(P_DATE,4)-1 \|\| right(P_DATE,3)` |
| 去年同期累计 | 去年 01 ~ 去年同月 |
| 去年上期累计 | 非 1 月：去年 01 ~ 去年上月 |
| 去年下期 | 去年同月 + 1 月 |
| 去年下期累计 | 非 1 月：去年 01 ~ 去年下月 |
| 下期 / 下期累计（预算/预测） | `P_DATE + 1 月` / 年初 ~ 次月 |

> ⚠️ **1 月份不生成"上期/下期"系列**：ETL 用 `substr(P_DATE,6,2) != '01'` 卡掉，因此 1 月问"上期累计/去年上期累计/下期"会**天然 0 行**（不是数据缺失、也不是 SQL 写错）。

> 预测族由 ETL 独立分支拼入（先 `flag NOT IN ('当期预测','累计预测','下期预测','下期累计预测')` 出实际+预算，再 `UNION ALL` 拼预测）——**预测值与实际值来自两次不同聚合**，不要假设一次扫描就能拿到全 flag 族。

> 预算族的"加：使用积分"在**对外呈现口径**上做了**符号翻转**：`CASE WHEN flag LIKE '%预算%' THEN incld_point_amt * -1 ELSE incld_point_amt END` —— 底表不翻转，直接拿底表预算族 `incld_point_amt` 与实际族对比会符号相反；反之若要复现对外呈现数，需自行取反。

### data_source 语义（2026-11-12 业务拍板 + 实测）

| 值 | 含义 | 实测承载 |
|----|------|---------|
| `S` | 对外卖出方（集团外） | **收入族**：含税收入、不含税净额、积分、自身口径营业利润/阿米巴利润 |
| `T` | 调整值（含国补改判，负值常见；**鹏美上报数据也强制打 T**） | 收入族（调整） |
| `D` | 供货方分成 | 收入族 |
| `U` | 事业部内部交易 | 收入族 |
| `W` | 卫浴非全资成本调整值 | 仅卫浴，量极小 |
| `NULL` | **合并系列** | **费用族**：销售/管理/研发/财务费用、物流费用/成本、税金及附加、减值、营业外、资金成本，及整段的营业利润/阿米巴利润总额（此行收入列恒 0） |
| `''`（空串） | **预算/预测族的填报分支** | 仅预算/预测 flag 行，实际族不存在；`COALESCE(data_source,'NAL')` **兜不住空串** |

⚠️ **单行不是完整损益**：收入/毛利在 S/T/D/U 行，费用在 NULL 合并行。实测（瓷砖 2026-10 当期）：S 含税收入 39,298 万、NULL 行销售费用 2,411 万 / 营业利润 −5,593 万（仅费用段）。问完整利润表口径需跨系组合，组合规则**待业务确认**（见文末）。

⚠️ `data_source` 字母语义跨表不一致（metrics.md 陷阱 22）：`W` 在本表=卫浴**非**全资成本调整值，在 Mix 体系=卫浴费全资成本调整值；`D` 在 ambv2=产品方分成行、在 Mix=重算。禁止跨表套用。

> **集团内/外拆分的 ETL 硬规则**（`销售成本2`/`销售成本：集团内`/`销售成本：集团外`、`不含税销售净额（管理）集团内/外` 均按此切）：
> - **集团内** = `data_source IN ('D','U')`
> - **集团外** = `COALESCE(data_source,'#') IN ('S','T','#')` —— **NULL 合并行计入集团外侧**
> 即集团内/外不是按公司代码/客户组判断，而是按**交易角色**判断；把 NULL 行当"未分类"丢掉会导致集团外金额偏小。

> **已核实的业务呈现口径（最接近"官方组合规则"）**：
> ```sql
> -- 集团视角：另叠加 dept_name='11000000' 组织过滤（该列本表不存在，见维度列缺口）
> COALESCE(data_source,'NAL') IN ('NAL','S','T','D')
> -- 事业部层：同上
> COALESCE(data_source,'NAL') IN ('NAL','S','T','D')
> -- 事业部以下层：追加 U（内部交易）
> COALESCE(data_source,'NAL') IN ('NAL','S','T','D','U')
> ```
> 即对外口径 = **合并行（NULL，呈现时别名 `NAL`）+ S + T + D**，事业部以下层再 **+U（内部交易）**；**`W` 不进入对外口径**。这是"全系列求和"倾向的实证依据，但 `W` 的排除意味着与手工"NULL+S+T+D+U+W"求和会有卫浴口径差。
>
> ⚠️ 该过滤是**白名单**，而预算/预测族存在 `data_source=''` 的填报分支（空串不入任何 COALESCE 兜底）——按此口径取数时这些分行会被静默剔除。若业务口径的预算/预测是"填报数"，需单独放开空串，**待核实**。

## 指标列与单位

⚠️ **全表金额单位 = 万元**。ETL 已确证：落表前对 `"阿米巴利润总额"`、收入/成本/费用各段统一 `/10000`（上游 `dm_fi_ambv2_profit_sum_t`、`dm_ambv2_zzt_xssr_t` 均为元），故**万元是落表口径而非推断**；与 mix/ambv2 表（元）对比须 ×10000。

| 族 | 列 |
|----|-----|
| 收入（在 S/T/D/U 行，NULL 行恒 0） | `tax_revenue`（含税，集团内/外拆分 `tax_internal`/`tax_external`）、`sales_net_management`/`sales_ext_management`（不含税净额·管理口径）、`incld_point_amt`（加：使用积分）、`noincld_point_amt`（减：预提积分） |
| 成本费用（在 NULL 合并行） | `noincld_sale_fee_amt`（销售成本2，集团内/外拆分 `noincld_sale_fee_amt_in`/`_out`）、`addl_tax_amt`（税金及附加）、`red_noincld_sale_fee_amt`（销售费用）、`lgstcs_fee_amt`/`lgstcs_cost_amt`（物流费用/成本）、`mng_fee_amt`、`dev_fee_amt`、`fin_fee_amt` |
| 其他损益 | `oth_income_amt`、`inv_income_amt`、`credit_impairment`、`asset_impairment`、`asset_dspsl_income_amt`、`sale_income_amt`/`extr_sale_cost_amt`（其他业务收支）、`incld_oth_income_prft_amt`/`incld_oth_expd_prft_amt`（营业外收支） |
| **利润结果** | `operating_profit`（**营业利润**）、`total_amiya_profit`（**阿米巴利润总额**）、`total_financing_cost`（资金成本合计）、`total_outside_sharing_margin`（对外分成毛利额合计） |
| 比较期汇总（ETL 预计算列） | `last_period_amiya_profit` / `period_amiya_profit` / `next_period_amiya_profit` / `last_year_same_period_amiya_profit` / `last_year_last_period_amiya_profit` / `last_year_next_period_amiya_profit` 共 6 列（文档早期写"7 列"，实测 DDL 为 6 列）——由 ETL 从"累计"系生成（同样 `/10000` 后落表），实测与该节点"累计"行的 `total_amiya_profit` 数值相等（万元）。**查询主指标直接用对应 flag 行，不要用这组汇总列** |
| 审计列 | `last_update_date`（timestamp，ETL 写 `current_timestamp`）—— 可用于判断某月是否已按最新脚本重跑 |

> **列名自带方向**：`加：使用积分`、`减：预提积分`、`减：销售费用`、`减：营业外支出`、`投资收益(损失负)`、`信用减值利得(损失)` —— 名称里的"加/减"和"损失负"已经是符号约定，**按列名直接 SUM 即可，不要再对"减"类列取反**；取反只发生在对外呈现口径的预算族 `incld_point_amt`（特例）。

> **本表没有的财务口径**：`减：所得税费用`（ETL 从 `upload_profit_submit_data_t` 取到但未落表）、`净利润`、`毛利率` 等"率"类指标——率指标需自行用金额列现算，且分母口径见 metrics.md。

## 口径公式（ETL tmp4~tmp6 原文，公式改动须与 ETL 同步）

```sql
-- 资金成本合计：平台/丽适节点强制为 0（node_name2 IN ('H11250401','H11000009') 或前缀 R91）
资金成本合计 = CASE WHEN 平台/丽适节点 THEN 0
  ELSE 应收账款利息(阿米巴)+库存利息+资金成本1~5+供应商付现利息 END

-- 营业利润（tmp5）
营业利润 = 整体毛利 - 税金及附加合计 - 销售费用 - 物流费用 - 物流成本 - 管理费用 - 研发费用
           - 财务费用 - 分摊费用(事业部内部) - 资产减值损失合计 - 信用减值损失合计
           + 公允价值变动 + 其他收益 + 投资收益 + 资产处置损益 + 其他业务收入 - 其他业务支出

-- 阿米巴利润总额（tmp6）
阿米巴利润总额 = 营业利润 + 营业外收入 - 营业外支出 - 资金成本合计 - 对外分成毛利额合计

-- 不含税销售净额(管理)-ST（tmp7，"不含税净额合计"列口径）
不含税销售净额(管理)-ST = CASE WHEN COALESCE(data_source,'NAL') IN ('NAL','S','T')
    THEN 不含税销售额合计 + 使用积分 - 预提积分-手工 - 预提积分-系统 ELSE 0 END
-- 注意：该口径只含 NAL/S/T，不含 D/U —— 与对外呈现口径（含 D、下层含 U）不是同一集合

-- 含税销售收入（xssr CTE，源 dm_ambv2_zzt_xssr_t 业绩表，非利润汇总表）
含税销售收入 = SUM(sales_performance + performance_1n + cross_performance + internal_performance)/10000
  过滤：calmonth = P_DATE
        AND coalesce(cust_group,'#') <> 'Z0'          -- 剔除内部客户组
        AND coalesce(node_name2,'nvl') <> 'R91000002'  -- 剔除过渡部门
  集团内 = data_source IN ('D','U')；集团外 = data_source IN ('S','T')
```

## 锚点值（2026-11-12 直连实测，calmonth=2026-10，flag=当期，瓷砖事业部=JOIN 树 node_desc2 聚合）

| data_source | 行数 | 含税收入(万) | 不含税净额(万) | 销售费用(万) | 营业利润(万) | 阿米巴利润总额(万) |
|---|---|---|---|---|---|---|
| S | 541 | 39,298 | 34,473 | 0 | 8,060 | 8,028 |
| T | 334 | −394 | 146 | 0 | −846 | −846 |
| D | 18 | 1,681 | 780 | 0 | 227 | 93 |
| U | 41 | 868 | 594 | 0 | 138 | 130 |
| NULL 合并 | 868 | 0 | 0 | 2,411 | −5,593 | −5,871 |
| **全系列求和** | — | **41,453** | **35,993** | **2,411** | **1,986** | **1,534** |

全系列求和（不过滤 data_source）的营业利润 1,986 万 / 收入 41,453 万 ≈ 4.8%，量级合理——与"上市口径利润表脚本不过滤 data_source"（ambv2-profit.md）的写法一致；**对外呈现口径为 NAL+S+T+D(+U)，不含 W**（见 data_source 节），与上表"全系列求和"仅在卫浴 W 行上有差。

## 已知陷阱

1. **备份变体表 6 张勿用**：`_20260429_qyj` / `_20260505_qyj` / `_wjh_20251010` / `_wjh_20260304` / `_wjh_260115` / `_wjh_260402`
2. **node_name9 是编码不是名称**：问"瓷砖事业部利润"必须 JOIN `dm_rpt_sales_group_t` 按 `node_desc2` 聚合；直接对 node_name9 等值过滤业务名称必然 0 行（伪 1 行 NULL 陷阱）
3. **单位万元**：与 mix/ambv2 表（元）不同，跨表对比/换算必须 ×10000（ETL `/10000` 已确证）
4. **收入族与费用族分家**：NULL 合并行收入恒 0，S 行费用恒 0——单行不是完整损益
5. **比较期汇总列勿当主指标**：`period_amiya_profit` 等仅是"累计"系的复制品；问当月/累计用对应 flag 行的 `total_amiya_profit`
6. **预算/预测族覆盖窄**：预算 ~757 单元 / 预测 ~81 单元（实际 ~1400），小单元大概率无预算数据
7. **同月数据日更**：当月数据每日重跑（delete+insert），日间问数数值可能变化；问完整月用已关账月份
8. **R91000002（过渡部门）ETL 已剔除**，树 JOIN 不必再排
9. **不含税净额"ST 口径"≠对外口径**：ETL 的 `不含税销售净额(管理)-ST` 只含 NAL/S/T，对外口径却含 D（下层含 U）——直接对 `sales_net_management`/`sales_ext_management` 求和即可，不要套 ST 派生列
10. **预算族积分符号**：底表不翻转，对外呈现对 `%预算%` 取 `incld_point_amt * -1`——复现对外数需自行取反，反之亦然
11. **1 月没有"上期/下期"系列**：ETL `substr(P_DATE,6,2) != '01'` 直接跳过分母分支，1 月问上期累计/下期必为 0 行
12. **预算/预测族混了粒度与来源**：收入侧来自业绩预算/业绩预测填报（按 `node_name9` + `data_source`），费用/利润侧来自利润上报数据表/利润预测填报（`node_name2 as node_name9`、`data_source=''`）——**同一 flag 行内的不同指标可能来自不同表、不同粒度**，下钻到单元层会大面积为空
13. **含税收入与毛利不同源**：`tax_revenue` 来自业绩表 `dm_ambv2_zzt_xssr_t`（已剔 `cust_group='Z0'`），不含税净额/成本/毛利来自利润汇总 `dm_fi_ambv2_profit_sum_t` —— 两者对账时"含税收入 ×（1−税率）≠ 不含税净额"属正常，不要互推
14. **鹏美数据以 `'T'` 并入**：`upload_profit_submit_data_t` 的鹏美上报数据被 ETL 强制 `data_source='T'`（调整值），问"调整值为何这么大"要想到这一支
15. **所得税/净利润不在表内**：ETL 取过 `income_tax_expense` 但未落列，问净利润必须换表
16. **`data_source=''` 与 NULL 不同**：预算/预测族用空串，`COALESCE(col,'NAL')` 兜不住，会静默丢行
17. **`dept_name` 口径缺口**：集团视角口径依赖 `dept_name='11000000'`，该列在本表不存在——按此过滤必报错，需改用组织树字段或确认表结构版本

## 待确认（不阻塞使用）

- 完整利润表口径的系列组合规则：已核实的对外口径为 `NAL`+S+T+D（下层 +U，不含 W），剩余待确认点是 **NULL 合并行的营业利润/阿米巴利润总额与 S 系营业利润是否可跨行相加**（锚点值表两种数字都已给出），eval 录制时以业务口径核对回填
- 白名单口径是否会剔除 `data_source=''` 的预算/预测填报分行（若剔除，业务口径的预算/预测 ≠ 填报口径）
- `tax_revenue` 列在预算/预测族有值、实际族 S 系有值——含税口径与 mix 表 `ambperformance` 的对账关系
- 集团视角 `dept_name='11000000'` 对应的真实字段（组织树哪一列）与是否仍在线

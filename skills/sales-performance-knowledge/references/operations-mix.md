---
name: sales-performance-operations-mix
description: DM_FIN_OPERATIONS_MIX_T 毛利以上合并底表参考 — 业绩表与收入成本表的 UNION 合并层，独有 infoprov 来源标识。需要按来源切分指标、或使用 comp_code/batch/bus_area/trading_mode 等 Mix 汇总表没有的细维度时使用。
---

# DM_FIN_OPERATIONS_MIX_T — 毛利以上合并底表（中间层）

## 定位

| 属性 | 值 |
|------|-----|
| 全名 | `dm.dm_fin_operations_mix_t` |
| 业务名 | **毛利以上合并底表** |
| 粒度 | 日 × 公司 × 销售组织 × 客户 × WBS × 销售组 × 物料 × 渠道 × 批次 × 业务范围 × 交易模式 |
| 列数 / 行数 | 约 105 列 / **2741.94 万行**（27,419,439，glossary 估算值） |
| 存储 / 分布列 | 列存；分布列 `material, calmonth` |
| 时间字段 | `calmonth` (YYYY-MM)、`calday` (YYYYMMDD)；另有 `s_calmonth`/`s_calday` 原日历 |
| ETL | `etl/DWR/FIN/GL/PJob_DWS_DM_FIN_OPERATIONS_MIX_T.txt`（39KB，DWS 侧活跃，2024-10 建，2025-02-21 改增量） |
| ⚠️ 单据号 | **没有 `doc_number` / `bill_num` / `ac_doc_nr`** —— 单据级追溯请回源表 |

---

## 三表血缘（本表在中间）

```
【源1】dm_ambv2_zzt_xssr_t   阿米巴业绩表  815万行   订单行×凭证行
        → 只提供 业绩 / 面积 / 数量（无成本）
【源2】dm_ambv2_profit_t     收入成本表    4600~5100万行  订单行×凭证行
        → 只提供 收入 / 成本 / 毛利（无业绩额）
【源3】DM_ZZT_XSSR_QT_T      其他业务收支  —
              │
              │  UNION ALL，用 infoprov 字段标记来源
              ▼
【本表】dm_fin_operations_mix_t   毛利以上合并底表  2741万行  ← 你在这里
              │  LEFT JOIN 8 张维度表 + GROUP BY
              ▼
【下游】dm_fin_operations_mix_sum_t  毛利以上表  903万行（主事实表，见 operations-mix-sum.md）
```

**源码证据**（`PJob_DWS_DM_FIN_OPERATIONS_MIX_T.txt`）：
- L131 + L156：`'dm_ambv2_profit_t' as infoprov ... from dm.dm_ambv2_profit_t`
- L266 + L288：`'dm_ambv2_zzt_xssr_t' as infoprov ... from DM.dm_ambv2_zzt_xssr_t`
- L401 + L423：`'dm_zzt_xssr_qt_t' as infoprov ... from DM.DM_ZZT_XSSR_QT_T`
- 汇总方向：`PJob_DWS_DM_FIN_OPERATIONS_MIX_SUM_T.txt` L146 `from dm.dm_fin_operations_mix_t t1`

> `data-lineage.md` 曾记录 mix_t 有 5 张来源表；当前归档脚本中可见 **3 个 UNION 来源块**（profit / zzt_xssr / zzt_xssr_qt）。另两张（`DM_ZZT_XSSR_T`、`DM_RPT_GROUP_ACHIEVEMENT_AMB_T`）在当前脚本版本中未见。以脚本为准。

---

## 什么时候用本表（相对 `mix_sum_t`）

| 场景 | 用谁 |
|---|---|
| 常规月度达成、渠道/品牌/客户/区域下钻、预算 vs 实际 | **`mix_sum_t`**（默认主表） |
| **需要按来源切分**（这指标来自业绩表还是收入成本表） | **本表**（独有 `infoprov`） |
| **需要 `comp_code` / `salesorg` / `batch` / `stor_loc` / `val_type` / `bus_area` / `trading_mode` / `kalsm`** | **本表**（mix_sum 的 GROUP BY 里没有这些） |
| **需要 `act_cost_profit_amt`**（实际成本毛利额） | **本表**（mix_sum 未继承该字段） |
| 需要 `node_desc1~9` 组织 9 级 | `mix_sum_t`（内置，本表要自己 JOIN） |
| 需要预算 `_ys` / 预测 `_yc` 字段 | `mix_sum_t`（本表无） |
| 单据/发票/凭证号追溯 | **都不是**，回 `ambv2_profit_t` / `zzt_xssr_t` |

---

## 独有核心字段：`infoprov` / `src_infoprov`

| 字段 | 含义 |
|---|---|
| `infoprov` | **信息提供者** —— 本行数据来自哪张源表 |
| `src_infoprov` | 信息提供者（源表）—— 源表自带的原始 `infoprov` |

取值（ETL 硬编码）：`'dm_ambv2_profit_t'` / `'dm_ambv2_zzt_xssr_t'` / `'dm_zzt_xssr_qt_t'`

### ⚠️ 三个指标只认收入成本表

下游 `mix_sum_t` ETL L129-131 对这三个指标做了来源限定：

```sql
sum(case when t1.infoprov='dm_ambv2_profit_t' then t1.zfdje end)                  as zfdje  -- 返点
sum(case when t1.infoprov='dm_ambv2_profit_t' then t1.zsyjf end)                  as zsyjf  -- 使用积分
sum(case when t1.infoprov='dm_ambv2_profit_t' then t1.zytjf_sg+t1.zytjf_xt end)   as zytjf  -- 预提积分
```

→ **返点 / 使用积分 / 预提积分只从收入成本表取**。在本表直接 `SUM(zfdje)` 而不加 `infoprov` 过滤，结果会比 mix_sum **偏大**。

---

## 指标字段

### 业绩 / 量
`ambperformance`(业绩)、`z_yjsgtzz`(业绩手工调整值)、`s_zxsmj`(业绩面积)、`s_zxssl`(业绩数量)、`zxsmj`(销售面积)、`zxssl`(销售数量)、`deal_price_total`(成交价总价)

### 收入 / 成本
`notax_sales_net_amt`(不含税销售净额-管理)、`act_cost_sum_amt`(实际成本合计-管理)、`actual_cost_exclude_logistics`(实际成本合计-剔除物流)、`standard_price_a`(标准成本A)、`zzyywsr_zyck`(主营业务收入-自营出口)、`zzyywcb_azf`(安装费)、`zyywcb_yf`(运费)、`zyywcb_zxf`(装卸费)

### 毛利（本表口径比 mix_sum 多）
`amb_profit_amt`(阿米巴毛利额)、`a_overall_profit_amt`(标A整体毛利)、**`act_cost_profit_amt`(实际成本毛利额)**、`gross_profit_after_sharing`(分成后整体毛利额)、`overall_profit_after_sharing`(总体利润分配后)

### 分成 / 结算价
`ext_profit_1n_amt`(1+N对外分成毛利额)、`ext_cross_profit_amt`(跨事业部对外分成毛利额)、`ext_dept_inner_profit_amt`(事业部内部对外分成毛利额)、`amb_internal_price`(阿米巴结算总价-销售单元)、`amb_internal_avg_price`(阿米巴结算单价-销售单元)、`amb_internal_avg_fac_price`(结算单价-生产基地)、`last_period_avg_price`(上期周期单价)、`last_period_sum_price`(上期周期总价)、`zzqj`(周期价)、`zzqjgl`(周期价-内审)

### 积分 / 返点 / 调整值
`zfdje`(返点)、`zsyjf`(使用积分)、`zytjf_sg`(预提积分-手工)、`zytjf_xt`(预提积分-系统)、`zsrtzz`(收入调整值)、`zcbtzz`(成本调整值)、`other_income_total_mgmt`(其他业务收入合计)、`other_expenses_total_mgmt`(其他业务支出合计)

---

## 维度字段

**组织/客户**：`comp_code`、`salesorg`(+`___t`)、`customer`、`wbs_elemt`、`zsalesgrp`(销售组-实际)、`sales_grp`(销售组 WBS+客户主档)、`zsales_grp`(销售组-销售方)、`cust_group`、`zzkunnr`(母客编)、`salesemply`(+`___t`)、`emp_num`/`emp_name`、`data_prmssn`(事业部权限)

**物料**：`material`、`sku_short_code`(简码SKU)、`batch`、`stor_loc`(+`___t`)、`plant`(+`___t`)、`val_type`(评估类型)、`zchanq`(产区)、`zchanq__t`、`zchanqbd`(产区变动)、`aeskd`(BOM母件号)、`bom_flag`(浴室柜齐套)、`product_brand_code`/`product_brand_name`(产品系列)、`factory_type`(自制外协)、`supplier_or_creditor_num`

**交易/渠道**：`distr_chan`、`integrate_channel`+`_desc`、`integrate_channel2`+`_desc`、`zsales_channel`(渠道-销售方)、`kalsm`(客户定价过程)、`bus_area`(+`___t`)、`trading_mode`+`_desc`、`zsfqc`(是否清仓)、`clearance_reason`(+`_t`)、`bstnk_vf`(销售政策)、`z_gcbbh`(工程报备号)、`zsjbm`(商机编码)、`zso_group_code`(订单组)、`export_country`、`masterseries_prod`(主推)、`mastersale_prod`(主销)

**来源标识**：`infoprov`、`src_infoprov`、`data_source`+`data_source_desc`、`trading_mode`+`trading_mode_desc`

---

## 已知陷阱

1. **⚠️ 未内置排除 `comp_code='8000'` 和 `cust_group='Z0'`** —— 这两条是下游 `mix_sum_t` ETL L173 做的（`coalesce(comp_code,'#')<>'8000' and coalesce(cust_group,'#')<>'Z0'`）。本表**没有**这层过滤，直接查本表与 mix_sum 对不上账时必须自己补上。
2. **⚠️ `infoprov` 没有传到下游** —— `mix_sum_t` 的 SELECT 列表里没有 `infoprov`，所以汇总层无法再按来源切分。
3. **没有单据号** —— `doc_number` / `bill_num` / `ac_doc_nr` 在 GROUP BY 中被丢弃，单据追溯必须回源表。
4. **没有 `node_desc1~9`** —— 组织 9 级要自己 `LEFT JOIN dm.dm_rpt_sales_group_t`。关联键受 `data_source` 影响（见下方）。
5. **组织归属受 data_source 影响**（`mix_sum` ETL L169，本表同逻辑）：`data_source IN ('S','T')` 时取 `coalesce(WBS销售组, 客户销售区域组, sales_grp)`，否则直接取 `sales_grp`。→ 同一行换组织口径可能落到不同组织。
6. **`data_source` 语义跨源表不一致** —— 本表 UNION 了三张源表，`data_source` 继承了各自的含义。`S/D/T/U/W` 在 `ambv2_profit_t` 与 Mix 体系下的含义**不同**（尤其 `D`：收入成本表是"产品方分成行"，Mix 体系是"重算"）。详见 [metrics.md](metrics.md) 跨表对照。
7. **备份表黑名单** —— 已见 `dm_fin_operations_mix_t_20250314_wjh`，禁用；只用 `dm.dm_fin_operations_mix_t`。
8. **增量刷新** —— ETL 为 `DELETE 按 calmonth 范围 + INSERT`（2025-02-21 由全量改为增量），重跑需指定月份区间。
9. **`zxsmj`/`zxssl` 与 `s_zxsmj`/`s_zxssl` 不是一回事** —— 前者销售面积/数量，后者业绩面积/数量。

---

## 查询模式

```sql
-- 模式1：按来源切分业绩与收入成本（本表独有能力）
SELECT infoprov,
       COUNT(*)                              AS 行数,
       SUM(ambperformance)::numeric(18,2)     AS 业绩,
       SUM(notax_sales_net_amt)::numeric(18,2) AS 不含税净额,
       SUM(amb_profit_amt)::numeric(18,2)     AS 阿米巴毛利
FROM dm.dm_fin_operations_mix_t
WHERE calmonth = '2026-10'
  AND coalesce(comp_code,'#') <> '8000'      -- 补 mix_sum 的内置过滤
  AND coalesce(cust_group,'#') <> 'Z0'
GROUP BY infoprov
ORDER BY 行数 DESC;

-- 模式2：返点/积分 —— 必须限定 infoprov，否则比 mix_sum 偏大
SELECT SUM(zfdje)::numeric(18,2)                    AS 返点,
       SUM(zsyjf)::numeric(18,2)                    AS 使用积分,
       SUM(zytjf_sg + zytjf_xt)::numeric(18,2)      AS 预提积分
FROM dm.dm_fin_operations_mix_t
WHERE calmonth = '2026-10'
  AND infoprov = 'dm_ambv2_profit_t'                -- 与 mix_sum 口径一致
  AND coalesce(comp_code,'#') <> '8000'
  AND coalesce(cust_group,'#') <> 'Z0';

-- 模式3：用 mix_sum 没有的细维度下钻（业务范围 / 交易模式 / 批次）
SELECT bus_area, trading_mode,
       SUM(ambperformance)::numeric(18,2) AS 业绩,
       SUM(amb_profit_amt)::numeric(18,2) AS 阿米巴毛利
FROM dm.dm_fin_operations_mix_t
WHERE calmonth = '2026-10'
  AND coalesce(comp_code,'#') <> '8000'
  AND coalesce(cust_group,'#') <> 'Z0'
GROUP BY bus_area, trading_mode
ORDER BY 业绩 DESC;

-- 模式4：与 mix_sum 对账（验证两边是否一致）
-- 若本表结果偏大，先检查是否漏了 comp_code/cust_group 过滤
SELECT SUM(ambperformance)::numeric(18,2) AS 业绩
FROM dm.dm_fin_operations_mix_t
WHERE calmonth = '2026-10'
  AND coalesce(comp_code,'#') <> '8000'
  AND coalesce(cust_group,'#') <> 'Z0';
-- 对照：SELECT SUM(ambperformance) FROM dm.dm_fin_operations_mix_sum_t WHERE calmonth='2026-10';
```

---

## 与其他表的关系

- **上游**：[ambv2-profit.md](ambv2-profit.md)（`dm_ambv2_profit_t`）、`dm_ambv2_zzt_xssr_t`（阿米巴业绩表）、`DM_ZZT_XSSR_QT_T`
- **下游**：[operations-mix-sum.md](operations-mix-sum.md)（`dm_fin_operations_mix_sum_t`，主事实表）
- **血缘**：[data-lineage.md](data-lineage.md)

## 待确认

- ❓ `DM_ZZT_XSSR_QT_T`（其他业务收支）在本表贡献哪些指标、占比多少，脚本未标注业务含义
- ❓ 历史文档记 mix_t 有 5 张来源表，当前脚本仅见 3 个 UNION 块 —— 是否为历史版本差异，待业务确认
- ❓ 本表是否应对齐 `mix_sum_t` 的 `comp_code`/`cust_group` 排除（当前未排除，属"未显式过滤"还是"有意保留"，待确认）

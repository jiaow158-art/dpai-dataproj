# 库存账龄明细（库龄明细主表）

## 快速参考

| 属性 | 值 |
|---|---|
| DWS 表名 | `dm.dm_fin_stock_detail_accage_t_2023` |
| 行数 | **2.28 亿**（2026-11-03 连库实测 `count(*)` = 228,112,817） |
| 列数 | 183（实测 `information_schema.columns`） |
| 时间范围 | 202012 ~ **202611**（72 个月，持续刷新） |
| 粒度 | 一行 = 一个物料 × 工厂 × 库存地点 × 批次 × 会计期间的月度库存快照 |
| 时间字段 | `calmonth` = YYYYMM（NOT NULL） |
| ETL | Hive 作业 `DM/PJob_DM_FIN_STOCK_DETAIL_ACCAGE_T_2023.txt`（dp_mrs_hive_prod）活跃；DWS 原生作业已标**废弃**，两者字段逻辑一致 |

**业务含义**：按物料+工厂+批次+库存地点+会计期间记录库存余额与金额，内嵌**四套账龄口径**、**两族减值/跌价**、**四套度量**。库存分析最核心的单表，也是跌价/资金成本族的唯一事实源。

---

## 一、指标口径卡（先看这节）

### 1.1 库存金额：二选一，默认管理

| 口径 | 字段 | 202607 全集团 | 何时用 |
|---|---|---|---|
| **管理（默认）** | `zsjkcje`（实际库存金额） | 14.71 亿 | 财务账面、报表、资金占用；**用户未指定时用这个** |
| 阿米巴结算价 | `stock_amt` | 17.52 亿 | 与业绩域阿米巴考核对齐时；需用户点名 |

⚠️ **不得相加、不得混用**。回答时须声明用的是哪个口径。

### 1.2 账龄口径：四套

| 口径 | 金额 | 数量 | 面积 | 体积 | 用途 |
|---|---|---|---|---|---|
| **标准（默认）** | `wbzq_*_amt` / `ybzq_*_amt` | `_qty` | `_area` | `_volume` | 常规库龄分析 |
| 自然账龄 | `zrzlcp_*_amt` | `_qty` | `_area` | — | 按批次入库日，不受保质期逻辑影响 |
| 阿米巴结算价 | `wbzq_*_aging` / `ybzq_*_aging` | — | — | — | 阿米巴考核口径 |
| 瓷砖销售单元阿米巴 | — | `amb_wbzq_*_qty` | `amb_wbzq_*_area` | — | 销售单元考核 |

### 1.3 减值/跌价：两族 × 两口径

| 族 | 管理口径 | 阿米巴口径 | 说明 |
|---|---|---|---|
| **减值（jc）** | `wbzq_jc_amt` / `ybzq_jc_amt` / `jchj_amt` | `wbzq_jc_aging` / `ybzq_jc_aging` / `jchj_aging` | 按比例估算，有保质期工厂白名单 |
| **跌价（fall）** | `wbzq_*_fall_amt` / `ybzq_*_fall_amt` | `*_fall_aging` | 预计算好，可直接 SUM |

⚠️ `jchj_amt`（2.877 亿）与 `jchj_aging`（3.301 亿）是**两套体系**，与上市口径表 `aging_*_fall_amt` 又不同（上市表非默认，仅特殊要求且须声明）。

### 1.4 度量：四套

```
金额（*_amt） 数量（*_qty） 面积（*_area） 体积（*_volume）
总括：zsjkcje / stock_amt、quantity、ZKCMJ、BUSI_VOLUME（+ VOLUME_UNIT_NAME）
```

---

## 二、字段语义纠错表（2026-08-19 ETL 实证）

| 字段 | ❌ 旧误读 | ✅ 实际语义 |
|---|---|---|
| `bz_flag` | 包装标志 | **保质期产品标识**（Y=有保质期，N=无保质期） |
| `wbzq_*` | 未包装周期 | **无保质期**产品库龄段 |
| `ybzq_*` | 已包装周期 | **有保质期**产品库龄段 |
| `*_jc_amt` / `jchj_amt` | "检出"金额 | **减值**估算（管理口径） |
| `*_aging` | 老化 | **阿米巴结算价**口径 |
| `zdpsyb` | 盘点损益 | **事业部**（码=组织架构 node2 去 H 前缀） |
| `zdpzgsdq` | 在制品核算地区 | **子公司大区** |
| `zyl01` | 预留相关 | **产品渠道** |
| `zww010` | 物料评估 | **产区** |
| `zisqc` | 是否切裁 | **是否清仓**（Y/N） |
| `ziswx` | 是否维修 | **是否外协**（自制/外协） |
| `zrzlcp_*` | — | **自然账龄**产品（DDL 无注释，以报表中文名为准） |
| `z_vfdat` | — | **货架寿命到期日**（表内落地字段；ETL 中的 `shelf_end_date` 为其上游来源） |

---

## 三、库龄分桶规则（ETL 实证）

### 3.1 无保质期产品（`bz_flag='N'`）——四段

按 `batch_rk_date`（批次入库日期，阿米巴调整后）距快照日 `zdate` 分桶：

| 段 | 金额 | 数量 | 面积 | 体积 | 跌价比例 |
|---|---|---|---|---|---|
| 6 月内 | `wbzq_6_amt` | `_qty` | `_area` | `_volume` | 0% |
| 6-12 月 | `wbzq_6_12_amt` | `_qty` | `_area` | `_volume` | 10% |
| 1-2 年 | `wbzq_12_24_amt` | `_qty` | `_area` | `_volume` | 40% |
| 2 年以上 | `wbzq_24_amt` | `_qty` | `_area` | `_volume` | 70% |

### 3.2 有保质期产品（`bz_flag='Y'`）——**四桶**（不是两桶）

按 `z_vfdat`（货架寿命到期日）分桶：

| 桶 | 金额 | 数量 | 面积 | 体积 | 跌价比例 |
|---|---|---|---|---|---|
| 已到期 | `ybzq_bzdq_amt` | `_qty` | `_area` | `_volume` | 100% |
| 距到期 ≤3 月 | `ybzq_bzdq_3_amt` | `_qty` | `_area` | `_volume` | 70% |
| **距到期 >3 月** | `ybzq_bzdq_d3_amt` | `_qty` | `_area` | `_volume` | **无跌价**（正常库存） |
| 结算价版本 | `ybzq_bzdq_aging` / `_3_aging` / `_d3_aging` | — | — | — | — |

⚠️ `_d3_` 桶（>3 个月）是最容易被漏掉的一档。只取「到期 + 3月内」算"临期库存"是对的，但算"有保质期库存总量"必须把 `d3` 加进来。

#### 实测警示：有保质期金额几乎为零（2026-11-03）

| 月份 | 行数 | `zsjkcje` 合计 | 已到期 | 3月内 | >3月 |
|---|---|---|---|---|---|
| 202606 | 35,728 | **1,041.80 元** | 168.53 | 830.52 | 42.75 |
| 202607 | 35,734 | **873.27 元** | 0.00 | 830.52 | 42.75 |
| 202608 | 35,734 | **873.27 元** | 830.52 | 0.00 | 42.75 |

**全集团有保质期产品库存金额不到 1000 元**（对比同月 `zsjkcje` 总额 14.71 亿）。3.5 万行里约 2.9 万行金额非零，但**绝大多数是同一批次的一正一负对冲行**（样本可见 +10/−10、+50/−50）。

→ **不要用有保质期桶做金额类分析**（"临期库存金额""保质期库存占比"），结果必然接近 0 且无业务意义。该口径只在**数量/面积**维度有微量数据。
→ 桶间移动是正常的：202607→202608，830.52 元从"3月内"整体迁到"已到期"。

### 3.3 特例

- **plant 前缀 7C** 的行用 `zpcrk_fc` 代替批次日期分桶（其余工厂用 `zmmm_o017_zbatch_date`）
- **自然账龄族** `zrzlcp_6/6_12/12_24/24_*`：按批次日期四段，独立于保质期体系
- **瓷砖销售单元阿米巴** `amb_wbzq_*`：仅无保质期四段，只有数量与面积，无金额

---

## 四、减值公式（管理口径，ETL 实证）

```text
wbzq_jc_amt（无保质期减值）= wbzq_6_amt×0 + wbzq_6_12_amt×0.1
                          + wbzq_12_24_amt×0.4 + wbzq_24_amt×0.7
ybzq_jc_amt（有保质期减值）= 仅特定工厂，其余恒 0：
  plant 7C   ：202203 前 = bzdq_3×0.6 + bzdq×1.0；202203 起 = ×0.7 / ×1.0
  plant 73   ：bzdq_3×0.7 + bzdq×1.0
  plant 7220 且 stor_loc IN ('TY','FC','QA','TA')：×0.7 / ×1.0
jchj_amt   = ybzq_jc_amt + wbzq_jc_amt（减值合计·管理口径）
jchj_aging = ybzq_jc_aging + wbzq_jc_aging（减值合计·阿米巴结算价）
```

> `jc` 族与 `fall` 族是同一套比例的两组字段（0/10/40/70% + 70/100%），2026-08-19 复算 0% 偏差，可直接互换验证。

---

## 五、核心字段

### 5.1 金额/数量/面积/体积

| 字段 | 含义 |
|---|---|
| `quantity` | 库存数量 |
| `zsjkcje` | **实际库存金额（管理口径，默认）** |
| `stock_amt` | 库存金额（阿米巴结算价） |
| `ZKCMJ` | 库存面积（总括） |
| `BUSI_VOLUME` / `VOLUME_UNIT_NAME` | 体积 / 体积单位 |

### 5.2 账龄族

| 族 | 字段 |
|---|---|
| 标准·无保质期 | `wbzq_6` / `wbzq_6_12` / `wbzq_12_24` / `wbzq_24` ×（`_amt`/`_qty`/`_area`/`_volume`） |
| 标准·有保质期 | `ybzq_bzdq` / `ybzq_bzdq_3` / `ybzq_bzdq_d3` ×（`_amt`/`_qty`/`_area`/`_volume`） |
| 自然账龄 | `zrzlcp_6` / `_6_12` / `_12_24` / `_24` ×（`_amt`/`_qty`/`_area`） |
| 阿米巴结算价 | `wbzq_*_aging`、`ybzq_bzdq_aging` / `_3_aging` / `_d3_aging` |
| 销售单元阿米巴 | `amb_wbzq_6` / `_6_12` / `_12_24` / `_24` ×（`_qty`/`_area`） |

### 5.3 减值/跌价

| 字段 | 含义 |
|---|---|
| `jchj_amt` / `jchj_aging` | 减值合计（管理 / 阿米巴），可直接 SUM |
| `wbzq_jc_amt` / `ybzq_jc_amt` | 无保质期 / 有保质期减值（管理） |
| `wbzq_jc_aging` / `ybzq_jc_aging` | 同上（阿米巴） |
| `wbzq_6_fall_amt` ~ `wbzq_24_fall_amt` | 无保质期各段跌价（0/10/40/70%） |
| `ybzq_bzdq_3_fall_amt` / `ybzq_bzdq_fall_amt` | 有保质期跌价（70% / 100%） |
| `*_fall_aging` | 同上结构，阿米巴结算价口径 |

### 5.4 维度字段

**基本信息**：`calmonth` / `calmonth2` / `calyear`、`material`(+`___t`)、`plant`(+`___t`)、`stor_loc`(+`___t`)、`batch`、`comp_code`(+`___t`)、`unit`(+`___t`)、`vendor`(+`___t`)、`doc_currcy`(+`___t`)、`industry`(+`___t`)

**库存属性**：`stockcat`(+`___t`)、`stocktype`(+`___t`)、`val_class`(+`___t`)、`val_type`、`matl_type`(+`___t`)、`zmatltype`(+`___t`)、`extmatlgrp`(+`___t`)、`matl_group`(+`___t`)

**产品层级**：`matl_grp_1~5`(+`___t`)、`zprodh1~5`(+`___t`)、`zyl01`（产品渠道）、`zyl06`（产品等级）、`zww010`（产区）、`prod_property` / `prod_property_name`（产品所有权）

**业务分类（高频，易漏）**：

| 字段 | 中文名 |
|---|---|
| `base` | 基地 |
| `product_base` | 生产基地 |
| `storage_classify` | 库位分类 |
| `classify_name` | 分类 |
| `category_name` | 品类 |
| `foreign_own` | 外协自产 |

**组织**：`zdpsyb`（事业部）+ `zdpsyb___t`、`zdpzgsdq`（子公司大区）+ `zdpzgsdq___t`、`wbs_elemt`(+`___t`)、`wbs_elm_ex`

**时间/标识**：`zmmm_o017_zbatch_date`（入库日期）、`batch_rk_date`（批次入库日期·阿米巴调整）、`z_vfdat`（货架寿命到期日）、`next_mon_date`、`time_diff`、`clear_inv_flag`、`CLEARANCE_REASON_CODE`/`CLEARANCE_REASON`、`PROMOTE_REASON_CODE`/`PROMOTE_REASON`、`dw_last_update_date`

---

## 六、粒度与时间语义

| 项 | 说明 |
|---|---|
| 快照语义 | 每行是**月末快照**，不是流水；同一物料+工厂+库位+批次每月一行 |
| `zdate` 基准 | 当月 → 取**昨天**；历史月 → 取该月**最后一天**（账龄计算基准，ETL 内生成，非表字段） |
| 当月完整性 | 当月数据随时刷新，**月中查询当月为不完整快照**；跨月对比需注明 |
| 跨月对比 | 对比月份须同为月末快照；`calmonth` 为字符串，比较用 `>=`/`<=` 而非日期函数 |

---

## 七、组织维度写法（无需 JOIN）

`zdpsyb` / `zdpzgsdq` **自带 `___t` 中文描述**，直接分组即可出名称：

```sql
SELECT zdpsyb, zdpsyb___t,
       SUM(zsjkcje) AS stock_amt
FROM dm.dm_fin_stock_detail_accage_t_2023
WHERE calmonth = '202608'
GROUP BY zdpsyb, zdpsyb___t;
```

- `zdpsyb` 编码 = 组织架构 `node2` **去掉 H 前缀**
- 要按 1~9 级组织层级汇总时，本表**没有** `node_desc1~9`，需 JOIN `dm.dm_rpt_sales_group_t` 或用编码前缀映射
- `zdpzgsdq`（子公司大区）粒度比 `zdpsyb` 粗，两者不是上下级关系，别混用

---

## 八、下游怎么用这张表

### 8.1 报表（2 张）

| 报表 | 用法 |
|---|---|
| `FI2012023库存明细账龄表.cptx`（集团/财经/库存） | 主查询走 `_2023` 表；⚠️ **参数下拉取自旧表** `dm_fin_stock_detail_accage_t` 的 `stockcat___t`，两表值域不一致时会选出空结果 |
| `SA228瓷砖产品报表-库存.cpt`（瓷砖事业部/研销） | 本表 + 业绩表 `dm_ambv2_zzt_xssr_t` + 发货表 + 出入库，综合口径 |

### 8.2 ETL（4 张）

| 下游表 | 取数条件 |
|---|---|
| `dm_fin_stock_capital_cost_t`（资金成本） | 取 `zsjkcje`，**排除 `stockcat='K'`** |
| `dm_ambv2_chdj_grp_t`（CHDJ） | `jc` 族减值，按 `zdpsyb` 范围过滤 |
| `dm_otd_wm_stock_turnover_m`（周转率） | `zdpsyb IN ('11000001','11000003')` 且 `matl_type='FERT'`，取 `zsjkcje` |
| `dm_fin_stock_d_accage_list_c_t_2023`（上市口径） | 非默认，仅特殊要求且须声明 |

---

## 九、跨域口径对照（重要）

同一张表，两个域默认口径**相反**：

| 域 | 默认库存金额 | 默认减值 |
|---|---|---|
| **inventory-knowledge（本域）** | `zsjkcje`（管理） | `jchj_amt` |
| sku-profitability | `stock_amt`（阿米巴） | `jchj_aging` |

→ 跨域问答时若数字对不上，**先查是不是这个差异**，不要当成数据错误。

---

## 十、陷阱

1. **表名带 `_2023` 但覆盖 202012 起全量**（最新 202611），**本表即业务默认的"全集团库存"口径（产成品）**——问到"库存/总库存/集团库存"直接用它，**不要与 `_others_t` 相加**（2026-11-03 业务确认）。非产成品在同目录 `_others_t`，仅当明确问"原材料/半成品/包装/非产成品"时才查，见 [stock-accage-others.md](stock-accage-others.md)。`dm_fin_stock_detail_accage_t`（91 列旧表）不要用
2. **`___t` 后缀** = 三下划线+t 文本描述（`plant` → `plant___t`）
3. **四套账龄口径并存**（标准 / 自然账龄 / 阿米巴结算价 / 销售单元阿米巴），用户未指定时默认标准 `wbzq_*_amt`
4. **`wbzq`/`ybzq` 是保质期维度不是包装维度**；`ybzq` 字段只在 `bz_flag='Y'` 行有值（2026-08 实证排他性）
5. **有保质期是四桶不是两桶**：`bzdq`（到期）/ `bzdq_3`（3 月内）/ **`bzdq_d3`（>3 月，最易漏）**
6. **`jc` 减值有保质期工厂白名单**（7C/73/7220），其余工厂 `ybzq_jc_amt` 恒 0——按事业部汇总减值时勿以为漏算
7. **plant 7C 分桶日期字段不同**（`zpcrk_fc`），跨工厂库龄对比存在口径微差
8. **`jchj_amt` ≠ `jchj_aging`**（2.877 亿 vs 3.301 亿）；`stock_amt` ≠ `zsjkcje`（17.52 亿 vs 14.71 亿），两两禁止混用
9. 大表必带 `calmonth` 过滤；`calmonth` NOT NULL
10. **`zprodh` 与 `matl_grp` 两套产品层级并存**，过滤产品优先 `matl_grp_*`
11. **`_d3_` 桶无跌价字段**：`ybzq_bzdq_d3` 只有金额/数量/面积/体积/aging，没有 `fall`——不是缺失，是未到期不提取
12. **`zrzlcp_*` 的 DDL 注释为空**，中文名（自然账龄产品金额/数量/面积）来自报表定义，不要按字段名猜
13. **库存金额默认 `zsjkcje`**；跨域到 sku-profitability 时要说明口径切换（见第九节）
14. **当月快照不完整**：月中查询当月，账龄与金额均可能偏低，需提示
15. **有保质期产品金额≈0**（202607 全集团 873 元，占总额 0.00006%）：3.5 万行中大量正负对冲行。做"临期库存金额/保质期库存占比"必然得到近零结果，**应改用数量/面积，或说明该口径在瓷砖业务下几乎无金额**

---

## 十一、常见查询模式

### 当前库存账龄汇总（按工厂）

```sql
SELECT plant, plant___t,
       SUM(quantity) AS total_qty,
       SUM(zsjkcje)  AS total_amount,
       SUM(wbzq_6_amt) AS aged_0_6m,
       SUM(wbzq_6_12_amt) AS aged_6_12m,
       SUM(wbzq_12_24_amt) AS aged_12_24m,
       SUM(wbzq_24_amt) AS aged_24m_plus,
       SUM(COALESCE(jchj_amt,0)) AS mgmt_impairment
FROM dm.dm_fin_stock_detail_accage_t_2023
WHERE calmonth = '202606'
GROUP BY plant, plant___t
ORDER BY total_amount DESC;
```

### 有保质期临期结构（四桶完整）

```sql
SELECT plant___t,
       SUM(COALESCE(ybzq_bzdq_amt,0))   AS expired,
       SUM(COALESCE(ybzq_bzdq_3_amt,0)) AS within_3m,
       SUM(COALESCE(ybzq_bzdq_d3_amt,0)) AS over_3m
FROM dm.dm_fin_stock_detail_accage_t_2023
WHERE calmonth = '202608' AND bz_flag = 'Y'
GROUP BY plant___t;
```

### 管理口径减值 TOP（按事业部）

```sql
SELECT zdpsyb, zdpsyb___t,
       ROUND(SUM(COALESCE(jchj_amt,0))) AS impairment_mgmt,
       ROUND(SUM(COALESCE(jchj_aging,0))) AS impairment_amb
FROM dm.dm_fin_stock_detail_accage_t_2023
WHERE calmonth = '202608'
GROUP BY zdpsyb, zdpsyb___t
ORDER BY impairment_mgmt DESC;
```

### 单物料库龄下钻

```sql
SELECT calmonth, plant___t, stor_loc___t, batch,
       quantity, zsjkcje,
       wbzq_6_amt, wbzq_6_12_amt, wbzq_12_24_amt, wbzq_24_amt
FROM dm.dm_fin_stock_detail_accage_t_2023
WHERE material = '物料号' AND calmonth >= '202601'
ORDER BY calmonth;
```

---

## 十二、血缘与下游

- 上游：SAP 库存账龄明细 → Hive ETL（`PJob_DM_FIN_STOCK_DETAIL_ACCAGE_T_2023`）→ 同步 DWS
- 下游：
  - → `dm_fin_stock_capital_cost_t`（资金成本，取 `zsjkcje`，排 `stockcat='K'`）
  - → `dm_ambv2_chdj_grp_t`（CHDJ：`jc` 族减值 → `inventory_value` / `inventory_value_amb`）
  - → `dm_otd_wm_stock_turnover_m`（周转率库存金额）
  - → `dm_fin_stock_d_accage_list_c_t_2023`（上市口径，非默认）
- 报表：`FI2012023库存明细账龄表`、`SA228瓷砖产品报表-库存`

---

## 十三、交叉引用

- 语义层 → [metrics.md](metrics.md)
- 内部口径跌价 → [stock-fall-list.md](stock-fall-list.md)
- CHDJ → [chdj-capital-cost.md](chdj-capital-cost.md)
- 资金成本 → [capital-cost-table.md](capital-cost-table.md)
- 库存统计月报 → [stock-stat-month.md](stock-stat-month.md)
- 完整 ETL 血缘 → [data-lineage.md](data-lineage.md)

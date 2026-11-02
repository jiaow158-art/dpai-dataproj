---
name: sales-performance-ambv2-profit
description: DM_AMBV2_PROFIT_T 阿米巴收入成本底表参考 — 明细粒度收入/成本/毛利三口径、分成、内部结算价。单据级追溯与 SKU 毛利下钻时使用。
---

# DM_AMBV2_PROFIT_T — 阿米巴收入成本底表（明细级）

## 定位

| 属性 | 值 |
|------|-----|
| 全名 | `dm.dm_ambv2_profit_t` |
| 粒度 | 订单行 × 开票行 × 财务凭证行（明细底表） |
| 列数 / 行数 | 331 列 / **4600~5100 万行** ⚠️ 两来源不一致：glossary 元数据估算 46,083,155；2026-11-02 直连实测口径 ~5100 万。引用行数时注明来源与日期 |
| 存储 | **列存** |
| 分布列 | `calday, doc_number, bill_num, bill_item`（列存分布键 → 按这 4 键 JOIN/追溯性能最佳） |
| 分区 | Hive 侧 `period_id_m`（`insert overwrite partition(period_id_m)`）；DWS 侧**无分区**（2026-11-02 实测 `pg_partition`=0，仅列存+分布键，时间过滤靠分布外扫描，务必带 calmonth） |
| 时间范围 | 2022-01 ~ 当月（月中即有快照，非完整月） |
| 时间字段 | `calmonth` (YYYY-MM) ⚠️ 唯一可靠的时间过滤字段 |
| ETL | Hive 侧生产（`PJob_DM_AMBV2_PROFIT_T`，DWR/FIN/COST，2023-12~2025-10 持续维护，62 条变更记录）→ 同步至 DWS |
| 官方口径文档 | 腾讯文档（ETL 脚本头 L5）：https://doc.weixin.qq.com/sheet/e3_ACcAAQacAAwgj6tdxhkTAmNVcXQk1?scode=AIEA0AcYABAkjifz7WAVQAMgY4AOw&tab=1l6zq6 |

**与 Mix 表的关系**：`dm_fin_operations_mix_sum_t` 的 `notax_sales_net_amt` / `act_cost_sum_amt` / `standard_price_a` / `amb_profit_amt` / 装卸费 / 运费 / 成本调整 / 安装费均源自本表（同名同源）。本表是这些指标的**明细真相表**。

**何时用本表**（否则一律 Mix，见 metrics.md「七」路由）：
- 单据/凭证/批次级追溯（订单号、发票号、财务凭证号）
- SKU/物料级收入成本毛利下钻
- 毛利三口径、1+N/跨事业部分成、阿米巴内部结算价、周期价
- Mix 表数字核对/口径解释

**⚠️ 何时不该用本表**（改走下游汇总表，见「下游表路由」）：
- 问"上市口径利润表" → `dm_fi_ambv2_profit_sum_listed_t`
- 问"卫浴/瓷砖事业部阿米巴利润表" → `dm_sw_fi_ambv2_profit_sum_t` / `dm_fi_ambv2_profit_sum_t`
- 只是要月度收入成本毛利序列 → 回 Mix 表，别扫 5000 万行

---

## 核心字段（按指标族）

### 收入

| 字段 | 含义 |
|------|------|
| `notax_sales_net_amt` | 不含税销售净额(管理) — **默认收入字段**，与 Mix 同源 |
| `ext_sales_income` | 对外销售收入 |
| `zhsje` / `zbhsje` / `zhwjz` | 含税金额 / 不含税金额 / 货物净值(不含税) |
| `zhsxse` | 含税销售额（业绩(不含调整值) + 使用积分） |
| `zyywsr_zyck` `zzyywsr_gn` `zyywsr_wm` `zyywsr_gsj` `zyywsr_jtj` `zzyywsr_qt` | 主营业务收入分量：自营出口/国内/国内(外贸)/公司间/集团间/其它 |
| `zyywsr_zyck_pzhb` | 主营业务收入-自营出口（凭证货币） |
| `zfdje` | 返点金额 |
| `ztpzk` | 特批折扣 |
| `zsyjf` `zytjf_sg` `zytjf_xt` | 使用积分 / 预提积分(手工/系统) |
| `zsrtzz` | 收入调整值 |

> ⚠️ **前缀陷阱**：收入分量里 `zyywsr_*` 与 `zzyywsr_*` 混用（自营出口是 `zyywsr_zyck`，国内是 `zzyywsr_gn`），是源系统历史遗留，不是笔误。写错不会报错，只会静默返回 NULL 列——**务必照抄本表**。

### 成本

| 字段 | 含义 |
|------|------|
| `act_cost_sum_amt` | 实际成本合计（Mix 的 A 成本同源） |
| `zyywcb` | 实际成本 |
| `ext_act_sales_cost` | 实际成本（对外销售） |
| `zzyywcb_zz` | 主营业务成本 |
| `zyywcb_gsj` `zyywcb_jtj` `zyywcb_dsf` `zyywcb_yf` `zyywcb_zxf` | 成本分量：公司间/集团间/第三方/运费/装卸费 |
| `zzyywcb_azf` `zzyywcb_qt` | 安装费 / 其它（注意这两个是 `zz` 前缀） |
| `ztms_yf` `zsgrz_yf` | TMS运费(计费) / 运费(SAP手工) |
| `ztms_zxf` `zsgrz_zxf` | TMS装卸费(计费) / 装卸费(SAP手工) |
| `zzyywcb_clcbcy` `zzyywcb_cbcbcy` `zzyywcb_cpjjss` | 材料成本差异 / 产品成本差异 / 产品降级损失 |
| `standard_price_a` | 标准成本A（标A成本） |
| `zckcb` | 参考成本 |
| `zpr00` | PR00 价格 |
| `zcbtzz` | 成本调整值 |
| `prod_cost_adjust` | 产品成本-非全资调整 |
| `zxscb_amb` | a事业部成本 |
| `amb_bath_cost_amt` | 阿米巴成本-卫浴事业部-销售单元 ⚠️ **无历史数据**（ETL 注释：改此字段须同步利润表） |

### 毛利三口径（⚠️ 差异巨大，必须先确认用户要哪个）

**毛利率分母规则（2026-11-02 业务口径裁定）**：三口径毛利率分母一律 `notax_sales_net_amt`（不含税销售净额）；本表 `zhsje`（含税金额）/`zhsxse`（含税销售额）及 Mix 表 `ambperformance`（含税达成额）**禁做分母**。

公式均为 ETL 源码确证（`PJob_DM_AMBV2_PROFIT_T.txt` L4084-4111）：

| 字段 | 口径 | 公式 | 2026-10 瓷砖 S 行实测 |
|------|------|------|----------------------|
| `amb_profit_amt` | 阿米巴毛利（内部结算、分成后） | 见下方完整 CASE | 4231 万 |
| `act_cost_profit_amt` | 实际成本毛利 | `notax_sales_net_amt − act_cost_sum_amt` | 8060 万 |
| `a_overall_profit_amt` | 标A整体毛利 | `notax_sales_net_amt − standard_price_a`（主分支 L4110；特殊 UNION 分支 L4457 另按 `material_qty × 标A单价/1.13` 计算，对不上主公式时先查是否命中该分支） | 1411 万 |

**`amb_profit_amt` 完整公式**（L4088-4090）：

```sql
CASE WHEN trading_mode = 'A' OR trading_mode IS NULL
     THEN notax_sales_net_amt - amb_internal_price
          - (CASE WHEN bus_area IN ('E000','F000','J000','H000','I000','G001') THEN zcbtzz ELSE 0 END)
     ELSE (notax_sales_net_amt - cost_1n - cross_cost
          - (CASE WHEN bus_area IN ('E000','F000','J000','H000','I000','G001') THEN zcbtzz ELSE 0 END))
          * (rate_1n + cross_rate)
END
```

> 源码注释还描述了按 `prod_property`（产品所有权 C0001~C0006/A0002）分叉的第三条规则，但 **2025-04-29 变更已取消产品所有权判断**，现行 SQL 只剩上面两个分支。历史月份（≤2025-04）与当前月份口径不同，跨年对比需声明。

**关于 `a_overall_profit_amt` 的"不含物流成本"**：该字段公式本身只是 `notax − standard_price_a`；"不含物流"来自 `standard_price_a` 自身的口径——ETL 2024-06-07 变更「标A整体毛利取消运费装卸费」。即：物流费的剔除发生在 `standard_price_a` 上游，不是本字段额外减了一次。

### 分成与内部结算（1+N / 跨事业部）

| 字段 | 含义 |
|------|------|
| `income_1n` `cost_1n` `rate_1n` `profit_1n` | 1+N 收入/成本/比例/利润 |
| `cross_income` `cross_cost` `cross_rate` `cross_profit` | 跨事业部 收入/成本/比例/利润 |
| `dept_inner_income` `dept_inner_cost` `dept_inner_rate` `dept_inner_profit` | 事业部内部 收入/成本/比例/利润 |
| `profit_1n_amt` `cross_profit_amt` `dept_inner_profit_amt` | **1+N/跨事业部/事业部内部「毛利额」** ⚠️ 与上面 `profit_*`（利润）**不是同一组字段**，不要混用 |
| `ext_profit_1n_amt` `ext_cross_profit_amt` `ext_dept_inner_profit_amt` | 对外分成毛利额（1+N / 跨事业部 / 事业部内部） |
| `ext_sales_rate` `ext_sales_profit` | 对外销售比例 / 对外销售收入利润 |
| `amb_internal_price` / `amb_internal_tax_price` | 阿米巴结算总价-销售单元（不含税/含税） |
| `amb_internal_avg_price` / `amb_internal_avg_fac_price` | 阿米巴结算单价-销售单元 / 生产基地 |
| `zzqj` / `zzqjgl` | 周期价 / 周期价(管理) |
| `last_period_avg_price` / `last_period_sum_price` | 上期周期单价 / 总价 |

> `dept_inner_profit` / `dept_inner_profit_amt` 只在 `data_source='U'` 时赋值（L3623、L3672）；`cross_profit_amt` 只在 `trading_mode='C'` 时赋值（L3671）。非对应模式下这些列恒为 0，不是缺数。

### 量

| 字段 | 含义 |
|------|------|
| `zxsmj` / `zxssl` | 销售面积 / 销售数量（与 Mix 同源） |
| `zxsmj_unit` / `zxssl_unit` | 面积/数量的单位 |

---

## 维度字段

**⚠️ 本表没有 `node_desc1~9`**（与 Mix/业绩表组织体系完全不同），组织过滤用：

| 字段 | 含义 | 主要值 |
|------|------|--------|
| `sales_division_1n_code` + `sales_division_1n` | 销售事业部(1+N)，等值过滤 | 11000001 瓷砖 / 11000002 卫浴 / 11240102 国际营销中心 / 11250401 丽适岩板 / 91000002 过渡部门 / 91000003 公司层面 / 11000009 集团品牌中心 / **91230602 上市主体内的关联交易（notax=0）** |
| `product_division_1n_code` + `product_division_1n` | 产品事业部(1+N) | |
| `zcpsyb` `zxssyb` `zscsyb` `zfhsyb` `zbsyb`（+`___t`） | 产品/销售/生产/发货/b 事业部 | |
| `one_level_dept_*` `two_level_dept_*` | 一/二级部门 | |
| `wbs_1~3_level_dept_*` | WBS 侧一~三级部门 | |
| `salesorg` `sales_off` `sales_grp` `zsalesgrp`(实际) `zsales_grp`(销售方) | 销售组织/办公室/销售组 | |

其他常用维度：`customer`(+`___t`)、`zzkunnr` 母客编、`lifnr_num/name/lifnr_org_code` 经销商、`material`(+`___t`)、`size_dim` 规格、`zpl`/`category_name` 品类、`prod_line_name` 产品线、`product_brand_code/name` 物料系列、`integrate_channel`/`integrate_channel2`（与 Mix 同源）、`distr_chan`、`wbs_elemt`、`batch` 批次、`ihrez` 合同号、`doc_type`、`clearance_flag`/`zsfqc` 清仓、`zchanq` 产区、`zferth` 产品上市时间、`zsrkm`/`zcbkm` 收入/成本科目、`factory_type` 自制外协、`matl_type` 产品类型、`emp_num`/`emp_name` 销售雇员、`zso_group_code` 订单组编码、色系/纹路/面相/材质等 20+ 产品属性。

单据键：`doc_number`+`s_ord_item`（订单）、`bill_num`+`bill_item`（开票）、`ac_doc_nr`+`ac_doc_ln`（财务凭证）、`refer_doc`+`refer_itm`（参考凭证）。

### 两个易漏但关键的过滤维度

| 字段 | 含义 | ETL 中的硬编码用法 |
|------|------|-------------------|
| `bus_area` | 业务范围 | ①`IN ('E000','F000','J000','H000','I000','G001')` → `zcbtzz` 才计入阿米巴毛利；②共享仓/周期价标准口径要求 `NOT IN ('G000','G001')`；③2025-09-04 新增 `'K000'` 常规积分业务调整 |
| `prod_property` | 产品所有权 | 2025-04-29 前参与阿米巴毛利分支判断，之后取消；共享仓单价计算仍要求非空 |

---

## data_source 语义（ETL 源码确证，非推断）

| 值 | 含义 | 赋值点 | 金额特征 |
|----|------|--------|---------|
| `S` | 主数据流 | L400、L1803 | 绝大多数行，金额齐全 — **聚合默认用它** |
| `D` | trading_mode B/C 的产品方分成行 | L807、L2128 | 与 S 行成对出现，**直接 SUM 会双计**（2026 C 模式 S/D 不含税额完全相同） |
| `T` | SAP 调整值 + 补数行 | L3010（取调整值表 `SJLY`，为空则 `'T'`） | notax=0，仅含调整值/毛利 |
| `U` | 事业部内部交易（trading_mode='U'） | L1174、L2720 | |
| `W` | 共享仓调整业绩 | L2415 | 金额 0 |

`trading_mode`：A 主流自营 / B、C 跨事业部交易（**S+D 成对**）/ U 内部交易。

> ⚠️ **国补改判陷阱**：L4064 会把 `data_source='S'` 且 `infoprov IN ('国补调整值-分摊','国补调整值-冲销')` 的行**改判为 `'T'`**。即部分原始 S 行最终落库为 T。若严格按 `data_source='S'` 聚合，国补调整值会被漏掉——需要国补口径时用 `IN ('S','T')` 并核对。

### ⚠️ 不要无脑 `data_source='S'`（下游汇总脚本实证）

**"聚合一律 `data_source='S'`"是过度简化**。D/U/W/T 行不是重复数据，而是**不同视角/不同性质**的记录，按指标族取值完全不同。三个生产汇总脚本的实际写法：

| 指标 / 场景 | 实际取的 data_source | 出处 |
|---|---|---|
| 收入总额、成本、物流成本 | `S` | `PJob_DM_FI_AMBV2_PROFIT_SUM_LISTED_T` L107/114 |
| **集团阿米巴利润汇总**（含 SAP 调整值） | **`IN ('S','T')`** | `PJob_DWS_DM_FI_AMBV2_PROFIT_SUM_T` L750 |
| **卫浴事业部利润表** | `= 'S'` | `PJob_DWS_DM_SW_FI_AMBV2_PROFIT_SUM_T` L1105 |
| **上市口径利润表** | **WHERE 不过滤 data_source**，全部在 CASE 内按指标判定 | `PJob_DM_FI_AMBV2_PROFIT_SUM_LISTED_T` L120-122 |
| 跨事业部收入/成本 — **对外卖出方** | `S` | `PJob_DWS_DM_FI_AMBV2_PROFIT_SUM_T` L773/804 |
| 跨事业部收入/成本 — **供货方** | `D` | 同上 L774/805 |
| 事业部内部 — 供货方 | `U` | `SW` L1162/1329 |
| 卫浴非全资调整值（取 `prod_cost_adjust`） | `W` | `PJob_DWS_DM_FI_AMBV2_PROFIT_SUM_T` L814 |
| 分成费用 | `S` 的 `ext_profit_1n_amt+ext_cross_profit_amt` **减去** `D` 的 `(profit_1n_amt+cross_profit_amt−ext_*_amt)` | `LISTED` L117-119 |

### 集团日报 V3 交叉验证（2026-11-02）

集团日报（FI255 / FI258）的数据集是 `dm_fin_group_daily_v3_t`，生产脚本 `PJob_DWS_DM_FIN_GROUP_DAILY_V3_T.txt`（379KB）。

⚠️ **集团日报不使用 `dm_ambv2_profit_t`**（2026-11-02 实测脚本内出现 0 次）——它是**业绩**口径（源为 `upload_achievement_prediction_t` 等），**不能用来验证本表的利润口径**。佐证"不能一律 S"：其内部各业务块 data_source 取值各异（四大事业部 `IN ('S','T','D')`、"其中：跨事业部交易"专取 `='D'`、"其中：1+N"取 `='S'`，L260/321/343/367），与"D=供货方"语义互相印证——同一份数据、不同业务块取不同 data_source 是常态。

**所以 S/D 不是简单的"重复"**：
- **总额类字段**（`notax_sales_net_amt`、`act_cost_sum_amt`、`zyywcb` 等）：S 与 D 是同一笔跨事业部交易的两条记录，值相同 → **相加才双计**，取 S 即可。
- **分成类字段**（`cross_income`/`cross_cost`/`profit_1n`/`cross_profit`/`ext_*_amt`）：S 装**卖出方**分成、D 装**供货方**分成，**值不同、不是重复** → 按要看哪一方选，选错了不是"双计"而是"取错口径"。

### 合并抵销过滤（三个汇总脚本共有，原文档漏）

除 data_source 外，利润口径还必须带：

| 条件 | 含义 |
|------|------|
| `cust_group <> 'Z0' OR cust_group IS NULL` | 排除 Z0 内部客户组（对外口径） |
| `comp_code <> 'Z000'` / `<> '7G00'` / `<> '8000'` | 按口径排除特定公司代码（Z000/7G00/8000 各脚本取舍不同） |
| `D.node_name2 <> 'R91000002'` | 排除过渡部门 —— 需 JOIN `dm_rpt_sales_group_t`（`node_name9 = A.sales_grp`）；等价于 `sales_division_1n_code <> '91000002'` |

> 这三个条件 + data_source 才构成"利润表口径"。只写 `data_source='S'` 得出的数字与集团利润表对不上。

---

## 已知陷阱（实测 + 源码）

1. **不要无脑 `data_source='S'`**（⚠️ 2026-11-02 依据下游汇总脚本修正，此前"一律取 S"的说法错误）：
   - **总额类字段**（收入/成本/面积/数量）：S 与 D 是同一笔跨事业部交易的两条记录，值相同 → 不加过滤直接 SUM 会双计，取 `S` 即可。
   - **分成类字段**（`cross_*`/`*1n*`/`ext_*_amt`/`dept_inner_*`）：S=卖出方、D=供货方、U=事业部内部供货方、W=卫浴非全资调整，**值不同、不是重复**，按要看的视角取，不是"S 通吃"。
   - **集团阿米巴利润汇总口径是 `IN ('S','T')`**（要含 SAP 调整值），不是 `='S'`。
   - **上市口径根本不在 WHERE 过滤**，全在 CASE 内按指标判定。
   - 完整判定表见上文「不要无脑 `data_source='S'`」。
2. **stat_day 有脏数据**（存在 `0002-11-30`、calday=`00000000`）——时间过滤**只用 calmonth**。
3. 大表（4600~5100 万行），任何查询必须带 calmonth 范围。
4. `sales_division_1n_code='91230602'`（关联交易）及 null 部门行金额为 0；对外口径如何处理待业务确认。
5. 无 node_desc —— 从 Mix 表经验带过来的 `node_desc2='瓷砖事业部'` 写法在本表**必然失败**，用 `sales_division_1n_code='11000001'`。
6. 当月为月中快照（如 2026-11 仅 stat_day=2026-11-01），回答当月需声明非完整月。且 **2025-07-26 / 2025-09-26 变更后，月结前（当月）实际成本读取的是"上期周期价/上期周期总价"**，当月成本与次月回看数值不同。
7. `val_type`（评估类型）多为凭证号类杂值，不作过滤维度。
8. **国补行被改判为 T**（见 data_source 一节），纯 `='S'` 聚合会漏国补调整值。
9. **备份/临时表同名泛滥**——以下一律禁用，只用 `dm.dm_ambv2_profit_t`：
   `_init`、`_temp`、`_tmp1`、`_tmp2`、`_20260429_qyj_250101hou`、`_20260602_qyj_260101_hou`。（`_ext` 不是备份表，是 EXT 补数作业产物，见血缘节）
10. `amb_bath_cost_amt` 无历史数据，做时间序列会得出"2024 年之前全是 0"的错误结论。

---

## 查询模式（实测可跑）

### 先选口径，再写 SQL

| 你要对齐什么 | data_source | 附加过滤 |
|---|---|---|
| 事业部收入/成本/毛利总额（**总额类字段**） | `= 'S'` | 事业部过滤即可 |
| **集团阿米巴利润表口径** | `IN ('S','T')` | `cust_group <> 'Z0'` + `node_name2 <> 'R91000002'` |
| **卫浴事业部利润表口径** | `= 'S'` | `cust_group <> 'Z0'` + `comp_code <> '7G00'` + `node_name2 <> 'R91000002'` |
| **上市口径** | 不过滤（CASE 内判定） | `comp_code <> 'Z000'` / `<> '8000'` + `cust_group <> 'Z0'` + `bill_type` 过滤 |
| 跨事业部**卖出方**分成 | `= 'S'` | — |
| 跨事业部**供货方**分成 | `= 'D'` | — |
| 事业部内部供货方 | `= 'U'` | — |
| 卫浴非全资调整值 | `= 'W'`（取 `prod_cost_adjust`） | — |

```sql
-- 模式1：某事业部月度收入成本毛利（总额类字段，S 视角）
-- 适用：看事业部自身经营的收入/成本/毛利序列
SELECT calmonth,
       SUM(notax_sales_net_amt)::numeric(18,2)    AS 不含税净额,
       SUM(act_cost_sum_amt)::numeric(18,2)       AS 实际成本,
       SUM(amb_profit_amt)::numeric(18,2)         AS 阿米巴毛利,
       SUM(act_cost_profit_amt)::numeric(18,2)    AS 实际成本毛利
FROM dm.dm_ambv2_profit_t
WHERE calmonth BETWEEN '2026-01' AND '2026-10'
  AND data_source = 'S'
  AND sales_division_1n_code = '11000001'
GROUP BY calmonth ORDER BY calmonth;

-- 模式1B：对齐「集团阿米巴利润表」口径（含 SAP 调整值 T 行 + 合并抵销）
-- 与模式1的差异：data_source IN ('S','T')、排除 Z0 内部客户组、排除过渡部门
SELECT A.calmonth,
       SUM(A.notax_sales_net_amt)::numeric(18,2) AS 不含税净额,
       SUM(A.amb_profit_amt)::numeric(18,2)      AS 阿米巴毛利
FROM dm.dm_ambv2_profit_t A
LEFT JOIN dm.dm_rpt_sales_group_t D
  ON D.node_name9 = A.sales_grp
WHERE A.calmonth BETWEEN '2026-01' AND '2026-10'
  AND A.data_source IN ('S','T')
  AND (A.cust_group <> 'Z0' OR A.cust_group IS NULL)
  AND D.node_name2 <> 'R91000002'
  AND SUBSTR(D.node_name2, 2, 999) = '11000001'   -- 事业部（去首位 R/H）
GROUP BY A.calmonth ORDER BY A.calmonth;

-- 模式2：TOP10 毛利贡献物料（SKU 级下钻）
SELECT material, material___t,
       SUM(notax_sales_net_amt)::numeric(18,2) AS 不含税净额,
       SUM(amb_profit_amt)::numeric(18,2)      AS 阿米巴毛利
FROM dm.dm_ambv2_profit_t
WHERE calmonth = '2026-10'
  AND data_source = 'S'
  AND sales_division_1n_code = '11000001'
GROUP BY material, material___t
HAVING SUM(amb_profit_amt) > 0
ORDER BY 阿米巴毛利 DESC LIMIT 10;

-- 模式3：单据级追溯（某订单的收入成本明细）
SELECT doc_number, s_ord_item, bill_num, ac_doc_nr,
       notax_sales_net_amt, act_cost_sum_amt, amb_profit_amt, data_source
FROM dm.dm_ambv2_profit_t
WHERE calmonth = '2026-10'
  AND doc_number = '<订单号>'
ORDER BY s_ord_item, ac_doc_ln;

-- 模式4：探查 data_source × trading_mode 分布（下钻前先看清楚再决定取哪个）
-- ⚠️ 仅用于探查：本查询按 (trading_mode, data_source) 分组，每组独立成行。
--    绝不能把各组 notax_sales_net_amt 横向相加——S/D 是同一笔交易的双方记录，相加即双计。
-- dept_inner_* 只在 data_source='U' 有值，cross_* 只在 trading_mode='C' 有值
SELECT trading_mode, data_source,
       COUNT(*)                                        AS 行数,
       SUM(notax_sales_net_amt)::numeric(18,2)         AS 不含税净额,
       SUM(profit_1n_amt)::numeric(18,2)               AS 1N毛利额,
       SUM(cross_profit_amt)::numeric(18,2)            AS 跨事业部毛利额,
       SUM(dept_inner_profit_amt)::numeric(18,2)       AS 事业部内部毛利额
FROM dm.dm_ambv2_profit_t
WHERE calmonth = '2026-10'
  AND sales_division_1n_code = '11000001'
GROUP BY trading_mode, data_source
ORDER BY 行数 DESC;

-- 模式5：对外口径（剔除关联交易 + 共享仓业务范围 + 合并抵销）
-- 在模式1基础上追加：排除 91230602 关联交易、G000/G001 业务范围、Z0 内部客户组
SELECT SUM(notax_sales_net_amt)::numeric(18,2) AS 不含税净额,
       SUM(amb_profit_amt)::numeric(18,2)      AS 阿米巴毛利
FROM dm.dm_ambv2_profit_t
WHERE calmonth = '2026-10'
  AND data_source = 'S'
  AND COALESCE(sales_division_1n_code, '') <> '91230602'
  AND (cust_group <> 'Z0' OR cust_group IS NULL)
  AND (bus_area IS NULL OR bus_area = '' OR bus_area NOT IN ('G000','G001'));

-- 模式6：跨事业部交易 — 卖出方 vs 供货方 分成对照
-- ⚠️ S=对外卖出方、D=供货方，两者的 cross_income / cross_cost 值不同、不是重复
SELECT '卖出方(S)' AS 视角,
       SUM(cross_income)::numeric(18,2) AS 跨事业部收入,
       SUM(cross_cost)::numeric(18,2)   AS 跨事业部成本,
       SUM(ext_cross_profit_amt)::numeric(18,2) AS 对外分成毛利额
FROM dm.dm_ambv2_profit_t
WHERE calmonth = '2026-10' AND data_source = 'S' AND trading_mode = 'C'
UNION ALL
SELECT '供货方(D)',
       SUM(cross_income)::numeric(18,2),
       SUM(cross_cost)::numeric(18,2),
       SUM(ext_cross_profit_amt)::numeric(18,2)
FROM dm.dm_ambv2_profit_t
WHERE calmonth = '2026-10' AND data_source = 'D' AND trading_mode = 'C';
```

---

## 口径变更时间线（ETL 脚本头 62 条变更史中，影响取数的 8 条）

| 日期 | 变更 | 对查询的影响 |
|------|------|-------------|
| 2024-06-07 | 标A整体毛利取消运费装卸费 | `a_overall_profit_amt` 前后不可直接跨年对比 |
| 2024-07-25 | 新增 `zzqjgl`（周期价-管理） | 该字段 2024-07 前无值 |
| 2025-01-17 | 新增经销商客编/名称/销售组织；修改母客编与组织逻辑 | 客户/组织维度前后口径不同 |
| 2025-03-12 | 整合渠道逻辑调整 | `integrate_channel` 跨年对比需谨慎 |
| 2025-04-22 | 新增 SAP 调整值表 | `T` 行来源与量级发生变化 |
| 2025-04-29 | **阿米巴毛利额逻辑调整**（取消产品所有权判断） | ⚠️ `amb_profit_amt` 2025-04 前后口径不同，跨年对比必须声明 |
| 2025-07-26 | 月结前，读取主营业务成本指标改为读取**上期周期价** | 当月快照成本 ≠ 次月回看值 |
| 2025-09-26 | 实际成本(`zyywcb`) 当数据年月=当前年月时读**上期周期总价** | 同上，强化当月口径差异 |

> 结论：**跨年（尤其跨 2025-04）对比阿米巴毛利、跨 2025-01 对比客户/组织维度时，必须在答案中声明口径变更**。

---

## 血缘

```
SDI.SDI_AMB_COST_RULES_T_1037 (阿米巴成本规则→trading_mode/分成率)   ┐
DWRDIM.DWR_DIM_ORG_SALE_GRP_TMP01 (组织树)                          │
DM.DM_ZZT_XSSR_T (销售输入事实)                                     │
DM.DM_RPT_ZZT_KCMX_T (库存明细→批次成本)                            ├→ Hive PJob_DM_AMBV2_PROFIT_T
DWRFIN.DWR_MAT_PERIOD_PRICE_R (期间价格→周期价)                     │   (DWR/FIN/COST, 活跃)
dwifin.dwi_prc_ztamb_cost_t (直营阿米巴成本)                        │   insert overwrite partition(period_id_m)
DWRFIN.DWR_SAP_ADJUST_DATA_T (SAP调整值→'T'行)                      │
DWRDIM.DWR_DIM_CUST_PARTNER_D (母客编)                              ┘
```

- 活跃脚本归档：`huaweiclaude/DWR/FIN/COST/PJob_DM_AMBV2_PROFIT_T.txt`（口径参考文档见脚本头腾讯文档链接）
- 停用脚本：`huaweiclaude/DM/DM_CT/PJob_DWS_DM_AMBV2_PROFIT_T-停用.txt`（DWS 原生旧版，勿参照）
- 伴随表 `dm_ambv2_profit_t_ext`：EXT 补数作业产物（成本调整值，特殊工程 F000/山西基地 I000），仅 973 行历史数据，一般查询不用

### 如何溯源下游报表（方法论，可复用）

帆软报表文件 `*.cpt` **不是二进制**——是 XML 明文（文件头 `<?xml version="1.0" encoding="UTF-8"?><WorkBook>`），可直接用正则解析出报表引用的表名（`\b(dm|dwr\w*|dwi\w*|sdi|upload)\.[a-z0-9_]+`）和过滤逻辑（`data_source` 出现次数；实测 FI255 内 0 次）。ripgrep 默认搜不到 `.cpt` 扩展，需 PowerShell `Get-Content -Raw` 提取。

**关键**：报表层通常**不含**过滤逻辑（`data_source`、`prod_property` 等全在 ETL 层），拿到表名后必须找对应 `PJob_*.txt` 才能看到真实口径。

> ⚠️ 路径说明：`.cpt` 报表文件（`reportlets/`）与 BI 服务器侧的 ETL 脚本目录（`etl/`）**不在本仓**——本仓的脚本归档在 `huaweiclaude/`。做报表溯源时需先从报表服务器取 `.cpt` 文件。

### 下游表路由（本表的汇总层，能不扫底表就不扫）

| 表 | 用途 | 何时替代本表 |
|----|------|-------------|
| `dm_fi_ambv2_profit_sum_t` | 阿米巴利润汇总 | 事业部/月度利润汇总 |
| `dm_fi_ambv2_profit_sum_listed_t` | **上市口径**利润表 | 用户问"上市口径/上市公司利润" |
| `dm_sw_fi_ambv2_profit_sum_t` | 卫浴事业部阿米巴利润 | 用户问"卫浴阿米巴利润" |
| `dm_sw_category_fi_ambv2_profit_sum_t` | 卫浴品类阿米巴利润 | 卫浴 + 品类粒度 |
| `dm_ambv2_zzt_xssr_t` | 阿米巴集团业绩表 | 本表**上游**，查业绩输入而非利润 |

---

## 待业务确认

- ✅ **已用 ETL 源码确证**（原待确认项，现关闭）："收入"默认字段确为 `notax_sales_net_amt` —— `act_cost_profit_amt` 与 `a_overall_profit_amt` 均以它为被减数，且与 Mix 表同名同源。
- 「三口径毛利」的业务问法映射（**建议稿，待业务拍板**）：
  - "阿米巴毛利/经营利润" → `amb_profit_amt`（内部结算价 + 分成后，事业部考核口径）
  - "实际成本毛利" → `act_cost_profit_amt`（最贴近财务口径）
  - "标A毛利/标准毛利" → `a_overall_profit_amt`（对标标准成本，看价格/结构差异）
- ❓ 仍待确认：`91230602` 关联交易行与 null 部门行在对外口径中何时排除（模式5 为建议写法，非业务确认口径）
- ❓ 仍待确认：`D`/`U`/`W` 行的业务读法（当前语义已由 ETL 赋值点确证，但业务侧叫法未对齐）

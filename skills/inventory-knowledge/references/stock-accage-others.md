# 非产成品库存库龄（FIFO 库龄表）

## 快速参考

| 属性 | 值 |
|---|---|
| DWS 表名 | `dm.dm_fin_stock_detail_accage_others_t` |
| 业务含义 | **非产成品**库存库龄（ETL 注释原文："非产成品库存库龄"）。库龄用 **FIFO 先进先出**倒推，不是按批次日期直接分桶 |
| 行数 | **6,526.7 万**（2026-11-03 连库 `count(*)` 实测 65,266,974） |
| 列数 | 102 |
| 时间范围 | 202401 ~ 202611（35 个月，比主表 `_2023` 短） |
| 分区键 | **`period_id_m`**（YYYYMM），分区表 |
| 粒度 | 物料 + 批次 + 公司 + 工厂 + 库存地点 + 统计月 |
| 物料范围 | **硬排除 `matl_type='FERT'`**（ETL L26/L168）；实际含 ROH/UNBW/VERP/HALB/Z001 |
| ETL | `huaweiclaude/DWR/OTD/WM/PJob_DM_FIN_STOCK_DETAIL_ACCAGE_OTHERS_T.txt`（16KB，5 层中间表 `_01`~`_04`） |

---

## 一、与主表的物料范围关系（**默认不要相加**）

**`_2023` 与 `_others_t` 物料范围零重叠**，2026-11-03 实测：

| 表 | 物料范围 | 202608 行数 | 202608 金额 |
|---|---|---|---|
| `dm_fin_stock_detail_accage_t_2023` | **100% FERT（产成品）** | 632.5 万 | **14.74 亿** |
| `dm_fin_stock_detail_accage_others_t` | **0 行 FERT（非产成品）** | 486.8 万 | **2.66 亿** |

⚠️ **业务默认的"库存 / 全集团库存 / 总库存"就是 `_2023` 的产成品口径（14.74 亿），不要叠加本表**（2026-11-03 业务确认）。

零重叠只是物料范围的客观事实，**不代表两者要合计成"总库存"**。本表只在用户明确问"原材料/半成品/包装/非产成品"时才查，且单独作答、不与产成品合并。

### 两表口径对照

| 维度 | `_2023`（产成品） | `_others_t`（非产成品） |
|---|---|---|
| 库龄算法 | 批次入库日期直接分桶 | **FIFO 物料凭证倒推** |
| 库龄表达 | 宽表多桶 `wbzq_*`/`ybzq_*`（金额/数量/面积/体积各一套） | 标量 `stockage`（天数）+ `stockage_seg`（9 段） |
| 金额字段 | `zsjkcje`（管理）/`stock_amt`（阿米巴） | `final_zsjkcje`（FIFO 分摊 + 差异补齐估值） |
| 数量 | `quantity` | `final_stock_qty` |
| 面积/体积 | `*_area` / `*_volume`（按段） | `final_kcmj` / `final_kctj`（按物料长宽高换算） |
| 时间字段 | `calmonth` | **`period_id_m`** |
| 特殊库存标识 | 无 | **`stock_k`**（K/NK） |
| 总账科目 | 无 | **`fipos`** |
| 保质期 | 有 `bz_flag` + 四桶 | **无**（非产成品不做保质期） |
| 减值/跌价 | 有 `jchj_*` / `*_fall_*` | **无** |

⚠️ 两张表**不能 UNION 后直接按库龄段对齐**——一边是 6/12/24 月桶，一边是 9 段天数桶，分档边界不同（见第四节）。

---

## 二、指标口径卡

### 2.1 库存量

| 指标 | 字段 | 说明 |
|---|---|---|
| 库存数量 | `final_stock_qty` | FIFO 分摊后的最终数量 |
| 库存金额 | `final_zsjkcje` | ⚠️ 见 2.2，**不等于账面库存金额** |
| 库存面积 | `final_kcmj` | 按物料长宽换算（第五节） |
| 库存体积 | `final_kctj` | 按物料长宽高换算（第五节） |
| 库龄天数 | `stockage` | 已算好，0 ~ 2863 天，均值约 205 天 |
| 库龄段 | `stockage_seg` | 9 档，见第四节 |

### 2.2 金额口径：不可直接当账面库存金额

202611 实测构成：

| `stockcat` | 行数 | 金额 | 占比 |
|---|---|---|---|
| **NULL** | 291,366 | **2.527 亿** | **99.5%** |
| K | 392 | 118.3 万 | 0.5% |
| Q | 860 | 1.4 万 | ~0 |
| E | 45 | 0.4 万 | ~0 |
| T | 271,949 | 1,519 元 | ~0 |
| U | 810,573 | **0 元** | 0 |

**99.5% 的金额落在 `stockcat IS NULL` 的行上**，这些是 ETL 的「差异补齐行」（第六节第 6 步），金额 = 差额数量 × `zmmm_o017_zzqj`（周期价/移动平均价），**是估值不是实际库存金额**。

→ 因此：
- `final_zsjkcje` 可用于**结构分析**（占比、趋势），不宜用于**账面核对**
- 需要账面金额时，非产成品部分应回上游 `dm_rpt_zzt_kcmx_others_t` 或财务账
- **不要与 `_2023` 的 `zsjkcje` 相加**：业务默认"库存金额"取 `_2023` 的 `zsjkcje`（产成品口径），本表金额只在问非产成品时单列使用

### 2.3 特殊库存

`stock_k`：`stockcat='K'` → `'K'`，其余 `'NK'`。202611：NK 137.5 万行 2.53 亿；K 仅 395 行约 100 万。

---

## 三、库龄算法（FIFO 实证，ETL 五步）

```text
第 1 步 上游取数（tmp）
  dm.dm_rpt_zzt_kcmx_others_t
  WHERE period_id_m = 当期 AND matl_type <> 'FERT'
  stock_k = CASE WHEN stockcat='K' THEN 'K' ELSE 'NK' END

第 2 步 汇总期末库存（_01）
  GROUP BY stock_k, comp_code, plant, material, batch, matl_type
  → quantity（数量）、zsjkcje（金额）

第 3 步 FIFO 累计入库（_02）
  JOIN sdi.sdi_matdoc_1001（物料凭证流水）
    ON 公司/工厂/物料/批次/stock_k
  WHERE stock_qty > 0 AND substr(budat,1,6) <= period_id_m
  窗口排序（优先级从高到低）：
    ① 入库类型在白名单且 BSTTYP_SG <> 'K'  → 优先
       白名单：101/911/913/701/Z01/511/982/991/309/131/531/411/561/653
    ② 未冲销（cancelled <> 'X'）优先
    ③ budat DESC → LIFNR DESC → WERKS DESC → MBLNR DESC → MJAHR DESC → ZEILE DESC → SHKZG DESC
  → 累计 sum_stockin

第 4 步 截取"刚好满足现有库存"的入库批次（_03）
  WHERE (sum_stockin >= quantity AND sum_stockin - stock_qty < quantity)
     OR sum_stockin < quantity
  stockage = datediff( LEAST(昨天, 统计月最后一天), budat )

第 5 步 按数量比例分摊到库位（_04）
  final_stock_qty = quantity    × (tmp_stock_qty / quantity_sum)
  final_zsjkcje   = zsjkcje     × (tmp_stock_qty / quantity_sum)
```

**库龄基准日** = `LEAST(昨天, 统计月最后一天)`。当月取昨天、历史月取月末，与 `_2023` 的 `zdate` 逻辑一致。

**第 6 步 差异补齐行**：当 `SUM(final_stock_qty) <> quantity_sum` 时补一行差额：

```text
final_stock_qty = quantity_sum − SUM(final_stock_qty)
final_zsjkcje   = 该差额 × zmmm_o017_zzqj（周期价）
stockcat / stocktype / stor_loc / vendor / wbs_elemt / doc_number 等维度全部 NULL
stockage        = MIN(stockage)  ← 取该组最小库龄
```

⚠️ ETL 内部有 `isfix='Y'/'N'` 标记，但**未写入最终表**（102 列里没有 `isfix`）。识别差异补齐行只能靠 **`stockcat IS NULL`**（202611 占 21% 行、99.5% 金额）。

---

## 四、库龄段分档（`stockage_seg`，9 档）

| 库龄段 | 天数区间 | 202611 行数 | 202611 金额 |
|---|---|---|---|
| 0-30天 | < 31 | 621,125 | 1.07 亿 |
| 31-60天 | 31 ~ 60 | 152,080 | 0.24 亿 |
| 61-90天 | 61 ~ 90 | 155,722 | 0.12 亿 |
| 91-180天 | 91 ~ 180 | 263,336 | 0.18 亿 |
| 181-270天 | 181 ~ 270 | 16,409 | 0.07 亿 |
| 271-360天 | 271 ~ 360 | 15,048 | 0.09 亿 |
| 1年-2年 | 361 ~ 720 | 33,577 | 0.22 亿 |
| 2年-3年 | 721 ~ 1080 | 21,104 | 0.17 亿 |
| 3年以上 | > 1080 | 96,784 | 0.38 亿 |

⚠️ **按 360 天/年分档**（1 年=360、2 年=720、3 年=1080），不是 365。自己写 `DATEDIFF` 分档时若用 365 会与 `stockage_seg` 对不上。

---

## 五、面积/体积计算规则（ETL L491-502）

**面积 `final_kcmj`**

```text
IF (单位首字母='Z' OR 单位 IN ('M2','M','Z09','L') OR 物料组='ZJGY')
   AND 单位 NOT IN ('Z33','Z35')
   THEN 面积 = final_stock_qty                    -- 已是面积计量
   ELSE 面积 = length_1 × width × final_stock_qty / 1000000
```

**体积 `final_kctj`**

```text
IF (单位 IN ('M3','M') OR 物料组='ZJGY')
   THEN 体积 = final_stock_qty                    -- 已是体积计量
   ELSE 体积 = length_1 × width × height × final_stock_qty / 1000000000
```

长宽高来自 `dwimd.dwi_md_data_material_general_t`（`length_1`/`width`/`height`）。**单位不同一，同一列可能混着"数量"和"换算值"**，跨物料汇总面积/体积时须知这一点。

---

## 六、字段说明

### 6.1 核心度量

| 字段 | 含义 |
|---|---|
| `final_stock_qty` | 最终库存数量（FIFO 分摊后） |
| `final_zsjkcje` | 最终库存金额（FIFO 分摊 + 差异补齐估值） |
| `final_kcmj` | 最终库存面积 |
| `final_kctj` | 最终库存体积 |
| `stockage` | 库龄天数（已算好，整数，无 NULL） |
| `stockage_seg` | 库龄段（9 档） |
| `quantity` / `zsjkcje` | 上游原始值（未分摊，工厂+批次级） |
| `quantity_sum` / `zsjkcje_sum` | FIFO 分组合计值 |
| `tmp_stock_qty` / `tmp_zsjkcje` | 中间计算值（建议勿用） |
| `zmmm_o017_zzqj` | 周期价/移动平均价（差异补齐行用它估值） |

### 6.2 时间字段

| 字段 | 含义 |
|---|---|
| `period_id_m` | 统计月份（YYYYMM，**分区键**） |
| `calmonth` / `calmonth2` / `calyear` | 冗余日历字段 |
| `budat` | **FIFO 命中的入库凭证过账日**（YYYYMMDD，库龄计算基准） |
| `earliest_voucher_post_date` | 批次主数据的**最早凭证过账日**（批次溯源用） |
| `zmmm_o017_zbatch_date` | SAP 批次入库日期 |
| `produce_date` | 生产日期 |
| `dw_last_update_date` | 数据同步时间 |

### 6.3 库存属性

| 字段 | 含义 |
|---|---|
| `stock_k` | 特殊库存标识（K/NK，按 `stockcat='K'`） |
| `stockcat` / `stockcat___t` | 库存类别。**IS NULL = 差异补齐行** |
| `stocktype` / `stocktype___t` | 库存类型 |
| `val_type` / `val_class` / `val_class___t` | 评估类型/评估类 |
| `fipos` | **总账科目**（`_2023` 无此字段） |
| `matl_type` / `matl_type___t` | 物料类型（**永不含 FERT**） |
| `unit` / `unit___t` | 基本计量单位 |

### 6.4 维度

与 `_2023` 高度一致：`comp_code`、`plant`、`stor_loc`、`material`、`batch`、`vendor`、`zdpsyb`（事业部）、`zdpzgsdq`（子公司大区）、`zprodh1~5`、`matl_grp_1~5`、`zyl01`（产品渠道）、`zyl06`（产品等级）、`zww010`（产区）、`wbs_elemt`，**均带 `___t` 中文描述**。

⚠️ 本表**没有** `_2023` 那 6 个业务分类字段（`base`/`product_base`/`storage_classify`/`classify_name`/`category_name`/`foreign_own`），按基地/品类分析需回 `_2023` 或 JOIN 主数据。

---

## 七、陷阱

1. **只含非产成品**：`matl_type <> 'FERT'` 是硬过滤。**业务默认"库存/总库存"取 `_2023` 产成品口径，本表不要叠加进去**（2026-11-03 业务确认）；仅在明确问非产成品时使用
2. **`final_zsjkcje` 不是账面金额**：99.5% 来自差异补齐行的周期价估值，只能做结构/趋势分析
3. **`stockcat IS NULL` = 差异补齐行**（21% 行、99.5% 金额），其 `stocktype`/`stor_loc`/`vendor` 也全为 NULL → 按库位或库存类别汇总会明显偏小
4. **60.5% 的行金额为 0**（202611：831,571/1,375,185），主要是 UNBW 非估价物料（81 万行）→ 按金额排序时这些物料会全部沉底，但它们有实际库存数量
5. **时间字段是 `period_id_m` 不是 `calmonth`**，写 `WHERE calmonth='202611'` 不会走分区裁剪
6. **行数不代表业务量级**：FIFO 会把一个批次的库存拆成多条入库记录。202604 186 万 → 202607 515 万 → 202610 骤降至 138 万，但**金额（2.5~2.8 亿）和数量（6400~7400 万）始终平稳** → 行数变化是拆分粒度变化，不是数据缺失
7. **`stockage` 已算好，不要重算**：库龄基准是 `LEAST(昨天, 月末)`，自己用 `DATEDIFF(now(), budat)` 会与当月口径不一致
8. **库龄段按 360 天/年**，不是 365
9. **面积/体积是混合单位**：部分物料面积=数量、部分=长×宽×数量/1e6，直接 SUM 前需确认物料范围
10. **月份从 202401 起**（35 个月），比 `_2023` 的 202012 短，跨表回溯要注意
11. **无保质期、无减值/跌价字段**：`bz_flag`、`wbzq_*`、`jchj_*` 都不在本表
12. **`batch` 可能为 `'#'`**（ETL `COALESCE(batch,'#')`），无批次库存用 `#` 占位，不是空值

---

## 八、常见查询

### 库龄段结构（按事业部）

```sql
SELECT zdpsyb, zdpsyb___t, stockage_seg,
       SUM(final_stock_qty) AS qty,
       SUM(final_zsjkcje)   AS amt
FROM dm.dm_fin_stock_detail_accage_others_t
WHERE period_id_m = '202611'
GROUP BY zdpsyb, zdpsyb___t, stockage_seg
ORDER BY zdpsyb, amt DESC;
```

### 按物料类型看库存规模

```sql
SELECT matl_type, matl_type___t,
       COUNT(*) AS rows,
       SUM(final_stock_qty) AS qty,
       SUM(final_zsjkcje)   AS amt,
       SUM(final_kcmj)      AS area
FROM dm.dm_fin_stock_detail_accage_others_t
WHERE period_id_m = '202611'
GROUP BY matl_type, matl_type___t
ORDER BY amt DESC;
```

### 与产成品规模并排对照（**只并排，不做合计**）

```sql
SELECT '产成品(FERT)' AS scope,
       SUM(zsjkcje) AS amt
FROM dm.dm_fin_stock_detail_accage_t_2023
WHERE calmonth = '202608'
UNION ALL
SELECT '非产成品', SUM(final_zsjkcje)
FROM dm.dm_fin_stock_detail_accage_others_t
WHERE period_id_m = '202608';
```

⚠️ 这是**两个独立口径并排**，不是"总库存"。业务默认"全集团库存"只取产成品那行（14.74 亿）；两行金额口径也不同（实际 vs FIFO 估值），**不可相加**。

### 长龄库存 TOP（排除差异补齐行）

```sql
SELECT material, material___t, plant___t, stockage_seg,
       SUM(final_stock_qty) AS qty,
       SUM(final_zsjkcje)   AS amt
FROM dm.dm_fin_stock_detail_accage_others_t
WHERE period_id_m = '202611'
  AND stockage > 360
  AND stockcat IS NOT NULL      -- 排除差异补齐行
GROUP BY material, material___t, plant___t, stockage_seg
ORDER BY amt DESC
LIMIT 50;
```

### 单物料 FIFO 溯源

```sql
SELECT material, batch, plant___t, stor_loc___t,
       budat, stockage, stockage_seg,
       final_stock_qty, final_zsjkcje, earliest_voucher_post_date
FROM dm.dm_fin_stock_detail_accage_others_t
WHERE period_id_m = '202611' AND material = '物料号'
ORDER BY stockage DESC;
```

---

## 九、血缘与下游

- **上游**
  - `dm.dm_rpt_zzt_kcmx_others_t`（非产成品库存明细，本期库存与金额）
  - `sdi.sdi_matdoc_1001`（SAP 物料凭证流水，FIFO 倒推依据）
  - `dwimd.dwi_md_data_material_general_t`（物料主数据，取长宽高算面积/体积）
  - `dwimd.dwi_md_matl_batch_info_t`（批次主数据，取 `earliest_voucher_post_date`，条件 `substr(end_date,1,4)='4712'` 即未失效）
- **中间表**：`dm_fin_stock_detail_accage_others_t_01` ~ `_04`（请勿直接查询）
- **下游**：**无报表、无下游 ETL 引用**（2026-11-03 全量扫描 `reportlets/` 与 `etl/` 均为 0）→ 本表供即席分析使用

---

## 十、交叉引用

- 主表（产成品）→ [stock-accage.md](stock-accage.md)
- 语义层 → [metrics.md](metrics.md)
- 完整血缘 → [data-lineage.md](data-lineage.md)
- 跌价/减值（仅产成品有）→ [stock-fall-list.md](stock-fall-list.md)

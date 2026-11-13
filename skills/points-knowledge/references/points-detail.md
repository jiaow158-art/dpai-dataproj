# 发票积分明细表 — `dwrfin.dwr_gl_pointsdetail_f`

**本域主事实表**。积分台账明细：一行 = 一条积分更改记录×行项目（期初/计提/使用/结转/清账/冲销全生命周期流水）。

| 属性 | 值（实测 2026-11-12） |
|---|---|
| 行数 / 体积 | 29,675,758 行 / 6.1 GB |
| 数据范围 | calmonth `2011-12` ~ `2026-11`（当月部分装载）；budat `2011-12-31` ~ `2026-11-11` |
| 组织覆盖 | 全事业部 30+ 公司代码（comp_code），含 `Z000` 跨公司调整行（下游汇总口径显式排除，见 metrics.md） |
| 刷新 | 月度增量（分区字段 period_id_m） |
| 大表红线 | **查询必须带时间过滤**（calmonth / budat / period_id_m 至少其一） |
| 分布列（DWS 列存） | `calmonth, material, comp_code, salesorg, vbeln, posnr, wbsid, rc_account, pointscategorycode, sales_group_code`（pgxc_class 实测：hash 分布 4096 桶，10 列）—— 时间红线之外，**过滤条件尽量再命中分布键**（comp_code/calmonth/material/vbeln 等），避免 2,900 万行全表重分布 shuffle |

## 备份变体表（禁用）

`dwr_gl_pointsdetail_f_260331_wjh` / `_t` / `_20250501_qyj` / `_20250429_wjh` 均为备份变体，禁止查询。

同域还有 `dwr_gl_pointsdetail_collect_f`（汇总表，实测 **879,285 行**——`reltuples` 统计过期显示 0，勿信估计值；行存表，用途见下"同域事实表"）。

## 字段说明（核心业务字段）

### 1. 标识与时间

| 字段 | 类型 | 说明 |
|---|---|---|
| `comp_code` | varchar | 公司代码（`Z000` = 跨公司调整） |
| `zjfggbh` / `zjfggit` | varchar | 更改记录编号（凭证号）/ 行项目 —— 凭证级下钻主键 |
| `calmonth` | varchar | 年月 **`YYYY-MM` 带横线**（脏值 `0000-00` 仅 1 行） |
| `budat` | varchar | 过账日期，**双形态**：10 位 `YYYY-MM-DD`（156 万行）与 19 位 `YYYY-MM-DD HH:MI:SS`（2,811 万行）——切年月日一律 `substr(budat,1,10)` |
| `erdat` | varchar | 操作日期 |
| `reconciliationdate` | varchar | 清账日期，8 位 **`YYYYMMDD`**；`00000000` = 未清账；约 248 万行空/NULL |
| `reconciliationflag` | varchar | 清账标识，`A` = 已清账（实测 2026-09：43 万行中仅 432 行为 A） |
| `offset_mark` | varchar | 冲销标识，`X` = 已冲销 |
| `period_id_m` | varchar | ETL 分区月 **`YYYYMM` 无横线**（全表统一 6 位） |
| `last_update_date` | **timestamp** | 最后更新时间 —— **全表唯一 timestamp 字段**（其余全部 varchar / numeric），可作增量重跑、数据新鲜度排查依据 |

### 2. 组织与客户

| 字段 | 说明 |
|---|---|
| `customer` | 客户编码（SAP KUNNR 10 位，双命名：他表或叫 `cust_num`/`debitor`） |
| `zzkunnr` / `zzkunnr_t` | 母客户编码/名称（ETL 兜底链：自带值 → WBS 项目厂商 → 客户销售范围维表母客户） |
| `cust_refer` | 客户参考（SAP 参考客户；与母客户兜底链的关系待确认，勿混用） |
| `salesorg` / `distr_chan` | 销售组织 / 渠道（SAP 原始 VTWEG） |
| `sales_group_code` / `sales_group_code_wbs` / `sale_group` | 销售组（主档）/（主档+WBS 兜底）/（实际）三套 |
| `region_code/name`、`cntry_region_code/name` | 地区（省份）/ 国家 |
| `export_country` | 出口国（出口业务专用，内销行为空） |
| `factory_code` / `inv_location` | 工厂 / 库存地点（可关联 MD 域工厂主档） |
| `productionregion` | 产区（值域待实测） |
| `integrate_channel` / `integrate_channel2` | 整合渠道层级1 / 整合品类（同业绩域渠道维度口径） |
| `category_code` / `category_name` | 品类（ETL 兜底物料主档） |

### 3. 单据关联（下钻用）

| 字段 | 说明 |
|---|---|
| `vbeln` / `posnr` | 销售订单号 / 行项目 |
| `vbeln_vf` / `posnr_vf` | 开票抬头 / 开票项目（"发票积分"得名于此） |
| `ordertype` / `purchase_order_type` | 订单类型 / 采购订单类型（过滤单据类别用，值域待实测） |
| `wbsid` / `wbs_description` | WBS 号 / 描述（工程项目） |
| `material` / `material_text` | 物料编码 / 描述（双命名：他表或叫 `material_num`） |
| `kwmeng` / `orderarea` / `salesunit` | 订单数量 / 面积 / 单位 —— **varchar，聚合前必须 CAST** |
| `netprice2` | 净价2（varchar） |
| `engineeringchange` / `aspricingdate` | 工程变更 / 定价日期（工程、定价类积分场景） |
| `ziswx` / `zsfqc` | 自制外协 / 是否清仓（物料标志位，值域待实测） |
| `points_text` | 文本 —— 上游 `dwr_cre_integral_change_f.text` 为 varchar(1800)，本表截断为 300，**存在截断风险，勿用于长文本分析** |
| `points_distribution` | 分配（对应上游 `integral_distribute_desc`） |
| `policyname` | 政策名称 |
| `rc_account` / `rc_account_description` | 总账科目 / 描述 |

### 4. 积分本体（口径字段，四套编码体系）

| 字段 | 说明 |
|---|---|
| `pointsvalue` | **积分金额（全表唯一 numeric 字段）**，带符号：计提 + / 使用 − |
| `zjflx` / `zjfms` | 积分类型 / 描述（见编码表一） |
| `zjfbglx` / `zjfbglxms` | 积分变更类型 / 描述（见编码表二，业务生命周期骨架） |
| `pointscategorycode` / `pointscategory` | 管理口径积分分类（编码表三） |
| `pointsbusinessscopecode` / `usepointsbusinessscope` | 管理口径使用积分业务范围（01 常规/02 工程/03 宣传资料） |
| `score_classification` | 审计口径切分：`使用积分` / `政策内` / `政策外`（编码表四，**下游利润表口径的切分键**） |
| `bxjf_bus_area_code` / `bxjf_bus_area_name` | 报销积分业务范围：`A 授予积分` / `B 使用积分`（ETL 由 zjflx+zjfbglx 组合推导） |
| `infoprov` | 来源标记：`ZJFTAB2`(积分凭证) / `INVOICE_CONDITIONAL`(发票条件) / `Accounting`(会计凭证) / `SAP调整值` —— **约半数行为 NULL，不能作唯一来源过滤** |
| `del_flag` | `N` 正常；SAP调整值分支为 NULL（约 1.5 万行）—— `del_flag='N'` 过滤会漏掉它们 |

> **余额语义澄清**：词典「积分业务」中的「原积分」（变动前余额）**不在本表** —— 本表是纯流水表，无任何余额字段。余额/原积分需按 `pointsvalue` 按客户累计推导，或取上游 `dwr_cre_integral_change_f` 的 `old_integral_bal` / `new_integral_bal`（变动前/后余额快照，仅该表有；**无 `integral_bal` 字段**，实测 information_schema）。

> 计提/使用/结转的**分组公式属业务口径，标「待业务确认」**：当前可靠切分是 ETL 已固化的 `score_classification`（审计口径）与 `pointscategory`（管理口径），见 metrics.md。

## 编码表一：积分类型 zjflx（实测值域）

| 码 | 含义 | 码 | 含义 |
|---|---|---|---|
| 00 | 常规积分 | 08 | 广告积分-区域 |
| 01 | 月度积分 | 09 | 广告积分-大区 |
| 02 | 季度积分 | 10 | 冻结/解冻积分 |
| 03 | 年度积分 | 11 | 应退客户款 |
| 04 | 高端积分 | 12 | 代收代垫款 |
| 05 | 装修积分 | 13 | 工程积分 |
| 06 | 宣传积分 | 14 | 应退信贷 |
| 07 | 广告积分-经销 | NULL | SAP调整值分支（月均约 3~4 千行） |

## 编码表二：积分变更类型 zjfbglx（台账生命周期）

| 码 | 含义 | 方向 |
|---|---|---|
| A0 | 期初导入 | 期初 |
| A2 | 系统计提积分 | 计提 + |
| ZA | 手工计提积分 | 计提 +（可负，冲调） |
| ZB | 积分(计业绩) | 计提 + |
| B1 | 销售使用积分 | 使用 − |
| C2 | 销售使用积分调整 | 使用 − |
| C3 | 实时积分结转调整 | 结转 |
| ZC | 现金结转 | 结转 − |
| ZD | 结转报销 | 结转 − |
| ZH | 一次性装修报销 | 结转 |
| ZE / ZJ | 同线组 / 不同线组积分转移 | 转移（一正一负对冲） |
| ZF | 政策外报销 | 报销 |
| ZG | 手工调整计提-不计入当期利润 | 调整 |
| ZK | 客户撤销 | 撤销 − |
| Z1 | 手工调增 | 调整 |

> 计提/使用/结转的**分组公式属业务口径，标「待业务确认」**：当前可靠切分是 ETL 已固化的 `score_classification`（审计口径）与 `pointscategory`（管理口径），见 metrics.md。

## 编码表三：管理口径积分分类 pointscategory

| 码 | 分类 | 覆盖 |
|---|---|---|
| A | 预提积分-手工 | zjfbglx 为 Z 开头（剔除 ZC/ZJ/ZE/ZG） |
| B | 预提积分-系统预提 | 发票条件来源的系统计提（主体，约 1,270 万行） |
| C | 使用积分 | zjflx 00/13/06 且 zjfbglx B1/C2，细分业务范围 01 常规/02 工程/03 宣传资料 |
| D | 计提服务费 | — |

## 编码表四：审计口径 score_classification（下游利润表切分键）

| 值 | 含义 | 金额取法 |
|---|---|---|
| 使用积分 | 销售使用/调整 | `-pointsvalue`（还原为正数） |
| 政策内 | zjflx 00/13 且非 ZF | `pointsvalue` |
| 政策外 | zjflx 00/13 且 zjfbglx=ZF | `pointsvalue` |
| NULL | 不在审计切分内（应退类/代垫/转移等） | — |

## 关联维度表

| 维度 | 表 | 关联键 |
|---|---|---|
| 客户名称/分组/销售范围 | `dwrdim.dwr_dim_cust_general_d` / `dwr_dim_cust_sales_area_d2` | `customer = cust_num`（+salesorg+distr_chan，end_date='4712-12-31' AND del_flag='N'） |
| 物料品类 | `dwimd.dwi_md_data_material_general_t` | `material = material_num` |
| WBS 项目 | `dwrdim.dwr_dim_wbs_basis_info_f`（WBS 层级+项目属性：项目类型/负责人/客户/销售组织/利润中心，134 万行） | `wbsid = wbs_level3`（2026-09 键命中 2,845/3,030 = 93.9%，行数不膨胀；`wbs_level3` 近唯一）；**勿用** `substr(wbsid,1,10) = wbs_top_level` —— 项目定义粒度 1:N 实测膨胀 60.9 倍（465,604/7,648 行）。原 `sdi.sdi_proj_1001` 因 sdi schema 在 DWS 不存在而不可用，2026-11-13 实证替换 |
| 组织树 | sources-of-truth org-hierarchy | 销售组织码挂 node 层级（同其他域） |

### 同域事实表与勾稽

| 表 | 关系 | 说明 |
|---|---|---|
| `dwrfin.dwr_gl_points_voucher_f`（861,025 行，实测） | 积分凭证，**会计勾稽表** | 积分明细记业务变动、积分凭证记会计处理，两者需勾稽；同构字段集，但 **pointsvalue 是 varchar(300)，聚合前必须 CAST**；勾稽键 `comp_code + zjfggbh + zjfggit` |
| `dwrfin.dwr_cre_integral_change_f`（2,975.4 万行，实测 COUNT） | CRM 积分流水（源对齐，DWI→DWR 月分区搬运） | 字段对应：`zjfggbh↔integral_change_num`、`zjfggit↔line_item`、`calmonth↔integral_month`、`zjflx↔integral_type`、`zjfbglx↔integral_change_type`、`pointsvalue↔integral_change_amt`、`reconciliationdate/flag↔square_up_num/flag`、`points_text↔text`（该表 varchar(1800)，本表截断为 300）、`points_distribution↔integral_distribute_desc`；余额快照 `old_integral_bal`/`new_integral_bal`（numeric）仅此表有，**无 `integral_bal` 字段** |
| `dwrfin.dwr_gl_pointsdetail_collect_f`（879,285 行，实测，**行存**） | 汇总表 | 客户×月×积分类型×变更类型×管理口径轻量汇总（无物料/单据维度），纯结构查询可用 |
| `dwrfin.dwrfin_cost_sales_gross_profit_d`（292 万行，列存） | 利润日表（**不直接读本表**） | `use_point`/`accrual_point_system`/`accrual_point_manual`/`budget_use_point`/`budget_accrual_point`/`last_year_use_point` 等积分指标列的 ETL 取数源是 `DM_ZZT_XSSR_T` 与 `DM_RPT_GROUP_ACHIEVEMENT_AMB_T`（业绩/达成表族），与本表是**同业务不同链路**——不可拿本表直接对其对账（间接勾稽关系待确认） |

> **装载结构（infoprov 时间分布实测 2026-11-12）**：主表 2024-01 起由凭证三表 UNION 增量装载（INVOICE_CONDITIONAL 1,379 万行 / ZJFTAB2 54.6 万 / Accounting 12.0 万 / SAP调整值 1.5 万，calmonth 均 ≥2023-12）；**2024-01 之前的 1,520.5 万行历史段为一次性装载、infoprov 全 NULL**（max calmonth=2023-12）——主表 2,967.6 万 vs 凭证三表合计约 1,308 万的差额由此而来，并非数据缺失。cre 流水 2,975.4 万比主表**多** 7.8 万行（部分分支未入主表），跨表对账时必须先区分装载段（2024-01 前 cre/历史段 ↔ 之后凭证增量段）。

## 敏感列红线（2026-11-13 DWS 实测）

- `dwr_dim_cust_general_d`：`phone_1`/`phone_2`/`legal_person_name`/`address_name`/`payer`/`ctr_object_person_name`
- `dwr_dim_cust_sales_area_d2`：`ctr_object_person_name`
- `dwr_dim_wbs_basis_info_f`：`sales_emp_name`（实测 644 个员工姓名）、`lifnr_name`（232 个供应商名）；`owner` 当前仅 1 个值、`owner_desc` 全空
- 积分问题禁止 `SELECT *`；只取业务必要的客户编码/名称/分组与 WBS 项目属性，非必要不输出个人姓名/联系方式。

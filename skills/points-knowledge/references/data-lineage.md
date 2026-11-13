# 发票积分 — 血缘与表关联

## 链路总览（依据 huaweiclaude ETL 导出实证，2026-11-12）

```
SAP 积分更改记录 ZJFTAB2 ─→ DWR_GL_POINTS_VOUCHER_F（积分凭证中间层）──┐ infoprov='ZJFTAB2'
发票条件凭证 ─→ DWR_GL_INVOICE_VOUCHER_F ─────────────────────────────┤ 'INVOICE_CONDITIONAL'
会计凭证 ─→ DWR_GL_ACCOUNTING_VOUCHER_F ──────────────────────────────┼─→ DWR_GL_POINTSDETAIL_F（本域主表）
SAP 调整值数据（预提积分≠0）dwr_sap_adjust_data_t ────────────────────┘ 'SAP调整值'
                                                                       │
                                       ┌───────────────────────────────┤
                                       ├→ DWR_GL_POINTSDETAIL_COLLECT_F（按客户×月×类型×管理口径汇总，无物料/单据维度）
                                       └→ 上市口径利润汇总（DM 层）—— 使用积分/本期报销/本期积分(政策外) 三指标
```

- 主表 ETL 同时做维度补全：物料主档（品类/物料名兜底）、WBS 项目（母客户兜底）、客户销售范围维表（母客户兜底）、客户主档（母客户名/国家/地区）
- **装载结构（infoprov 时间分布实测 2026-11-12）**：2024-01 起走凭证三表 UNION 增量（INVOICE_CONDITIONAL/ZJFTAB2/Accounting/SAP调整值）；2024-01 前 1,520.5 万行历史段一次性装载、infoprov 全 NULL。凭证三表合计约 1,308 万 ≠ 主表 2,967.6 万，差额即历史段，**并非数据缺失**
- 另有 CRM 积分流水支线：`dwifin.DWI_CRE_INTEGRAL_CHANGE_T → dwrfin.dwr_cre_integral_change_f`（2,975.4 万行，月分区搬运），比主表多 7.8 万行；余额快照 `old_integral_bal`/`new_integral_bal` 与 1800 位长文本仅此表有（字段映射见 points-detail.md「同域事实表与勾稽」）
- `bxjf_bus_area`（报销积分业务范围）与 `zzkunnr`（母客户）均为 ETL 推导/兜底字段，非源系统原生
- 凭证中间层（VOUCHER_F）的 `pointsvalue = 源表积分更改额 − 冲销额`（该表 pointsvalue 为 varchar，勾稽聚合前 CAST）

## 本域表清单

| 表 | 层 | 粒度 | 用途 |
|---|---|---|---|
| `dwrfin.dwr_gl_pointsdetail_f` | DWR | 凭证行项目 | **主表**，一切积分问答默认入口 |
| `dwrfin.dwr_gl_pointsdetail_collect_f` | DWR | 客户×月×类型×管理口径汇总 | 轻量汇总（879,285 行，行存；无单据/物料维度），大数据量纯结构查询可用，默认仍走主表 |
| `dwrfin.dwr_cre_integral_change_f` | DWR | CRM 积分流水 | **上游源对齐表**（2,975.4 万行）：余额快照 old/new_integral_bal、1800 位文本仅此表有；对账时注意比主表多 7.8 万行 |
| `dwrfin.dwr_gl_points_voucher_f` | DWR | 凭证行项目 | 中间层，**不直接查**（主表已含其全部行） |

## 关联键

```
detail.customer = dwr_dim_cust_general_d.cust_num（客户名/母客户，end_date='4712-12-31'）
detail.customer + salesorg + distr_chan = dwr_dim_cust_sales_area_d2（客户分组/销售范围）
detail.material = dwi_md_data_material_general_t.material_num（品类）
detail.wbsid = dwr_dim_wbs_basis_info_f.wbs_level3（WBS 项目属性；sdi_proj_1001 在 DWS 不可访问，2026-11-13 实证替换）
```

组织树挂接（销售组织/事业部维度）同其他域：见 `../../sources-of-truth/business-context/org-hierarchy.md`。

## 跨域关系

- **→ sales-performance（业绩域）**：本表是上市口径利润汇总的直接上游；业绩域 mix/ambv2 表的"使用积分/预提积分"指标（`zsyjf`/`zytjf`）是**聚合后的业绩口径**，与本表明细口径的关系：
  - 问"积分对业绩/利润的影响" → 业绩域聚合口径（`0−zsyjf`、`zytjf`）
  - 问"客户/凭证级积分明细、余额、清账" → 本域主表
  - 两口径对账用 metrics.md 第四节公式
- **→ fin-cost（费用域）**：积分报销的**费用科目侧**分析（总账科目 `rc_account`）如需展开，走费用域；本域只答积分台账。

## 备份变体表（禁用）

`dwr_gl_pointsdetail_f_260331_wjh` / `_t` / `_20250501_qyj` / `_20250429_wjh`

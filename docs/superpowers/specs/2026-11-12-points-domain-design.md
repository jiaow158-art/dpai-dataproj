# 发票积分专题域（points）— 设计文档

**日期**：2026-11-12
**状态**：已执行（域归属经用户拍板：新建域）
**数据材料**：`dwrfin.dwr_gl_pointsdetail_f`（业务提供的报表 SELECT）+ `huaweiclaude/` ETL 导出血缘 + 直连 DWS 实测

---

## 0. 背景与决策

业务要求接入发票积分表（29.7M 行台账明细）。四个候选：新建 points 域 / 扩 sales-performance / 扩 ar / 扩 fin-cost。

**决策：新建 points 域**（用户 2026-11-12 拍板）。判定依据：
- 积分语义自成体系（zjflx 15 值 × zjfbglx 16 值 × 管理口径 4 类 × 审计口径 3+1 态四套编码 + 台账生命周期），塞入任何现有域都会显著撑大其 metrics.md 决策树且概念不搭
- 业务问题主体是**客户/凭证级台账**（余额/明细/清账/报销），不是业绩口径（后者现有 mix/ambv2 聚合表已覆盖）
- 路由干净：现有 6 域 description 均不含积分台账关键词；sku-profitability（2026-08-18）已有专题域建域先例

## 1. 数据实证（2026-11-12 直连 DWS）

### 1.1 血缘（huaweiclaude/DWR/FIN/GL + DM/DM_CT ETL 原文）

```
SDI_ZJFTAB2_1001(SAP积分更改记录) → DWR_GL_POINTS_VOUCHER_F ─┐ 'ZJFTAB2'
发票条件凭证 → DWR_GL_INVOICE_VOUCHER_F ─────────────────────┤ 'INVOICE_CONDITIONAL'
会计凭证 → DWR_GL_ACCOUNTING_VOUCHER_F ──────────────────────┼→ DWR_GL_POINTSDETAIL_F
dwr_sap_adjust_data_t(YTJF≠0) ───────────────────────────────┘ 'SAP调整值'
                                                                ├→ DWR_GL_POINTSDETAIL_COLLECT_F
                                                                └→ DM_FI_AMBV2_PROFIT_SUM_LISTED_T（上市口径利润汇总）
```

维度补全：物料主档/WBS 项目/客户销售范围/客户主档（母客户、国家地区均 ETL 兜底字段）。

### 1.2 指标口径（ETL 原逻辑）

- `pointsvalue` 带符号台账（计提+/使用−），**余额=SUM(pointsvalue)**
- 管理口径 pointscategory：A 预提-手工 / B 预提-系统 / C 使用(常规/工程/宣传) / D 计提服务费
- 审计口径 score_classification：使用积分/政策内/政策外（zjfbglx=ZF 且 zjflx∈00,13 → 政策外）
- 上市口径（DM 下游作业原逻辑）：使用积分=`-pointsvalue`；必带 `comp_code<>'Z000'` + 客户范围维表 JOIN 滤 `cust_group<>'Z0'`

### 1.3 关键陷阱（实测，全部写入 knowledge）

1. `budat` 双形态（10 位日期 156 万行 / 19 位时间戳 2,811 万行）→ 一律 `substr(budat,1,10)`
2. 日期三格式：calmonth='YYYY-MM' / period_id_m='YYYYMM' / reconciliationdate='YYYYMMDD'（业务报表模板中 TO_DATE(...,'YYYY-MM-DD') 写法与实库不符）
3. 全表仅 pointsvalue 为 numeric；kwmeng/orderarea/netprice2 是 varchar
4. zjflx/zjfbglx 有 NULL（SAP调整值分支）；infoprov 约半数 NULL；del_flag 有 NULL
5. 备份变体表 4 张（`_wjh/_t/_qyj` 等）
6. 2,968 万行大表红线：必带时间过滤

### 1.4 锚点值（2026-09）

使用积分 −2,091 万（18,681 行）/ 政策内 +1,405 万 / 政策外 +29 万 / 审计外 −295 万；客户余额 TOP 240 万~1,480 万元。

## 2. 域结构

```
skills/points-knowledge/
├── SKILL.md                        # 路由：积分余额/明细/计提/使用/报销/清账/冲销/政策内外
└── references/
    ├── metrics.md                  # 语义层：决策树/口径公式/锚点值/pattern 路由/陷阱
    ├── points-detail.md            # 主表 69 列 + 四套编码值域 + 维度关联
    └── data-lineage.md             # 血缘 + 跨域关系（业绩域聚合口径 ↔ 本域明细口径）
skills/points-analyst/
└── SKILL.md                        # 6 步工作流 + 模式 A-G（余额/结构/使用/趋势/下钻/清账/上市口径）
```

## 3. 跨域关系（双向指针）

- sales-performance `metrics.md`「积分字段（易错）」节 + `ambv2-profit.md` 字段表下：已加「跨域」注——业绩口径聚合（zsyjf/zytjf）留业绩域，台账明细走 points 域
- points 域 data-lineage.md / metrics.md 决策树反向指回业绩域

## 4. 变更清单

| 文件 | 变更 |
|---|---|
| `skills/points-knowledge/SKILL.md` | 新增 |
| `skills/points-knowledge/references/{metrics,points-detail,data-lineage}.md` | 新增 |
| `skills/points-analyst/SKILL.md` | 新增 |
| `skills/sales-performance-knowledge/references/metrics.md` | 积分字段节加跨域注（1 处） |
| `skills/sales-performance-knowledge/references/ambv2-profit.md` | 字段表后加跨域注（1 处） |
| `eval_dataset.json` | 新增 points 域场景（见 eval 变更清单文档）+ meta.domains 加 "points" |

## 5. 遗留待确认（不阻塞）

- zjfbglx 计提/使用/结转的业务分组公式（当前可靠切分 = 管理口径 + 审计口径两套 ETL 固化口径）
- 清账率分母业务定义
- pattern 路由表第五节为实证版，eval 录制后按录制口径回填

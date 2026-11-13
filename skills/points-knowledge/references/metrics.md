# 发票积分 — 语义层（强制首读）

## 一、问题决策树

| 用户问法（典型） | 口径 | 关键字段 |
|---|---|---|
| "某客户/事业部**还剩多少**积分" | **余额 = 累计 SUM(pointsvalue)**（带符号台账，计提+/使用−），截至指定月末 | `calmonth <= 'YYYY-MM'` + `customer`/`zzkunnr`/`comp_code` |
| "本月**计提/获得**多少积分" | 计提侧：管理口径 `pointscategory IN ('A','B')`；或变更类型 `zjfbglx IN ('A2','ZA','ZB')`（分组待业务确认） | `pointscategory` / `zjfbglx` |
| "本月**使用/报销**多少积分" | 审计口径 `score_classification='使用积分'`，金额取 `-SUM(pointsvalue)` 还原为正 | `score_classification` |
| "**政策内/政策外**报销" | `score_classification='政策内' / '政策外'`（政策外 = zjfbglx ZF 且常规/工程积分） | `score_classification` |
| "按**管理口径**分类看积分" | A 预提-手工 / B 预提-系统 / C 使用(常规/工程/宣传资料) / D 计提服务费 | `pointscategory` + `usepointsbusinessscope` |
| "**清账**了多少 / 什么时候清的" | 已清账 `reconciliationflag='A'`；清账日期 `reconciliationdate`（YYYYMMDD，`00000000`=未清） | `reconciliationflag/date` |
| "**冲销**记录" | `offset_mark='X'` | `offset_mark` |
| "某**发票/订单/WBS** 的积分明细" | 凭证级下钻：`vbeln_vf` / `vbeln` / `wbsid` | 单据字段族 |
| "积分**趋势**（月度）" | 按 calmonth 分组的净发生额 SUM(pointsvalue)，或计提/使用分开 | `calmonth` |
| "**上市口径**的积分（进利润表的）" | `comp_code<>'Z000'` + JOIN 客户销售范围维表滤 `cust_group_code<>'Z0'`，再按 score_classification 切分（下游利润汇总的原始逻辑） | 见第四节公式 |
| "使用积分/预提积分**对业绩利润的影响**" | **跨域**：业绩口径聚合（`zsyjf`/`zytjf`）走 sales-performance 域 mix/ambv2 表；本表只答凭证明细与对账 | 跨域指针见 data-lineage.md |

## 二、核心口径公式

```
积分余额（截至 YYYYM 月末） = SUM(pointsvalue)          -- 全历史累计，带符号
本期计提（管理口径）        = SUM(CASE WHEN pointscategory IN ('A','B') THEN pointsvalue END)
本期使用（审计口径，正值）  = -SUM(CASE WHEN score_classification='使用积分' THEN pointsvalue END)
本期报销-政策内            = SUM(CASE WHEN score_classification='政策内' THEN pointsvalue END)
本期报销-政策外            = SUM(CASE WHEN score_classification='政策外' THEN pointsvalue END)
清账率                     = 已清账行数 ÷ 应清账行数（reconciliationflag='A'；业务分母待确认）
```

**锚点值（2026-09 实测，全口径含 Z000）**：使用积分 −2,091 万（18,681 行）；政策内报销 +1,405 万（1,140 行）；政策外 +29 万（2,047 行）；不在审计切分内 −295 万（38.5 万行）。客户余额 TOP 量级 240 万~1,480 万元。

**数量级常识**：单月流水约 40 万行；全表 2,968 万行。

## 三、指标→字段速查

| 指标 | 字段 | 备注 |
|---|---|---|
| 积分金额 | `pointsvalue` | **唯一 numeric**，带符号 |
| 积分类型 | `zjflx`/`zjfms` | 00~14 + NULL，见 points-detail.md 编码表一 |
| 变更类型（生命周期） | `zjfbglx`/`zjfbglxms` | 见编码表二 |
| 管理口径分类 | `pointscategory(code)` | A/B/C/D |
| 审计口径切分 | `score_classification` | 使用积分/政策内/政策外/NULL |
| 母客户 | `zzkunnr`/`zzkunnr_t` | ETL 已兜底补全 |
| 销售组三套 | `sales_group_code`（主档）/ `_wbs`（主档+WBS）/ `sale_group`（实际） | 默认用 `sale_group`（实际） |
| 渠道/品类 | `integrate_channel`/`integrate_channel2`/`category_name` | 同业绩域渠道口径 |

## 四、上市口径公式（下游利润汇总的原始逻辑）

下游利润表口径从本表取三个积分指标，**原逻辑**（ETL 2026-11 实证）：

```sql
SELECT calmonth,
       sales_group_code_wbs AS sales_grp,
       comp_code,
       SUM(CASE WHEN score_classification='使用积分' THEN -COALESCE(pointsvalue,0) ELSE 0 END) AS 使用积分,
       SUM(CASE WHEN score_classification='政策内'  THEN  COALESCE(pointsvalue,0) ELSE 0 END) AS 本期报销,
       SUM(CASE WHEN score_classification='政策外'  THEN  COALESCE(pointsvalue,0) ELSE 0 END) AS 本期积分_政策外
FROM dwrfin.dwr_gl_pointsdetail_f jf
LEFT JOIN dwrdim.dwr_dim_cust_sales_area_d2 l
  ON jf.customer=l.cust_num AND jf.distr_chan=l.distribution_chnl_code AND jf.salesorg=l.sales_org_code
 AND l.end_date='4712-12-31' AND l.del_flag='N'
WHERE jf.comp_code <> 'Z000'
  AND (l.cust_group_code <> 'Z0' OR l.cust_group_code IS NULL)
  AND calmonth BETWEEN :m1 AND :m2
GROUP BY 1,2,3
```

问"上市口径/进利润表的积分"时**必须**带 `comp_code<>'Z000'` 与 cust_group_code 过滤，否则与利润表对不上。

## 五、pattern → 首选表与字段路由

> 本节为**实证版**（2026-11-12 直连 DWS 验证）；eval_dataset 录制 points 场景后按录制口径回填修订（对齐 eval 录制口径是判定标准）。

| pattern | 首选表 | 指标/关键列 | 窗口习惯 |
|---|---|---|---|
| points_balance（客户/组织积分余额 TOP N） | detail 单表 | `SUM(pointsvalue)` 累计；维度 customer/zzkunnr/comp_code/sale_group | `calmonth <= 截至月`，不带下限 |
| points_structure（积分类型/管理口径结构） | detail 单表 | `SUM(pointsvalue)` BY zjfms 或 pointscategory | 单月 `calmonth='YYYY-MM'` 或给定区间 |
| points_usage_audit（使用/报销，审计口径） | detail 单表 | score_classification 切分，使用取负还原 | 单月或给定区间 |
| points_trend（月度净发生趋势） | detail 单表 | `SUM(pointsvalue)` BY calmonth | 给定区间逐月 |
| points_drilldown（发票/订单/WBS 明细） | detail 单表 | vbeln_vf/vbeln/wbsid + pointsvalue 明细行 | 给定单据号，可不带时间 |
| points_recon（清账/冲销进度） | detail 单表 | reconciliationflag='A'、reconciliationdate、offset_mark='X' | 给定区间 |
| points_listed（上市口径三指标） | detail × cust_sales_area_d2 | 第四节公式 | 给定区间 |

**通用规则**：必带时间过滤（除单据号下钻）；分类汇总遇 zjflx/zjfbglx NULL 行（SAP调整值分支）时 `COALESCE(zjfms,'未分类')` 呈现并在回答声明；不用 `MAX(calmonth)` 探测最新月（当月部分装载）。

## 六、陷阱清单（全部实测 2026-11-12）

1. **budat 双形态**：10 位 `YYYY-MM-DD` 与 19 位时间戳混存 —— 按日/按月切必须 `substr(budat,1,10)`，直接 `budat='2026-09-05'` 会漏掉 95% 的行。
2. **日期格式三处不同**：`calmonth='YYYY-MM'`（带横线）/ `period_id_m='YYYYMM'`（无横线）/ `reconciliationdate='YYYYMMDD'`（8 位，`00000000`=未清）。业务报表模板中 `TO_DATE(reconciliationdate,'YYYY-MM-DD')` 的写法与实库不符，**以 YYYYMMDD 为准**。
3. **全表只有 pointsvalue 是 numeric**：kwmeng/orderarea/netprice2 均 varchar，聚合前 CAST，否则报错或静默串接。
4. **zjflx/zjfbglx 有 NULL**（月均 3~4 千行，SAP调整值分支）：GROUP BY 会单列一行 NULL，呈现时合并为「未分类」并声明。
5. **infoprov 约半数为 NULL，且 NULL 有明确结构**（实测）：2024-01 前历史段 1,520.5 万行一次性装载、全 NULL（calmonth ≤2023-12）；2024-01 起增量才有来源标记。按来源切分只对 2024-01 后有意义，且不能作唯一过滤条件。
6. **comp_code='Z000' 跨公司调整行**：问总量未必须排除，**问上市口径必须排除**（第四节）；客户分组 `cust_group_code='Z0'` 同理。
7. **del_flag 有 NULL**（SAP调整值分支约 1.5 万行）：`del_flag='N'` 会漏；默认不过滤该字段。
8. **备份变体表 4 张禁用**（`_wjh/_t/_qyj` 等后缀）。
9. **calmonth 脏值 `0000-00`** 仅 1 行：字符串区间过滤天然排除，无需特判。
10. **大表红线**：2,968 万行，任何查询必带时间过滤或单据号等值条件。
11. **空串即 NULL（DWS Oracle 兼容语义）**：`wbsid <> ''` 之类空串比较恒为假（'' 按 NULL 处理），判非空一律 `IS NOT NULL`；`NULLIF(col,'')` 同理无效。实测 2026-09：`wbsid <> ''` 过滤 0 行，`wbsid IS NOT NULL` 得 7,648 行。
12. **禁止无过滤 COUNT/全表探索**：积分主表 COUNT 必须带 `calmonth`/`budat`/`period_id_m` 或单据号（`vbeln`/`vbeln_vf`/`zjfggbh`）；Guard/MCP 会直接拒绝无过滤 COUNT。

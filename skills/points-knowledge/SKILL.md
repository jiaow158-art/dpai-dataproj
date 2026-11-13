---
name: points-knowledge
description: 发票积分领域数据知识库。当用户询问积分余额、积分明细、积分计提、使用积分、报销积分、积分清账、冲销、政策内外、客户/工程积分、积分类型等积分台账相关问题时自动激活。覆盖 DWRFIN 层积分数据模型。
---

# 发票积分领域 — 数据知识路由

## 作用

本 Skill 是路由层。积分是**带符号台账**（期初→计提→使用→结转→清账→冲销），根据问题类型引导到对应参考文档获取准确的表结构、口径公式、过滤条件和查询模式。

## 可用的参考文档

### 语义层（必须首先查阅）

| 文档 | 说明 |
|---|---|
| **[metrics.md](references/metrics.md)** | **🔴 强制优先阅读**。问题决策树（余额/计提/使用/清账/上市口径）、口径公式与锚点值、pattern→表路由、全部已知陷阱 |

### 表级参考文档

| 文档 | 对应问题类型 |
|---|---|
| [points-detail.md](references/points-detail.md) | 主表结构：69 列说明、四套编码值域（积分类型/变更类型/管理口径/审计口径）、关联维度表 |
| [data-lineage.md](references/data-lineage.md) | 数据血缘（SAP 源→凭证中间层→明细主表→汇总/上市口径利润）、跨域关系（业绩域积分聚合口径） |

## 跨域共享参考

| 文档 | 说明 |
|---|---|
| [组织架构](../../sources-of-truth/business-context/org-hierarchy.md) | 销售组织树、事业部枚举值，与积分表的关联方式 |
| [客户主数据](../../sources-of-truth/business-context/customer-master.md) | 客户名称/分组/母客户 |

## 边界（问这些不归本域）

- "使用积分/预提积分对业绩利润的影响" → sales-performance 域（聚合口径 `zsyjf`/`zytjf`）
- 积分报销的**费用科目**分析（科目余额/费用中心） → fin-cost 域
- 本域只答积分台账本身（余额/明细/计提/使用/清账/冲销/政策内外）

## 使用方式

1. **首先**加载 [metrics.md](references/metrics.md)，用问题决策树定位口径与 pattern
2. 需要字段/值域细节时加载 [points-detail.md](references/points-detail.md)
3. 跨域对账时加载 [data-lineage.md](references/data-lineage.md)

## 标准全局过滤条件

- 大表红线：2,968 万行，**任何查询必带时间过滤**（单据号等值下钻除外）
- 上市口径必带 `comp_code<>'Z000'` + 客户分组过滤（见 metrics.md 第四节）
- 默认**不**过滤 del_flag / infoprov（均有 NULL 语义，见 metrics.md 陷阱 5/7）

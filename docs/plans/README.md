# 开发方案导读

`docs/plans/` 顶层现在只保留两类内容：

1. 当前仍然稳定有效的协议
2. 少量确实需要长期固定路径的协议说明

## 当前优先阅读

| 文档 | 类型 | 什么时候看 |
| --- | --- | --- |
| [`统一决策对象协议.md`](./统一决策对象协议.md) | 稳定协议 | 涉及统一决策 summary / details 输出时 |
| [`策略工厂策略对象协议.md`](./策略工厂策略对象协议.md) | 稳定协议 | 涉及 candidate / submission payload、策略对象建模时 |

## 历史策略工厂方案去哪看

原先平铺在本目录下的历史策略工厂方案、专题审计与分期规划，已统一迁入：

- [`../archive/strategy-factory/README.md`](../archive/strategy-factory/README.md)

## 策略工厂当前入口

如果你的任务是当前策略工厂开发，请优先看：

1. [`../../策略工厂/README.md`](../../策略工厂/README.md)
2. [`../../策略工厂/策略工厂整改详细清单.md`](../../策略工厂/策略工厂整改详细清单.md)
3. [`策略工厂策略对象协议.md`](./策略工厂策略对象协议.md)

## 已归档材料

更明确的历史方案和研究蓝图请看：

- [`../archive/strategy-factory/README.md`](../archive/strategy-factory/README.md)
- [`archive/README.md`](./archive/README.md)

## 使用原则

1. 改接口或对象结构时，先看协议。
2. 做当前策略工厂任务时，先看根目录 `策略工厂/` 导读和整改清单。
3. 需要追溯某个历史判断时，优先去 `docs/archive/strategy-factory/`。

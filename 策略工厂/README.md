# 策略工厂导读

`策略工厂/` 现在只承担“当前导读 + 当前整改主线”两件事，历史方案已经迁出，不再作为默认入口。

## 当前应从哪里开始

1. [`策略工厂整改详细清单.md`](./策略工厂整改详细清单.md)
2. [`../packages/strategy-factory/README.md`](../packages/strategy-factory/README.md)
3. [`../docs/plans/策略工厂策略对象协议.md`](../docs/plans/策略工厂策略对象协议.md)
4. [`../docs/plans/统一决策对象协议.md`](../docs/plans/统一决策对象协议.md)

## 当前代码主线

### 主实现

- `packages/strategy-factory/src/strategy_factory/`

### MCP 兼容层与入口

- `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory/`
- `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py`

### BFF / Web 消费面

- `apps/bff/src/strategy/`
- `apps/web/app/strategy-market/`

## 当前文档分层

### 当前入口

- [`README.md`](./README.md)
- [`策略工厂整改详细清单.md`](./策略工厂整改详细清单.md)

### 当前稳定协议

- [`../docs/plans/策略工厂策略对象协议.md`](../docs/plans/策略工厂策略对象协议.md)
- [`../docs/plans/统一决策对象协议.md`](../docs/plans/统一决策对象协议.md)

### 历史参考

- [`../docs/archive/strategy-factory/README.md`](../docs/archive/strategy-factory/README.md)
- [`../docs/archive/strategy-factory/root-2026-04/README.md`](../docs/archive/strategy-factory/root-2026-04/README.md)

历史分析、阶段方案、研究蓝图和专题优化文档都已迁入统一归档目录，只保留背景价值，不再作为当前执行入口。

## 已完成的文档整理动作

- 根目录 dated 方案已迁入 `docs/archive/root/`
- 因子挖掘专题长文已迁入 `docs/archive/factor-mining/`
- 历史策略工厂方案与研究长文已迁入 `docs/archive/strategy-factory/`
- 2026-04 曾回流到根目录的策略工厂专题文档已再次归档到 `docs/archive/strategy-factory/root-2026-04/`
- 当前策略工厂入口统一收敛到本目录和 `packages/strategy-factory`

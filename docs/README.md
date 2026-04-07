# AIASK 文档导读

`docs/` 现在只承担两件事：

1. 给当前代码提供可靠入口
2. 把历史材料从主阅读路径里隔离出去

## 先看哪几份

| 场景 | 推荐顺序 | 说明 |
| --- | --- | --- |
| 第一次进入仓库 | [`../README.md`](../README.md) -> [`MCP_CONFIG_GUIDE.md`](./MCP_CONFIG_GUIDE.md) -> [`AGENTS.md`](./AGENTS.md) | 先建立项目边界、启动方式和协作约束 |
| MCP 接入 / 排障 | [`MCP_CONFIG_GUIDE.md`](./MCP_CONFIG_GUIDE.md) -> [`../packages/akshare-mcp/README.md`](../packages/akshare-mcp/README.md) -> [`171工具全量对话式深度测试任务.md`](./171工具全量对话式深度测试任务.md) | 先接入，再看服务面，再看运行时矩阵 |
| Web / BFF 开发 | [`../README.md`](../README.md) -> [`../apps/web/app/`](../apps/web/app/) -> [`../apps/bff/src/`](../apps/bff/src/) | 当前页面与接口行为以源码为准 |
| 策略工厂开发 | [`../策略工厂/README.md`](../策略工厂/README.md) -> [`../策略工厂/策略工厂整改详细清单.md`](../策略工厂/策略工厂整改详细清单.md) -> [`plans/策略工厂策略对象协议.md`](./plans/策略工厂策略对象协议.md) | 当前入口以根目录策略工厂导读和整改清单为主 |

## 当前有效入口

### 运行与协作

- [`AGENTS.md`](./AGENTS.md)
- [`MCP_CONFIG_GUIDE.md`](./MCP_CONFIG_GUIDE.md)
- [`DEMO.md`](./DEMO.md)

### 稳定协议

- [`plans/统一决策对象协议.md`](./plans/统一决策对象协议.md)
- [`plans/策略工厂策略对象协议.md`](./plans/策略工厂策略对象协议.md)

### 运行时基线

- [`171工具全量对话式深度测试任务.md`](./171工具全量对话式深度测试任务.md)
- [`../packages/akshare-mcp/MCP_MANAGER_CONTRACT.md`](../packages/akshare-mcp/MCP_MANAGER_CONTRACT.md)
- [`../packages/akshare-mcp/docs/metrics-contract.md`](../packages/akshare-mcp/docs/metrics-contract.md)

### 历史与归档

- [`archive/README.md`](./archive/README.md)
- [`archive/strategy-factory/README.md`](./archive/strategy-factory/README.md)
- [`plans/archive/README.md`](./plans/archive/README.md)

## 不再作为主入口的材料

以下内容仍保留，但默认不应当成“现行开发入口”：

- 已迁入 `docs/archive/strategy-factory/` 的历史策略工厂实施方案、阶段专题和研究蓝图
- `docs/archive/` 下的带日期专项审计、阶段修复记录、根目录迁入材料
- `tests/` 目录中的 legacy 报告与一次性测试说明

## 使用原则

1. 需要改代码时，优先看源码，再回看协议和导读。
2. 看到“历史方案”“校准说明”“某日审计”这类文档时，默认先把它当时点材料。
3. 当前入口失效时，优先修导读和 README，不要再往根目录平铺新长文。
4. 新增文档前先看 [`文档维护规范.md`](./文档维护规范.md)。

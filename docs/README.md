# AIASK 文档导读

`docs/` 现在按“先导读，再选文档”的方式组织，避免开发同学一上来就掉进历史方案和研究蓝图里。

## 先看哪几份

| 场景 | 推荐阅读顺序 | 说明 |
| --- | --- | --- |
| 新同学首次进入项目 | [`../README.md`](../README.md) -> [`MCP_CONFIG_GUIDE.md`](./MCP_CONFIG_GUIDE.md) -> [`AGENTS.md`](./AGENTS.md) -> [`plans/README.md`](./plans/README.md) | 先建立项目边界、启动方式和文档地图 |
| MCP / 工具链接入 | [`MCP_CONFIG_GUIDE.md`](./MCP_CONFIG_GUIDE.md) -> [`AGENTS.md`](./AGENTS.md) -> [`171工具全量对话式深度测试任务.md`](./171工具全量对话式深度测试任务.md) | 先看接入，再看执行规范，最后看运行时覆盖基线 |
| Web / BFF 开发 | [`plans/README.md`](./plans/README.md) -> [`../apps/bff/src/`](../apps/bff/src/) / [`../apps/web/app/`](../apps/web/app/) -> [`plans/archive/README.md`](./plans/archive/README.md) | 当前 `docs/` 内没有完整的现行 Web/BFF 实施手册；接口与页面行为应优先以源码为准，历史方案只补背景 |
| 策略工厂相关开发 | [`../策略工厂/README.md`](../策略工厂/README.md) -> [`../策略工厂/策略工厂整改详细清单.md`](../策略工厂/策略工厂整改详细清单.md) -> [`plans/策略工厂重构方案.md`](./plans/策略工厂重构方案.md) -> [`plans/策略工厂策略对象协议.md`](./plans/策略工厂策略对象协议.md) | 现行入口以根目录文档集和重构方案为主；`策略工厂方案.md` 更适合作为历史实施参考 |

## 目录分层

### 1. 运行与协作入口

- [`AGENTS.md`](./AGENTS.md)：项目级代理执行规范
- [`AGENT.MD`](./AGENT.MD)：兼容入口，指向 `AGENTS.md`
- [`MCP_CONFIG_GUIDE.md`](./MCP_CONFIG_GUIDE.md)：MCP 启动与配置指南
- [`DEMO.md`](./DEMO.md)：功能演示与对话样例

### 2. 稳定参考

- [`plans/统一决策对象协议.md`](./plans/统一决策对象协议.md)：统一决策对象契约
- [`plans/策略工厂策略对象协议.md`](./plans/策略工厂策略对象协议.md)：策略对象协议
- [`strategy-factory-p0-inventory.md`](./strategy-factory-p0-inventory.md)：策略工厂 P0 能力盘点

### 3. 当前实施文档

- [`plans/README.md`](./plans/README.md)：`plans/` 入口与阅读顺序
- [`plans/策略工厂重构方案.md`](./plans/策略工厂重构方案.md)：策略工厂重构路径
- [`plans/策略工厂策略对象协议.md`](./plans/策略工厂策略对象协议.md)：策略对象协议
- [`plans/统一决策对象协议.md`](./plans/统一决策对象协议.md)：统一决策输出协议

### 4. 历史方案与研究材料

- [`plans/archive/README.md`](./plans/archive/README.md)：已归档方案总览
- [`plans/策略工厂方案.md`](./plans/策略工厂方案.md)：历史实施方案与能力盘点参考
- [`plans/策略超市集成可行性分析报告.md`](./plans/策略超市集成可行性分析报告.md)：历史代码审计，保留原路径供策略工厂文档引用
- [`plans/策略超市五期开发方案.md`](./plans/策略超市五期开发方案.md)：历史分期规划，保留原路径供策略工厂文档引用

### 5. 审计与资源

- [`a11y-audit.md`](./a11y-audit.md)：前端可访问性审计
- [`171工具全量对话式深度测试任务.md`](./171工具全量对话式深度测试任务.md)：工具覆盖矩阵，部分脚本依赖其路径
- [`frontend-admin-audit.json`](./frontend-admin-audit.json)：后台页面审计结果
- [`screenshots/`](./screenshots/)：静态截图资源，不建议作为阅读入口
- [`../apps/bff/src/`](../apps/bff/src/)：当前 BFF 接口与服务实现
- [`../apps/web/app/`](../apps/web/app/)：当前 Web 页面与路由入口

## 使用原则

1. 先看导读，再看专题文档，不要直接从最长的方案开始读。
2. 凡是带“校准说明”“历史方案”“研究蓝图”的文档，默认都不是当前仓库事实快照。
3. 需要执行开发任务时，优先找“协议”和“当前实施文档”；历史材料只用于补背景、找证据、看演进脉络。
4. 新增文档前先看 [`文档维护规范.md`](./文档维护规范.md)，避免再次把 `docs/` 堆成平铺仓库。

## 本轮整理结果

- 新增统一入口：`docs/README.md`
- 为 `plans/` 增加导读和归档分层
- 将明确属于历史方案/研究蓝图且没有现有引用依赖的材料移动到 `docs/plans/archive/`
- 保留策略工厂相关文档原路径，避免影响根目录 `策略工厂/` 文档集的引用

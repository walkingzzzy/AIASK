# 策略工厂方案文档集

本目录用于沉淀“策略工厂”相关方案文档，但不同文档的定位并不相同。

## 文档分层

- **研究蓝图**：`策略工厂系统设计与实现.md`
  - 定位：研究报告 / 理论参考
  - 特征：包含事件溯源、完整模拟盘孵化、pgvector/HNSW、LLM/RL 生成等超前方案
  - 使用方式：用于理解长期方向，不作为当前仓库的实施承诺

- **落地方案**：`01` ~ `05`
  - 定位：基于当前仓库能力整理出的**现状说明 + 缺口分析 + 分期演进建议**
  - 使用方式：用于排期、评审和后续增量实施
  - 重要约束：文档中的“建议新增 / 中期演进 / 远期规划”均不代表仓库已实现

## 场景路由（按角色选读）

| 你的角色 | 推荐阅读 | 目的 |
|:---------|:---------|:-----|
| **排期评审 / PM** | `README.md` → `01` → `03` 第 4 节（排期顺序） | 了解当前能力边界与分期优先级 |
| **开发实施** | `README.md` → `docs/plans/策略工厂方案.md`（核心实施文档）→ `02`（接口契约）→ `04`（状态机） | 获取代码级实现细节与验收标准 |
| **技术审查 / 架构评审** | `README.md` → `docs/plans/策略超市集成可行性分析报告.md`（代码级审计）→ `01` → `策略工厂系统设计与实现.md`（研究蓝图） | 评估系统成熟度与技术风险 |
| **长期规划** | `策略工厂系统设计与实现.md` → `docs/plans/策略超市五期开发方案.md` | 理解愿景方向与分期路线 |

## 关联文档（docs/plans/ 下）

| 文档 | 定位 | 与本目录文档的关系 |
|:-----|:-----|:-------------------|
| `docs/plans/策略工厂方案.md` | 实施方案（含完整代码） | 01-04 的开发实施补充，含 P0 修复、数据信号映射、新增策略算法、每日流程等 |
| `docs/plans/策略超市集成可行性分析报告.md` | 代码级审计报告 | 01 第 4 节引用的缺陷来源，含 12 个代码缺陷详细分析 |
| `docs/plans/策略超市五期开发方案.md` | 五期分期规划 | 范围超出策略工厂，涵盖 UI/WebSocket/KYC/NLP 等更广议题 |

## 推荐阅读顺序

1. `README.md`：先明确文档分层和使用边界
2. `01-系统架构设计文档.md`：看当前架构基线与演进原则
3. `02-接口定义与数据模型.md`：看已实现接口、运行时对象与草案模型
4. `03-模块功能方案.md`：看各模块现状、短期、中期、远期路径
5. `04-策略生命周期管理流程图.md`：看当前状态机和建议演进流程
6. `05-向量设计方案.md`：看当前向量接线边界与后续演进
7. `策略工厂系统设计与实现.md`：作为研究蓝图补充阅读

## 当前代码基线

| 层级 | 路径 | 说明 |
|:-----|:-----|:-----|
| MCP 工厂 | `packages/akshare-mcp/src/akshare_mcp/services/strategy_factory.py` | 数据采集、规则生成、AI 候选接入、回测筛选、参数+向量复筛、提交、淘汰、调度 |
| MCP 生命周期 | `packages/akshare-mcp/src/akshare_mcp/tools/managers/strategy_manager.py` | 状态转换、质量门禁、生命周期扫描、审查报告、事件流、工厂运行态 |
| MCP 验证 | `packages/akshare-mcp/src/akshare_mcp/services/validation.py` | Walk-Forward / Purged K-Fold / Bootstrap |
| MCP AI 生成 | `packages/akshare-mcp/src/akshare_mcp/services/strategy_autonomy.py` | 规则候选、LLM 代理候选、参数演化、实验记录、任务运行记录 |
| MCP 向量检索 | `packages/akshare-mcp/src/akshare_mcp/services/vector_search.py` | 向量检索基础能力，已被 `Deduplicator` 用于可疑候选复筛 |
| MCP 向量平台 | `packages/akshare-mcp/src/akshare_mcp/services/vector_platform.py` | 构建策略画像、登记索引、支持相似画像查询 |
| MCP 孵化 | `packages/akshare-mcp/src/akshare_mcp/services/incubation.py` | 孵化账户绑定、信号转模拟订单、孵化指标记录与决策输出 |
| MCP 模拟盘 | `packages/akshare-mcp/src/akshare_mcp/services/paper_trading.py` | 模拟交易引擎，被孵化服务部分复用，但尚未形成完整生产级 NAV 晋级闭环 |
| MCP 信号跟踪 | `packages/akshare-mcp/src/akshare_mcp/services/signal_tracker.py` | 信号生成、前向收益验证 |
| MCP 存储 | `packages/akshare-mcp/src/akshare_mcp/storage/timescaledb/strategy.py` | 策略 CRUD、质量报告、状态事件、运行历史、血缘、淘汰日志、快照、孵化与向量画像 |
| BFF | `apps/bff/src/strategy/` | 已暴露工厂状态、运行历史、审查报告、事件流、孵化概览等 REST 接口 |
| Web | `apps/web/app/strategy-market/page.tsx` | 已展示工厂运行态、运行历史详情、失败聚合、趋势与对比视图 |

## 文档使用约束

- 以代码为准，文档不能倒逼事实。
- 任何未在代码中出现的接口、表结构、状态或服务，必须标明为“建议新增”或“草案”。
- 任何涉及 `pgvector/HNSW`、完整 Event Sourcing、真实模拟撮合、LLM/RL 自动生成的描述，默认归入中长期规划，除非后续代码落地。

## 本轮整理目标

本次更新重点不是扩写研究蓝图，而是把文档统一收敛为：

1. **当前已实现能力**
2. **短期可增量补齐项**
3. **中期可演进能力**
4. **远期研究方向**

这样可以避免把“理论方案”误读为“现有系统说明”。

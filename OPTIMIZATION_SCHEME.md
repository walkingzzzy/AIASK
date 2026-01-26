# 量化系统深度研究与优化方案

## 1. 研究摘要：顶级量化公司的核心实践

通过对幻方量化（High-Flyer）、九坤投资、以及国际巨头 Renaissance Technologies、Two Sigma、Citadel 的深度研究，我们总结出以下核心技术实践：

### 1.1 技术架构与算力
*   **超级计算集群**：幻方量化投入巨资构建“萤火二号”超算中心（一万张 A100 GPU），用于深度学习模型训练。Top 级公司均拥有自建的高性能计算（HPC）集群。
*   **研发与生产分离**：严格区分“研究环境”（Python/Jupyter，注重灵活性）与“生产环境”（C++/Rust/FPGA，注重低延迟与稳定性）。
*   **分布式计算**：广泛使用 Kubernetes (k8s)、Ray、Spark 进行分布式因子计算和大规模回测。Two Sigma 更是强调“数据即代码”的工程化管理。

### 1.2 数据体系
*   **极致的数据广度**：除了传统的量价数据，大量引入“另类数据”（新闻情感、供应链、卫星图像等）。
*   **定制化存储**：自研高性能文件系统（如幻方的 3FS、Two Sigma 的 Smooth），优化时序数据的读写吞吐（GB/s 级别）。
*   **实时流处理**：采用 FPGA 或软硬结合的方式处理 Tick 级全量数据，实现纳秒/微秒级响应（Citadel 典型特征）。

### 1.3 策略与风控
*   **AI 原生**：从因子挖掘到交易执行，全流程引入深度学习（Transformer, GNN, LSTM）。
*   **多层风控体系**：包含 事前（Pre-trade）、事中（Real-time）、事后（Post-trade）三层风控。实时监控 VaR（风险价值）、敞口暴露、以及流动性风险。
*   **自动化流水线**：因子的挖掘、测试、上线完全自动化，减少人工干预。

---

## 2. 项目现状分析

我们深入分析了当前项目中的两个核心 MCP 服务：

### 2.1 服务 1: `akshare-mcp` (Python)
*   **定位**：无状态数据网关（Stateless Data Gateway）。
*   **代码实证**：
    *   `data_source.py` 中实现了 Tier 1-4 的降级策略 (Tushare -> AkShare -> eFinance)。
    *   **完全无状态**：`get_kline` 直接返回 list[dict]，未发现任何数据库写入或本地缓存代码 (`cache.py` 仅作内存缓存)。
    *   **脆弱性**：依赖外部 API 的实时响应，若 AkShare 接口变动（常见情况），整个服务将即刻不可用。

### 2.2 服务 2: `mcp-server-compact` (Node.js/TypeScript)
*   **定位**：业务逻辑与分析核心。
*   **代码实证与严重缺陷**：
    *   **虚假的风险模型**：`risk-model.ts` 中的 `calculateBarraRisk` 并非真实回归，而是**硬编码的启发式逻辑**（如：代码以 688 开头直接判定为"科技"行业，因子暴露度直接赋值 1.0 或 0.2）。这在专业量化中是不可接受的。
    *   **低效的回测引擎**：`backtest.ts` 中的 `runBacktest` 使用 `for (let i = 0; i < klines.length; i++)` 显式循环。
    *   **阻塞式参数优化**：`optimizeParameters` 使用递归生成参数组合，然后在单线程中同步运行回测。对于多参数 (Grid Search) 场景，这将导致 Node.js 事件循环长时间阻塞，服务失去响应。
    *   **TA 库性能**：`technical-analysis.ts` 依赖纯 JS 实现的 `technicalindicators` 库，计算 MACD/RSI 的效率远低于 C++ 编写的 TA-Lib。

---

## 3. 对比分析与差距识别

| 维度 | 顶级量化公司 (Top Tier) | 当前项目 (Current) | 差距 (Gap) |
| :--- | :--- | :--- | :--- |
| **计算引擎** | C++/Rust (生产), Python (研究) | Node.js **Loop-based** Backtest | **性能坍塌**：当前 JS 实现是 O(N) 循环，无法向量化。参数优化会导致服务阻塞。 |
| **风险模型** | 真实的因子回归 (Barra) | **Hardcoded Heuristics** | **准确性缺失**：当前的 Risk Model 是“模拟”而非真实计算。 |
| **数据流** | 实时流式处理 + 本地高性能列存 | 按需 API 调用 + 简单缓存 | **数据延迟与稳定性**：缺乏本地 Tick/K线 数据库，严重依赖第三方 API 实时性。 |
| **策略研发** | 离线研究平台 (Notebook) -> 在线部署 | 集成在 Server 中的代码逻辑 | **灵活性差**：策略修改需重启服务，缺乏交互式研究环境。 |
| **AI 应用** | 大规模 GPU 集群训练 + 推理 | 简单的 NLP 解析 | **深度不足**：缺乏真正的预测模型训练管道。 |

---

## 4. 优化建议方案

基于上述差距，我们提出 **"混合侧车架构 (Hybrid Sidecar Architecture)"** 优化方案，保留 MCP 的连接性，但重构计算核心。

### 4.1 架构层面优化：Python 化计算核心
**核心思想**：Node.js 仅负责 MCP 协议交互和编排，将所有“重计算”下沉到 Python（或 Rust）微服务中。

*   **建议 1：计算下沉 (Offload Computation)**
    *   将 `mcp-server-compact` 中的 `backtest.ts`, `factor-calculator.ts`, `risk-model.ts` 的核心逻辑迁移至 Python 服务（可扩展现有的 `akshare-mcp` 或新建 `quant-engine`）。
    *   Node.js 通过 gRPC 或 ZeroMQ 与 Python 引擎通信，仅传递指令和结果，不处理大数据。
    *   **收益**：利用 Pandas/NumPy 实现 100x 以上的回测速度提升，直接接入 PyTorch/Scikit-learn 生态。

*   **建议 2：数据本地化 (Data Localization)**
    *   在 `akshare-mcp` 中引入 **"Data Collector" (数据采集器)** 模式。
    *   **不再是被动响应**，而是主动定时抓取核心标的（如沪深300成分股）的日线/分钟线，写入 TimescaleDB。
    *   业务查询优先读 DB，DB 无数据再 Fallback 到实时 API。

### 4.2 算法与策略改进
*   **向量化回测**：
    *   放弃 TypeScript 的循环式回测，改用 Python 的向量化回测（Vectorized Backtesting）。
*   **引入因子库 (Factor Library)**：
    *   移植 WorldQuant 风格的 101 Alpha 因子计算逻辑到 Python 端。

### 4.3 性能与稳定性
*   **并发控制**：
    *   在 Python 数据端增加全局限流器（Rate Limiter），针对不同源（东财、新浪）设置不同阈值，避免 IP 被封。
*   **缓存分层**：
    *   L1: 内存缓存 (Redis/LRU) - 存秒级实时行情。
    *   L2: 数据库 (TimescaleDB) - 存历史 K 线。

---

## 5. 技术选型建议

| 模块 | 推荐技术栈 | 理由 |
| :--- | :--- | :--- |
| **协议层 (Interface)** | Node.js (MCP SDK) | 优秀的 I/O 处理能力，不仅适配 MCP 协议，且作为胶水层非常轻量。 |
| **计算层 (Compute)** | **Python (FastAPI + Pandas + Polars)** | 兼顾开发效率与计算性能（通过 C 扩展）。未来瓶颈可迁移至 Rust。 |
| **存储层 (Storage)** | **TimescaleDB (PostgreSQL)** | 处理时序数据的最佳开源方案，支持 SQL 复杂查询。 |
| **通信层 (Bus)** | gRPC / HTTP | 强类型契约，高效跨语言调用。 |
| **数据源 (Source)** | AkShare (Base) + Crawlers | 基础数据用库，特色数据用自研爬虫。 |

---

## 6. 实施路线图 (Roadmap)

### 第一阶段：架构解耦 (2周)
1.  **数据下沉**：将 `mcp-server-compact` 直连 DB 的逻辑剥离，确立 `akshare-mcp` (或新 Data Service) 为唯一数据写入方。
2.  **接口标准化**：定义 Node.js Server 调用 Python 计算服务的标准 API。

### 第二阶段：计算引擎重构 (3周)
1.  **Python 回测引擎**：实现一个基于 Pandas 的向量化简单回测器。
2.  **迁移核心指标**：将 JS 版的 `technical-analysis.ts` 替换为 Python 的 `TA-Lib` 调用。

### 第三阶段：深度与智能 (持续)
1.  **AI 预测模型实验**：在 Python 端接入 PyTorch，尝试训练基于 LSTM 的股价趋势预测 demo。
2.  **本地数据仓库建设**：完善 TimescaleDB 的数据清洗和补录脚本。

---
**风险提示**：
- **数据源稳定性**：免费开源数据源（AkShare）面临接口变更频繁的风险。建议增加数据源健康度监控。
- **重构成本**：跨语言调用（Node <-> Python）会增加部署复杂度，需使用 Docker Compose 统一编排。

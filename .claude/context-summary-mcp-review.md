## 项目上下文摘要（MCP服务功能审查）
生成时间：2026-01-31

### 1. 项目概览

**项目名称**：AIASK - AI驱动的A股量化分析系统
**核心组件**：AKShare MCP Server v2.0
**技术栈**：Python 3.10+, FastMCP, TimescaleDB, Ray, Numba
**项目状态**：生产就绪（v2.0）

### 2. 架构分析

#### 2.1 整体架构
```
packages/
├── akshare-mcp/              # Python MCP服务器（核心，活跃开发）
│   ├── src/akshare_mcp/
│   │   ├── server.py         # MCP服务器入口
│   │   ├── tools/            # MCP工具层（26个文件，12222行代码）
│   │   ├── services/         # 核心服务层（5086行代码）
│   │   ├── core/             # 核心组件（缓存、限流、验证等）
│   │   ├── storage/          # 数据存储（TimescaleDB）
│   │   └── data_source.py    # 数据源管理
│   └── tests/                # 测试文件
│
└── mcp-server-compact/       # TypeScript MCP服务器（已废弃，所有文件标记删除）
```

#### 2.2 模块结构

**Tools层（26个工具模块）**：
- market.py - 市场数据（行情、K线）
- finance.py - 财务数据
- fund_flow.py - 资金流向
- macro.py - 宏观数据
- news.py - 新闻资讯
- backtest.py - 回测工具
- technical.py - 技术分析
- portfolio.py - 投资组合
- valuation.py - 估值分析
- decision.py - 决策支持
- search.py - 搜索工具
- semantic.py - 语义分析
- vector.py - 向量搜索
- sentiment.py - 情绪分析
- quant.py - 量化工具
- options.py - 期权分析
- alerts.py - 告警工具
- data_warmup.py - 数据预热
- managers.py, managers_complete.py, managers_extended.py - 管理器（30个Managers）
- market_blocks.py - 市场板块
- research.py - 研究工具
- skills.py - 技能工具

**Services层（核心服务）**：
- backtest.py - 回测引擎
- factor_calculator.py, factor_calculator_extended.py - 因子计算
- factor_analysis.py - 因子分析
- portfolio_optimization.py, portfolio_optimizer.py - 组合优化
- vector_search.py - 向量搜索
- nlp_query_engine.py - NLP查询引擎
- industry_knowledge_graph.py - 产业链知识图谱
- pattern_recognition.py - 形态识别
- risk_model.py - 风险模型
- sentiment.py - 情绪分析
- technical_analysis.py - 技术分析
- options_pricing.py - 期权定价

**Core层（基础组件）**：
- cache_manager.py - 缓存管理
- rate_limiter.py - 限流器
- retry.py - 重试机制
- validators.py - 数据验证（Pydantic）
- smart_cache.py - 智能缓存
- performance_monitor.py - 性能监控
- batch_operations.py - 批量操作
- vectorized_indicators.py - 向量化指标

### 3. 数据源管理

#### 3.1 数据源优先级策略（data_source.py）
1. **Tushare Pro**（主要数据源）
   - 使用 TUSHARE_TOKEN 和 TUSHARE_HTTP_URL
   - 支持自建/代理服务
   - 白名单机制（tushare_whitelist.py）
2. **Tushare Legacy**（备用）
   - 旧版 Tushare 接口
3. **Baostock**（备用）
   - 免费历史数据
4. **eFinance**（最后备用）
   - 东方财富数据

#### 3.2 数据源配置
```env
TUSHARE_TOKEN=<token>
TUSHARE_HTTP_URL=http://lianghua.nanyangqiankun.top
TUSHARE_WHITELIST_PATH=src/akshare_mcp/config/tushare_proxy_whitelist.json
```

### 4. 核心功能清单

#### 4.1 数据获取（100+工具）
- 实时行情：单只/批量股票行情
- K线数据：日线/周线/月线/分钟级
- 财务数据：财务指标分析
- 北向资金：沪深港通资金流向
- 板块资金：行业/概念板块资金流向
- 龙虎榜：每日龙虎榜数据
- 融资融券：市场两融数据
- 指数行情：主要指数实时行情

#### 4.2 技术分析
- 20+技术指标（MA、EMA、MACD、RSI、KDJ、BOLL等）
- 形态识别
- 趋势分析
- 向量搜索（DTW动态时间规整）

#### 4.3 回测系统
- 4种策略（MA Cross、Momentum、RSI、Mean Reversion）
- 动态止损
- 仓位管理
- 并行回测（Ray）
- 参数优化
- 性能指标：
  - MA Cross回测：<100ms（250天）
  - 参数优化：<1s（4组参数）
  - 蒙特卡洛：<2s（100次）

#### 4.4 因子系统
- 8大类32个因子
- IC分析
- 分组回测
- 因子评估

#### 4.5 风险管理
- VaR/CVaR
- 4种压力测试
- Barra风险分解

#### 4.6 组合优化
- Black-Litterman模型
- 有效前沿
- 风险平价
- 最大夏普比率

#### 4.7 智能功能
- NLP查询解析
- 向量搜索（K线形态相似度）
- 知识图谱（产业链分析）
- AI决策支持

### 5. 依赖关系

#### 5.1 核心依赖
```python
mcp>=1.0.0              # MCP框架
akshare>=1.10.0         # 主要数据源
pandas>=2.0.0           # 数据处理
tushare>=1.4.0          # Tushare数据源
baostock>=0.8.8         # Baostock数据源
efinance>=0.5.5         # 东方财富数据源
pydantic>=2.0.0         # 数据验证
numpy>=1.26.0           # 数值计算
scipy>=1.11.0           # 科学计算
numba>=0.59.0           # JIT编译
asyncpg>=0.29.0         # 异步PostgreSQL
pandas-ta>=0.3.14       # 技术分析
TA-Lib>=0.4.28          # 技术分析库
ray[default]>=2.9.0     # 并行计算（可选）
```

### 6. 测试策略

#### 6.1 测试文件
- test_backtest_performance.py - 回测性能测试
- test_priority3_features.py - 优先级3功能测试
- verify_fixes.py - 修复验证
- verify_all_fixes.py - 全量验证
- test_current_status.py - 当前状态测试
- test_tushare_access.py - Tushare访问测试
- test_single_stock.py - 单只股票测试
- verify_online_sources.py - 在线数据源验证

#### 6.2 测试覆盖
- 单元测试：50+个
- 性能测试：7个基准
- 集成测试：完整流程

### 7. 配置管理

#### 7.1 环境变量（.env.example）
```env
# TimescaleDB配置
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=password
DB_CONNECT_TIMEOUT_MS=10000

# AKShare配置
AKSHARE_SPOT_TTL_SECONDS=2
AKSHARE_SPOT_TIMEOUT_SECONDS=15

# Tushare配置
TUSHARE_TOKEN=<token>
TUSHARE_HTTP_URL=<proxy_url>
TUSHARE_WHITELIST_PATH=src/akshare_mcp/config/tushare_proxy_whitelist.json
```

### 8. 项目约定

#### 8.1 命名约定
- 模块名：小写下划线（snake_case）
- 类名：大驼峰（PascalCase）
- 函数名：小写下划线（snake_case）
- 常量：大写下划线（UPPER_SNAKE_CASE）

#### 8.2 代码风格
- PEP 8代码风格
- Type hints类型注解
- Docstring文档字符串
- 使用Pydantic进行数据验证

#### 8.3 文件组织
- tools/ - MCP工具定义和注册
- services/ - 核心业务逻辑
- core/ - 基础组件和工具
- storage/ - 数据存储层

### 9. 关键风险点

#### 9.1 架构风险
- **重复实现**：mcp-server-compact被废弃，但功能是否完全迁移到akshare-mcp？
- **模块重复**：portfolio_optimization.py 和 portfolio_optimizer.py 可能存在功能重复
- **Manager过多**：3个managers文件（managers.py, managers_complete.py, managers_extended.py），可能存在重复

#### 9.2 数据源风险
- **Tushare依赖**：高度依赖Tushare Pro，需要付费Token
- **代理服务**：使用第三方代理服务（lianghua.nanyangqiankun.top），可靠性未知
- **降级策略**：多数据源降级策略是否充分测试？

#### 9.3 性能风险
- **并发控制**：ThreadPoolExecutor使用是否合理？
- **缓存策略**：多层缓存（_spot_cache, ProcessCache, smart_cache）是否会导致数据不一致？
- **超时设置**：多个超时配置（SPOT_TIMEOUT, QUOTE_TIMEOUTS, KLINE_TIMEOUTS），是否合理？

#### 9.4 测试风险
- **测试覆盖不足**：主要集中在回测和优先级功能，缺少数据源、缓存、限流等基础组件的单元测试
- **集成测试缺失**：缺少端到端的集成测试

#### 9.5 文档风险
- **文档不一致**：README.md中有两份内容（v2.0完整版 + 旧版简化版）
- **配置文档缺失**：缺少完整的配置说明和最佳实践

### 10. 技术债务识别

#### 10.1 代码重复
- portfolio_optimization.py vs portfolio_optimizer.py
- managers.py vs managers_complete.py vs managers_extended.py
- 多个缓存实现（cache.py, cache_manager.py, smart_cache.py）

#### 10.2 废弃代码
- packages/mcp-server-compact/ 整个目录标记删除但未清理

#### 10.3 配置管理
- .env.example中包含真实Token（应该使用占位符）
- 配置项过多且分散

#### 10.4 错误处理
- 部分模块使用 ok()/fail() 返回字典，部分使用异常
- 错误处理策略不统一

### 11. 改进建议方向

#### 11.1 架构优化
- 清理废弃的mcp-server-compact目录
- 合并重复的managers模块
- 统一缓存策略

#### 11.2 测试增强
- 补充基础组件的单元测试
- 添加端到端集成测试
- 添加数据源降级测试

#### 11.3 文档完善
- 清理README.md中的重复内容
- 补充配置说明文档
- 添加架构设计文档

#### 11.4 代码质量
- 统一错误处理策略
- 添加更多类型注解
- 改进日志记录

### 12. 观察报告

#### 12.1 发现的异常
1. .env.example包含真实Token，存在安全风险
2. README.md包含两份内容，文档不一致
3. mcp-server-compact被标记删除但未清理
4. 多个功能相似的模块（portfolio_*, managers_*）

#### 12.2 信息不足之处
1. mcp-server-compact的功能是否完全迁移？
2. 数据源降级策略的测试覆盖如何？
3. 并行回测（Ray）的实际使用情况？
4. TimescaleDB的表结构和索引设计？

#### 12.3 建议深入的方向
1. 审查重复模块的功能差异
2. 检查数据源降级的完整性
3. 评估测试覆盖的充分性
4. 分析性能瓶颈和优化空间

# MCP Server Compact - 测试文档

## 测试覆盖范围

### 核心服务测试 (P0优先级)

1. **风险模型服务** (`services/risk-model.test.ts`)
   - Barra风险分解
   - VaR/CVaR计算
   - 压力测试
   - 综合风险报告

2. **回测引擎** (`services/backtest.test.ts`)
   - 4种策略回测 (buy_and_hold, ma_cross, momentum, rsi)
   - 参数优化
   - 蒙特卡洛模拟
   - Walk-forward分析

3. **技术分析** (`services/technical-analysis.test.ts`)
   - 技术指标计算 (SMA, EMA, RSI, MACD, BOLL)
   - 支撑阻力位检测
   - 交易信号生成

4. **组合优化** (`services/portfolio-optimizer.test.ts`)
   - 协方差矩阵计算
   - 均值方差优化
   - 等权重优化

## 运行测试

```bash
# 运行所有测试
npm test

# 运行测试并生成覆盖率报告
npm test -- --coverage

# 运行特定测试文件
npm test -- test/services/backtest.test.ts

# 监听模式
npm test -- --watch
```

## 测试策略

### 单元测试
- 测试单个函数的输入输出
- 使用模拟数据避免外部依赖
- 覆盖正常情况和边界情况

### 集成测试
- 测试服务之间的交互
- 使用真实数据库（测试环境）
- 验证端到端流程

## 测试数据

### 模拟数据
- K线数据：使用随机生成的价格序列
- 股票代码：使用常见的测试代码 (600519, 000858等)

### 真实数据
- 需要配置数据库连接
- 部分测试会在数据缺失时跳过

## 覆盖率目标

- 核心服务：60%+ (P0)
- 工具层：40%+ (P1)
- 整体：50%+ (P1)

## 注意事项

1. 某些测试依赖真实数据，如果数据不可用会自动跳过
2. 测试超时设置为10秒，适应数据库查询
3. 使用vitest作为测试框架，支持TypeScript

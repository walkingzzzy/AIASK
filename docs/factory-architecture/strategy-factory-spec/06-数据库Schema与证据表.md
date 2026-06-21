# 数据库Schema与证据表

## 文档信息

| 项目 | 内容 |
|---|---|
| 文档版本 | 1.0.0 |
| 更新日期 | 2026-06-21 |
| 数据库路径 | `data/db/akshare_mcp.sqlite3` |
| 数据库大小 | 156 MB (152表) |

## 1. 核心证据表

### 1.1 策略主表

**表名**: `strategies`

| 字段 | 类型 | 说明 | 约束 |
|------|------|------|------|
| id | UUID | 主键 | PRIMARY KEY |
| strategy_id | VARCHAR | 业务ID | UNIQUE |
| name | VARCHAR | 策略名称 | NOT NULL |
| status | ENUM | 状态 | NOT NULL |
| created_at | TIMESTAMP | 创建时间 | NOT NULL |
| updated_at | TIMESTAMP | 更新时间 | NOT NULL |

**实际数据** (2026-06-21): 23,008行

**索引**:
```sql
CREATE INDEX idx_strategies_status ON strategies(status);
CREATE INDEX idx_strategies_created_at ON strategies(created_at);
```

### 1.2 信号表

**表名**: `strategy_signals`

| 字段 | 类型 | 说明 |
|------|------|------|
| signal_id | UUID | 主键 |
| strategy_id | UUID | 外键 |
| symbol | VARCHAR | 股票代码 |
| direction | ENUM | buy/sell/hold |
| timestamp | TIMESTAMP | 信号时间 |
| strength | FLOAT | 信号强度 |

**实际数据**: 19,312行

### 1.3 订单表

**表名**: `paper_orders`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| strategy_id | UUID | 外键 |
| signal_id | UUID | 外键(可空) |
| symbol | VARCHAR | 股票代码 |
| side | ENUM | buy/sell |
| quantity | INT | 数量 |
| price | FLOAT | 价格 |
| status | ENUM | pending/filled/cancelled |

**实际数据**: 3,835行

### 1.4 成交表

**表名**: `paper_trades`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| order_id | UUID | 外键 |
| symbol | VARCHAR | 股票代码 |
| side | ENUM | buy/sell |
| quantity | INT | 成交数量 |
| price | FLOAT | 成交价格 |
| timestamp | TIMESTAMP | 成交时间 |

**实际数据**: 3,764行

### 1.5 持仓表

**表名**: `strategy_trade_positions`

| 字段 | 类型 | 说明 |
|------|------|------|
| position_id | UUID | 主键 |
| strategy_id | UUID | 外键 |
| symbol | VARCHAR | 股票代码 |
| quantity | INT | 持仓数量 |
| entry_price | FLOAT | 入场价格 |
| exit_price | FLOAT | 出场价格(可空) |
| status | ENUM | open/closed |
| realized_pnl | FLOAT | 已实现盈亏 |
| entry_time | TIMESTAMP | 入场时间 |
| exit_time | TIMESTAMP | 出场时间(可空) |

**实际数据**: 3,660行 (3,602 open, 51 closed)

### 1.6 前向收益表

**表名**: `signal_forward_returns`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| signal_id | UUID | 外键 |
| horizon | INT | 前向天数 |
| forward_return | FLOAT | 前向收益率 |
| benchmark_return | FLOAT | 基准收益率 |
| excess_return | FLOAT | 超额收益率 |

**实际数据**: 39,449行

### 1.7 孵化指标表

**表名**: `strategy_incubation_metrics`

| 字段 | 类型 | 说明 |
|------|------|------|
| strategy_id | UUID | 外键 |
| effective_n_5d | INT | 5日有效样本数 |
| effective_n_10d | INT | 10日有效样本数 |
| effective_n_20d | INT | 20日有效样本数 |
| ic_mean_5d | FLOAT | 5日IC均值 |
| sharpe_5d | FLOAT | 5日Sharpe |
| hit_rate | FLOAT | 命中率 |
| lcb | FLOAT | 置信下界 |

**实际数据**: 27,343行

### 1.8 审计快照表

**表名**: `strategy_execution_audit_snapshots`

| 字段 | 类型 | 说明 |
|------|------|------|
| snapshot_id | UUID | 主键 |
| strategy_id | UUID | 外键 |
| verdict_status | ENUM | missing/bootstrap_pending/insufficient/failed/ready/passed |
| realized_trade_count | INT | 已实现交易数 |
| expectancy | FLOAT | 期望收益 |
| audit_result | JSON | 审计详情 |
| snapshot_time | TIMESTAMP | 快照时间 |

**实际数据**: 20,392行

## 2. 关键查询

### 2.1 证据链完整性

```sql
-- 信号→订单转换率
SELECT 
    COUNT(DISTINCT s.strategy_id) as strategies_with_signals,
    COUNT(DISTINCT o.strategy_id) as strategies_with_orders,
    ROUND(100.0 * COUNT(DISTINCT o.strategy_id) / COUNT(DISTINCT s.strategy_id), 2) as conversion_rate
FROM strategy_signals s
LEFT JOIN paper_orders o ON s.strategy_id = o.strategy_id;

-- 订单→成交转换率
SELECT 
    COUNT(*) as total_orders,
    COUNT(t.id) as filled_orders,
    ROUND(100.0 * COUNT(t.id) / COUNT(*), 2) as fill_rate
FROM paper_orders o
LEFT JOIN paper_trades t ON o.id = t.order_id;

-- 持仓退出率
SELECT 
    COUNT(*) FILTER (WHERE status = 'open') as open_positions,
    COUNT(*) FILTER (WHERE status = 'closed') as closed_positions,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'closed') / COUNT(*), 2) as close_rate
FROM strategy_trade_positions;
```

### 2.2 Hard Gate统计

```sql
SELECT 
    verdict_status,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM strategy_execution_audit_snapshots
GROUP BY verdict_status
ORDER BY count DESC;
```

## 3. 数据库配置

### 3.1 路径配置

**默认路径**: `data/db/akshare_mcp.sqlite3`

**环境变量**: `AKSHARE_MCP_SQLITE_PATH`

**代码读取**:
```python
from aiask_quant_core.config import get_settings
settings = get_settings()
db_path = settings.sqlite_path
```

### 3.2 连接管理

**位置**: `packages/strategy-factory/src/strategy_factory/infrastructure/persistence/sqlite/`

**CRUD**: `_strategy_crud_core.py`

## 相关文档

- [00-四工厂体系总览](00-四工厂体系总览.md)
- [05-生命周期与状态机](05-生命周期与状态机.md)

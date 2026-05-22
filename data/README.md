# 数据目录

所有数据库文件统一存放在此目录下。

## 文件说明

| 文件 | 用途 |
|---|---|
| `db/akshare_mcp.sqlite3` | 主数据库（市场数据 + 策略 + 向量） |
| `db/strategy_factory_task_board.sqlite3` | 策略工厂任务追踪 |

## 环境变量配置

在 `.env` 中设置：
```
AKSHARE_MCP_SQLITE_PATH=./data/db/akshare_mcp.sqlite3
STRATEGY_FACTORY_TASK_BOARD_PATH=./data/db/strategy_factory_task_board.sqlite3
```

## 数据同步

统一入口：
```bash
# 初始化数据库（建表）
python scripts/db_init.py

# 全量历史同步
python scripts/db_sync.py --full

# 增量同步（日常）
python scripts/db_sync.py --incremental

# 仅同步特定类型
python scripts/db_sync.py --type kline --codes 600519,000001
python scripts/db_sync.py --type north_fund
python scripts/db_sync.py --type margin
python scripts/db_sync.py --type financial
```

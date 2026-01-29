# 数据库脚本说明

## 核心脚本

| 脚本 | 用途 | 命令 |
|------|------|------|
| `migrate-advanced-tables.ts` | 创建数据库表结构 | `npm run db:migrate` |
| `init-database-free.ts` | 初始化基础数据（akshare-mcp） | `npm run init-db-free` |
| `init-database-full.ts` | 下载完整K线数据 | `npm run init-db-full` |
| `supplement-data.ts` | 补充龙虎榜等数据 | `npm run supplement-data` |
| `diagnose-market-tools.ts` | 诊断盘口/成交明细/涨停入口 | `npx tsx scripts/diagnose-market-tools.ts` |

## 股票列表同步脚本

统一通过 akshare-mcp 获取股票列表：

| 脚本 | 数据源 | 状态 | 说明 |
|------|--------|------|------|
| `sync-stocks-baostock.py` | akshare-mcp | ✅ 可用 | 导出股票列表到 `stocks_akshare.json` |

## 已知限制

1. **北交所数据缺失**：约 260 只北交所股票无法通过现有接口获取
2. **B股数据缺失**：约 80 只 B 股未包含
3. **网络限制**：数据源由 akshare-mcp 统一处理，若外部接口不可用将自动降级或返回空结果

## 数据库当前状态

- 股票数量：5187 只（沪深A股）
- 日K线：约 128 万条
- 分钟K线：约 620 万条（5m/15m/30m/60m）
- 龙虎榜：约 1900 条
- 北向资金：约 300 条

## 后续补充方案

如需补充北交所数据，可：
1. 从北交所官网 https://www.bse.cn 手动下载
2. 在网络正常环境下运行 akshare-mcp 同步脚本

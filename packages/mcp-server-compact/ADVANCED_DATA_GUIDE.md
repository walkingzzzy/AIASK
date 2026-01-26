# 高级数据下载指南

本指南说明如何下载和同步所有高级A股数据，包括分钟K线、龙虎榜、北向资金、融资融券、大宗交易、新闻等。

## 📋 数据类型概览

### ✅ 基础数据（由 init-database.ts 下载）
- **股票列表**：5,473 只A股基础信息
- **日线K线**：250天历史数据
- **财务数据**：最新财报数据

### 🚀 高级数据（由 init-database-full.ts 下载）
- **分钟K线**：1m, 5m, 15m, 30m, 60m（最近30天）
- **龙虎榜**：最近90天数据
- **北向资金**：最近365天流向数据
- **融资融券**：最近90天数据
- **大宗交易**：最近90天数据
- **新闻资讯**：每只股票最近20条新闻

### 💡 实时数据（按需获取，不需要预下载）
- **实时行情**：价格、涨跌幅
- **盘口数据**：买卖五档
- **分时数据**：当日分时走势

## 🔧 初始化步骤

### 步骤 1：数据库迁移（添加高级数据表）

```bash
cd packages/mcp-server-compact
npm run db:migrate
```

这将创建以下表：
- `kline_1m`, `kline_5m`, `kline_15m`, `kline_30m`, `kline_60m` - 分钟K线表
- `dragon_tiger` - 龙虎榜表
- `north_fund` - 北向资金表
- `margin_data` - 融资融券表
- `block_trades` - 大宗交易表
- `stock_news` - 新闻表

### 步骤 2：下载基础数据（如果还没有）

```bash
npm run init-db > init-database.log 2>&1 &
```

这将下载：
- 5,473 只A股基础信息
- 每只股票250天日线K线
- 每只股票最新财务数据

**预计时间**：1-2小时（取决于网络速度）

**查看进度**：
```bash
tail -f init-database.log
```

### 步骤 3：下载高级数据

```bash
npm run init-db-full > init-database-full.log 2>&1 &
```

这将下载：
- 分钟K线（5个周期 × 5,473只股票 × 30天）
- 龙虎榜（90天）
- 北向资金（365天）
- 融资融券（全市场标的）
- 大宗交易（90天）
- 新闻资讯（每只股票20条）

**预计时间**：4-8小时（取决于网络速度和数据量）

**查看进度**：
```bash
tail -f init-database-full.log
```

## 📊 数据量估算

### 基础数据
- 股票信息：5,473 条
- 日线K线：5,473 × 250 = 1,368,250 条
- 财务数据：5,473 条

### 高级数据（30天分钟K线）
- 1分钟K线：5,473 × 20交易日 × 240根 = 26,270,400 条
- 5分钟K线：5,473 × 20交易日 × 48根 = 5,254,080 条
- 15分钟K线：5,473 × 20交易日 × 16根 = 1,751,360 条
- 30分钟K线：5,473 × 20交易日 × 8根 = 875,680 条
- 60分钟K线：5,473 × 20交易日 × 4根 = 437,840 条
- 龙虎榜：90天 × 平均50只/天 = 4,500 条
- 北向资金：365 条
- 融资融券：约1,000只标的 × 90天 = 90,000 条
- 大宗交易：90天 × 平均100笔/天 = 9,000 条
- 新闻：5,473 × 20 = 109,460 条

**总数据量**：约3,459万条记录（分钟K线），预计占用 **2-3GB** 磁盘空间（TimescaleDB压缩后）

**注意**：如果需要存储更长时间的历史数据：
- 1年分钟K线：约 12-15 GB
- 3年分钟K线：约 40-50 GB

## ⚙️ 配置选项

### 修改下载参数

编辑 `scripts/init-database-full.ts`：

```typescript
// 分钟K线回溯天数（默认30天）
const lookbackDays = 30;

// 龙虎榜回溯天数（默认90天）
await downloadDragonTiger(progress, 90);

// 北向资金回溯天数（默认365天）
await downloadNorthFund(progress, 365);

// 每只股票新闻数量（默认20条）
const newsPerStock = 20;
```

### 调整下载速度

```typescript
// 批次大小（默认5-10）
const batchSize = 10;

// 批次间延迟（默认3000-5000ms）
const delayBetweenBatches = 5000;

// 股票间延迟（默认500ms）
const delayBetweenStocks = 500;
```

## 🔄 数据同步

### 增量更新

当前的 `data-sync.ts` 和 `data-warmup.ts` 只同步基础数据（日线K线和财务数据）。

**高级数据需要定期重新运行 `init-database-full.ts`**，或者创建专门的同步脚本。

### 建议的同步策略

1. **日线K线 + 财务数据**：每日收盘后自动同步（使用现有 data-sync）
2. **分钟K线**：每周同步一次最近7天数据
3. **龙虎榜**：每日同步前一交易日数据
4. **北向资金**：每日同步前一交易日数据
5. **融资融券**：每周同步一次
6. **大宗交易**：每日同步前一交易日数据
7. **新闻**：每日同步热门股票新闻

## 🚨 注意事项

### 1. 数据源限制
- 东方财富、新浪、腾讯等数据源有访问频率限制
- 如果IP被封，脚本会自动切换到备用数据源
- 建议在非交易时间（晚上）运行大批量下载

### 2. 磁盘空间
- 分钟K线数据量：约2-3GB（30天）
- 如果存储1年：约12-15GB
- 如果存储3年：约40-50GB
- 确保有足够的磁盘空间
- 可以选择只下载部分周期（如只下载5m和60m）

### 3. 下载时间
- 完整下载需要4-8小时
- 可以分批下载，脚本会自动跳过已有数据
- 支持断点续传（重新运行脚本即可）

### 4. 数据质量
- 部分股票可能缺少某些数据（如停牌股票）
- 脚本会记录失败的股票代码
- 可以后续单独补充缺失数据

## 📈 数据验证

### 检查数据完整性

```bash
# 连接数据库
psql -U postgres -d aiask_stock

# 检查各表记录数
SELECT 'kline_1d' as table_name, COUNT(*) as count FROM kline_1d
UNION ALL
SELECT 'kline_1m', COUNT(*) FROM kline_1m
UNION ALL
SELECT 'kline_5m', COUNT(*) FROM kline_5m
UNION ALL
SELECT 'dragon_tiger', COUNT(*) FROM dragon_tiger
UNION ALL
SELECT 'north_fund', COUNT(*) FROM north_fund
UNION ALL
SELECT 'margin_data', COUNT(*) FROM margin_data
UNION ALL
SELECT 'block_trades', COUNT(*) FROM block_trades
UNION ALL
SELECT 'stock_news', COUNT(*) FROM stock_news;

# 检查某只股票的数据
SELECT * FROM kline_1d WHERE code = '600519' ORDER BY time DESC LIMIT 10;
SELECT * FROM kline_5m WHERE code = '600519' ORDER BY time DESC LIMIT 10;
SELECT * FROM stock_news WHERE code = '600519' ORDER BY time DESC LIMIT 5;
```

## 🛠️ 故障排除

### 问题 1：下载速度慢
**解决方案**：
- 增加批次大小：`batchSize = 20`
- 减少延迟：`delayBetweenBatches = 2000`
- 使用更快的网络

### 问题 2：IP被封
**解决方案**：
- 脚本会自动切换数据源
- 增加延迟：`delayBetweenBatches = 10000`
- 使用代理或VPN

### 问题 3：数据库连接超时
**解决方案**：
- 检查 TimescaleDB 是否运行：`docker ps | grep timescale`
- 检查连接配置：`echo $DATABASE_URL`
- 增加连接池大小：修改 `timescaledb.ts` 中的 `max: 20`

### 问题 4：磁盘空间不足
**解决方案**：
- 默认配置只需2-3GB，通常不会不足
- 如果需要更长历史，可以逐步增加回溯天数
- 只下载部分周期：注释掉不需要的周期（如只保留5m和60m）
- 清理旧数据：`DELETE FROM kline_1m WHERE time < NOW() - INTERVAL '7 days'`
- 扩展磁盘空间

## 📚 相关文档

- [数据库优化指南](./OPTIMIZATION_SCHEME.md)
- [数据质量报告](./DATA_QUALITY_REPORT.md)
- [MCP工具文档](./README.md)

## 🎯 快速开始

```bash
# 1. 迁移数据库（添加高级数据表）
npm run db:migrate

# 2. 下载基础数据（如果还没有）
npm run init-db > init-database.log 2>&1 &

# 3. 等待基础数据下载完成（1-2小时）
tail -f init-database.log

# 4. 下载高级数据
npm run init-db-full > init-database-full.log 2>&1 &

# 5. 查看进度
tail -f init-database-full.log

# 6. 验证数据
psql -U postgres -d aiask_stock -c "SELECT 'kline_1m', COUNT(*) FROM kline_1m"
```

## ✅ 完成后

数据下载完成后，您可以：

1. **启动 MCP 服务**：`npm start`
2. **使用 MCP 工具**：通过 Claude Desktop 或其他 MCP 客户端访问数据
3. **运行回测**：使用完整的历史数据进行策略回测
4. **分析市场**：使用龙虎榜、北向资金等数据进行市场分析
5. **监控资金流向**：使用融资融券、大宗交易数据监控主力动向

祝您使用愉快！🎉

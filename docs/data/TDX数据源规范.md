# TDX 数据源规范

> 本文件是项目数据获取的**唯一权威规范**。所有数据同步、实时查询、因子计算、策略回测的数据来源必须遵循本文件。

## 1. 数据源架构

```
通达信客户端 (C:\new_tdx_test)
    │
    ├── tqcenter SDK (PYPlugins/sys/tqcenter.py)
    │       │
    │       ├── get_market_data()      → K线 OHLCV + 复权因子
    │       ├── get_market_snapshot()   → 实时快照
    │       ├── get_more_info()         → 换手率/PE/PB/市值/涨幅/主力净流入
    │       ├── get_financial_data()    → 580+ 字段专业财务
    │       ├── get_stock_info()        → 基础信息/行业/股本
    │       ├── get_gpjy_value()        → 个股交易(融资融券/龙虎榜/陆股通/大宗)
    │       ├── get_scjy_value()        → 市场交易(北向/融资/涨跌停)
    │       ├── get_sector_list()       → 板块列表
    │       ├── get_stock_list_in_sector() → 板块成分股
    │       ├── get_trading_dates()     → 交易日历
    │       └── get_gb_info()           → 每日股本
    │
    └── vipdoc 本地文件 (降级备用)
            ├── sh/lday/*.day           → 日线二进制
            ├── sz/lday/*.day
            ├── sh/fzline/*.lc5         → 5分钟线
            └── sh/minline/*.lc1        → 1分钟线
```

## 2. 优先级规则

1. **首选**：`tqcenter` SDK（需通达信客户端运行）
2. **降级**：本地 vipdoc 二进制文件解析（仅 K 线，无财务/交易数据）
3. **禁止**：Tushare / AKShare / eFinance / Baostock / 东方财富HTTP / 新浪HTTP / 腾讯HTTP

## 3. 数据同步流程

### 3.1 全量同步（首次 / 每周末）

```bash
python scripts/db_sync.py --full
```

执行顺序：
1. **stocks** — `get_stock_list("HsA")` + 逐只 `get_stock_info()` → stocks 表
2. **calendar** — `get_trading_dates()` → trading_dates 表
3. **kline** — `get_market_data(period="1d", count=2000)` → kline_1d 表
4. **financials** — `get_financial_data(fields=[FN1,FN4,FN6,FN74,FN95,...])` → financials 表
5. **valuation** — `get_more_info()` 批量 → stock_quotes 表 (PE/PB/市值/换手率)
6. **north_fund** — `get_scjy_value(["SC2","SC20"])` → north_fund_flow 表
7. **margin** — `get_scjy_value(["SC1","SC25"])` → margin_market_flow 表
8. **sector_flow** — `get_bkjy_value()` → market_blocks 表
9. **block_stocks** — `get_sector_list()` + `get_stock_list_in_sector()` → block_stocks 表

### 3.2 增量同步（每日盘后）

```bash
python scripts/db_sync.py --incremental
```

仅同步：kline(最近5天) + valuation + north_fund + margin

### 3.3 实时数据（盘中）

通过 `data_source` 单例的 `get_realtime_quote()` / `get_kline()` 实时调用 tqcenter。

## 4. tqcenter SDK 使用注意事项

1. **必须先 initialize**：`tq.initialize(__file__)` 在进程生命周期内只调一次
2. **通达信客户端必须运行**：SDK 通过 DLL 与客户端通信，客户端关闭则所有调用失败
3. **数据需要先下载**：客户端菜单 → 系统 → 盘后数据下载 → 勾选"专业财务数据"
4. **单次最多 24000 条**：K 线数据单次请求上限，超过需分批
5. **field_list 大小写**：财务字段用 `FN193` 格式（大写 FN + 数字）
6. **stock_code 格式**：必须带市场后缀，如 `600519.SH`、`000001.SZ`

## 5. 数据库表与 TDX 接口映射

| DB 表 | TDX 接口 | 同步频率 |
|-------|---------|---------|
| kline_1d | get_market_data(period="1d") | 每日 |
| stocks | get_stock_list + get_stock_info | 每周 |
| trading_dates | get_trading_dates | 每月 |
| financials | get_financial_data | 每季报后 |
| stock_quotes | get_more_info | 每日 |
| north_fund_flow | get_scjy_value(SC02/SC20) | 每日 |
| margin_market_flow | get_scjy_value(SC01/SC25) | 每日 |
| margin_detail | get_gpjy_value(GP03/GP11-13) | 每日 |
| stock_fund_flow | get_more_info(Zjl_HB) | 每日 |
| market_blocks | get_sector_list + get_bkjy_value | 每日 |
| block_stocks | get_stock_list_in_sector | 每周 |
| dragon_tiger | get_gpjy_value(GP02) | 每日 |
| factor_values | 计算生成（基于上述数据） | 按需 |

## 6. 三大工厂数据需求覆盖

| 工厂 | 需要的数据 | TDX 覆盖 |
|------|-----------|---------|
| 策略工厂 DataCollector | 指数K线、涨跌停统计、北向资金、融资融券、板块资金流 | ✅ 全覆盖 |
| 策略工厂 BacktestFilter | 个股K线(250天+)、交易日历 | ✅ 全覆盖 |
| 因子挖掘 核心特征帧 | OHLCV + amount + 收益率 + 动量 + 波动率 | ✅ 全覆盖 |
| 因子挖掘 扩展特征帧 | 换手率、PE/PB、ROE、营收增长、北向资金、融资余额 | ✅ 全覆盖 |
| 孵化工厂 ForwardVerifier | 信号日后的实际K线 | ✅ 全覆盖 |
| 孵化工厂 SignalGenerator | 最新行情 + 策略参数 | ✅ 全覆盖 |

## 7. 官方文档参考

- TdxQuant 官方帮助：https://help.tdx.com.cn/quant
- 本地文档副本：`tdx_quant_docs/` 目录
- 财务字段对照表：`tdx_quant_docs/TdxQuant.md_mindoc-1h10m001ic888.md`（FN1-FN584）
- 股票交易数据：`tdx_quant_docs/TdxQuant.md_mindoc-1h10muc82r55k.md`（GP01-GP46）
- 市场交易数据：`tdx_quant_docs/TdxQuant.md_mindoc-1h10p8op6ia9g.md`（SC01-SC42）

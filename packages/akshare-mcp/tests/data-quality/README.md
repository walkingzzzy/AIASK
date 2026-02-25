# 数据质量测试套件

针对 AKShare MCP Server 的 TDX、Tushare、AkShare 多数据源进行全面数据质量验证。

## 测试分类

| 文件 | 测试内容 | 数据源 |
|------|---------|--------|
| test_01_tushare_macro.py | 宏观数据(CPI/PPI/M2/SHIBOR) | Tushare Pro |
| test_02_tushare_finance.py | 财务数据(600519/000001) | Tushare Pro |
| test_03_tushare_valuation.py | 估值数据(daily_basic历史PE/PB) | Tushare Pro |
| test_04_tushare_limit_up.py | 涨停板数据(stk_limit) | Tushare Pro |
| test_05_tushare_block_trades.py | 大宗交易+名称映射 | Tushare Pro |
| test_06_tdx_kline.py | K线数据质量 | TDX |
| test_07_tdx_technical.py | 技术指标(DMA/MACD/KDJ) | TDX |
| test_08_cross_source.py | 跨源一致性(TDX vs Tushare K线) | TDX + Tushare |
| test_09_mcp_integration.py | MCP工具集成(manager层) | MCP Tools |

## 运行方式

```bash
# 运行全部测试
python tests/data-quality/run_all_tests.py

# 运行单个测试
python tests/data-quality/test_01_tushare_macro.py
```

## 环境要求

- TDX 测试需要通达信客户端运行中
- Tushare 测试需要配置 TUSHARE_TOKEN 和代理地址

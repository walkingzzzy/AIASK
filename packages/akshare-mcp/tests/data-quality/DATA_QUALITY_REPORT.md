# 数据质量测试报告

- 运行时间: 2026-03-03 12:07:13
- 耗时: 14.2 秒
- 结果: 0 通过, 12 失败, 0 跳过

| 测试文件 | 描述 | 结果 |
|---------|------|------|
| test_01_tushare_macro.py | 宏观数据质量 | FAIL |
| test_02_tushare_finance.py | 财务数据质量 | FAIL |
| test_03_tushare_valuation.py | 历史估值质量 | FAIL |
| test_04_tushare_limit_up.py | 涨停板数据质量 | FAIL |
| test_05_tushare_block_trades.py | 大宗交易+名称映射 | FAIL |
| test_06_tdx_kline.py | TDX K线全面质量 | FAIL |
| test_07_tdx_technical.py | TDX 公式系统与技术指标 | FAIL |
| test_08_cross_source.py | 跨源一致性 | FAIL |
| test_10_tdx_finance.py | TDX 财务数据与股票信息 | FAIL |
| test_11_tdx_trading.py | TDX 交易数据与市场数据 | FAIL |
| test_12_tdx_misc.py | TDX 其他接口(IPO/可转债/板块/公式) | FAIL |
| test_09_mcp_integration.py | MCP 集成测试 | FAIL |

## 测试覆盖的问题

| 原始问题 | 对应测试 |
|---------|----------|
| FAIL #1 CPI 数据 | test_01, test_09 |
| WARN #2 财务数据 null | test_02, test_09 |
| WARN #7 大宗交易 name 空 | test_05, test_09 |
| WARN #8 000001 Invalid argument | test_02 |
| WARN #9 历史估值不足 | test_03 |
| WARN #10/#11/#14 涨停统计全0 | test_04, test_09 |
| WARN #15 PE/PB/PS=0 | test_03, test_09 |
| WARN #19 DMA 跳变 | test_07 |
| 跨源一致性 | test_08 |

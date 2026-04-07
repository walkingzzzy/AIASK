# 数据质量测试套件

针对 AKShare MCP Server 的核心数据源与 MCP 集成链路进行数据质量验证。

> 校准说明：本文描述的是测试套件覆盖范围与运行前提，不等价于“当前环境已全部通过”。
>
> 当前测试目录主路径中不再维护单独的 Markdown 结果报告；实际通过/失败情况请以最近一次运行结果、pytest 输出或 CI 记录判断。尤其是 Tushare Token、数据库、代理和网络条件等外部依赖会直接影响结果。


## 测试分类

| 文件 | 测试内容 | 数据源 |
|------|---------|--------|
| test_01_tushare_macro.py | 宏观数据(CPI/PPI/M2/SHIBOR) | Tushare Pro |
| test_02_tushare_finance.py | 财务数据(600519/000001) | Tushare Pro |
| test_03_tushare_valuation.py | 估值数据(daily_basic历史PE/PB) | Tushare Pro |
| test_04_tushare_limit_up.py | 涨停板数据(stk_limit) | Tushare Pro |
| test_05_tushare_block_trades.py | 大宗交易+名称映射 | Tushare Pro |
| test_09_mcp_integration.py | MCP工具集成(manager层) | MCP Tools |

## 运行方式

```bash
# 运行全部测试
python tests/data-quality/run_all_tests.py

# 运行当前保留的核心测试子集
python tests/data-quality/run_core_tests.py

# 运行单个测试
python tests/data-quality/test_01_tushare_macro.py
```

## 环境要求

- Tushare 测试需要配置 TUSHARE_TOKEN 和代理地址
- 如需查看 tests 目录中的历史 Markdown 报告，请回到 [`../README.md`](../README.md) 和 [`../archive/README.md`](../archive/README.md)

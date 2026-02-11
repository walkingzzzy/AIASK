# TDX 前端与 MCP 服务交互式测试方案

> 文件名：`TDX_FRONTEND_INTERACTIVE_TEST_PLAN.md`  
> 适用对象：TDX 客户端前端 + akshare-mcp 服务联调  
> 测试方式：**对话式 MCP 工具调用（非 Python 批处理）**

---

## 1. 测试目标

1. 验证 TDX 前端与 MCP 服务端到端交互链路：**请求 -> MCP -> TdxQuant -> TDX 前端可视化反馈**。  
2. 覆盖 TDX 手册 7 大模块（GP/BK/SC/HQ/ZB/GS/其他）对应 MCP 能力。  
3. 重点验证 Phase 1~4 已落地的 13 个工具，并补充 `tdx_integration.py` 与 `tdx_formula` 场景工具。  
4. 输出可复用、可回归、可截图留证的测试执行标准。

## 2. 参考依据

- `packages/akshare-mcp/src/akshare_mcp/tools/tdx_integration.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/tdx_trading_data.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/tdx_file_sector.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/tdx_realtime.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/tdx_formula/shortcuts.py`
- `TDX_MCP_EXTENSION_PLAN.md`
- `tests/tdxquant-integration/test_tdx_frontend.py`
- `packages/akshare-mcp/tests/real_world_scenarios/scenario_05_backtest_tdx_visualization.md`
- `packages/akshare-mcp/tests/real_world_scenarios/MCP_TOOL_TEST_RESULTS.md`

## 3. 测试环境准备

### 3.1 前置检查（必做）

- [ ] TDX 客户端已启动并登录（可手工打开任意股票 K 线）
- [ ] TDX 已下载盘后数据包（用于 GP/BK/SC）
- [ ] MCP 服务已启动，工具可调用
- [ ] `data_source.is_tdx_available()` 预期为 true
- [ ] Python 环境依赖完整（akshare-mcp 对应虚拟环境）

### 3.2 环境变量建议

- `TDX_PLUGIN_PATH`：指向 TDX `PYPlugins` 目录
- MCP 服务 `.env` 与运行目录一致
- 若有权限限制，TDX 与 MCP 使用同一用户权限运行

### 3.3 快速连通性冒烟

1) 调 `push_message({"message":"MCP联调冒烟|TDX在线检查"})`  
2) 调 `get_user_sectors()`  
3) 两者成功则进入完整测试。

## 4. 测试数据准备

| 类别 | 建议数据 |
|---|---|
| 股票代码 | `600519`,`000001`,`000858`,`300750`,`601318`,`600036` |
| ETF/转债 | `510050`,`123039` |
| 板块代码 | `MCP_IT_001`（测试专用） |
| 板块名称 | `MCP交互测试板块` |
| 回测区间 | `2025-01-01` ~ `2025-12-31` |
| GP/BK/SC日期 | `20260101`（单日）或 `20250101~20250131`（区间） |
| 文件样例 | `mcp_tdx_report.html`、`mcp_tdx_note.txt` |

## 5. 7 大模块与 MCP 工具映射

| 模块 | 目标能力 | 关键 MCP 工具 |
|---|---|---|
| GP | 个股交易扩展数据 | `tdx_get_stock_trading_data` |
| BK | 板块交易扩展数据 | `tdx_get_sector_trading_data` |
| SC | 全市场交易扩展数据 | `tdx_get_market_trading_data` |
| HQ | 行情订阅/缓存刷新 | `tdx_manage_subscription`,`tdx_refresh_data` |
| ZB | 公式/指标/选股/专家 | `tdx_calculate_indicator`,`tdx_screen_stocks`,`tdx_get_expert_signals`,`tdx_calculate_macd/kdj/rsi/boll/trix/dma/expma/dmi/cr/vr`,`tdx_get_formula_data` |
| GS | 个股财务/F10增强 | `tdx_get_financial_snapshot`,`tdx_get_financial_history`,`tdx_get_f10_info` |
| 其他 | 前端交互、文件、回测可视化 | `create_watchlist`,`add_stocks_to_watchlist`,`delete_watchlist`,`push_message`,`push_warn`,`send_backtest_result`,`send_backtest_trades`,`tdx_send_file`,`tdx_download_data`,`tdx_rename_sector`,`tdx_clear_sector` |

## 6. Phase 1~4（13 工具）重点验证矩阵

| Phase | 工具 | 验证点 | 成功标准 |
|---|---|---|---|
| P1 | `tdx_get_stock_trading_data` | GP字段返回 | `success=true` 且含请求字段 |
| P1 | `tdx_get_sector_trading_data` | BK字段返回 | 结构含 `Date/Value` 或最新值 |
| P1 | `tdx_get_market_trading_data` | SC字段返回 | 至少1个字段有非空值 |
| P2 | `tdx_send_file` | 文件推送前端 | TDX可打开文件/工具返回成功 |
| P2 | `tdx_download_data` | 数据下载 | 返回下载成功消息/结果对象 |
| P2 | `tdx_rename_sector` | 板块改名 | `get_user_sectors` 名称变化 |
| P2 | `tdx_clear_sector` | 清空成分股 | 板块仍在但成分清空 |
| P3 | `tdx_get_financial_snapshot` | 单股财务快照 | 返回字段集非空 |
| P3 | `tdx_get_financial_history` | 指定日财务 | 按 date 成功返回 |
| P3 | `tdx_get_f10_info` | F10附加信息 | `success=true` 且有内容 |
| P4 | `tdx_manage_subscription` | 订阅/退订/列表 | 三动作均返回合理结果 |
| P4 | `tdx_refresh_data` | 刷新cache/kline | 返回执行状态与结果 |
| P4 | `tdx_custom_formula_calc` | 自定义K线公式 | 支持则计算成功；不支持给出引导 |

## 7. 交互式测试步骤（核心场景）

> 每步执行后都要记录：MCP返回JSON、TDX前端截图、判定结论。

### 7.1 板块管理类

1) `create_watchlist({"block_code":"MCP_IT_001","block_name":"MCP交互测试板块","stock_codes":["600519","000001","000858"]})`  
预期：TDX“自定义板块”出现新板块并自动切换。  
2) `add_stocks_to_watchlist({"block_code":"MCP_IT_001","stock_codes":["300750","601318"],"show":true})`  
预期：前端成分增加。  
3) `delete_watchlist({"block_code":"MCP_IT_001"})`  
预期：板块消失。

### 7.2 消息推送类

1) `push_message({"message":"MCP测试消息|第1行|第2行"})`  
2) `push_warn({"stock_code":"600519","price":1500.0,"reason":"MCP测试预警","bs_flag":0})`  
预期：TDX出现消息/预警弹窗或提示记录。

### 7.3 回测可视化类

1) `send_backtest_result({"stock_code":"600519","time_list":["20250115","20250320","20250610","20250901"],"data_list":[["B"],["S"],["买入"],["HOLD"]],"count":1})`  
预期：K线图买卖点标记可见（B/S自动映射）。  
2) `send_backtest_trades({"stock_code":"600519","trades":[{"time":"20250115","price":1800,"signal":"buy","shares":100,"profit":0},{"time":"20250320","price":1950,"signal":"sell","shares":100,"profit":150}]})`  
预期：不足4笔会自动补齐；前端交易记录可视化成功。  
3) `run_backtest_and_send_to_tdx(...)`（若当前环境已注册）；若未注册，采用 `run_backtest_with_trades + send_backtest_*` 组合验证。

### 7.4 文件交互类

1) `tdx_send_file({"file_path":"mcp_tdx_report.html"})`  
2) `tdx_download_data({"stock_code":"688318","date":"20250101","data_type":"shareholder"})`  
预期：前端可打开文件；下载返回成功并在数据目录可查。

### 7.5 公式计算类（14工具）

按“总入口+快捷指标”执行：  
- 总入口：`tdx_calculate_indicator`、`tdx_screen_stocks`、`tdx_get_expert_signals`、`tdx_get_formula_data`  
- 快捷指标：`tdx_calculate_macd/kdj/rsi/boll/trix/dma/expma/dmi/cr/vr`  
预期：返回 `success=true` 且数据序列长度合理；若走 Python fallback，应记录 `source=python_fallback`。

## 8. 验证标准（表格化）

| 功能点 | 成功判定 | 失败判定 |
|---|---|---|
| MCP调用 | `success=true` 且关键字段齐全 | 报错/字段缺失/结构异常 |
| TDX前端响应 | 页面、弹窗、板块、标记与调用一致 | 前端无变化或显示错位 |
| 数据一致性 | 代码/名称/时间/字段与输入匹配 | 参数被错误转换或丢失 |
| 可回归性 | 二次执行结果稳定（允许时间差） | 高频随机失败且不可恢复 |

## 9. 异常处理与边界方案

- **TDX未启动/未登录**：先终止测试，启动客户端后重试冒烟。  
- **TdxQuant初始化失败**：重试1次；仍失败则记录环境诊断（路径、权限、版本）。  
- **订阅接口不支持**：记录 capability 降级信息，不判致命失败。  
- **公式API缺失**：按引导改用 `tdx_calculate_*` 或 `calculate_technical_indicators`。  
- **回测交易不足4条**：使用 `send_backtest_trades` 自动填充机制。  
- **文件类型不支持**：仅使用 `txt/pdf/html`。

## 10. 截图与留痕规范

建议每步至少1张图，命名：`step_序号_工具名_时间.png`。  
重点截图：
1. 板块创建后前端列表；
2. 消息与预警提示；
3. K线买卖信号标记；
4. 回测交易面板；
5. 文件在 TQ 浏览器打开界面。

---

## 11. 交付物

- 本方案文档：`TDX_FRONTEND_INTERACTIVE_TEST_PLAN.md`
- 执行记录表（建议另存）：每步参数、返回、截图、结论、备注
- 缺陷清单：按 P0/P1/P2 分级（参考 `MCP_TOOL_TEST_RESULTS.md` 风格）


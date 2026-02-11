# TDX-MCP 扩展方案与落地状态（v3）

> 基于通达信 TdxQuant SDK API 清单与 AKShare MCP 实际代码逐行对照；本版为 **2026-02-11** 状态更新。
> 历史基线：`available_tools` 在 2026-02-09 记录为 137；当前本地运行时实测为 152。

## 0. 本次更新摘要（2026-02-11）

- Phase 1~4 规划的 **13 个工具已全部落地**。
- 额外落地 1 个辅助工具：`tdx_list_available_fields(data_type)`。
- 文档原“2.3 C 类清单（19 个 API）”已全部落地并可调用。
- 审计发现：`get_financial_data()` 当前未检索到实际调用，原 B2 描述已过期。
- 本文档由“扩展计划”升级为“计划 + 落地状态 + 后续增强点”。

---

## 一、现状概览

### 1.1 架构

```
AI Client (Cursor/Kiro) ←→ MCP Protocol (stdio) ←→ AKShare MCP Server (FastMCP)
                                                         ↓
                                                    TdxQuant SDK (tqcenter)
                                                         ↓
                                                    通达信客户端终端
```

### 1.2 TDX 手册全量 API 清单（7 大模块，45 个 API）

| 模块 | API 数量 | API 列表 |
|------|---------|----------|
| Common 通用 | 12 | `initialize`, `subscribe_hq`, `unsubscribe_hq`, `get_subscribe_hq_stock_list`, `refresh_cache`, `refresh_kline`, `send_message`, `send_warn`, `send_file`, `send_bt_data`, `download_file`, `get_trading_dates` |
| Market 行情 | 7 | `get_market_data`, `get_market_snapshot`, `get_stock_info`, `get_divid_factors`, `get_ipo_info`, `get_more_info`, `get_gb_info` |
| Finance 财务 | 9 | `get_financial_data`, `get_financial_data_by_date`, `get_gpjy_value`, `get_gpjy_value_by_date`, `get_bkjy_value`, `get_bkjy_value_by_date`, `get_scjy_value`, `get_scjy_value_by_date`, `get_gp_one_data` |
| Sector 板块 | 3 | `get_sector_list`, `get_stock_list`, `get_stock_list_in_sector` |
| Custom Sector 自定义板块 | 6 | `get_user_sector`, `create_sector`, `delete_sector`, `rename_sector`, `send_user_block`, `clear_sector` |
| Formula 公式 | 7 | `formula_set_data_info`, `formula_set_data`, `formula_get_data`, `formula_format_data`, `formula_zb`, `formula_xg`, `formula_exp` |
| Bond/Futures 债券期货 | 1 | `get_cb_info` |

---

## 二、精确使用状态审计（2026-02-11）

### 分类说明

- **A 类 — 直接 MCP 工具**：TDX API 被封装为独立 MCP 工具，用户可直接调用。
- **B 类 — 内部数据源**：TDX API 在 `data_source.py` / helper 中作为内部能力使用。
- **C 类 — 未使用**：当前代码库中未检索到调用点。

### 2.1 A 类 — 直接 MCP 工具（已显著扩展）

当前 TDX 直连工具合计 **36 个**（运行时统计），覆盖如下模块：

- `tdx_integration.py`：8 个工具（消息/预警/板块管理/回测结果推送）
- `tdx_formula/`：14 个工具（指标/选股/专家系统/公式数据）
- `tdx_trading_data.py`：4 个工具（含 `tdx_list_available_fields`）
- `tdx_file_sector.py`：4 个工具
- `finance.py`（TDX 增强）：3 个工具
- `tdx_realtime.py`：3 个工具

### 2.2 B 类 — 内部数据源调用（当前主要调用集）

以下 API 在当前代码中作为内部数据源被调用（部分同时也有 A 类封装）：

- `initialize`
- `get_market_data`
- `get_market_snapshot`
- `get_stock_info`
- `get_divid_factors`
- `get_sector_list`
- `get_stock_list_in_sector`
- `get_trading_dates`
- `get_ipo_info`
- `get_cb_info`
- `get_gb_info`
- `get_stock_list(5)`

> 说明：原文档中将 `get_financial_data()` 归为 B2，但当前代码检索未发现实际调用点。

### 2.3 原 C 类清单（19 个 API）落地状态

`TDX_MCP_EXTENSION_PLAN.md` 原 2.3 列出的 19 个 API 现已全部落地为可调用工具：

| 原 C 类 API | 当前状态 | 主要实现位置 |
|------------|---------|-------------|
| `get_gpjy_value`, `get_gpjy_value_by_date` | ✅ 已落地 | `tools/tdx_trading_data.py` |
| `get_bkjy_value`, `get_bkjy_value_by_date` | ✅ 已落地 | `tools/tdx_trading_data.py` |
| `get_scjy_value`, `get_scjy_value_by_date` | ✅ 已落地 | `tools/tdx_trading_data.py` |
| `get_financial_data_by_date` | ✅ 已落地 | `tools/finance.py` |
| `get_gp_one_data` | ✅ 已落地 | `tools/finance.py` |
| `get_more_info` | ✅ 已落地 | `tools/finance.py` |
| `send_file`, `download_file` | ✅ 已落地 | `tools/tdx_file_sector.py` |
| `rename_sector`, `clear_sector` | ✅ 已落地 | `tools/tdx_file_sector.py` |
| `unsubscribe_hq`, `get_subscribe_hq_stock_list` | ✅ 已落地 | `tools/tdx_realtime.py` |
| `refresh_cache`, `refresh_kline` | ✅ 已落地 | `tools/tdx_realtime.py` |
| `formula_set_data`, `formula_format_data` | ✅ 已落地 | `tools/tdx_realtime.py` |

### 2.4 审计结论

```
原 2.3 C 类清单（19 个 API）: 已全部落地
Phase 1~4 计划工具（13 个） : 已全部落地
额外新增工具               : tdx_list_available_fields（1 个）
运行时工具总数             : 152（2026-02-11 本地实测）
```

待处理偏差：

- 文档历史描述中 `get_financial_data()` 的 B2 调用点与当前代码不一致（当前未检索到调用）。
- 场景文档（`scenario_*.md`）尚未覆盖 Phase 1~4 新增工具调用示例。


---

## 三、扩展方案（已落地）

### Phase 1：通达信独有交易数据（已完成）

> 状态：✅ 已落地（`tdx_trading_data.py`）

> 目标：封装 GP/BK/SC 系列交易数据 — 这是 TDX 本地数据包中 AkShare/Tushare 无法替代的独有数据。

#### 新建文件

```
packages/akshare-mcp/src/akshare_mcp/tools/tdx_trading_data.py
```

#### 工具 1：`tdx_get_stock_trading_data` — 股票交易数据

```python
def tdx_get_stock_trading_data(
    stock_codes: list[str],   # 股票代码列表，如 ["600519", "000001"]
    fields: list[str],        # 字段列表，如 ["GP1", "GP3", "GP6"]（注意：无前导零）
    start_date: str = "",     # 起始日期 YYYYMMDD，为空则取最新
    end_date: str = ""        # 结束日期 YYYYMMDD
) -> dict
```

- 底层 API：`get_gpjy_value()` / `get_gpjy_value_by_date()`
- 覆盖字段（GP1~GP46 精选，API 调用时使用无前导零的简写）：

| 字段 | 含义 | 应用场景 |
|------|------|----------|
| GP1 | 股东户数 | 筹码集中度分析 |
| GP2 | 龙虎榜买卖 | 游资动向追踪 |
| GP3 | 融资融券余额 | 杠杆资金情绪 |
| GP4 | 大宗交易 | 机构动向 |
| GP5 | 增减持 | 股东行为分析 |
| GP6 | 陆股通持股量 | 外资动向 |
| GP7 | 陆股通净买入 | 北向资金流向 |
| GP15 | 涨跌停状态/封单 | 涨停板分析 |
| GP16 | 总市值 | 市值筛选 |
| GP21 | 股息率 | 红利策略 |

- 实现逻辑：
  - 日期范围查询（start_date/end_date 非空）→ `get_gpjy_value(start_time=start_date, end_time=end_date)`
  - 单日期/最新查询（仅 start_date 或均为空）→ `get_gpjy_value_by_date(year=int, mmdd=int)`，需将 YYYYMMDD 字符串拆分为 `year`(int) 和 `mmdd`(int) 两个整数参数；均为空时传 `year=0, mmdd=0` 取最新

#### 工具 2：`tdx_get_sector_trading_data` — 板块交易数据

```python
def tdx_get_sector_trading_data(
    sector_codes: list[str],  # 板块代码列表
    fields: list[str],        # 字段列表，如 ["BK5", "BK9", "BK12"]（无前导零）
    start_date: str = "",
    end_date: str = ""
) -> dict
```

- 底层 API：`get_bkjy_value()` / `get_bkjy_value_by_date()`
- 覆盖字段（BK5~BK19）：板块PE/PB、涨跌家数、涨停家数、融资融券、陆股通等
- 日期参数处理逻辑同工具 1

#### 工具 3：`tdx_get_market_trading_data` — 市场交易数据

```python
def tdx_get_market_trading_data(
    fields: list[str],        # 字段列表，如 ["SC1", "SC2", "SC3"]（注意：需确认 SC 系列是否有前导零）
    start_date: str = "",
    end_date: str = ""
) -> dict
```

- 底层 API：`get_scjy_value()` / `get_scjy_value_by_date()`
- 覆盖字段（SC01~SC42 精选）：全市场融资融券、陆股通、涨跌停、股指期货净持仓、ETF申赎等
- 日期参数处理逻辑同工具 1

#### 与现有工具的联动增强

| 现有 MCP 工具 | 可引入的 Phase 1 数据 |
|--------------|---------------------|
| `generate_daily_report()` | SC 系列市场数据（涨跌停、融资融券、陆股通） |
| `sentiment_manager()` | SC03/SC04 涨跌停数据增强情绪分析 |
| `sector_manager()` | BK 系列板块估值/资金数据 |
| `smart_stock_diagnosis()` | GP 系列股东/资金/融资融券数据 |

---

### Phase 2：文件交互与板块管理补全（已完成）

> 状态：✅ 已落地（`tdx_file_sector.py`）

#### 新建文件

```
packages/akshare-mcp/src/akshare_mcp/tools/tdx_file_sector.py
```

#### 工具 4：`tdx_send_file` — 发送文件到客户端

```python
def tdx_send_file(
    file_path: str            # 文件路径（支持 txt/pdf/html，类型由扩展名自动识别）
                              # 放于 PYPlugins/file/ 下时可仅传文件名，否则需绝对路径
) -> dict
```

- 底层 API：`send_file(file: str)`（单参数，仅接受文件路径）
- 应用场景：AI 生成的分析报告（HTML）推送到通达信 TQ 策略数据浏览器

#### 工具 5：`tdx_download_data` — 下载特定数据文件

```python
def tdx_download_data(
    stock_code: str,
    date: str,
    data_type: str = "shareholder"  # "shareholder" 或 "etf_redemption"
) -> dict
```

- 底层 API：`download_file()`

#### 工具 6：`tdx_rename_sector` — 重命名自定义板块

```python
def tdx_rename_sector(block_code: str, new_name: str) -> dict
```

- 底层 API：`rename_sector()`

#### 工具 7：`tdx_clear_sector` — 清空板块成份股

```python
def tdx_clear_sector(block_code: str) -> dict
```

- 底层 API：`clear_sector()`

#### AI 报告推送闭环

```
AI 分析 → 生成 HTML 报告 → 写入 PYPlugins/file/ → tdx_send_file() → 通达信 TQ 策略数据浏览器打开
```

---

### Phase 3：财务数据增强（已完成）

> 状态：✅ 已落地（`finance.py`）

#### 在现有文件中扩展

```
packages/akshare-mcp/src/akshare_mcp/tools/finance.py  # 扩展
```

#### 工具 8：`tdx_get_financial_snapshot` — 单只股票最新财务快照

```python
def tdx_get_financial_snapshot(
    stock_code: str
) -> dict
```

- 底层 API：`get_gp_one_data()`（注意：虽然函数名含 `gp`，但字段使用 `GO` 前缀，GO1~GO47）
- 当前实现返回全量快照字段，暂未提供 `field_list` 过滤参数
- 与现有 `get_financials()` 的区别：`get_gp_one_data()` 一次返回单股最新全部字段，更快；`get_financial_data()` 支持多股+时间范围查询

#### 工具 9：`tdx_get_financial_history` — 指定日期财务数据

```python
def tdx_get_financial_history(
    stock_codes: list[str],
    field_list: list[str],
    date: str  # YYYYMMDD，内部转换为 year: int 和 mmdd: int 传给底层 API
) -> dict
```

- 底层 API：`get_financial_data_by_date(stock_list, field_list, year: int, mmdd: int)`
- 补充现有 `get_financial_data()` 的按日期精确查询能力
- 日期转换示例：`date="20250615"` → `year=2025, mmdd=615`

#### 工具 10：`tdx_get_f10_info` — F10 附加信息

```python
def tdx_get_f10_info(stock_code: str, info_type: int = 0) -> dict
```

- 底层 API：`get_more_info()`

---

### Phase 4：行情订阅与缓存管理（已完成）

> 状态：✅ 已落地（`tdx_realtime.py`）

#### 新建文件

```
packages/akshare-mcp/src/akshare_mcp/tools/tdx_realtime.py
```

#### 工具 11：`tdx_manage_subscription` — 行情订阅管理

```python
def tdx_manage_subscription(
    action: str,              # "subscribe" / "unsubscribe" / "list"
    stock_codes: list[str] = None
) -> dict
```

- 底层 API：`unsubscribe_hq()`, `get_subscribe_hq_stock_list()`
- 注意：`subscribe_hq()` 已在 `data_source.py` 中有基础实现（B类），此工具补全取消订阅和查询功能

> MCP 协议是请求-响应模式，不支持持续推送。订阅后通过 `check_all_alerts()` 轮询检查。

#### 工具 12：`tdx_refresh_data` — 刷新数据缓存

```python
def tdx_refresh_data(
    refresh_type: str = "all"  # "cache" / "kline" / "all"
) -> dict
```

- 底层 API：`refresh_cache()`, `refresh_kline()`

#### 工具 13：`tdx_custom_formula_calc` — 自定义K线公式计算

```python
def tdx_custom_formula_calc(
    stock_code: str,
    kline_data: list[dict],   # 自定义K线数据
    formula_name: str = "MACD",
    formula_args: str = ""
) -> dict
```

- 底层 API：`formula_format_data()` + `formula_set_data()` + `formula_zb()`
- 允许用户传入自定义K线数据进行公式计算（现有工具只能用 TDX 内置K线）

---

## 四、B 类 API 的潜在增强点

虽然以下 API 已在内部使用，但存在增强空间：

| TDX API | 当前使用方式 | 潜在增强 |
|---------|------------|---------|
| `get_stock_list(5)` | `helpers.py` 中仅用 `market=5`（沪深A股） | TDX 支持 30+ 种 market 类型（ETF/基金/港股通/期货/期权等），可扩展为通用的市场证券列表工具 |
| `get_financial_data()` | 当前代码未检索到直接调用 | 可新增“TDX 584 字段批量财务查询”工具，补齐历史 B2 设计 |
| `subscribe_hq()` | 同时存在于 `data_source.py`（内部）与 `tdx_realtime.py`（A 类工具） | 可增强为订阅状态缓存、幂等重试、批量订阅诊断 |

---

## 五、实现结果与后续计划

### 5.1 文件结构

```
packages/akshare-mcp/src/akshare_mcp/tools/
├── tdx_integration.py          # 现有：消息推送、板块管理、回测可视化（8 个 MCP 工具）
├── tdx_formula/                # 现有：公式计算（14 个 MCP 工具，包结构）
│   ├── __init__.py
│   ├── api.py                  # 核心 MCP 工具注册
│   ├── shortcuts.py            # 快捷指标计算工具
│   ├── fallback.py             # Python 回退计算
│   └── utils.py                # 工具函数
├── tdx_trading_data.py         # Phase 1：GP/BK/SC 交易数据 + 字段查询（4 个工具）
├── tdx_file_sector.py          # Phase 2：文件交互 + 板块管理补全（4 个工具）
├── finance.py                  # Phase 3：财务数据增强（3 个工具）
└── tdx_realtime.py             # Phase 4：行情订阅与缓存管理（3 个工具）
```

### 5.2 落地状态

| 阶段 | 内容 | 覆盖原 C 类 API | 工具数（现状） | 状态 |
|------|------|----------------|---------------|------|
| Phase 1 | GP/BK/SC 交易数据 | 6 个 | 4（含字段查询辅助） | ✅ 已完成 |
| Phase 2 | 文件交互 + 板块补全 | 4 个 | 4 | ✅ 已完成 |
| Phase 3 | 财务数据增强 | 3 个 | 3 | ✅ 已完成 |
| Phase 4 | 行情订阅与缓存 | 6 个 | 3 | ✅ 已完成 |
| **合计** | | **19 个** | **14** | **✅ 全部完成** |

### 5.3 统一实现模式

已落地工具遵循现有代码的统一模式（简化示例）：

```python
@mcp.tool()
def tdx_xxx(...) -> dict:
    """工具描述"""
    try:
        if not data_source.is_tdx_available():
            return {"success": False, "error": "TdxQuant 不可用，请启动通达信客户端"}
        tq = data_source.get_tdxquant()
        tdx_codes = [data_source._convert_to_tdx_code(c) for c in codes]
        result = tq.xxx(...)
        return {"success": True, "data": result, "source": "tdxquant"}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

#### 日期参数转换辅助函数

`by_date` 系列 API 使用 `year: int` 和 `mmdd: int` 参数，需要统一的转换函数：

```python
def _parse_date_to_year_mmdd(date_str: str) -> tuple[int, int]:
    """将 YYYYMMDD 字符串转换为 (year, mmdd) 整数元组
    
    示例：'20250615' → (2025, 615)
          ''         → (0, 0)  # 取最新数据
    """
    if not date_str:
        return 0, 0
    return int(date_str[:4]), int(date_str[4:])
```

---

## 六、数据流全景（扩展后）

```
┌──────────────────────────────────────────────────────────────┐
│                      AI Client (用户)                         │
├──────────────────────────────────────────────────────────────┤
│  分析诊断 │ 选股筛选 │ 回测策略 │ 风险管理 │ 组合优化         │
├──────────────────────────────────────────────────────────────┤
│                    MCP Server (FastMCP)                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  数据获取 (TDX → MCP)                操作推送 (MCP → TDX)    │
│  ─────────────────────                ───────────────────    │
│  A 类 直接工具:                       A 类 直接工具:          │
│  ● 公式计算（指标/选股/专家系统）      ● 消息/预警推送         │
│  ● 股票交易数据 GP系列 [已上线]       ● 自定义板块管理        │
│  ● 板块交易数据 BK系列 [已上线]       ● 回测结果可视化        │
│  ● 市场交易数据 SC系列 [已上线]       ● 文件推送 [已上线]     │
│  ● 财务快照/历史 [已上线]             ● 板块重命名/清空       │
│  ● F10附加信息 [已上线]                  [已上线]             │
│  ● 自定义公式计算 [已上线]            ● 订阅管理 [已上线]     │
│                                                              │
│  B 类 内部数据源:                                             │
│  ● K线/行情/快照 (data_source.py)                            │
│  ● 财务数据 584字段 (finance.py)                              │
│  ● 板块/成份股列表 (data_source.py)                           │
│  ● 股票列表 (helpers.py)                                     │
│  ● 可转债/IPO/股本/除权因子 (data_source.py)                  │
│  ● 交易日历 (data_source.py)                                 │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│                TdxQuant SDK (tqcenter)                        │
├──────────────────────────────────────────────────────────────┤
│                通达信客户端终端                                 │
│  ● TQ策略管理器（消息/预警/回测图表）                           │
│  ● TQ策略数据浏览（文件查看）[已上线]                          │
│  ● 自定义板块（选股结果）                                      │
│  ● K线图表（回测信号叠加）                                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 七、注意事项

### 7.1 TDX 环境依赖

- 所有 TDX API 调用前必须确保通达信客户端已启动并登录
- GP/BK/SC 系列数据需要在客户端中先下载「盘后数据包」
- 公式系统需要在通达信 `PYPlugins/user` 环境下才能完整挂载

### 7.2 降级策略

- TDX 可用 → 优先使用 TDX 本地数据（速度快、字段全）
- TDX 不可用 → 降级到 AkShare / Tushare（如果有对应数据源）
- 全部不可用 → 返回明确错误信息（`success=false`）

### 7.3 代码格式转换

TDX 使用 `600519.SH` 格式，MCP 工具统一使用 `600519` 六位数字格式。复用现有的 `_convert_to_tdx_code()` 方法。

### 7.4 GP/BK/SC 字段辅助

已新增辅助工具 `tdx_list_available_fields(data_type)`，用于查询 GP/BK/SC 可用字段及含义（100+ 字段）。

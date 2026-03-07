## 项目上下文摘要（修复171工具测试问题）
生成时间：2026-03-06

### 1. 相似实现分析
- **实现1**: `packages/akshare-mcp/src/akshare_mcp/tools/vector.py`
  - `search_by_kline` 已实现“优先行业候选、无行业则全市场候选”的降级模式
  - 可复用到 `search_similar_stocks`，避免因 `industry` 为空直接失败
- **实现2**: `packages/akshare-mcp/src/akshare_mcp/tools/valuation.py`
  - `get_historical_valuation` 已有 `source_chain/fallback_reason/data_quality` 审计结构
  - 适合在 `stock_quotes` 查询异常时保留审计链并继续降级
- **实现3**: `packages/akshare-mcp/src/akshare_mcp/tools/quant.py`
  - `SUPPORTED_FACTORS` 已维护 canonical factor + aliases 元数据
  - 应由 `_normalize_factor_name` 统一别名映射，避免上层工具重复判断
- **实现4**: `packages/akshare-mcp/src/akshare_mcp/tools/managers/*.py`
  - 多个 manager 已采用 `_normalize_kwargs/_normalize_manager_kwargs` 兼容 `kwargs="{}"` 与别名参数
  - 本轮修复应沿用同一兼容模式

### 2. 项目约定
- **返回结构**: 统一使用 `ok(...) / fail(...)`
- **注册模式**: `register(mcp)` 或 `register_xxx_manager(mcp)`
- **参数兼容**: manager 层优先兼容 `kwargs` JSON 字符串、`code/Code/stock_code/symbol`
- **测试模式**: `tests/test_p0_regressions.py` 中使用 `_DummyMCP + monkeypatch + FakeDB`

### 3. 可复用组件清单
- `akshare_mcp.utils.ok/fail`
- `quant.py -> SUPPORTED_FACTORS`
- `vector.py -> search_by_kline` 的候选池降级策略
- `research_manager.py / sector_manager.py / alerts_manager.py` 的 kwargs 归一模式

### 4. 测试策略
- 在 `packages/akshare-mcp/tests/test_p0_regressions.py` 追加回归测试
- 覆盖范围：
  - 正常路径：参数兼容成功、过滤命中、状态保持
  - 边界路径：行业为空、limit 为字符串、单 code 快扫
  - 错误恢复：DB 字段缺失降级、空异常信息回填默认错误文案
- 验证方式：优先单文件 `pytest packages/akshare-mcp/tests/test_p0_regressions.py`

### 5. 依赖与集成点
- 数据访问：`get_db()`, `db.acquire()`, `db.get_stock_info/get_financials/get_klines`
- 内部工具依赖：`fund_flow`, `news`, `market.quote`, `market_blocks`
- 无新增第三方依赖，保持现有测试框架不变

### 6. 关键风险点
- `stock_quotes` 查询异常不能再导致整体失败
- factor alias 归一会影响 `calculate_factor`、IC、回测、OOS 校验等多处入口
- manager 更新逻辑需避免破坏现有返回结构
- 告警更新若修改过多字段，需避免状态被隐式改写


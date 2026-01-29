# 数据源优化方案 - 实施复盘与可行性评估

## 目标与范围

- 方案选择：以 EPS/ROE 类指标为主，财务数据统一走 akshare-mcp。
- 范围：财务指标、北向资金、行情/K线（不强制统一，保留多源兜底）。

## 现状对比（已落地）

### 数据源与工具

- AKShare 适配器统一调用 akshare-mcp 工具：`get_batch_quotes` / `get_kline` / `get_financials` / `get_north_fund` / `get_stock_list`
- 兼容别名补齐：`get_realtime_quotes` -> `get_batch_quotes`；`get_north_fund_flow` -> `get_north_fund`
- 数据源优先级：财务/北向资金优先 `akshare`

### 数据模型与存储

- `financials` 表新增 `bvps`、`roa`、`revenue_growth`、`profit_growth`，字段允许为 `NULL`
- `FinancialData` 类型与写入逻辑统一为可空字段，避免缺失值阻断写入
- `upsert/batchUpsert` 已写入新增字段

### 同步与校验

- 财务完整性校验仅要求 `code/reportDate/eps/roe`
- EPS/ROE 允许为 0，其余字段走可空校验
- 估值与基本面主链路已对可空字段兜底（`?? 0/?? null`）

## 关键修复与策略补充

- 代理规避：akshare-mcp 子进程自动清理本地代理（127.0.0.1:7890）；支持 `AKSHARE_MCP_PROXY_MODE=disable` / `AKSHARE_MCP_DISABLE_PROXY=1`
- 行情降级：`get_batch_quotes` 在 akshare 上游不稳定时，回退 DataSource/Sina/Tencent，避免整体失败
- 北向资金过期降级：无最新数据时返回 `*_stale`，允许回填；可用 `NORTH_FUND_FAST_MODE=1` 快速模式
- 北向资金单位策略：根据中位数识别单位并归一到“元”，避免累计值重复换算；异常 scale 写入 warnings
- 清理重同步：`resync-north-fund.ts` 已重建 `north_fund`
- 行业/板块同步：新增 `sync-stock-industry.ts`，支持分批补齐 sector/industry

## 最新审计结果（2026-01-28）

### MCP 工具可用性（akshare-mcp）

- `get_stock_list`：✅ 返回 5475 只
- `get_kline`：✅ 返回 100 条（样本来自 baostock fallback）
- `get_financials`：✅
- `get_dragon_tiger`：✅ 返回 81 条
- `get_batch_quotes`：✅（上游偶发断开时自动回退）
- `get_north_fund`：✅ 返回 30 条（stale 历史数据）
- `get_margin_data`：❌ 无数据

### 数据库覆盖概览

- `stocks`：5,187 只（sector/industry 已填充 1,353 只，缺失 3,834 只；行业/板块各 104 类）
- `kline_1d`：1,284,696 条 / 覆盖 5,182 只 / 2024-11-06 ~ 2026-01-26
- `financials`：5,187 条 / 覆盖 5,187 只 / 2025-09-30 ~ 2025-12-31（营收/净利常为 0 需复核映射）
- `stock_quotes`：5,178 条 / 覆盖 5,178 只 / 2026-01-28
- `dragon_tiger`：1,636 条 / 2025-12-29 ~ 2026-01-27
- `north_fund`：365 条 / 2023-02-01 ~ 2024-09-27 / 累计净流入 -3.65 亿元
- `margin_data`：107,484 条 / 覆盖 3,589 只 / 2012-12-14 ~ 2026-01-26
- `block_trades`：0 条

### 同步补全结果

- `sync-missing-data.ts financials 200`：缺失 0，覆盖 5,187 只

## 可行度评估

- 可行度：高（核心链路已落地，akshare-mcp 覆盖 EPS/ROE/BVPS/ROA）
- 数据完整性：中（营收/净利/增长类字段在 akshare-mcp 中可能为空）
- 业务影响：营收/净利驱动的指标或选股逻辑会降级，需要补充数据源或延后
- 风险：北向资金为历史回填（stale），行情上游偶发断开；行业信息仍需补齐

## 待确认/待整理

1. 是否引入 Tushare/HKEX 等来源刷新北向资金最新数据
2. 行业/板块补齐：剩余 3,834 只需分批同步
3. 财务营收/净利映射仍为 0 的原因
4. 大宗交易 `block_trades` 数据源与同步策略

## 验证建议

- 复测：`$env:AKSHARE_MCP_PROXY_MODE='disable'; $env:NORTH_FUND_FAST_MODE='1'; npx tsx packages/mcp-server-compact/scripts/audit-data-sources.ts`
- 行业补齐：`npx tsx packages/mcp-server-compact/scripts/sync-stock-industry.ts 200 80`
- 北向资金重建：`npx tsx packages/mcp-server-compact/scripts/resync-north-fund.ts 365`

---

**文档更新**: 2026-01-28  
**状态**: 已修复 akshare-mcp 代理/行情降级，北向资金单位归一并重建，行业同步进行中

---
name: akshare-quant-data-engineering
description: 量化数据工程：数据源确认、质量检查、缺口补齐与缓存策略。
capability_tier: hybrid
runtime_status: executable
product_surfaces: ["mcp"]
artifacts: []
backing_tools: ["run_skill"]
backing_managers: ["skills_executor"]
regulatory_scope: ["data_lineage", "model_governance"]
role_tags: ["quant", "research"]
last_runtime_verified_at: "2026-04-19"
---

# 目标
确保研究与回测所需数据可靠可用，并建立数据质量检查流程。

# 使用流程
- 数据源确认：说明数据来源与更新频率（AKShare/本地DB）。
- 数据拉取：用 `get_kline_data`、`get_realtime_quote` 等获取数据。
- 质量检查：优先用 `data_quality_workflow` 检查缺失值、重复、异常跳变；需要适配器级校验时用 `data_validation`。
- 实验留痕：研究数据口径、样本窗口和复现实验元数据使用 `experiment_tracker`。
- 数据补齐：若缺口明显，提示使用数据同步/预热工具（`data_warmup`）。
- 结果标注：输出数据完整性与限制说明。

# 失败与兜底
- 数据源不可用：提示更换数据源或延后验证。
- 历史数据不足：缩短区间或使用更高流动性标的。
- 工具分流：`data_warmup` 失败时按 `sync_kline_data -> batch_sync_klines -> data_sync_manager(action=sync)` 顺序补数。

# 参考
- 数据预热：`data_warmup`。

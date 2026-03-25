# Vector P0-P4 Acceptance

目的：
- 把 `P0-P4` 的实现状态落到一套可重复执行的生产验收脚本。
- 直接验证 live DB 上的 schema、统一向量层、回填、snapshot、benchmark 和 smoke search。

入口脚本：
- [scripts/vector_p0_p4_acceptance.py](/Users/mac/Desktop/股票/scripts/vector_p0_p4_acceptance.py)

执行前提：
- 已配置 `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME`
- 数据库可连通，且允许当前账号执行表初始化与写入
- 如果希望 `P2` 市场文本 phase 真正通过，文本 embedding provider 需要可用；否则 `market_doc_chunks` 只能落文档与 chunk，无法形成 dense profile

默认执行内容：
1. `P0`：检查 schema 漂移修复结果
2. `P1`：重建策略 unified vector index，并跑 health / benchmark / smoke
3. `P2`：回填 `market_doc_chunks`，构建 snapshot，跑 benchmark / hybrid smoke
4. `P3`：回填 `kline_pattern_embeddings`，构建 snapshot，跑 benchmark / smoke
5. `P4`：回填 `stock_profile_embeddings` 与 `factor_candidate_embeddings`，构建 snapshot，跑 benchmark / smoke

默认输出：
- JSON 报告：`reports/vector-acceptance/vector_p0_p4_acceptance_<tag>.json`
- Markdown 摘要：`reports/vector-acceptance/vector_p0_p4_acceptance_<tag>.md`

推荐命令：

```bash
python scripts/vector_p0_p4_acceptance.py --code-limit 20 --sample-size 10 --top-k 5
```

如果只想先验证 schema 与环境：

```bash
python scripts/vector_p0_p4_acceptance.py \
  --skip-strategy \
  --skip-market-docs \
  --skip-kline \
  --skip-stock-profiles \
  --skip-factor-candidates
```

如果只想做不落库的预演：

```bash
python scripts/vector_p0_p4_acceptance.py --dry-run
```

退出码约定：
- `0`：通过，或通过但带 warning
- `1`：存在 failure
- `2`：没有 failure，但存在 skipped，说明当前环境数据不足，不能判定为完整验收通过

判定标准：
- `P0`
  - `stocks.stock_code`、`financials.stock_code` 在库中存在
  - `stock_quotes.change_amt / prev_close / mkt_cap` 与兼容别名列存在
  - `vector_collections / vector_profiles / vector_index_snapshots / vector_index_items / market_doc_chunks` 存在
  - default collections 已注册
- `P1`
  - `strategy_behavior` 能完成 rebuild
  - unified health 返回 active index
  - exact vs ANN benchmark 可运行
- `P2`
  - `market_documents + market_doc_chunks + vector_profiles` 成功写入
  - snapshot 可构建
  - hybrid search smoke 可返回结果
- `P3`
  - `kline_pattern_windows + vector_profiles` 成功写入
  - snapshot / benchmark / smoke 可运行
- `P4`
  - `stock_profile_embeddings` 和 `factor_candidate_embeddings` 成功写入
  - snapshot / benchmark / smoke 可运行

注意：
- `skipped` 不等于通过。通常表示当前库里缺少待处理源数据，例如没有策略、没有候选因子、没有可用文档。
- `passed_with_warnings` 最常见于 `pgvector` 未启用但 fallback 仍可运行。若要把 `pgvector` 作为硬门槛，执行时加 `--require-pgvector`。

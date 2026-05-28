# S05 · 资金流/北向/龙虎榜

- **判定**: ⚠️ 通过 (Pass=1 / Degraded=2 / Fail=0)

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `get_north_fund(10d)` | ⚠️ Degraded | 4 源全跪(north_fund_flow stale + tushare/hkex/eastmoney empty),items=[],envelope 完整 6 quality checks。**§2.1 政策性不可解 RFC-001** |
| `get_dragon_tiger()` | ⚠️ Degraded | sina+eastmoney 双跪 5/15→5/20 6 个交易日全 unavailable,fallback_reason 详尽列出 12 行,`age_seconds=553771`(6.4 天),quality_gate freshness_sla failed warning |
| `get_sector_fund_flow(top5)` | ✅ Pass | 5 个板块完整(半导体/银行/电池/油气/能源金属),db.market_blocks fallback,envelope 完整。**§4.5.5 db_cache 残缺 warning 完美** |

## v1 → v2 Delta
- ⚠️ §2.1 北向资金 4 源全跪 — 政策性,RFC-001 已说明(2024-08-19 后 NET_DEAL_AMT 全 null)
- ⚠️ §5.5 龙虎榜 sina+eastmoney 双跪 — 政策性
- ✅ get_sector_fund_flow envelope + 真实数据(db.market_blocks 提供 fallback)

# Vector P0-P4 Acceptance Report

- generated_at: 2026-03-25T01:49:43.096906+00:00
- overall_status: incomplete
- exit_code: 2
- pgvector_enabled: True
- vector_backend: pgvector

## Phases

### p0_schema

- status: passed
- summary: tables_missing=0 columns_missing=0 collections_missing=0 pgvector=on

### p1_strategy

- status: passed
- summary: strategies=20 built_profiles=20 collection=strategy_behavior_embeddings

### p2_market_docs

- status: skipped
- summary: docs=0 chunks=0 profiles=0

### p3_kline_patterns

- status: passed
- summary: windows=5 profiles=5

### p4_stock_profiles

- status: passed
- summary: processed_codes=5 profiles=5

### p4_factor_candidates

- status: passed
- summary: processed_records=50 profiles=50

# Vector P0-P4 Acceptance Report

- generated_at: 2026-03-25T01:40:33.078071+00:00
- overall_status: failed
- exit_code: 1
- pgvector_enabled: True
- vector_backend: pgvector

## Phases

### p0_schema

- status: passed
- summary: tables_missing=0 columns_missing=0 collections_missing=0 pgvector=on

### p1_strategy

- status: failed
- summary: operator does not exist: integer = text
HINT:  No operator matches the given name and argument types. You might need to add explicit type casts.

### p2_market_docs

- status: failed
- summary: docs=56 chunks=56 profiles=0

### p3_kline_patterns

- status: failed
- summary: invalid input for query argument $3: '2026-03-23' ('str' object has no attribute 'toordinal')

### p4_stock_profiles

- status: failed
- summary: could not determine data type of parameter $1

### p4_factor_candidates

- status: failed
- summary: could not determine data type of parameter $1

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

export UD_BENCH_RUNS="${UD_BENCH_RUNS:-3}"

echo "━━━ Unified Decision Verification ━━━"
echo "Benchmark runs: $UD_BENCH_RUNS"
echo ""

echo "▸ 运行 BFF assistant 测试（含真实 HTTP / 登录态 / snapshot / AppModule smoke）..."
(cd "$ROOT_DIR" && npm run test:assistant -w apps/bff)

echo ""
echo "▸ 运行统一决策 benchmark 基线..."
(cd "$ROOT_DIR" && npm run verify:unified-decision-benchmark)

echo ""
echo "✅ Unified decision verification passed"

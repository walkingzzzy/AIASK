#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORT_DIR="$ROOT_DIR/reports/performance"
LOG_DIR="$REPORT_DIR/logs"

PORT="${UD_BENCH_PORT:-3301}"
AUTO_START="${UD_BENCH_AUTO_START:-1}"
HARNESS_MODE="${UD_BENCH_HARNESS_MODE:-1}"
BASE_URL="${1:-${BFF_BASE_URL:-http://127.0.0.1:${PORT}/api}}"
RUNS="${UD_BENCH_RUNS:-5}"
CODE="${UD_BENCH_CODE:-600519}"
STYLE="${UD_BENCH_STYLE:-balanced}"
LEGACY_MODE="${UD_BENCH_LEGACY_MODE:-false}"
USERNAME="${BFF_BENCH_USERNAME:-demo}"
PASSWORD="${BFF_BENCH_PASSWORD:-demo123}"

AVG_THRESHOLD="${UD_BENCH_AVG_MS:-2500}"
P95_THRESHOLD="${UD_BENCH_P95_MS:-4500}"
MAX_THRESHOLD="${UD_BENCH_MAX_MS:-7000}"

REPORT_JSON="$REPORT_DIR/unified-decision-benchmark.json"
REPORT_MD="$REPORT_DIR/unified-decision-benchmark.md"
START_LOG="$LOG_DIR/unified-decision-bff.log"

mkdir -p "$REPORT_DIR" "$LOG_DIR"

APP_PID=""
cleanup() {
  if [[ -n "${APP_PID}" ]] && kill -0 "${APP_PID}" >/dev/null 2>&1; then
    kill "${APP_PID}" >/dev/null 2>&1 || true
    wait "${APP_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "━━━ Unified Decision Benchmark Baseline ━━━"
echo "Base URL: $BASE_URL"
echo "Runs: $RUNS  Code: $CODE  Style: $STYLE  LegacyMode: $LEGACY_MODE"
echo ""

if [[ "$AUTO_START" == "1" ]]; then
  echo "▸ 构建并启动统一决策基准实例..."
  (cd "$ROOT_DIR" && npm run build -w apps/bff >/dev/null)
  if [[ "$HARNESS_MODE" == "1" ]]; then
    (cd "$ROOT_DIR" && npm exec -w apps/bff -- node -r ts-node/register scripts/unified-decision-benchmark-harness.ts --port="$PORT" >"$START_LOG" 2>&1) &
  else
    (cd "$ROOT_DIR" && BFF_PORT="$PORT" npm run start -w apps/bff >"$START_LOG" 2>&1) &
  fi
  APP_PID=$!

  for _ in $(seq 1 60); do
    if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if ! curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
    echo "❌ BFF 未能在预期时间内启动，日志: $START_LOG"
    exit 1
  fi
else
  echo "▸ 使用外部已运行的 BFF 实例"
fi

echo "▸ 执行统一决策基准测试..."
if ! (cd "$ROOT_DIR" && npm exec -w apps/bff -- node scripts/unified-decision-benchmark.mjs \
  --base-url="$BASE_URL" \
  --runs="$RUNS" \
  --code="$CODE" \
  --style="$STYLE" \
  --legacy-mode="$LEGACY_MODE" \
  --username="$USERNAME" \
  --password="$PASSWORD" >"$REPORT_JSON"); then
  echo "❌ benchmark 执行失败，请检查 $REPORT_JSON 或 $START_LOG"
  exit 1
fi

export REPORT_JSON REPORT_MD AVG_THRESHOLD P95_THRESHOLD MAX_THRESHOLD BASE_URL RUNS CODE STYLE LEGACY_MODE
node <<'EOF'
const fs = require('node:fs');

const reportPath = process.env.REPORT_JSON;
const markdownPath = process.env.REPORT_MD;
const avgThreshold = Number(process.env.AVG_THRESHOLD);
const p95Threshold = Number(process.env.P95_THRESHOLD);
const maxThreshold = Number(process.env.MAX_THRESHOLD);

const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
const summary = report.summary || {};
const failures = [];

if ((summary.failureCount || 0) > 0) {
  failures.push(`存在 ${summary.failureCount} 次失败请求`);
}
if ((summary.avgMs || 0) > avgThreshold) {
  failures.push(`avgMs=${summary.avgMs} 超过阈值 ${avgThreshold}`);
}
if ((summary.p95Ms || 0) > p95Threshold) {
  failures.push(`p95Ms=${summary.p95Ms} 超过阈值 ${p95Threshold}`);
}
if ((summary.maxMs || 0) > maxThreshold) {
  failures.push(`maxMs=${summary.maxMs} 超过阈值 ${maxThreshold}`);
}

const lines = [
  '# Unified Decision Benchmark Baseline',
  '',
  `- Base URL: ${process.env.BASE_URL}`,
  `- Runs: ${process.env.RUNS}`,
  `- Code: ${process.env.CODE}`,
  `- Style: ${process.env.STYLE}`,
  `- Legacy Mode: ${process.env.LEGACY_MODE}`,
  '',
  '| Metric | Value | Threshold |',
  '|---|---:|---:|',
  `| avgMs | ${summary.avgMs ?? '-'} | <= ${avgThreshold} |`,
  `| p95Ms | ${summary.p95Ms ?? '-'} | <= ${p95Threshold} |`,
  `| maxMs | ${summary.maxMs ?? '-'} | <= ${maxThreshold} |`,
  `| failureCount | ${summary.failureCount ?? '-'} | = 0 |`,
  '',
];

if (failures.length) {
  lines.push('## Status', '', 'FAILED', '', '## Reasons', ...failures.map((item) => `- ${item}`));
} else {
  lines.push('## Status', '', 'PASSED');
}

fs.writeFileSync(markdownPath, `${lines.join('\n')}\n`, 'utf8');

console.log(`avgMs=${summary.avgMs} p95Ms=${summary.p95Ms} maxMs=${summary.maxMs} failureCount=${summary.failureCount}`);
if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}
EOF

echo ""
echo "✅ 基线报告已生成:"
echo "  JSON: $REPORT_JSON"
echo "  MD:   $REPORT_MD"

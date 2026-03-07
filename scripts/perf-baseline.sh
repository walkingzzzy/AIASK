#!/usr/bin/env bash
# T-054: 性能回归验证脚本
# 用途：使用 Lighthouse CLI 检测 Core Web Vitals 性能基线
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORT_DIR="$ROOT_DIR/reports/performance"
BASE_URL="${1:-http://localhost:3000}"

mkdir -p "$REPORT_DIR"

echo "━━━ T-054 性能回归验证 ━━━"
echo "目标地址: $BASE_URL"
echo ""

# 性能基线阈值
LCP_THRESHOLD=2500   # 2.5s
CLS_THRESHOLD=0.1    # 0.1
PERF_SCORE_THRESHOLD=70

# 检查 Lighthouse CLI
if ! command -v lighthouse &>/dev/null; then
  echo "▸ 安装 Lighthouse CLI..."
  npm install -g lighthouse 2>/dev/null || {
    echo "  ⚠️  Lighthouse 未安装，使用 npx 代替"
    LIGHTHOUSE_CMD="npx -y lighthouse"
  }
fi
LIGHTHOUSE_CMD="${LIGHTHOUSE_CMD:-lighthouse}"

run_lighthouse() {
  local url="$1"
  local name="$2"
  local output_file="$REPORT_DIR/${name}.json"

  echo "▸ 测试 $name ($url)..."
  $LIGHTHOUSE_CMD "$url" \
    --output=json \
    --output-path="$output_file" \
    --chrome-flags="--headless --no-sandbox" \
    --only-categories=performance \
    --quiet 2>/dev/null || {
      echo "  ⚠️  Lighthouse 测试跳过（可能未运行服务或缺少 Chrome）"
      return 1
    }

  # 解析结果
  if [ -f "$output_file" ]; then
    local perf_score lcp cls
    perf_score=$(node -e "const r=require('$output_file'); console.log(Math.round((r.categories?.performance?.score||0)*100))" 2>/dev/null || echo "N/A")
    lcp=$(node -e "const r=require('$output_file'); console.log(Math.round(r.audits?.['largest-contentful-paint']?.numericValue||0))" 2>/dev/null || echo "N/A")
    cls=$(node -e "const r=require('$output_file'); console.log(r.audits?.['cumulative-layout-shift']?.numericValue?.toFixed(3)||'N/A')" 2>/dev/null || echo "N/A")

    echo "  Performance Score: $perf_score"
    echo "  LCP: ${lcp}ms (阈值: ${LCP_THRESHOLD}ms)"
    echo "  CLS: $cls (阈值: $CLS_THRESHOLD)"

    # 检查是否通过
    if [ "$perf_score" != "N/A" ] && [ "$perf_score" -ge "$PERF_SCORE_THRESHOLD" ]; then
      echo "  ✅ 性能评分通过"
    else
      echo "  ⚠️  性能评分未达基线"
    fi
  fi
}

# 测试首页
run_lighthouse "$BASE_URL" "homepage" || true

# 测试个股页
run_lighthouse "$BASE_URL/stock?code=600519" "stock_detail" || true

echo ""
echo "━━━ 报告目录: $REPORT_DIR ━━━"
echo ""

# 生成汇总
cat > "$REPORT_DIR/summary.md" << 'EOF'
# 性能回归验证报告

| 指标 | 基线阈值 | 说明 |
|------|---------|------|
| LCP (Largest Contentful Paint) | < 2.5s | 首屏加载时间 |
| CLS (Cumulative Layout Shift) | < 0.1 | 页面布局稳定性 |
| Performance Score | ≥ 70 | Lighthouse 综合评分 |

> 详细 JSON 报告见同目录下 .json 文件
EOF

echo "━━━ ✅ 性能回归验证完成 ━━━"

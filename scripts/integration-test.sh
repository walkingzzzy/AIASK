#!/usr/bin/env bash
# T-053: 全平台集成测试脚本
# 用途：跨浏览器 Playwright E2E 测试（Chromium / WebKit / Mobile）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WEB_DIR="$ROOT_DIR/apps/web"

echo "━━━ T-053 全平台集成测试 ━━━"
echo ""

cd "$WEB_DIR"

# 检查 Playwright 是否安装
if ! npx playwright --version 2>/dev/null; then
  echo "▸ 安装 Playwright..."
  npx -y playwright install --with-deps 2>/dev/null || npx -y playwright install
fi

REPORT_DIR="$ROOT_DIR/reports/e2e"
mkdir -p "$REPORT_DIR"

echo "▸ 运行 Chromium 测试..."
npx playwright test --project=chromium --reporter=html 2>&1 | tee "$REPORT_DIR/chromium.log" || true

echo ""
echo "▸ 运行 WebKit (Safari) 测试..."
npx playwright test --project=webkit --reporter=html 2>&1 | tee "$REPORT_DIR/webkit.log" || true

echo ""
echo "▸ 运行 Mobile (iPhone 14) 测试..."
npx playwright test --project=mobile --reporter=html 2>&1 | tee "$REPORT_DIR/mobile.log" || true

echo ""
echo "━━━ 测试报告 ━━━"
echo "Chromium:  $REPORT_DIR/chromium.log"
echo "WebKit:    $REPORT_DIR/webkit.log"
echo "Mobile:    $REPORT_DIR/mobile.log"
echo "HTML报告:  $WEB_DIR/playwright-report/index.html"
echo ""
echo "━━━ ✅ 全平台集成测试完成 ━━━"

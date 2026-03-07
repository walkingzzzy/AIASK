#!/usr/bin/env bash
# T-055: 安全扫描脚本
# 用途：npm audit + CSP 策略验证 + 安全头检查
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORT_DIR="$ROOT_DIR/reports/security"

mkdir -p "$REPORT_DIR"

echo "━━━ T-055 安全扫描 ━━━"
echo ""

PASS=0
WARN=0
FAIL=0

# 1) npm audit 依赖漏洞扫描
echo "▸ [1/3] npm audit 依赖漏洞扫描..."
cd "$ROOT_DIR"
if npm audit --omit=dev 2>&1 | tee "$REPORT_DIR/npm-audit.log"; then
  echo "  ✅ 无严重漏洞"
  PASS=$((PASS+1))
else
  CRITICAL=$(grep -c "critical" "$REPORT_DIR/npm-audit.log" 2>/dev/null || echo "0")
  HIGH=$(grep -c "high" "$REPORT_DIR/npm-audit.log" 2>/dev/null || echo "0")
  echo "  ⚠️  发现漏洞 (critical: $CRITICAL, high: $HIGH)"
  if [ "$CRITICAL" -gt 0 ]; then FAIL=$((FAIL+1)); else WARN=$((WARN+1)); fi
fi

echo ""

# 2) CSP 策略验证
echo "▸ [2/3] CSP 策略验证..."
CSP_FILE="$ROOT_DIR/apps/web/next.config.mjs"
if [ -f "$CSP_FILE" ]; then
  if grep -q "Content-Security-Policy" "$CSP_FILE"; then
    echo "  ✅ Content-Security-Policy 已配置"
    PASS=$((PASS+1))

    # 检查关键指令
    if grep -q "default-src" "$CSP_FILE"; then echo "    ✓ default-src 已设置"; fi
    if grep -q "script-src" "$CSP_FILE"; then echo "    ✓ script-src 已设置"; fi
    if grep -q "frame-ancestors" "$CSP_FILE"; then echo "    ✓ frame-ancestors 已设置"; fi
  else
    echo "  ❌ CSP 未配置"
    FAIL=$((FAIL+1))
  fi
else
  echo "  ❌ next.config 文件未找到"
  FAIL=$((FAIL+1))
fi

echo ""

# 3) 安全头检查
echo "▸ [3/3] 安全响应头检查..."
SECURITY_HEADERS=(
  "X-Frame-Options"
  "X-Content-Type-Options"
  "Referrer-Policy"
  "Strict-Transport-Security"
  "Permissions-Policy"
  "Content-Security-Policy"
)

HEADERS_FOUND=0
for header in "${SECURITY_HEADERS[@]}"; do
  if grep -rq "$header" "$ROOT_DIR/apps/web/next.config.mjs" 2>/dev/null; then
    echo "  ✓ $header"
    HEADERS_FOUND=$((HEADERS_FOUND+1))
  else
    echo "  ✗ $header - 未找到"
  fi
done

if [ "$HEADERS_FOUND" -eq "${#SECURITY_HEADERS[@]}" ]; then
  echo "  ✅ 全部安全头已配置 ($HEADERS_FOUND/${#SECURITY_HEADERS[@]})"
  PASS=$((PASS+1))
else
  echo "  ⚠️  部分安全头缺失 ($HEADERS_FOUND/${#SECURITY_HEADERS[@]})"
  WARN=$((WARN+1))
fi

echo ""

# 汇总报告
cat > "$REPORT_DIR/summary.md" << EOF
# 安全扫描报告

| 检查项 | 状态 |
|--------|------|
| npm audit 漏洞扫描 | $([ $FAIL -eq 0 ] && echo "✅ 通过" || echo "⚠️ 存在问题") |
| CSP 策略配置 | $(grep -q "Content-Security-Policy" "$CSP_FILE" 2>/dev/null && echo "✅ 已配置" || echo "❌ 未配置") |
| 安全响应头 | ${HEADERS_FOUND}/${#SECURITY_HEADERS[@]} 已配置 |

> 详细日志见 npm-audit.log
EOF

echo "━━━ 扫描结果汇总 ━━━"
echo "  ✅ 通过: $PASS"
echo "  ⚠️  警告: $WARN"
echo "  ❌ 失败: $FAIL"
echo ""
echo "报告目录: $REPORT_DIR"
echo "━━━ ✅ 安全扫描完成 ━━━"

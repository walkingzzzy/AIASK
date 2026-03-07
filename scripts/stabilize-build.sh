#!/usr/bin/env bash
# T-041: 构建稳定化脚本
# 用途：清理缓存 → 安装依赖 → 验证构建
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WEB_DIR="$ROOT_DIR/apps/web"

echo "━━━ T-041 构建稳定化检查 ━━━"
echo ""

# 1) 清理缓存
echo "▸ 清理 .next 构建缓存..."
rm -rf "$WEB_DIR/.next"

# 2) 检查 lightningcss 兼容性
echo "▸ 检查 lightningcss 状态..."
if node -e "require('lightningcss')" 2>/dev/null; then
  echo "  ✅ lightningcss 可用"
else
  echo "  ⚠️  lightningcss 不可用，尝试重新安装..."
  cd "$ROOT_DIR" && npm install --prefer-offline 2>/dev/null || true
fi

# 3) 验证 package-lock.json
echo "▸ 检查 package-lock.json..."
if [ -f "$ROOT_DIR/package-lock.json" ]; then
  echo "  ✅ package-lock.json 已提交"
else
  echo "  ⚠️  package-lock.json 缺失，运行 npm install 生成"
fi

# 4) TypeScript 类型检查
echo "▸ 运行 TypeScript 类型检查..."
cd "$WEB_DIR"
if npx tsc --noEmit 2>&1; then
  echo "  ✅ TypeScript 类型检查通过"
else
  echo "  ❌ TypeScript 类型检查失败"
  exit 1
fi

# 5) 尝试构建
echo "▸ 运行 Next.js 构建..."
if npm run build 2>&1; then
  echo ""
  echo "━━━ ✅ 构建稳定化验证通过 ━━━"
else
  echo ""
  echo "━━━ ❌ 构建失败，请检查错误日志 ━━━"
  exit 1
fi

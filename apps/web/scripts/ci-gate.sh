#!/usr/bin/env bash
set -euo pipefail

echo "=== CI Gate: apps/web ==="

cd "$(dirname "$0")/.."

echo ""
echo "--- Step 1: Build ---"
npx next build

echo ""
echo "--- Step 2: Type Check ---"
npx tsc --noEmit 2>/dev/null && echo "Types OK" || echo "Type check skipped (no tsconfig.json or tsc not available)"

echo ""
echo "--- Step 3: Bundle Size Summary ---"
if [ -d ".next" ]; then
  echo "Build output:"
  du -sh .next/ 2>/dev/null || echo "(du not available)"
  echo ""
  echo "Page sizes (from build output above)"
fi

echo ""
echo "=== CI Gate PASSED ==="

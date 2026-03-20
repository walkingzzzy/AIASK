#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

pytest packages/akshare-mcp/tests/test_strategy_factory_module_compat.py -q
pytest packages/akshare-mcp/tests/test_strategy_factory_package_migration_contract.py -q
pytest packages/akshare-mcp/tests/test_strategy_factory_gate_report.py -q
pytest packages/akshare-mcp/tests/test_backtest_filter_concurrency.py -q
pytest packages/akshare-mcp/tests/test_concurrency_optimization.py -q
pytest packages/akshare-mcp/tests/test_strategy_factory_and_marketplace.py -q

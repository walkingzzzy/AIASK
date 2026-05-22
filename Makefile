.PHONY: bootstrap test test-agent test-finance typecheck build-desktop package-desktop smoke

bootstrap:
	cd packages/agent && uv sync
	cd desktop && npm install

test: test-agent test-finance
	cd desktop && npm test

test-agent:
	cd packages/agent && pytest -q tests

test-finance:
	cd packages/akshare-mcp && pytest -q tests/test_strategy_mgr_capabilities_health.py tests/test_tool_argument_contract.py tests/test_strategy_market_incubation_surface.py

typecheck:
	cd desktop && npm run typecheck

build-desktop:
	cd desktop && npm run build
	cd desktop/src-tauri && cargo check

package-desktop:
	cd desktop && npm run tauri:build

smoke:
	curl -fsS http://127.0.0.1:$${AIASK_AGENT_PORT:-8767}/health

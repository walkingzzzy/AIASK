# AKShare MCP Makefile

.PHONY: help install test test-perf lint format tool-registry scenario-audit healthcheck healthcheck-extended healthcheck-full tool-description-audit clean

help:
	@echo "Available commands:"
	@echo "  make install     - Install dependencies"
	@echo "  make test        - Run all tests"
	@echo "  make test-perf   - Run performance benchmarks"
	@echo "  make lint        - Run linting"
	@echo "  make format      - Format code"
	@echo "  make tool-registry - Export runtime tool registry"
	@echo "  make scenario-audit - Audit legacy real-world scenario artifacts"
	@echo "  make healthcheck - Run tool healthcheck (quick)"
	@echo "  make healthcheck-extended - Run tool healthcheck (extended)"
	@echo "  make healthcheck-full - Run tool healthcheck (full)"
	@echo "  make tool-description-audit - Generate tool description audit report"
	@echo "  make clean       - Clean cache files"

install:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio pytest-benchmark

test:
	pytest tests/ -v

test-perf:
	pytest tests/test_backtest_performance.py -v --benchmark-only --benchmark-autosave

lint:
	flake8 src/ tests/ --max-line-length=120 --ignore=E501,W503

format:
	black src/ tests/ --line-length=120

tool-registry:
	python scripts/export_tool_registry.py

scenario-audit:
	python scripts/audit_real_world_scenarios.py

healthcheck:
	python scripts/run_tool_healthcheck.py --mode quick

healthcheck-extended:
	python scripts/run_tool_healthcheck.py --mode extended

healthcheck-full:
	python scripts/run_tool_healthcheck.py --mode full

tool-description-audit:
	python scripts/generate_tool_description_audit.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".benchmark" -exec rm -rf {} +

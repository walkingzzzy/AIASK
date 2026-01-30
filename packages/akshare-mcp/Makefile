# AKShare MCP Makefile

.PHONY: help install test test-perf lint format clean

help:
	@echo "Available commands:"
	@echo "  make install     - Install dependencies"
	@echo "  make test        - Run all tests"
	@echo "  make test-perf   - Run performance benchmarks"
	@echo "  make lint        - Run linting"
	@echo "  make format      - Format code"
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

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".benchmark" -exec rm -rf {} +

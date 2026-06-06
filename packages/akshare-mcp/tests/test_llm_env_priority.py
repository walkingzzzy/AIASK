from __future__ import annotations

import os

from akshare_mcp.env_loader import load_mcp_env
from akshare_mcp.services.factor_llm_provider_parts.context import FactorLLMConfig
from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig


def test_mcp_llm_env_file_overrides_process_env_without_overriding_non_llm(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "STRATEGY_LLM_ENABLED=1",
                "STRATEGY_LLM_MODEL=file-strategy-model",
                "STRATEGY_LLM_BASE_URL=https://file-strategy.example.test/v1",
                "STRATEGY_LLM_API_KEY=sk-file-strategy",
                "FACTOR_LLM_MODEL=file-factor-model",
                "FACTOR_LLM_BASE_URL=https://file-factor.example.test/v1",
                "FACTOR_LLM_API_KEY=sk-file-factor",
                "AKSHARE_MCP_SQLITE_PATH=file-shadow.sqlite3",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AKSHARE_MCP_ENV", str(env_file))
    monkeypatch.setenv("STRATEGY_LLM_MODEL", "process-strategy-model")
    monkeypatch.setenv("STRATEGY_LLM_BASE_URL", "https://process-strategy.example.test/v1")
    monkeypatch.setenv("STRATEGY_LLM_API_KEY", "sk-process-strategy")
    monkeypatch.setenv("FACTOR_LLM_MODEL", "process-factor-model")
    monkeypatch.setenv("FACTOR_LLM_BASE_URL", "https://process-factor.example.test/v1")
    monkeypatch.setenv("FACTOR_LLM_API_KEY", "sk-process-factor")
    monkeypatch.setenv("AKSHARE_MCP_SQLITE_PATH", "process.sqlite3")

    load_mcp_env(override=False)
    strategy = StrategyLLMConfig.from_env()
    factor = FactorLLMConfig.from_env()

    assert strategy.enabled is True
    assert strategy.model == "file-strategy-model"
    assert strategy.base_url == "https://file-strategy.example.test/v1"
    assert strategy.api_key == "sk-file-strategy"
    assert factor.model == "file-factor-model"
    assert factor.base_url == "https://file-factor.example.test/v1"
    assert factor.api_key == "sk-file-factor"
    assert os.environ["AKSHARE_MCP_SQLITE_PATH"] == "process.sqlite3"

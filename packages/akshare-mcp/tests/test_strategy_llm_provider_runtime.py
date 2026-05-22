from __future__ import annotations

import asyncio
import json

import httpx

from akshare_mcp.services.strategy_llm_provider import StrategyLLMConfig, StrategyLLMProvider


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={
            "id": "chatcmpl-test",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"completion_tokens": 12},
        },
    )


def _provider_with_responses(responses: list[httpx.Response], *, stage_retry_count: int = 1) -> StrategyLLMProvider:
    queue = list(responses)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer test-key"
        assert queue
        return queue.pop(0)

    provider = StrategyLLMProvider(
        StrategyLLMConfig(
            enabled=True,
            base_url="https://llm.example.test/v1",
            api_key="test-key",
            model="test-model",
            stage_retry_count=stage_retry_count,
            stage_retry_backoff_sec=0.0,
            retry_count=stage_retry_count,
            retry_backoff_sec=0.0,
            compatibility_cooldown_sec=60.0,
            max_concurrency=1,
        )
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return provider


def _provider_with_handler(handler, *, stage_retry_count: int = 1) -> StrategyLLMProvider:
    provider = StrategyLLMProvider(
        StrategyLLMConfig(
            enabled=True,
            base_url="https://llm.example.test/v1",
            api_key="test-key",
            model="test-model",
            stage_retry_count=stage_retry_count,
            stage_retry_backoff_sec=0.0,
            retry_count=stage_retry_count,
            retry_backoff_sec=0.0,
            compatibility_cooldown_sec=60.0,
            max_concurrency=1,
        )
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return provider


def _pin_mock_client_to_current_loop(provider: StrategyLLMProvider) -> None:
    provider._runtime_loop_id = id(asyncio.get_running_loop())


def test_strategy_llm_extracts_markdown_fenced_json() -> None:
    provider = _provider_with_responses(
        [
            _chat_response(
                '```json\n{"confidence":0.81,"events":[{"code":"600519","reason":"ok"}]}\n```'
            )
        ]
    )

    async def _run() -> dict:
        try:
            _pin_mock_client_to_current_loop(provider)
            return await provider.call_stage(
                stage_id="event_recognition",
                input_data={"topic": "test"},
                system_prompt="Return JSON.",
            )
        finally:
            await provider.close()

    result = asyncio.run(_run())
    assert result["confidence"] == 0.81
    assert result["events"][0]["code"] == "600519"


def test_strategy_llm_extracts_json_from_prose() -> None:
    provider = _provider_with_responses(
        [
            _chat_response(
                'Here is the result:\n{"confirmations":[{"code":"000001","score":0.7}],"confidence":0.7}\nDone.'
            )
        ]
    )

    async def _run() -> dict:
        try:
            _pin_mock_client_to_current_loop(provider)
            return await provider.call_stage(
                stage_id="market_confirmation",
                input_data={"topic": "test"},
                system_prompt="Return JSON.",
            )
        finally:
            await provider.close()

    result = asyncio.run(_run())
    assert result["confirmations"][0]["code"] == "000001"
    assert result["confidence"] == 0.7


def test_strategy_llm_bad_non_empty_json_does_not_trigger_compatibility_cooldown() -> None:
    provider = _provider_with_responses(
        [
            _chat_response('{"confirmations":[{"code":"000001","score":0.7}],'),
            _chat_response('{"confirmations":[{"code":"000001","score":0.8}],"confidence":0.8}'),
            _chat_response('{"candidates":[],"analysis":{"hypothesis":"still usable"}}'),
        ],
        stage_retry_count=1,
    )

    async def _run() -> tuple[dict, dict]:
        try:
            _pin_mock_client_to_current_loop(provider)
            stage_result = await provider.call_stage(
                stage_id="market_confirmation",
                input_data={"topic": "test"},
                system_prompt="Return JSON.",
            )
            generated = await provider.generate_candidates(limit=1, research_task={"topic": "test"})
            return stage_result, generated or {}
        finally:
            await provider.close()

    stage_result, generated = asyncio.run(_run())
    assert stage_result["confirmations"][0]["score"] == 0.8
    assert generated["analysis"]["hypothesis"] == "still usable"
    health = provider.get_health_snapshot()
    assert health["compatibility_cooldown_active"] is False
    assert health["scheduler_should_disable"] is False
    assert health["last_error_type"] is None


def test_strategy_llm_bad_non_empty_json_final_failure_keeps_provider_available() -> None:
    provider = _provider_with_responses(
        [
            _chat_response('{"events":[{"code":"600519"}],'),
            _chat_response('{"candidates":[],"analysis":{"hypothesis":"still usable"}}'),
        ],
        stage_retry_count=0,
    )

    async def _run() -> dict:
        try:
            _pin_mock_client_to_current_loop(provider)
            try:
                await provider.call_stage(
                    stage_id="event_recognition",
                    input_data={"topic": "test"},
                    system_prompt="Return JSON.",
                )
            except Exception as exc:
                payload = json.loads(str(exc).split("attempts: ", 1)[-1])
                assert "not valid JSON" in payload["error"]
            return await provider.generate_candidates(limit=1, research_task={"topic": "test"}) or {}
        finally:
            await provider.close()

    generated = asyncio.run(_run())
    assert generated["analysis"]["hypothesis"] == "still usable"
    assert provider.get_health_snapshot()["compatibility_cooldown_active"] is False


def test_strategy_llm_stage_prompt_is_self_describing() -> None:
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        captured["user_prompt"] = payload["messages"][1]["content"]
        return _chat_response('{"confirmations":[{"symbol":"000001","confirmed":true}]}')

    provider = _provider_with_handler(handler, stage_retry_count=0)

    async def _run() -> dict:
        try:
            _pin_mock_client_to_current_loop(provider)
            return await provider.call_stage(
                stage_id="market_confirmation",
                input_data={"headline": "test headline"},
                system_prompt="Return JSON.",
            )
        finally:
            await provider.close()

    result = asyncio.run(_run())
    assert result["confirmations"][0]["confirmed"] is True
    user_prompt = captured["user_prompt"]
    assert "Execute Strategy Factory pipeline stage: market_confirmation" in user_prompt
    assert "The required top-level key is: confirmations" in user_prompt
    assert "Return only one valid JSON object" in user_prompt
    assert '"headline":"test headline"' in user_prompt

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from akshare_mcp.services.strategy_llm_provider import (
    StrategyLLMConfig,
    StrategyLLMProvider,
    StrategyLLMRequestError,
)


class _Response:
    def __init__(
        self,
        payload: dict,
        *,
        content_type: str = "application/json",
        status_code: int = 200,
        text: str | None = None,
    ):
        self._payload = payload
        self.headers = {"content-type": content_type}
        self.status_code = status_code
        self.text = str(text) if text is not None else json.dumps(payload, ensure_ascii=False)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _StreamResponse:
    def __init__(self, chunks: list[str], *, content_type: str = "text/event-stream", status_code: int = 200):
        self._chunks = list(chunks)
        self.headers = {"content-type": content_type}
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        return None

    async def aiter_text(self):
        for chunk in self._chunks:
            yield chunk


class _PostOnlyClient:
    def __init__(self, response: _Response):
        self.post = AsyncMock(return_value=response)

    async def aclose(self) -> None:
        return None


class _ReplayClient:
    def __init__(self, response: _Response, stream_chunks: list[str]):
        self.post = AsyncMock(return_value=response)
        self._stream_chunks = list(stream_chunks)
        self.stream_calls: list[dict[str, object]] = []

    def stream(self, *args, **kwargs):
        self.stream_calls.append({"args": args, "kwargs": kwargs})
        return _StreamResponse(self._stream_chunks)

    async def aclose(self) -> None:
        return None


def _sse_chunk(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@pytest.mark.asyncio
async def test_call_stage_accepts_choices_text_payload():
    provider = StrategyLLMProvider(
        StrategyLLMConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="https://example.com/v1",
            api_key="k",
            model="m",
            stage_retry_count=0,
        )
    )
    provider._client = _PostOnlyClient(
        _Response(
            {
                "choices": [
                    {
                        "text": json.dumps(
                            {
                                "events": [
                                    {"theme_code": "chip_domestic", "event_type": "policy_shift"}
                                ]
                            }
                        )
                    }
                ]
            }
        )
    )

    try:
        result = await provider.call_stage(
            stage_id="event_recognition",
            input_data={"market_snapshot": {"date": "2026-03-09"}},
            system_prompt="Return JSON only.",
            timeout_sec=5,
        )
    finally:
        await provider.close()

    assert result["events"][0]["event_type"] == "policy_shift"


@pytest.mark.asyncio
async def test_call_stage_marks_missing_content_as_compatibility_failure_and_skips_followups():
    provider = StrategyLLMProvider(
        StrategyLLMConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="https://example.com/v1",
            api_key="k",
            model="m",
            stage_retry_count=0,
            compatibility_cooldown_sec=60,
        )
    )
    provider._client = _PostOnlyClient(
        _Response(
            {
                "id": "resp_missing_content",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"completion_tokens": 9},
            },
            content_type="text/event-stream",
        )
    )

    try:
        with pytest.raises(StrategyLLMRequestError) as excinfo:
            await provider.call_stage(
                stage_id="event_recognition",
                input_data={"market_snapshot": {"date": "2026-03-09"}},
                system_prompt="Return JSON only.",
                timeout_sec=5,
            )

        assert excinfo.value.metrics["status"] == "compatibility_failed"
        assert excinfo.value.metrics["last_error_type"] == "ProviderCompatibilityError"
        assert excinfo.value.metrics["response_content_type"] == "text/event-stream"
        assert excinfo.value.metrics["stream_fallback_unavailable"] is True
        assert provider._client.post.await_count == 1

        with pytest.raises(StrategyLLMRequestError) as followup_exc:
            await provider.call_stage(
                stage_id="event_recognition",
                input_data={"market_snapshot": {"date": "2026-03-09"}},
                system_prompt="Return JSON only.",
                timeout_sec=5,
            )

        assert followup_exc.value.metrics["status"] == "compatibility_skip"
        assert provider._client.post.await_count == 1
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_call_stage_recovers_via_chat_stream_replay_when_nonstream_content_is_empty():
    stage_payload = {
        "events": [
            {"theme_code": "chip_domestic", "event_type": "policy_shift"},
        ]
    }
    nonstream_payload = {
        "id": "resp_missing_content",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"completion_tokens": 9},
    }
    stream_chunks = [
        _sse_chunk(
            {
                "id": "resp_stream",
                "object": "chat.completion.chunk",
                "model": "m",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }
        ),
        _sse_chunk(
            {
                "id": "resp_stream",
                "object": "chat.completion.chunk",
                "model": "m",
                "choices": [{"index": 0, "delta": {"content": json.dumps(stage_payload, ensure_ascii=False)}, "finish_reason": None}],
            }
        ),
        _sse_chunk(
            {
                "id": "resp_stream",
                "object": "chat.completion.chunk",
                "model": "m",
                "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": "stop"}],
            }
        ),
        "data: [DONE]\n\n",
    ]

    provider = StrategyLLMProvider(
        StrategyLLMConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="https://example.com/v1",
            api_key="k",
            model="m",
            stage_retry_count=0,
        )
    )
    provider._client = _ReplayClient(
        _Response(nonstream_payload, content_type="text/event-stream"),
        stream_chunks,
    )

    try:
        result = await provider.call_stage(
            stage_id="event_recognition",
            input_data={"market_snapshot": {"date": "2026-03-09"}},
            system_prompt="Return JSON only.",
            timeout_sec=5,
        )
    finally:
        await provider.close()

    assert result["events"][0]["event_type"] == "policy_shift"
    assert provider._client.post.await_count == 1
    assert provider._client.post.await_args.kwargs["headers"]["Accept"] == "application/json, text/event-stream"
    assert provider._client.stream_calls[0]["kwargs"]["headers"]["Accept"] == "text/event-stream, application/json"
    assert provider.get_health_snapshot()["effective_response_count"] == 1
    assert provider.get_health_snapshot()["compatibility_failure_count"] == 0


@pytest.mark.asyncio
async def test_generate_candidates_recovers_via_chat_stream_replay_when_nonstream_content_is_empty():
    import pandas as pd

    candidate_payload = {
        "analysis": {"market_regime": "trend_up"},
        "candidates": [
            {
                "name": "stream_candidate",
                "strategy_type": "ma_cross",
                "target_symbols": ["688981"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["688981"]},
                "dsl": {
                    "version": "1.0",
                    "timeframe": "daily",
                    "entry": {
                        "any": [
                            {
                                "op": "cross_above",
                                "left": {"field": "close"},
                                "right": {"indicator": "sma", "field": "close", "window": 10},
                            }
                        ]
                    },
                    "exit": {
                        "any": [
                            {
                                "op": "cross_below",
                                "left": {"field": "close"},
                                "right": {"indicator": "sma", "field": "close", "window": 10},
                            }
                        ]
                    },
                },
                "portfolio_spec": {
                    "position_assumption": "equal_weight_proxy",
                    "target_weight_scheme": "equal_weight",
                },
                "execution_assumptions": {
                    "commission_rate": 0.00025,
                    "slippage_bps": 5,
                    "tradability_filter": True,
                    "slippage_model": "fixed",
                },
                "validation_profile": {
                    "profile": "trade_rule_validation",
                    "validation_focus": "target_plus_representative",
                    "primary_validation_layer": "target",
                },
                "tags": ["external_llm"],
            }
        ],
    }
    nonstream_payload = {
        "id": "resp_missing_candidates",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"completion_tokens": 18},
    }
    stream_chunks = [
        _sse_chunk(
            {
                "id": "resp_stream_candidates",
                "object": "chat.completion.chunk",
                "model": "m",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }
        ),
        _sse_chunk(
            {
                "id": "resp_stream_candidates",
                "object": "chat.completion.chunk",
                "model": "m",
                "choices": [{"index": 0, "delta": {"content": json.dumps(candidate_payload, ensure_ascii=False)}, "finish_reason": None}],
            }
        ),
        _sse_chunk(
            {
                "id": "resp_stream_candidates",
                "object": "chat.completion.chunk",
                "model": "m",
                "choices": [{"index": 0, "delta": {"content": ""}, "finish_reason": "stop"}],
            }
        ),
        "data: [DONE]\n\n",
    ]

    provider = StrategyLLMProvider(
        StrategyLLMConfig(
            enabled=True,
            provider="openai_compatible",
            base_url="https://example.com/v1",
            api_key="k",
            model="m",
            retry_count=0,
        )
    )
    provider._client = _ReplayClient(
        _Response(nonstream_payload, content_type="text/event-stream"),
        stream_chunks,
    )

    try:
        result = await provider.generate_candidates(
            snapshot={"date": "2026-03-09", "fear_greed_index": 50},
            market_frame=pd.DataFrame({"close": [1.0, 1.1, 1.2], "volume": [100, 120, 110]}),
            research_context={
                "market_regime": {"fg_level": "neutral", "fear_greed_index": 50},
                "candidate_universe": [{"code": "688981"}],
            },
            research_task={"task_id": "t1", "target_symbols": ["688981"]},
            limit=2,
        )
    finally:
        await provider.close()

    assert result["analysis"]["market_regime"] == "trend_up"
    assert result["candidates"][0]["name"] == "stream_candidate"
    assert result["compatibility_mode"] == "chat_stream_replay"
    assert result["request_metrics"]["compatibility_mode"] == "chat_stream_replay"
    assert result["raw_response"]["compatibility_mode"] == "chat_stream_replay"
    assert provider._client.post.await_count == 1
    assert provider._client.post.await_args.kwargs["headers"]["Accept"] == "application/json, text/event-stream"
    assert provider._client.stream_calls[0]["kwargs"]["headers"]["Accept"] == "text/event-stream, application/json"
    assert provider.get_health_snapshot()["effective_response_count"] == 1

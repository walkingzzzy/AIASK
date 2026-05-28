
        async def call_stage(
            self,
            *,
            stage_id: str,
            input_data: dict[str, Any],
            system_prompt: str,
            max_tokens: int = 500,
            temperature: float = 0.2,
            timeout_sec: Optional[float] = None,
        ) -> dict[str, Any]:
            """Execute a single pipeline stage via the external LLM.

            This reuses the existing HTTP infrastructure (retry, timeout
            degradation, cooldown tracking) but with a much simpler prompt
            structure: a short system prompt + JSON-serialised input data.

            Returns the parsed JSON dict from the LLM response.
            Raises ``StrategyLLMRequestError`` on failure.
            """
            if not self.is_enabled():
                raise StrategyLLMRequestError(
                    f"call_stage({stage_id}): LLM provider not enabled",
                    metrics={"stage_id": stage_id, "status": "disabled"},
                )
            await self._ensure_runtime_async_state()

            started_at = time.perf_counter()
            stage_timeout = float(timeout_sec or 10.0)
            compatibility_metrics = self._active_compatibility_failure()
            if compatibility_metrics is not None:
                raise StrategyLLMRequestError(
                    f"call_stage({stage_id}) skipped during compatibility cooldown",
                    metrics={
                        "stage_id": stage_id,
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                        **compatibility_metrics,
                        "status": "compatibility_skip",
                    },
                )
            connectivity_metrics = self._active_connectivity_failure()
            if connectivity_metrics is not None:
                raise StrategyLLMRequestError(
                    f"call_stage({stage_id}) skipped during connectivity cooldown",
                    metrics={
                        "stage_id": stage_id,
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                        **connectivity_metrics,
                        "status": "cooldown_skip",
                    },
                )
            _compact_level, degrade_reason = self._recent_failure_degrade_state()
            if degrade_reason in {'recent_timeout', 'recent_overload'}:
                is_overload = degrade_reason == 'recent_overload'
                raise StrategyLLMRequestError(
                    f"call_stage({stage_id}) skipped during {'overload' if is_overload else 'timeout'} cooldown",
                    metrics={
                        "stage_id": stage_id,
                        "status": "cooldown_skip",
                        "cooldown_reason": degrade_reason,
                        "last_error_type": "RecentOverloadCooldown" if is_overload else "RecentTimeoutCooldown",
                        "recent_timeout_streak": self._recent_timeout_streak,
                        "recent_timeout_cooldown_sec": round(
                            max(self._recent_timeout_cooldown_until - time.monotonic(), 0.0),
                            4,
                        ),
                        "recent_overload_streak": int(getattr(self, "_recent_overload_streak", 0) or 0),
                        "recent_overload_cooldown_sec": round(
                            max(getattr(self, "_recent_overload_cooldown_until", 0.0) - time.monotonic(), 0.0),
                            4,
                        ),
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                    },
                )
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }

            _STAGE_OUTPUT_CONTRACTS: dict[str, dict[str, Any]] = {
                "event_recognition": {
                    "top_level_key": "events",
                    "item_required_fields": ["theme_code", "event_type"],
                    "item_hint": {
                        "theme_code": "short_theme_id",
                        "event_type": "sector_rotation|policy|earnings|fund_flow|risk",
                        "event_id": "stable_event_id",
                        "title": "brief Chinese event title",
                        "severity": 1,
                        "evidence": ["brief evidence"],
                    },
                },
                "theme_propagation": {
                    "top_level_key": "themes",
                    "item_required_fields": ["theme_code"],
                    "item_hint": {
                        "theme_code": "short_theme_id",
                        "theme_name": "brief Chinese theme name",
                        "source_event_id": "event_id when available",
                        "direction": "bullish|bearish|neutral",
                        "confidence": 0.0,
                    },
                },
                "exposure_mapping": {
                    "top_level_key": "exposures",
                    "item_required_fields": ["theme_code", "target_symbols"],
                    "item_hint": {
                        "theme_code": "short_theme_id",
                        "target_symbols": ["600519"],
                        "sector": "sector name",
                        "exposure_type": "direct_beneficiary|supply_chain|style_proxy",
                        "weight": 0.0,
                    },
                },
                "market_confirmation": {
                    "top_level_key": "confirmations",
                    "item_required_fields": ["symbol", "confirmed"],
                    "item_hint": {
                        "symbol": "600519",
                        "confirmed": True,
                        "theme_code": "short_theme_id",
                        "signal_strength": "weak|moderate|strong",
                        "entry_timing": "immediate|wait|avoid",
                        "risk_level": "low|medium|high",
                    },
                },
                "strategy_generation": {
                    "top_level_key": "candidates",
                    "item_required_fields": ["name", "strategy_type", "target_symbols", "dsl"],
                    "item_hint": {
                        "name": "brief Chinese strategy name",
                        "strategy_type": "ma_cross|rsi|breakout|mean_reversion|dsl_rule",
                        "target_symbols": ["600519"],
                        "dsl": {
                            "version": "1.0",
                            "timeframe": "daily",
                            "entry": {"all": []},
                            "exit": {"any": []},
                        },
                        "tags": ["ai_staged"],
                    },
                },
            }
            output_contract = _STAGE_OUTPUT_CONTRACTS.get(
                stage_id,
                {
                    "top_level_key": "results",
                    "item_required_fields": [],
                    "item_hint": {},
                },
            )
            user_prompt = "\n".join(
                [
                    f"Execute Strategy Factory pipeline stage: {stage_id}.",
                    "Return only one valid JSON object. Do not include prose, markdown fences, explanations, or follow-up questions.",
                    f"The required top-level key is: {output_contract['top_level_key']}.",
                    "Each list item must satisfy item_required_fields. Use [] only when the input has no usable signal.",
                    "Output contract:",
                    json.dumps(output_contract, ensure_ascii=False, default=str, separators=(",", ":")),
                    "Input data:",
                    json.dumps(input_data, ensure_ascii=False, default=str, separators=(",", ":")),
                ]
            )
            # PR-AI3: 对 strategy_generation 阶段使用 JSON Schema 约束
            # 2026-05-28 (P0/C): 官方 DeepSeek 不支持 response_format=json_schema(返回
            # "This response_format type is unavailable now" → HTTP 400),改回 json_object,
            # 让 prompt 自带 schema 描述驱动 LLM 输出结构,后续 _try_find_list 兼容降级。
            # 兼容其他 provider(如 OpenAI / Tongyi) 时若需 json_schema 可通过 env 覆盖。
            _response_format: dict[str, Any] = {"type": "json_object"}
            payload = {
                "model": self.config.model,
                "temperature": temperature,
                "max_tokens": max(128, max_tokens),
                "response_format": _response_format,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }

            last_exc: Optional[Exception] = None
            attempts = max(1, int(getattr(self.config, "stage_retry_count", 1) or 0) + 1)
            attempt_reports: list[dict[str, Any]] = []

            client = self._client
            for attempt in range(1, attempts + 1):
                request_started_at = time.perf_counter()
                try:
                    async with self._request_semaphore:
                        data, _body, _content, _compatibility_mode = await self._request_and_parse_payload(
                            headers=headers,
                            request_payload=payload,
                            request_kind=f"call_stage({stage_id})",
                            timeout=self._request_timeout(stage_timeout),
                        )
                    if isinstance(data, list):
                        # LLM 返回了裸数组 — 根据 stage_id 包装成 dict
                        _STAGE_LIST_KEY = {
                            "event_recognition": "events",
                            "theme_propagation": "themes",
                            "exposure_mapping": "exposures",
                            "market_confirmation": "confirmations",
                            "strategy_generation": "candidates",
                        }
                        wrap_key = _STAGE_LIST_KEY.get(stage_id, "results")
                        data = {wrap_key: data}
                    if not isinstance(data, dict):
                        raise ValueError(f"call_stage({stage_id}): expected JSON object, got {type(data).__name__}")
                    self._record_request_success()
                    return data
                except StrategyLLMProviderCompatibilityError as exc:
                    last_exc = exc
                    attempt_reports.append({
                        "attempt": attempt,
                        "status": "compatibility_failed",
                        "elapsed_seconds": round(time.perf_counter() - request_started_at, 4),
                        "error_type": str(dict(getattr(exc, "metrics", {}) or {}).get("last_error_type") or "ProviderCompatibilityError"),
                        "error": self._error_text(exc),
                        "status_code": self._status_code_from_error(exc),
                        **dict(getattr(exc, "metrics", {}) or {}),
                    })
                    break
                except (
                    httpx.TimeoutException,
                    httpx.ConnectError,
                    httpx.ReadError,
                    httpx.RemoteProtocolError,
                    httpx.HTTPStatusError,
                    json.JSONDecodeError,
                    StrategyLLMResponseParseError,
                    ValueError,
                ) as exc:
                    last_exc = exc
                    attempt_reports.append({
                        "attempt": attempt,
                        "status": "failed",
                        "elapsed_seconds": round(time.perf_counter() - request_started_at, 4),
                        "error_type": self._failure_type(exc),
                        "error": self._error_text(exc),
                        "status_code": self._status_code_from_error(exc),
                        "retry_after_sec": self._retry_after_seconds(exc),
                    })
                    if attempt >= attempts or not (
                        isinstance(exc, StrategyLLMResponseParseError) or self._should_retry_request_error(exc)
                    ):
                        break
                    await asyncio.sleep(
                        self._retry_backoff_delay(
                            attempt,
                            exc,
                            base_delay=float(getattr(self.config, "stage_retry_backoff_sec", self.config.retry_backoff_sec) or 0.0),
                        )
                    )

            if last_exc is not None:
                if isinstance(last_exc, StrategyLLMProviderCompatibilityError):
                    self._record_compatibility_failure(last_exc)
                else:
                    self._record_request_failure(last_exc)
            raise StrategyLLMRequestError(
                f"call_stage({stage_id}) failed after {len(attempt_reports)} attempts: {self._error_text(last_exc or RuntimeError('unknown'))}",
                metrics={
                    "stage_id": stage_id,
                    "status": "failed",
                    "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                    "attempt_count": len(attempt_reports),
                    "attempts": attempt_reports,
                    "last_error_type": (self._failure_type(last_exc) if last_exc else "RuntimeError"),
                    "last_error_status_code": self._status_code_from_error(last_exc) if last_exc else None,
                    "last_error": self._error_text(last_exc or RuntimeError("unknown")),
                    "recent_timeout_streak": self._recent_timeout_streak,
                    "recent_timeout_cooldown_sec": round(max(self._recent_timeout_cooldown_until - time.monotonic(), 0.0), 4),
                    "recent_overload_streak": int(getattr(self, "_recent_overload_streak", 0) or 0),
                    "recent_overload_cooldown_sec": round(max(getattr(self, "_recent_overload_cooldown_until", 0.0) - time.monotonic(), 0.0), 4),
                    **(dict(getattr(last_exc, "metrics", {}) or {}) if isinstance(last_exc, StrategyLLMProviderCompatibilityError) else {}),
                },
            ) from last_exc

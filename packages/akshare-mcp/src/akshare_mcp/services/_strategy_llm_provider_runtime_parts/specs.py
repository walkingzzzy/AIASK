
        def get_health_snapshot(self) -> dict[str, Any]:
            active_compatibility = self._active_compatibility_failure()
            outcomes = list(getattr(self, "_recent_request_outcomes", []) or [])
            recent_request_count = len(outcomes)
            compatibility_failure_count = sum(
                1 for item in outcomes if bool(dict(item or {}).get("compatibility_failed"))
            )
            effective_response_count = sum(
                1 for item in outcomes if str(dict(item or {}).get("status") or "").strip().lower() == "succeeded"
            )
            empty_200_response_count = sum(
                1 for item in outcomes if bool(dict(item or {}).get("empty_200_response"))
            )
            compatibility_failure_ratio = (
                round(compatibility_failure_count / recent_request_count, 4) if recent_request_count else 0.0
            )
            effective_response_ratio = (
                round(effective_response_count / recent_request_count, 4) if recent_request_count else 0.0
            )
            scheduler_should_disable = False
            scheduler_skip_reason = None
            connectivity_failure = self._active_connectivity_failure()
            if connectivity_failure is not None:
                scheduler_should_disable = True
                scheduler_skip_reason = "connectivity_cooldown_active"
            elif active_compatibility is not None:
                scheduler_should_disable = True
                scheduler_skip_reason = "compatibility_cooldown_active"
            elif recent_request_count >= 2 and compatibility_failure_ratio >= 0.5:
                scheduler_should_disable = True
                scheduler_skip_reason = "compatibility_failure_ratio_high"
            elif empty_200_response_count > 0 and effective_response_ratio < 0.34:
                scheduler_should_disable = True
                scheduler_skip_reason = "empty_200_false_success_detected"
            if scheduler_should_disable:
                health_status = "blocked"
            elif recent_request_count <= 0 and active_compatibility is None and not self._last_failure_type:
                health_status = "unknown"
            elif compatibility_failure_count > 0 or effective_response_ratio < 1.0:
                health_status = "degraded"
            else:
                health_status = "healthy"
            return {
                "health_status": health_status,
                "recent_request_count": recent_request_count,
                "compatibility_failure_count": compatibility_failure_count,
                "effective_response_count": effective_response_count,
                "empty_200_response_count": empty_200_response_count,
                "compatibility_failure_ratio": compatibility_failure_ratio,
                "effective_response_ratio": effective_response_ratio,
                "connectivity_cooldown_active": connectivity_failure is not None,
                "connectivity_cooldown_sec": (
                    connectivity_failure.get("recent_connectivity_cooldown_sec") if connectivity_failure else 0.0
                ),
                "recent_connectivity_streak": (
                    connectivity_failure.get("recent_connectivity_streak")
                    if connectivity_failure
                    else int(getattr(self, "_recent_connectivity_streak", 0) or 0)
                ),
                "compatibility_cooldown_active": active_compatibility is not None,
                "compatibility_cooldown_sec": (
                    active_compatibility.get("compatibility_cooldown_sec") if active_compatibility else 0.0
                ),
                "scheduler_should_disable": scheduler_should_disable,
                "scheduler_skip_reason": scheduler_skip_reason,
                "last_error_type": self._last_failure_type,
                "last_error_status_code": self._last_failure_status_code,
            }

        def _raise_compatibility_error(
            self,
            message: str,
            *,
            response: Optional[httpx.Response],
            payload: Any = None,
            raw_text_preview: str = "",
            content_preview: str = "",
            empty_200_response: bool = False,
            extra_metrics: Optional[dict[str, Any]] = None,
        ) -> None:
            metrics = self._response_structure_metrics(payload, response=response)
            if raw_text_preview:
                metrics["raw_text_preview"] = str(raw_text_preview)[:400]
            if content_preview:
                metrics["content_preview"] = str(content_preview)[:400]
            if extra_metrics:
                metrics.update(dict(extra_metrics or {}))
            raise StrategyLLMProviderCompatibilityError(
                message,
                metrics={
                    "status": "compatibility_failed",
                    "last_error_type": "ProviderCompatibilityError",
                    "last_error_status_code": getattr(response, "status_code", None),
                    "empty_200_response": bool(empty_200_response),
                    **metrics,
                },
            )

        def _raise_missing_content_error(
            self,
            *,
            request_kind: str,
            payload: Any,
            response: Optional[httpx.Response],
        ) -> None:
            metrics = self._response_structure_metrics(payload, response=response)
            content_type = str(metrics.get("response_content_type") or "unknown")
            choice_keys = metrics.get("choice_keys") or []
            message_keys = metrics.get("message_keys") or []
            self._raise_compatibility_error(
                f"{request_kind}: response missing extractable content "
                f"(content-type={content_type}, choice_keys={choice_keys}, message_keys={message_keys})",
                response=response,
                payload=payload,
                empty_200_response=True,
            )

        def _recent_failure_degrade_state(self) -> tuple[int, Optional[str]]:
            initial_level = max(0, min(int(self.config.initial_compact_level or 0), 2))
            now = time.monotonic()
            if self._recent_timeout_cooldown_until > 0 and self._recent_timeout_cooldown_until <= now:
                self._recent_timeout_streak = 0
                self._recent_timeout_cooldown_until = 0.0
            if getattr(self, "_recent_overload_cooldown_until", 0.0) > 0 and self._recent_overload_cooldown_until <= now:
                self._recent_overload_streak = 0
                self._recent_overload_cooldown_until = 0.0
            if self._recent_timeout_streak >= max(1, int(self.config.recent_timeout_minimal_streak or 1)) and self._recent_timeout_cooldown_until > now:
                return max(initial_level, 2), 'recent_timeout'
            if getattr(self, "_recent_overload_streak", 0) >= max(1, int(getattr(self.config, "recent_overload_minimal_streak", 1) or 1)) and getattr(self, "_recent_overload_cooldown_until", 0.0) > now:
                return max(initial_level, 2), 'recent_overload'
            return initial_level, None

        def _record_request_failure(self, exc: Exception) -> None:
            self._last_failure_type = self._failure_type(exc)
            self._last_failure_status_code = self._status_code_from_error(exc)
            self._append_recent_request_outcome(status="failed")
            if self._is_connectivity_error(exc):
                self._recent_connectivity_streak = int(getattr(self, "_recent_connectivity_streak", 0) or 0) + 1
                self._recent_connectivity_cooldown_until = time.monotonic() + max(
                    0.0,
                    float(getattr(self.config, "recent_connectivity_cooldown_sec", 600.0) or 0.0),
                )
                self._recent_timeout_streak += 1
                self._recent_timeout_cooldown_until = time.monotonic() + max(0.0, float(self.config.recent_timeout_cooldown_sec or 0.0))
            elif self._is_timeout_like_error(exc):
                self._recent_timeout_streak += 1
                self._recent_timeout_cooldown_until = time.monotonic() + max(0.0, float(self.config.recent_timeout_cooldown_sec or 0.0))
            elif self._is_overload_like_error(exc):
                self._recent_overload_streak = int(getattr(self, "_recent_overload_streak", 0) or 0) + 1
                retry_after = self._retry_after_seconds(exc)
                cooldown_sec = max(
                    float(getattr(self.config, "recent_overload_cooldown_sec", 90.0) or 0.0),
                    float(retry_after or 0.0),
                )
                self._recent_overload_cooldown_until = time.monotonic() + max(0.0, cooldown_sec)

        def _record_compatibility_failure(self, exc: Exception) -> None:
            metrics = dict(getattr(exc, "metrics", {}) or {})
            self._last_failure_type = str(metrics.get("last_error_type") or exc.__class__.__name__)
            self._last_failure_status_code = self._status_code_from_error(exc)
            empty_200_response = self._is_empty_200_compatibility_metrics(
                {
                    **metrics,
                    "last_error": metrics.get("last_error") or self._error_text(exc),
                    "empty_200_response": metrics.get("empty_200_response"),
                }
            )
            self._last_compatibility_failure_metrics = {
                "status": "compatibility_failed",
                "last_error_type": self._last_failure_type,
                "last_error": self._error_text(exc),
                "empty_200_response": empty_200_response,
                **metrics,
            }
            self._append_recent_request_outcome(
                status="compatibility_failed",
                compatibility_failed=True,
                empty_200_response=empty_200_response,
            )
            cooldown_sec = max(0.0, float(getattr(self.config, "compatibility_cooldown_sec", 300.0) or 300.0))
            self._compatibility_cooldown_until = time.monotonic() + cooldown_sec if cooldown_sec > 0 else 0.0

        def _record_request_success(self) -> None:
            self._recent_timeout_streak = 0
            self._recent_timeout_cooldown_until = 0.0
            self._recent_connectivity_streak = 0
            self._recent_connectivity_cooldown_until = 0.0
            self._recent_overload_streak = 0
            self._recent_overload_cooldown_until = 0.0
            self._last_failure_type = None
            self._last_failure_status_code = None
            self._compatibility_cooldown_until = 0.0
            self._last_compatibility_failure_metrics = {}
            self._append_recent_request_outcome(status="succeeded")

        async def generate_candidates(
            self,
            *,
            snapshot: Optional[dict[str, Any]] = None,
            market_frame: Optional[pd.DataFrame] = None,
            research_context: Optional[dict[str, Any]] = None,
            parent_strategies: Optional[list[dict[str, Any]]] = None,
            history_summary: Optional[list[dict[str, Any]]] = None,
            research_task: Optional[dict[str, Any]] = None,
            limit: int = 3,
        ) -> Optional[dict[str, Any]]:
            if not self.is_enabled():
                return None
            await self._ensure_runtime_async_state()

            started_at = time.perf_counter()
            compatibility_metrics = self._active_compatibility_failure()
            if compatibility_metrics is not None:
                raise StrategyLLMRequestError(
                    "external llm request skipped during compatibility cooldown",
                    metrics={
                        "endpoint": self._endpoint(),
                        "provider": self.config.provider,
                        "model": self.config.model,
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                        **compatibility_metrics,
                        "status": "compatibility_skip",
                    },
                )
            connectivity_metrics = self._active_connectivity_failure()
            if connectivity_metrics is not None:
                raise StrategyLLMRequestError(
                    "external llm request skipped during connectivity cooldown",
                    metrics={
                        "endpoint": self._endpoint(),
                        "provider": self.config.provider,
                        "model": self.config.model,
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                        **connectivity_metrics,
                        "status": "cooldown_skip",
                    },
                )
            requested_limit = self._normalize_limit(limit)
            market_summary = self._summarize_market_frame(market_frame)
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            last_exc: Optional[Exception] = None
            attempts = max(1, int(self.config.retry_count or 0) + 1)
            attempt_reports: list[dict[str, Any]] = []
            initial_compact_level, degrade_reason = self._recent_failure_degrade_state()
            initial_prompt_profile = self._prompt_profile_name(initial_compact_level)
            effective_attempts = 1 if degrade_reason in {'recent_timeout', 'recent_overload'} else attempts
            client = self._client
            for attempt in range(1, effective_attempts + 1):
                compact_level = max(initial_compact_level, self._compact_level_for_attempt(attempt, effective_attempts))
                request_limit = self._request_limit_for_attempt(requested_limit, attempt, initial_compact_level=initial_compact_level)
                compact_research_context = self._compact_research_context(research_context, compact_level=compact_level)
                system_prompt, user_prompt = self._build_prompt(
                    snapshot or {},
                    market_summary,
                    compact_research_context,
                    list(parent_strategies or []),
                    list(history_summary or []),
                    request_limit,
                    research_task=research_task,
                    compact_level=compact_level,
                )
                prompt_profile = self._prompt_profile_name(compact_level)
                request_timeout_sec = self._timeout_for_attempt(attempt, effective_attempts)
                if degrade_reason in {'recent_timeout', 'recent_overload'} and attempt == 1:
                    request_timeout_sec = max(request_timeout_sec, min(float(self.config.timeout_sec or request_timeout_sec), 15.0))
                max_tokens = self._max_tokens_for_attempt(request_limit, compact_level)
                payload = {
                    "model": self.config.model,
                    "temperature": self.config.temperature,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                request_started_at = time.perf_counter()
                try:
                    async with self._request_semaphore:
                        data, body, content, compatibility_mode = await self._request_and_parse_payload(
                            headers=headers,
                            request_payload=payload,
                            request_kind="generate_candidates",
                            timeout=self._request_timeout(request_timeout_sec),
                        )
                    raw_candidates = data.get("candidates") if isinstance(data, dict) else None
                    if not isinstance(raw_candidates, list):
                        raise ValueError("external llm response missing candidates")
                    analysis = self._normalize_analysis(data.get("analysis") if isinstance(data, dict) else {})
                    candidates = []
                    for item in raw_candidates:
                        normalized_candidate = self._normalize_candidate_payload(
                            item,
                            research_task=research_task,
                            allow_legacy_contract_defaults=True,
                        )
                        if normalized_candidate is not None:
                            candidates.append(normalized_candidate)
                    selected_candidates = candidates[:requested_limit]
                    self._record_request_success()
                    request_metrics = {
                        "status": "succeeded",
                        "endpoint": self._endpoint(),
                        "provider": self.config.provider,
                        "model": self.config.model,
                        "requested_limit": requested_limit,
                        "attempt_count": attempt,
                        "prompt_profile": prompt_profile,
                        "initial_prompt_profile": initial_prompt_profile,
                        "degrade_reason": degrade_reason,
                        "recent_timeout_streak": self._recent_timeout_streak,
                        "prompt_chars": len(system_prompt) + len(user_prompt),
                        "max_tokens": max_tokens,
                        "response_chars": len(content),
                        "raw_candidate_count": len(raw_candidates),
                        "returned_candidate_count": len(candidates),
                        "selected_candidate_count": len(selected_candidates),
                        "non_executable_candidate_count": max(0, len(raw_candidates) - len(candidates)),
                        "analysis_present": bool(analysis),
                        "analysis_keys": sorted(list(analysis.keys())),
                        "compatibility_mode": compatibility_mode,
                        "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                        "attempts": [*attempt_reports, {
                            "attempt": attempt,
                            "status": "succeeded",
                            "request_limit": request_limit,
                            "timeout_sec": request_timeout_sec,
                            "prompt_profile": prompt_profile,
                            "prompt_chars": len(system_prompt) + len(user_prompt),
                            "max_tokens": max_tokens,
                            "elapsed_seconds": round(time.perf_counter() - request_started_at, 4),
                            "raw_candidate_count": len(raw_candidates),
                            "returned_candidate_count": len(candidates),
                            "non_executable_candidate_count": max(0, len(raw_candidates) - len(candidates)),
                            "analysis_present": bool(analysis),
                            "compatibility_mode": compatibility_mode,
                        }],
                    }
                    return {
                        "provider": self.config.provider,
                        "model": self.config.model,
                        "prompt": {
                            "system": system_prompt,
                            "user": user_prompt,
                            "profile": prompt_profile,
                        },
                        "raw_candidates": [dict(item or {}) for item in raw_candidates],
                        "raw_response": body,
                        "content": content,
                        "analysis": analysis,
                        "research_context": compact_research_context,
                        "research_task": dict(research_task or {}),
                        "candidates": selected_candidates,
                        "compatibility_mode": compatibility_mode,
                        "request_metrics": request_metrics,
                    }
                except StrategyLLMProviderCompatibilityError as exc:
                    last_exc = exc
                    attempt_reports.append({
                        "attempt": attempt,
                        "status": "compatibility_failed",
                        "request_limit": request_limit,
                        "timeout_sec": request_timeout_sec,
                        "prompt_profile": prompt_profile,
                        "prompt_chars": len(system_prompt) + len(user_prompt),
                        "max_tokens": max_tokens,
                        "degrade_reason": degrade_reason,
                        "initial_prompt_profile": initial_prompt_profile,
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
                        "request_limit": request_limit,
                        "timeout_sec": request_timeout_sec,
                        "prompt_profile": prompt_profile,
                        "prompt_chars": len(system_prompt) + len(user_prompt),
                        "max_tokens": max_tokens,
                        "degrade_reason": degrade_reason,
                        "initial_prompt_profile": initial_prompt_profile,
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
                            base_delay=float(self.config.retry_backoff_sec or 0.0),
                        )
                    )

            if last_exc is not None:
                if isinstance(last_exc, StrategyLLMProviderCompatibilityError):
                    self._record_compatibility_failure(last_exc)
                else:
                    self._record_request_failure(last_exc)
            metrics = {
                "status": "failed",
                "endpoint": self._endpoint(),
                "provider": self.config.provider,
                "model": self.config.model,
                "requested_limit": requested_limit,
                "initial_prompt_profile": initial_prompt_profile,
                "degrade_reason": degrade_reason,
                "recent_timeout_streak": self._recent_timeout_streak,
                "recent_timeout_cooldown_sec": round(max(self._recent_timeout_cooldown_until - time.monotonic(), 0.0), 4),
                "recent_overload_streak": int(getattr(self, "_recent_overload_streak", 0) or 0),
                "recent_overload_cooldown_sec": round(max(getattr(self, "_recent_overload_cooldown_until", 0.0) - time.monotonic(), 0.0), 4),
                "elapsed_seconds": round(time.perf_counter() - started_at, 4),
                "attempt_count": len(attempt_reports),
                "attempts": attempt_reports,
                "last_error_type": self._failure_type(last_exc) if last_exc else "RuntimeError",
                "last_error_status_code": self._status_code_from_error(last_exc) if last_exc else None,
                "last_error": self._error_text(last_exc or RuntimeError("external llm request failed")),
            }
            if isinstance(last_exc, StrategyLLMProviderCompatibilityError):
                metrics.update(dict(getattr(last_exc, "metrics", {}) or {}))
            raise StrategyLLMRequestError(
                f"external llm request failed after {len(attempt_reports)} attempts: {metrics['last_error_type']}",
                metrics=metrics,
            ) from last_exc

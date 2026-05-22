        def _runtime_client_is_customized(client: Any) -> bool:
            if client is None:
                return False
            if not isinstance(client, httpx.AsyncClient):
                return True
            client_dict = getattr(client, "__dict__", {}) or {}
            return "post" in client_dict or "stream" in client_dict

        async def _ensure_runtime_async_state(self) -> None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop_id = id(loop)
            if getattr(self, "_runtime_loop_id", None) == loop_id:
                return
            client = getattr(self, "_client", None)
            client_is_customized = self._runtime_client_is_customized(client)
            if client is not None and not client_is_customized:
                try:
                    await client.aclose()
                except Exception:
                    pass
            self._request_semaphore = asyncio.Semaphore(max(1, int(self.config.max_concurrency or 1)))
            if client is None or not client_is_customized:
                self._client = httpx.AsyncClient(follow_redirects=True, http2=False)
            self._runtime_loop_id = loop_id

        def _timeout_for_attempt(self, attempt: int, total_attempts: int) -> float:
            base = max(float(self.config.timeout_sec or 0), 5.0)
            if total_attempts <= 1:
                return base
            if total_attempts == 2:
                schedule = [
                    min(base, max(12.0, round(base * 0.6, 4))),
                    base,
                ]
            else:
                schedule = [
                    min(base, max(12.0, round(base * 0.5, 4))),
                    min(base, max(20.0, round(base * 0.75, 4))),
                    base,
                ]
            timeout_sec = schedule[min(max(attempt - 1, 0), len(schedule) - 1)]
            return max(5.0, timeout_sec)

        def _request_timeout(self, request_timeout_sec: float) -> httpx.Timeout:
            connect_timeout = max(1.0, min(float(self.config.connect_timeout_sec or request_timeout_sec), request_timeout_sec))
            write_timeout = max(1.0, min(float(self.config.write_timeout_sec or request_timeout_sec), request_timeout_sec))
            pool_timeout = max(1.0, min(float(self.config.pool_timeout_sec or request_timeout_sec), request_timeout_sec))
            return httpx.Timeout(connect=connect_timeout, read=request_timeout_sec, write=write_timeout, pool=pool_timeout)

        def _request_limit_for_attempt(self, limit: int, attempt: int, *, initial_compact_level: int = 0) -> int:
            requested_limit = self._normalize_limit(limit)
            base_reduction = 1 if initial_compact_level >= 1 and requested_limit > 1 else 0
            minimum_limit = 2 if requested_limit >= 2 else 1
            return max(minimum_limit, requested_limit - base_reduction - max(0, attempt - 1))

        @staticmethod
        def _compact_level_for_attempt(attempt: int, total_attempts: int) -> int:
            index = max(int(attempt or 1) - 1, 0)
            if int(total_attempts or 1) <= 1:
                return 0
            if index == 0:
                return 0
            return 2

        def _max_tokens_for_attempt(self, request_limit: int, compact_level: int) -> int:
            base = max(128, int(self.config.max_tokens or 900))
            analysis_budget = 260 if compact_level <= 0 else (160 if compact_level == 1 else 96)
            candidate_budget = max(1, int(request_limit or 1)) * (220 if compact_level <= 0 else (170 if compact_level == 1 else 140))
            return max(128, min(base, analysis_budget + candidate_budget))

        @staticmethod
        def _is_timeout_like_error(exc: Exception) -> bool:
            return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError))

        @staticmethod
        def _is_connectivity_error(exc: Exception) -> bool:
            return isinstance(exc, httpx.ConnectError)

        @staticmethod
        def _status_code_from_error(exc: Exception) -> Optional[int]:
            try:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                return int(status_code) if status_code is not None else None
            except Exception:
                return None

        @staticmethod
        def _is_overload_status_code(status_code: Optional[int]) -> bool:
            return int(status_code or 0) in {429, 502, 503, 504, 529}

        def _is_overload_like_error(self, exc: Exception) -> bool:
            return self._is_overload_status_code(self._status_code_from_error(exc))

        def _failure_type(self, exc: Exception) -> str:
            status_code = self._status_code_from_error(exc)
            return f"HTTP{status_code}" if status_code else exc.__class__.__name__

        @staticmethod
        def _retry_after_seconds(exc: Exception) -> Optional[float]:
            response = getattr(exc, "response", None)
            headers = getattr(response, "headers", None)
            if headers is None:
                return None
            raw = headers.get("Retry-After") or headers.get("retry-after")
            if raw in (None, ""):
                return None
            try:
                return max(0.0, float(raw))
            except Exception:
                return None

        def _retry_backoff_delay(self, attempt: int, exc: Exception, *, base_delay: float, max_delay: float = 15.0) -> float:
            retry_after = self._retry_after_seconds(exc)
            if retry_after is not None:
                return min(max(retry_after, base_delay), max_delay)
            multiplier = 2.0 if self._is_overload_like_error(exc) else (1.5 if self._is_timeout_like_error(exc) else 1.0)
            delay = max(0.0, float(base_delay or 0.0)) * max(1.0, multiplier * (2 ** max(int(attempt) - 1, 0)))
            return min(delay, max_delay)

        def _should_retry_request_error(self, exc: Exception) -> bool:
            return self._is_timeout_like_error(exc) or self._is_overload_like_error(exc)

        def _raise_response_parse_error(
            self,
            message: str,
            *,
            response: Optional[httpx.Response],
            payload: Any = None,
            raw_text_preview: str = "",
            content_preview: str = "",
        ) -> None:
            metrics = self._response_structure_metrics(payload, response=response)
            if raw_text_preview:
                metrics["raw_text_preview"] = str(raw_text_preview)[:400]
            if content_preview:
                metrics["content_preview"] = str(content_preview)[:400]
            raise StrategyLLMResponseParseError(
                json.dumps(
                    {
                        "error": str(message),
                        "status_code": getattr(response, "status_code", None),
                        **metrics,
                    },
                    ensure_ascii=False,
                    default=str,
                )
            )

        def _active_compatibility_failure(self) -> Optional[dict[str, Any]]:
            now = time.monotonic()
            cooldown_until = float(getattr(self, "_compatibility_cooldown_until", 0.0) or 0.0)
            metrics = dict(getattr(self, "_last_compatibility_failure_metrics", {}) or {})
            if not metrics:
                return None
            if cooldown_until > 0 and cooldown_until <= now:
                self._compatibility_cooldown_until = 0.0
                self._last_compatibility_failure_metrics = {}
                return None
            if cooldown_until > 0:
                metrics["compatibility_cooldown_sec"] = round(max(cooldown_until - now, 0.0), 4)
            return metrics

        def _active_connectivity_failure(self) -> Optional[dict[str, Any]]:
            now = time.monotonic()
            cooldown_until = float(getattr(self, "_recent_connectivity_cooldown_until", 0.0) or 0.0)
            minimal_streak = max(1, int(getattr(self.config, "recent_connectivity_minimal_streak", 1) or 1))
            streak = int(getattr(self, "_recent_connectivity_streak", 0) or 0)
            if cooldown_until > 0 and cooldown_until <= now:
                self._recent_connectivity_streak = 0
                self._recent_connectivity_cooldown_until = 0.0
                return None
            if streak < minimal_streak or cooldown_until <= 0:
                return None
            return {
                "cooldown_reason": "recent_connectivity",
                "recent_connectivity_streak": streak,
                "recent_connectivity_cooldown_sec": round(max(cooldown_until - now, 0.0), 4),
                "last_error_type": self._last_failure_type or "ConnectError",
                "last_error_status_code": self._last_failure_status_code,
            }

        def _response_structure_metrics(
            self,
            payload: Any,
            *,
            response: Optional[httpx.Response],
        ) -> dict[str, Any]:
            body = dict(payload or {}) if isinstance(payload, dict) else {}
            choices = list(body.get("choices") or [])
            first_choice = dict(choices[0] or {}) if choices else {}
            message = dict(first_choice.get("message") or {})
            usage = dict(body.get("usage") or {})
            try:
                raw_preview = json.dumps(body, ensure_ascii=False, default=str)[:400]
            except Exception:
                raw_preview = str(body)[:400]
            return {
                "response_content_type": str((getattr(response, "headers", {}) or {}).get("content-type") or ""),
                "response_keys": sorted(str(key) for key in list(body.keys())[:20]),
                "choice_keys": sorted(str(key) for key in list(first_choice.keys())[:20]),
                "message_keys": sorted(str(key) for key in list(message.keys())[:20]),
                "finish_reason": first_choice.get("finish_reason"),
                "completion_tokens": usage.get("completion_tokens"),
                "raw_response_preview": raw_preview,
            }

        @staticmethod
        def _is_empty_200_compatibility_metrics(metrics: Optional[dict[str, Any]]) -> bool:
            payload = dict(metrics or {})
            error_text = str(payload.get("last_error") or "").strip().lower()
            return bool(payload.get("empty_200_response")) or "missing extractable content" in error_text

        @staticmethod
        def _has_direct_json_payload(payload: Any) -> bool:
            if isinstance(payload, list):
                return True
            if not isinstance(payload, dict):
                return False
            return "choices" not in payload and "output" not in payload

        @classmethod
        def _append_text_fragments(cls, fragments: list[str], value: Any) -> None:
            if value is None:
                return
            if isinstance(value, str):
                fragments.append(value)
                return
            if isinstance(value, list):
                for item in value:
                    cls._append_text_fragments(fragments, item)
                return
            if isinstance(value, dict):
                if isinstance(value.get("text"), str):
                    fragments.append(str(value.get("text") or ""))
                elif "text" in value:
                    cls._append_text_fragments(fragments, value.get("text"))
                if isinstance(value.get("delta"), str):
                    fragments.append(str(value.get("delta") or ""))
                elif "delta" in value:
                    cls._append_text_fragments(fragments, value.get("delta"))
                if "content" in value:
                    cls._append_text_fragments(fragments, value.get("content"))
                if "output_text" in value:
                    cls._append_text_fragments(fragments, value.get("output_text"))

        @classmethod
        def _extract_stream_event_text(cls, payload: Any, *, event_name: str = "") -> str:
            fragments: list[str] = []
            if not isinstance(payload, dict):
                return ""

            for choice in list(payload.get("choices") or []):
                if not isinstance(choice, dict):
                    continue
                cls._append_text_fragments(fragments, choice.get("delta"))
                cls._append_text_fragments(fragments, choice.get("message"))

            payload_type = str(payload.get("type") or event_name or "").strip().lower()
            if payload_type.endswith("output_text.delta"):
                cls._append_text_fragments(fragments, payload.get("delta"))
            if payload_type.endswith("output_text.done"):
                cls._append_text_fragments(fragments, payload.get("text"))

            cls._append_text_fragments(fragments, payload.get("item"))
            cls._append_text_fragments(fragments, payload.get("response"))
            return "".join(fragments)

        @staticmethod
        def _parse_sse_events(raw_text: str) -> list[dict[str, Any]]:
            events: list[dict[str, Any]] = []
            current_event: Optional[str] = None
            current_data_lines: list[str] = []

            def _flush() -> None:
                nonlocal current_event, current_data_lines
                if current_event is None and not current_data_lines:
                    return
                data_raw = "\n".join(current_data_lines).strip()
                record: dict[str, Any] = {
                    "event": current_event,
                    "data_raw": data_raw,
                }
                if data_raw == "[DONE]":
                    record["done"] = True
                elif data_raw:
                    try:
                        record["payload"] = json.loads(data_raw)
                    except Exception:
                        record["payload"] = None
                events.append(record)
                current_event = None
                current_data_lines = []

            for raw_line in str(raw_text or "").splitlines():
                line = raw_line.rstrip("\r")
                if not line.strip():
                    _flush()
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip() or None
                    continue
                if line.startswith("data:"):
                    current_data_lines.append(line[len("data:") :].strip())
                    continue
            _flush()
            return events

        def _should_retry_with_stream(self, exc: StrategyLLMProviderCompatibilityError) -> bool:
            metrics = dict(getattr(exc, "metrics", {}) or {})
            content_type = str(metrics.get("response_content_type") or "").strip().lower()
            error_text = self._error_text(exc).lower()
            if "missing extractable content" in error_text:
                return True
            if "text/event-stream" not in content_type:
                return False
            return False

        def _should_retry_without_response_format(
            self,
            exc: StrategyLLMProviderCompatibilityError,
            *,
            request_payload: Optional[dict[str, Any]],
        ) -> bool:
            if not isinstance(request_payload, dict):
                return False
            if "response_format" not in request_payload:
                return False
            metrics = dict(getattr(exc, "metrics", {}) or {})
            content_type = str(metrics.get("response_content_type") or "").strip().lower()
            if "application/json" not in content_type:
                return False
            return self._is_empty_200_compatibility_metrics(
                {
                    **metrics,
                    "last_error": metrics.get("last_error") or self._error_text(exc),
                }
            )

        async def _stream_parse_response_payload(
            self,
            *,
            headers: dict[str, Any],
            request_payload: dict[str, Any],
            request_kind: str,
            timeout: httpx.Timeout,
        ) -> tuple[Any, Any, str]:
            await self._ensure_runtime_async_state()
            stream_method = getattr(self._client, "stream", None)
            if not callable(stream_method):
                self._raise_compatibility_error(
                    f"{request_kind}: stream fallback unavailable for event-stream compatibility replay",
                    response=None,
                    payload=None,
                    empty_200_response=True,
                    extra_metrics={
                        "response_content_type": "text/event-stream",
                        "stream_fallback_unavailable": True,
                    },
                )

            stream_payload = dict(request_payload or {})
            stream_payload["stream"] = True
            raw_chunks: list[str] = []
            async with self._client.stream(
                "POST",
                self._endpoint(),
                headers={**headers, "Accept": "text/event-stream, application/json"},
                json=stream_payload,
                timeout=timeout,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    if chunk:
                        raw_chunks.append(str(chunk))
            raw_text = "".join(raw_chunks)
            events = self._parse_sse_events(raw_text)
            content_parts: list[str] = []
            last_payload: dict[str, Any] = {}
            for event in events:
                payload = event.get("payload")
                if isinstance(payload, dict):
                    last_payload = payload
                    text = self._extract_stream_event_text(payload, event_name=str(event.get("event") or ""))
                    if text:
                        content_parts.append(text)
            content = "".join(content_parts)
            if not str(content or "").strip():
                self._raise_missing_content_error(
                    request_kind=f"{request_kind}: stream replay",
                    payload=last_payload or None,
                    response=response,
                )
            parsed_text = self._extract_json_text(content)
            if not str(parsed_text or "").strip():
                self._raise_compatibility_error(
                    f"{request_kind}: stream replay content missing JSON payload",
                    response=response,
                    payload=last_payload or None,
                    raw_text_preview=raw_text,
                    content_preview=content,
                )
            try:
                parsed = json.loads(parsed_text)
            except Exception as exc:
                self._raise_response_parse_error(
                    f"{request_kind}: stream replay content is not valid JSON ({self._error_text(exc)})",
                    response=response,
                    payload=last_payload or None,
                    raw_text_preview=raw_text,
                    content_preview=content,
                )

            synthetic_body = {
                "id": last_payload.get("id") if isinstance(last_payload, dict) else None,
                "object": last_payload.get("object") if isinstance(last_payload, dict) else None,
                "model": last_payload.get("model") if isinstance(last_payload, dict) else None,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": content,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": last_payload.get("usage") if isinstance(last_payload, dict) else None,
                "compatibility_mode": "chat_stream_replay",
            }
            return parsed, synthetic_body, content

        def _parse_response_payload(
            self,
            response: httpx.Response,
            *,
            request_kind: str,
        ) -> tuple[Any, Any, str]:
            try:
                raw_text = str(getattr(response, "text", "") or "")
            except Exception:
                raw_text = ""
            try:
                body = response.json()
            except Exception as exc:
                empty_200_response = int(getattr(response, "status_code", 0) or 0) == 200 and not raw_text.strip()
                self._raise_compatibility_error(
                    f"{request_kind}: response body is not valid JSON ({self._error_text(exc)})",
                    response=response,
                    payload={},
                    raw_text_preview=raw_text,
                    empty_200_response=empty_200_response,
                )
            if self._has_direct_json_payload(body):
                return body, body, ""
            content = self._extract_content(body if isinstance(body, dict) else {})
            if not str(content or "").strip():
                self._raise_missing_content_error(
                    request_kind=request_kind,
                    payload=body,
                    response=response,
                )
            parsed_text = self._extract_json_text(content)
            if not str(parsed_text or "").strip():
                self._raise_compatibility_error(
                    f"{request_kind}: response content missing JSON payload",
                    response=response,
                    payload=body,
                    raw_text_preview=raw_text,
                    content_preview=content,
                )
            try:
                parsed = json.loads(parsed_text)
            except Exception as exc:
                self._raise_response_parse_error(
                    f"{request_kind}: response content is not valid JSON ({self._error_text(exc)})",
                    response=response,
                    payload=body,
                    raw_text_preview=raw_text,
                    content_preview=content,
                )
            return parsed, body, content

        async def _request_and_parse_payload(
            self,
            *,
            headers: dict[str, Any],
            request_payload: dict[str, Any],
            request_kind: str,
            timeout: httpx.Timeout,
            allow_response_format_replay: bool = True,
        ) -> tuple[Any, Any, str, str]:
            await self._ensure_runtime_async_state()
            # Transform payload for Responses API if needed
            actual_payload = self._adapt_payload_for_endpoint(request_payload)
            response = await self._client.post(
                self._endpoint(),
                headers=headers,
                json=actual_payload,
                timeout=timeout,
            )
            response.raise_for_status()
            try:
                parsed, body, content = self._parse_response_payload(
                    response,
                    request_kind=request_kind,
                )
                return parsed, body, content, "direct"
            except StrategyLLMProviderCompatibilityError as exc:
                if self._should_retry_with_stream(exc):
                    try:
                        parsed, body, content = await self._stream_parse_response_payload(
                            headers=headers,
                            request_payload=request_payload,
                            request_kind=request_kind,
                            timeout=timeout,
                        )
                        return parsed, body, content, "chat_stream_replay"
                    except StrategyLLMProviderCompatibilityError:
                        pass
                if allow_response_format_replay and self._should_retry_without_response_format(
                    exc,
                    request_payload=request_payload,
                ):
                    replay_payload = dict(request_payload or {})
                    replay_payload.pop("response_format", None)
                    parsed, body, content, inner_mode = await self._request_and_parse_payload(
                        headers=headers,
                        request_payload=replay_payload,
                        request_kind=f"{request_kind}: no-response-format replay",
                        timeout=timeout,
                        allow_response_format_replay=False,
                    )
                    replay_mode = (
                        "chat_no_response_format_replay"
                        if inner_mode == "direct"
                        else f"chat_no_response_format_{inner_mode}"
                    )
                    if isinstance(body, dict):
                        body = {
                            **body,
                            "compatibility_mode": replay_mode,
                        }
                    return parsed, body, content, replay_mode
                raise

        def _append_recent_request_outcome(
            self,
            *,
            status: str,
            compatibility_failed: bool = False,
            empty_200_response: bool = False,
        ) -> None:
            from collections import deque

            outcomes = getattr(self, "_recent_request_outcomes", None)
            if not isinstance(outcomes, deque):
                outcomes = deque(maxlen=12)
                self._recent_request_outcomes = outcomes
            outcomes.append(
                {
                    "status": str(status or "").strip().lower() or "unknown",
                    "compatibility_failed": bool(compatibility_failed),
                    "empty_200_response": bool(empty_200_response),
                }
            )

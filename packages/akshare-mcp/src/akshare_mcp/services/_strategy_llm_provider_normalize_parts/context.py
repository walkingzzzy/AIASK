        _LEGACY_PORTFOLIO_REQUIRED_KEYS = ("position_assumption", "target_weight_scheme")
        _LEGACY_EXECUTION_REQUIRED_KEYS = ("commission_rate", "slippage_bps", "tradability_filter", "slippage_model")
        _LEGACY_VALIDATION_REQUIRED_KEYS = ("profile", "validation_focus", "primary_validation_layer")

        @staticmethod
        def _openai_compatible_api_base(base_url: str) -> str:
            base = str(base_url or "").rstrip("/")
            if not base:
                return base
            lowered = base.lower()
            if lowered.endswith(("/chat/completions", "/responses")):
                return base
            remainder = base.split("://", 1)[1] if "://" in base else base
            path = remainder.split("/", 1)[1] if "/" in remainder else ""
            if not path:
                return f"{base}/v1"
            return base

        def _endpoint(self) -> str:
            base = self.config.base_url.rstrip("/")
            if base.endswith("/chat/completions"):
                return base
            if base.endswith("/responses"):
                return base
            api_base = self._openai_compatible_api_base(base)
            # Support openai_responses provider type
            if getattr(self.config, 'provider', '') == 'openai_responses':
                return f"{api_base}/responses"
            return f"{api_base}/chat/completions"

        def _adapt_payload_for_endpoint(self, payload: dict) -> dict:
            """Transform chat completions payload to Responses API format if needed."""
            if getattr(self.config, 'provider', '') != 'openai_responses':
                return payload
            # Convert chat completions format → Responses API format
            messages = payload.get("messages") or []
            # Build input from messages
            input_parts = []
            instructions = None
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    instructions = content
                else:
                    input_parts.append({"role": role, "content": content})
            # Use last user message as input if simple
            if len(input_parts) == 1 and input_parts[0]["role"] == "user":
                input_value = input_parts[0]["content"]
            else:
                input_value = input_parts
            adapted = {
                "model": payload.get("model", self.config.model),
                "input": input_value,
                "store": False,
            }
            if instructions:
                adapted["instructions"] = instructions
            if payload.get("max_tokens"):
                adapted["max_output_tokens"] = payload["max_tokens"]
            if payload.get("temperature") is not None:
                adapted["temperature"] = payload["temperature"]
            return adapted

        @staticmethod
        def _error_text(exc: Exception) -> str:
            text = str(exc or "").strip()
            return text or exc.__class__.__name__

        @staticmethod
        def _round_number(value: Any, digits: int = 6) -> Any:
            try:
                if isinstance(value, bool):
                    return value
                if isinstance(value, int):
                    return value
                if isinstance(value, float):
                    return round(value, digits)
            except Exception:
                return value
            return value

        @staticmethod
        def _compact_text(value: Any, limit: int = 120) -> str:
            text = str(value or '').strip()
            if len(text) <= limit:
                return text
            return text[: max(0, limit - 1)] + '...'

        @staticmethod
        def _extract_json_text(text: str) -> str:
            raw = str(text or "").strip()
            if not raw:
                return raw

            def balanced_slice(value: str, start: int) -> str:
                if start < 0 or start >= len(value) or value[start] not in "{[":
                    return ""
                stack: list[str] = []
                in_string = False
                escaped = False
                pairs = {"{": "}", "[": "]"}
                for index in range(start, len(value)):
                    char = value[index]
                    if in_string:
                        if escaped:
                            escaped = False
                        elif char == "\\":
                            escaped = True
                        elif char == '"':
                            in_string = False
                        continue
                    if char == '"':
                        in_string = True
                        continue
                    if char in pairs:
                        stack.append(pairs[char])
                        continue
                    if char in "}]":
                        if not stack or char != stack[-1]:
                            return ""
                        stack.pop()
                        if not stack:
                            return value[start : index + 1].strip()
                return ""

            def first_balanced_json(value: str) -> str:
                for index, char in enumerate(value):
                    if char in "{[":
                        candidate = balanced_slice(value, index)
                        if candidate:
                            return candidate
                return ""

            fence_blocks = re.findall(r"```[^\n`]*\n?(.*?)```", raw, flags=re.S)
            for block in fence_blocks:
                candidate = first_balanced_json(str(block or "").strip())
                if candidate:
                    return candidate
            if raw.startswith("{") or raw.startswith("["):
                candidate = balanced_slice(raw, 0)
                if candidate:
                    return candidate
                return raw
            candidate = first_balanced_json(raw)
            if candidate:
                return candidate
            return raw

        @staticmethod
        def _extract_content(payload: dict[str, Any]) -> str:
            choices = list(payload.get("choices") or [])
            if choices:
                first_choice = dict(choices[0] or {})
                message = dict(first_choice.get("message") or {})
                content = message.get("content")
                if isinstance(content, list):
                    return "\n".join(str(item.get("text") or item) for item in content)
                if content not in (None, ""):
                    return str(content)
                message_text = message.get("text")
                if message_text not in (None, ""):
                    return str(message_text)
                choice_text = first_choice.get("text")
                if choice_text not in (None, ""):
                    return str(choice_text)
                delta = dict(first_choice.get("delta") or {})
                delta_content = delta.get("content")
                if isinstance(delta_content, list):
                    return "\n".join(str(item.get("text") or item) for item in delta_content)
                if delta_content not in (None, ""):
                    return str(delta_content)
            output = list(payload.get("output") or [])
            parts = []
            for item in output:
                for content in list((item or {}).get("content") or []):
                    text = content.get("text") if isinstance(content, dict) else None
                    if text:
                        parts.append(str(text))
            if parts:
                return "\n".join(parts)
            output_text = payload.get("output_text")
            if output_text not in (None, ""):
                return str(output_text)
            return ""

        @staticmethod
        def _normalize_analysis(analysis: Any) -> dict[str, Any]:
            if not isinstance(analysis, dict):
                return {}
            normalized: dict[str, Any] = {}
            for key in ("market_regime", "style_bias", "hypothesis", "selection_notes", "risk_focus", "evidence", "universe_view", "selection_plan", "trade_plan"):
                value = analysis.get(key)
                if value is None:
                    continue
                if isinstance(value, list):
                    normalized[key] = [str(item) for item in value[:6]]
                elif isinstance(value, dict):
                    normalized[key] = value
                else:
                    normalized[key] = str(value)
            for key, value in analysis.items():
                if key not in normalized and len(normalized) < 10:
                    normalized[key] = value
            return normalized

        @staticmethod
        def _normalize_code_list(values: Any, limit: int = 12) -> list[str]:
            codes: list[str] = []
            seen: set[str] = set()

            def visit(value: Any):
                if value is None:
                    return
                if isinstance(value, dict):
                    for key in ('code', 'symbol', 'stock_code'):
                        if value.get(key) is not None:
                            visit(value.get(key))
                    for key in ('codes', 'symbols', 'stock_codes', 'target_symbols'):
                        if value.get(key) is not None:
                            visit(value.get(key))
                    return
                if isinstance(value, (list, tuple, set)):
                    for item in value:
                        visit(item)
                    return
                raw = str(value or '').strip()
                if not raw:
                    return
                if any(sep in raw for sep in [',', ';', '|', '\n', '\t', ' ']):
                    normalized = raw.replace(';', ',').replace('|', ',').replace('\n', ',').replace('\t', ',').replace(' ', ',')
                    for part in normalized.split(','):
                        visit(part)
                    return
                code = raw.split('.')[0].strip()
                if not code or code in seen:
                    return
                seen.add(code)
                codes.append(code)

            visit(values)
            return codes[: max(1, min(int(limit or 12), 40))]

        @staticmethod
        def _contract_value_missing(value: Any) -> bool:
            return value in (None, "", [], {})

        @classmethod
        def _has_required_contract_keys(
            cls,
            payload: Any,
            *,
            required_keys: tuple[str, ...],
        ) -> bool:
            if not isinstance(payload, dict) or not payload:
                return False
            return all(not cls._contract_value_missing(payload.get(key)) for key in required_keys)

        @classmethod
        def _canonicalize_validation_profile(
            cls,
            candidate: dict[str, Any],
            *,
            strategy_type: str,
            normalized_task: dict[str, Any],
            validation_profile: Any,
        ) -> dict[str, Any]:
            explicit_profile = dict(validation_profile or {}) if isinstance(validation_profile, dict) else {}
            canonical_profile = resolve_candidate_validation_profile(
                {
                    "strategy_type": strategy_type,
                    "research_task": dict(normalized_task),
                },
                research_task=normalized_task,
            )
            if not cls._has_required_contract_keys(
                explicit_profile,
                required_keys=cls._LEGACY_VALIDATION_REQUIRED_KEYS,
            ):
                return dict(canonical_profile)
            actual_profile = str(explicit_profile.get("profile") or "").strip().lower()
            actual_focus = str(explicit_profile.get("validation_focus") or "").strip().lower()
            actual_layer = str(explicit_profile.get("primary_validation_layer") or "").strip().lower()
            expected_profile = str(canonical_profile.get("profile") or "").strip().lower()
            expected_focus = str(canonical_profile.get("validation_focus") or "").strip().lower()
            expected_layer = str(canonical_profile.get("primary_validation_layer") or "").strip().lower()
            if (
                actual_profile == expected_profile
                and actual_focus == expected_focus
                and actual_layer == expected_layer
            ):
                return explicit_profile
            return {
                **explicit_profile,
                **canonical_profile,
            }

        @classmethod
        def _merge_precision_preferences(
            cls,
            validation_profile: dict[str, Any],
            *,
            candidate: dict[str, Any],
            normalized_task: dict[str, Any],
        ) -> dict[str, Any]:
            merged = dict(validation_profile or {})
            hypothesis_artifact = dict(candidate.get("hypothesis_artifact") or candidate.get("hypothesis_structured") or {})
            explicit_profile = dict(candidate.get("validation_profile") or {})
            for field_name in (
                "objective_profile",
                "trade_density_preference",
                "entry_selectivity",
                "regime_required",
                "cost_robust_required",
            ):
                for value in (
                    explicit_profile.get(field_name),
                    hypothesis_artifact.get(field_name),
                    normalized_task.get(field_name),
                ):
                    if value not in (None, "", [], {}):
                        merged[field_name] = value
                        break
            return merged

        @staticmethod
        def _normalize_targeting_policy_payload(
            payload: Any,
            *,
            fallback: dict[str, Any],
        ) -> dict[str, Any]:
            if isinstance(payload, dict) and payload:
                return dict(payload)
            if payload not in (None, "", [], {}):
                return {"mode": str(payload).strip()}
            return dict(fallback)

        @classmethod
        def _normalize_open_dsl_candidate_contract(
            cls,
            candidate: dict[str, Any],
            *,
            normalized_task: dict[str, Any],
        ) -> Optional[dict[str, Any]]:
            if not is_open_dsl_candidate(candidate):
                return None
            compilation = compile_open_dsl_candidate(candidate)
            if compilation.attempted and not compilation.accepted:
                candidate["_open_dsl_reject_reasons"] = list(compilation.reject_reasons)
                candidate["_open_dsl_audit"] = dict(compilation.audit or {})
                return None
            compiled = dict(compilation.compiled or {})
            params = dict(compiled.get("params") or {})
            compiled_dsl = dict(params.get("dsl") or {})
            if not compiled_dsl:
                candidate["_open_dsl_reject_reasons"] = ["open_dsl_missing:compiled_dsl"]
                candidate["_open_dsl_audit"] = dict(compilation.audit or {})
                return None
            compiled_meta = dict(compiled.get("metadata") or {})
            target_symbols = cls._normalize_code_list(
                [
                    candidate.get("target_symbols"),
                    candidate.get("stock_pool"),
                    compiled_meta.get("target_symbols"),
                    (compiled_dsl.get("metadata") or {}).get("target_symbols"),
                ],
                limit=8,
            )
            stock_pool_payload = candidate.get("stock_pool")
            stock_pool = {
                "selection_mode": "explicit" if target_symbols else "screened",
                "symbols": list(target_symbols),
            }
            if isinstance(stock_pool_payload, dict):
                stock_pool = {
                    "selection_mode": str(
                        stock_pool_payload.get("selection_mode")
                        or stock_pool_payload.get("mode")
                        or stock_pool.get("selection_mode")
                        or ""
                    ).strip()
                    or stock_pool.get("selection_mode")
                    or "screened",
                    "symbols": cls._normalize_code_list(
                        stock_pool_payload.get("symbols")
                        or stock_pool_payload.get("codes")
                        or target_symbols,
                        limit=8,
                    ),
                    "filters": dict(stock_pool_payload.get("filters") or {}),
                    "rationale": stock_pool_payload.get("rationale"),
                }
            strategy_type = str(candidate.get("strategy_type") or compiled.get("strategy_type") or "dsl_rule").strip() or "dsl_rule"
            holding_horizon = dict(candidate.get("holding_horizon") or compiled_meta.get("holding_horizon") or {})
            if not holding_horizon:
                holding_horizon = _default_holding_horizon(strategy_type, normalized_task, str(normalized_task.get("task_source") or ""))
            trade_plan = candidate.get("trade_plan")
            normalized_trade_plan = dict(trade_plan) if isinstance(trade_plan, dict) and trade_plan else _default_trade_plan(strategy_type, str(normalized_task.get("task_source") or ""))
            risk_rules = dict(candidate.get("risk_rules") or compiled_meta.get("risk_rules") or compiled_dsl.get("risk_rules") or {})
            if not risk_rules:
                risk_rules = _default_risk_rules(str(normalized_task.get("task_source") or ""), holding_horizon)
            position_sizing = candidate.get("position_sizing")
            normalized_position_sizing = dict(position_sizing) if isinstance(position_sizing, dict) and position_sizing else _default_position_sizing(target_symbols)
            rebalance_rule = candidate.get("rebalance_rule")
            normalized_rebalance_rule = dict(rebalance_rule) if isinstance(rebalance_rule, dict) and rebalance_rule else _default_rebalance_rule(strategy_type, str(normalized_task.get("task_source") or ""))
            portfolio_spec = dict(candidate.get("portfolio_spec") or {})
            if not cls._has_required_contract_keys(portfolio_spec, required_keys=cls._LEGACY_PORTFOLIO_REQUIRED_KEYS):
                portfolio_spec = {
                    "position_assumption": "single_name_full_notional" if len(target_symbols) <= 1 else "equal_weight_proxy",
                    "target_weight_scheme": "single_name" if len(target_symbols) <= 1 else "equal_weight",
                }
            execution_assumptions = dict(candidate.get("execution_assumptions") or {})
            if not cls._has_required_contract_keys(execution_assumptions, required_keys=cls._LEGACY_EXECUTION_REQUIRED_KEYS):
                execution_assumptions = {
                    "commission_rate": 0.00025,
                    "slippage_bps": 5,
                    "tradability_filter": True,
                    "slippage_model": "fixed",
                }
            validation_profile = cls._canonicalize_validation_profile(
                candidate,
                strategy_type=strategy_type,
                normalized_task=normalized_task,
                validation_profile=candidate.get("validation_profile"),
            )
            validation_profile = cls._merge_precision_preferences(
                validation_profile,
                candidate=candidate,
                normalized_task=normalized_task,
            )
            dsl_metadata = dict(compiled_dsl.get("metadata") or {})
            dsl_metadata.update(
                {
                    "target_symbols": list(target_symbols),
                    "stock_pool": dict(stock_pool),
                    "portfolio_spec": dict(portfolio_spec),
                    "execution_assumptions": dict(execution_assumptions),
                    "validation_profile": dict(validation_profile),
                    "open_dsl_audit": dict(compilation.audit or {}),
                    "open_dsl_source_mode": "provider_normalize_bridge",
                }
            )
            compiled_dsl["metadata"] = dsl_metadata
            return {
                **dict(candidate or {}),
                "strategy_type": strategy_type,
                "dsl": compiled_dsl,
                "target_symbols": list(target_symbols),
                "stock_pool": dict(stock_pool),
                "holding_horizon": dict(holding_horizon),
                "trade_plan": dict(normalized_trade_plan),
                "risk_rules": dict(risk_rules),
                "position_sizing": dict(normalized_position_sizing),
                "execution_notes": candidate.get("execution_notes") or compiled_meta.get("execution_notes") or "prefer liquid session execution with tradability filter",
                "rebalance_rule": dict(normalized_rebalance_rule),
                "portfolio_spec": dict(portfolio_spec),
                "execution_assumptions": dict(execution_assumptions),
                "validation_profile": dict(validation_profile),
                "_open_dsl_audit": dict(compilation.audit or {}),
                "_open_dsl_compiled": True,
            }

        @classmethod
        def _require_explicit_contract_dict(
            cls,
            candidate: dict[str, Any],
            field: str,
            *,
            required_keys: tuple[str, ...],
        ) -> tuple[dict[str, Any], list[str]]:
            payload = candidate.get(field)
            if not isinstance(payload, dict) or not payload:
                return {}, [f"{field}_missing"]
            normalized = dict(payload)
            missing_keys = [
                key
                for key in required_keys
                if cls._contract_value_missing(normalized.get(key))
            ]
            if missing_keys:
                return normalized, [f"{field}_missing_keys:{','.join(missing_keys)}"]
            return normalized, []

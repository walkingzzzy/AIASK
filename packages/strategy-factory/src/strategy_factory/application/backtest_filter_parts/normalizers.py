    """回测筛选候选策略。"""

    SHARPE_MIN = BACKTEST_DEFAULT_THRESHOLDS["sharpe_min"]
    MDD_MAX = BACKTEST_DEFAULT_THRESHOLDS["mdd_max"]
    TRADES_MIN = BACKTEST_DEFAULT_THRESHOLDS["trades_min"]
    MIN_SAMPLES = BACKTEST_DEFAULT_THRESHOLDS["min_samples"]

    def __init__(self):
        self.last_report: dict = {
            "summary": {
                "input_count": 0,
                "passed_count": 0,
                "failed_count": 0,
                "strategy_type_counts": {},
                "passed_strategy_type_counts": {},
                "failed_strategy_type_counts": {},
                "failed_reason_counts": {},
                "thresholds_by_type": {},
            },
            "passed": [],
            "failed": [],
        }
        self.type_thresholds = dict(BACKTEST_TYPE_THRESHOLDS)
        self._kline_cache: dict[str, list] = {}

    async def preload_klines(self, db, codes: list[str] | None = None) -> None:
        """批量预取 K 线至缓存，后续 _test_one 复用。"""
        representative_stocks = list(_compat_setting("REPRESENTATIVE_STOCKS", REPRESENTATIVE_STOCKS))
        code_concurrency = int(_compat_setting("BACKTEST_CODE_CONCURRENCY", BACKTEST_CODE_CONCURRENCY) or BACKTEST_CODE_CONCURRENCY)
        codes = list(dict.fromkeys(codes or representative_stocks))
        sem = asyncio.Semaphore(code_concurrency)

        async def _fetch(code: str) -> None:
            async with sem:
                try:
                    self._kline_cache[code] = await db.get_klines(code, limit=500)
                except Exception:
                    pass

        await asyncio.gather(*[_fetch(c) for c in codes if c not in self._kline_cache])

    def get_last_report(self) -> dict:
        return self.last_report

    @staticmethod
    def _count_by_strategy_type(items: List[dict]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in items:
            strategy_type = str(item.get("strategy_type") or "unknown")
            counts[strategy_type] = counts.get(strategy_type, 0) + 1
        return counts

    @staticmethod
    def _build_report_entry(candidate: dict) -> dict:
        return {
            "strategy_type": candidate.get("strategy_type"),
            "generator_type": candidate.get("generator_type"),
            "params": candidate.get("params"),
            "spawn_reason": candidate.get("spawn_reason"),
            "generation_reason": candidate.get("generation_reason") or {},
            "target_symbols": candidate.get("target_symbols") or _extract_target_codes_from_payload(candidate),
            "stock_pool": candidate.get("stock_pool") or {},
            "selection_logic": candidate.get("selection_logic") or [],
            "research_task": candidate.get("research_task") or {},
            "event_context": candidate.get("event_context") or {},
            "tags": candidate.get("tags") or [],
            "constraint_check": candidate.get("constraint_check") or {},
            "validation_profile": candidate.get("validation_profile") or {},
            "backtest_result": candidate.get("backtest_result") or {},
            "backtest_metrics": candidate.get("backtest_metrics") or {},
            "backtest_metrics_contract": candidate.get("backtest_metrics_contract") or {},
        }

    @staticmethod
    def _build_failed_metric(field: str, operator: str, threshold: Any, actual: Any, label: str) -> dict:
        return {
            "field": field,
            "operator": operator,
            "threshold": threshold,
            "actual": actual,
            "label": label,
        }

    def _get_thresholds(self, strategy_type: str, candidate: Optional[dict] = None) -> dict:
        thresholds = {
            **dict(_compat_setting("BACKTEST_DEFAULT_THRESHOLDS", BACKTEST_DEFAULT_THRESHOLDS)),
            **(dict(_compat_setting("BACKTEST_TYPE_THRESHOLDS", BACKTEST_TYPE_THRESHOLDS)).get(strategy_type) or {}),
        }
        candidate = dict(candidate or {})
        tags = {str(tag).strip().lower() for tag in list(candidate.get("tags") or [])}
        generator_type = str(candidate.get("generator_type") or "").strip().lower()
        has_parent_strategy = bool(str(candidate.get("parent_strategy_id") or "").strip())
        if (
            strategy_type == "dsl_rule"
            or generator_type in {"external_llm", "llm_proxy", "pipeline_staged", "rl_bandit"}
            or "external_llm" in tags
            or "ai_generated" in tags
            or "llm_proxy_fallback" in tags
            or has_parent_strategy
        ):
            thresholds = {**thresholds, **dict(_compat_setting("BACKTEST_AI_PROTOTYPE_THRESHOLDS", BACKTEST_AI_PROTOTYPE_THRESHOLDS))}
        submission_trade_floor = self._resolve_submission_trade_count_floor(candidate)
        if submission_trade_floor > 0:
            thresholds["trades_min"] = max(float(thresholds.get("trades_min") or 0.0), submission_trade_floor)
        return thresholds

    @classmethod
    def _resolve_submission_trade_count_floor(cls, candidate: Optional[dict] = None) -> float:
        payload = apply_resolved_candidate_envelope(candidate or {})
        research_task = _normalize_research_task_contract(payload.get("research_task") or {})
        validation_focus = str(research_task.get("validation_focus") or "").strip().lower()
        target_codes = _extract_target_codes_from_payload(payload, limit=12)
        if not _is_single_target_bulk_candidate_target_only(
            payload,
            research_task=research_task,
            validation_focus=validation_focus,
            target_codes=target_codes,
        ):
            return 0.0

        trade_floor = float(FACTORY_SUBMISSION_MIN_BACKTEST_TRADES)
        try:
            from .submission_gate import _resolve_validation_profile, _trade_gate_thresholds

            profile = _resolve_validation_profile(payload)
            trade_floor = max(
                trade_floor,
                float(_trade_gate_thresholds(profile, admission_level="incubation").get("trade_count_min") or 0.0),
            )
        except Exception:
            pass
        return max(0.0, trade_floor)

    @classmethod
    def _collect_preload_codes(cls, candidates: List[dict]) -> List[str]:
        ordered_codes: List[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            evaluated_codes, _, _, _, _ = cls._resolve_backtest_plan(candidate)
            for code in evaluated_codes:
                if code in seen:
                    continue
                seen.add(code)
                ordered_codes.append(code)
        return ordered_codes

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): BacktestFilter._json_safe(item)
                for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            }
        if isinstance(value, (list, tuple, set)):
            return [BacktestFilter._json_safe(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _build_shared_result_key(self, candidate: dict) -> str:
        strategy_type = str(candidate.get("strategy_type") or "unknown").strip().lower() or "unknown"
        research_task = _normalize_research_task_contract(candidate.get("research_task") or {})
        evaluated_codes, target_codes, representative_codes, code_source, validation_focus = self._resolve_backtest_plan(candidate)
        params = dict(candidate.get("params") or {})
        identity = structural_identity(candidate)
        if not params.get("strategy_instance_hash") or not params.get("tested_object_hash"):
            params = materialize_strategy_params(
                strategy_type,
                params,
                seed_context={"source": "backtest_filter_identity", "validation_focus": validation_focus},
                slot_index=0,
                targets=target_codes or _extract_target_codes_from_payload(candidate, limit=20),
            )
            candidate["params"] = params
            identity = structural_identity({**candidate, "params": params})
            candidate["strategy_instance_hash"] = params.get("strategy_instance_hash")
            candidate["tested_object_hash"] = params.get("tested_object_hash")
            candidate["candidate_contract_hash"] = params.get("candidate_contract_hash")
        contract_hash = build_candidate_contract_hash(candidate)
        sanitized_params = executable_param_payload(strategy_type, params)
        targets = target_payload(candidate, params)
        signature_payload = {
            "candidate_contract_hash": contract_hash,
            "candidate_contract_hash_param": params.get("candidate_contract_hash"),
            "strategy_instance_hash": params.get("strategy_instance_hash") or identity.get("strategy_instance_hash"),
            "tested_object_hash": params.get("tested_object_hash") or identity.get("tested_object_hash"),
            "param_fingerprint": params.get("param_fingerprint") or identity.get("param_fingerprint"),
            "target_fingerprint": params.get("target_fingerprint") or identity.get("target_fingerprint"),
            "logic_fingerprint": params.get("logic_fingerprint") or identity.get("logic_fingerprint"),
            "strategy_type": strategy_type,
            "params": sanitized_params,
            "target_identity": targets,
            "research_task": research_task,
            "target_codes": target_codes,
            "representative_codes": representative_codes,
            "evaluated_codes": evaluated_codes,
            "code_source": code_source,
            "validation_focus": validation_focus,
            "execution_assumptions": dict(candidate.get("execution_assumptions") or {}),
            "portfolio_spec": dict(candidate.get("portfolio_spec") or {}),
            "generator_type": str(candidate.get("generator_type") or "").strip().lower(),
            "tags": sorted(
                str(tag).strip().lower()
                for tag in list(candidate.get("tags") or [])
                if str(tag).strip()
            ),
            "parent_strategy_id": str(candidate.get("parent_strategy_id") or "").strip(),
            "thresholds": self._get_thresholds(strategy_type, candidate),
        }
        serialized = json.dumps(
            self._json_safe(signature_payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"shared:{hashlib.sha1(serialized.encode('utf-8')).hexdigest()}"

    @staticmethod
    def _build_candidate_exception_result(candidate: dict, error: BaseException) -> dict:
        return {
            "passed": False,
            "reason_code": "candidate_exception",
            "reason": f"候选策略回测异常: {type(error).__name__}",
            "strategy_type": candidate.get("strategy_type") or "unknown",
            "sample_count": 0,
            "required_sample_count": 0,
            "evaluated_code_count": 0,
            "successful_code_count": 0,
            "evaluated_codes": [],
            "successful_codes": [],
            "target_codes": _extract_target_codes_from_payload(candidate),
            "representative_codes": [],
            "code_source": "candidate_exception",
            "primary_layer": "none",
            "queue_wait_ms": 0.0,
            "backtest_run_ms": 0.0,
            "code_run_ms_total": 0.0,
            "code_run_count": 0,
            "failed_metrics": [],
            "failed_codes": [],
            "skipped_codes": [],
            "metrics": {},
            "error": f"{type(error).__name__}: {error}",
        }

    @staticmethod
    def _annotate_shared_result(candidate: dict, result: dict, *, key: str, reused: bool, reuse_count: int) -> dict:
        payload = deepcopy(dict(result or {}))
        params = dict(candidate.get("params") or {})
        payload["constraint_check"] = dict(candidate.get("constraint_check") or payload.get("constraint_check") or {})
        payload["shared_result_key"] = key
        payload["shared_result_reused"] = bool(reused)
        payload["shared_result_reuse_count"] = max(0, int(reuse_count or 0))
        payload["strategy_instance_hash"] = params.get("strategy_instance_hash") or candidate.get("strategy_instance_hash")
        payload["tested_object_hash"] = params.get("tested_object_hash") or candidate.get("tested_object_hash")
        payload["cache_identity_fields"] = {
            "strategy_instance_hash": payload.get("strategy_instance_hash"),
            "tested_object_hash": payload.get("tested_object_hash"),
            "candidate_contract_hash": params.get("candidate_contract_hash") or candidate.get("candidate_contract_hash"),
            "param_fingerprint": params.get("param_fingerprint"),
            "target_fingerprint": params.get("target_fingerprint"),
            "logic_fingerprint": params.get("logic_fingerprint"),
        }
        return payload

    def _apply_result_to_candidate(
        self,
        candidate: dict,
        result: dict,
        passed: List[dict],
        failed: List[dict],
    ) -> None:
        candidate["backtest_result"] = result
        derived_trade_metrics = self._derive_trade_validation_metrics(candidate, result)
        metrics_contract = self._build_backtest_metrics_contract(candidate, result)
        candidate["backtest_metrics_contract"] = metrics_contract
        candidate["backtest_metrics"] = {
            **dict(result.get("metrics") or {}),
            "constraint_check": dict(result.get("constraint_check") or {}),
            "target_quality_summary": dict(result.get("target_quality_summary") or {}),
            "validation_focus": result.get("validation_focus"),
            "primary_validation_layer": result.get("primary_validation_layer"),
            "event_window_config": dict(result.get("event_window_config") or {}),
            "contamination_summary": dict(result.get("contamination_summary") or {}),
            "cost_assumptions": dict(result.get("cost_assumptions") or {}),
            "explicit_cost_breakdown": dict(result.get("explicit_cost_breakdown") or {}),
            "implicit_cost_breakdown": dict(result.get("implicit_cost_breakdown") or {}),
            "tradability_summary": dict(result.get("tradability_summary") or {}),
            "capacity_summary": dict(result.get("capacity_summary") or {}),
            "implementation_shortfall_model_source": result.get("implementation_shortfall_model_source"),
            "implementation_shortfall_components": dict(result.get("implementation_shortfall_components") or {}),
            "position_assumption": result.get("position_assumption"),
            "execution_summary": dict(result.get("execution_summary") or {}),
            "cash_curve_summary": _summarize_numeric_series(result.get("cash_curve")),
            "gross_exposure_curve_summary": _summarize_numeric_series(result.get("gross_exposure_curve")),
            "net_exposure_curve_summary": _summarize_numeric_series(result.get("net_exposure_curve")),
            "target_layer_metrics": _compact_backtest_metric_payload(
                ((result.get("layers") or {}).get("target") or {}).get("metrics") or {}
            ),
            "representative_layer_metrics": _compact_backtest_metric_payload(
                ((result.get("layers") or {}).get("representative") or {}).get("metrics") or {}
            ),
            "combined_layer_metrics": _compact_backtest_metric_payload(
                ((result.get("layers") or {}).get("combined") or {}).get("metrics") or {}
            ),
            "event_window_metrics": dict(result.get("event_window_metrics") or {}),
            "target_layer_oos_return": float((((result.get("layers") or {}).get("target") or {}).get("metrics") or {}).get("total_return") or 0.0),
            "post_cost_sharpe": float((result.get("metrics") or {}).get("sharpe_ratio") or 0.0),
            "backtest_assumptions": dict(result.get("backtest_assumptions") or {}),
            "backtest_metrics_contract": metrics_contract,
            "backtest_metrics_contract_status": metrics_contract.get("status"),
            **derived_trade_metrics,
        }
        if result.get("passed"):
            passed.append(candidate)
        else:
            failed.append(candidate)

    def _build_last_report(self, candidates: List[dict], passed: List[dict], failed: List[dict]) -> dict:
        failed_reason_counts: Dict[str, int] = {}
        thresholds_by_type: Dict[str, dict] = {}
        candidate_run_ms_total = 0.0
        code_run_ms_total = 0.0
        code_run_count = 0
        cache_hit_total = 0
        evaluated_code_total = 0
        shared_result_reused_count = 0
        shared_result_keys: set[str] = set()
        for item in candidates:
            strategy_type = str(item.get("strategy_type") or "unknown")
            result = item.get("backtest_result") or {}
            thresholds_by_type[strategy_type] = result.get("thresholds") or self._get_thresholds(strategy_type, item)
            candidate_run_ms_total += float(result.get("backtest_run_ms") or 0.0)
            code_run_ms_total += float(result.get("code_run_ms_total") or 0.0)
            code_run_count += int(result.get("code_run_count") or 0)
            cache_hit_total += int(result.get("kline_cache_hit_count") or 0)
            evaluated_code_total += int(result.get("evaluated_code_count") or 0)
            shared_result_reused_count += int(bool(result.get("shared_result_reused")))
            if int(result.get("shared_result_reuse_count") or 0) > 0 and str(result.get("shared_result_key") or "").strip():
                shared_result_keys.add(str(result.get("shared_result_key")))
        for item in failed:
            reason_code = str((item.get("backtest_result") or {}).get("reason_code") or "unknown")
            failed_reason_counts[reason_code] = failed_reason_counts.get(reason_code, 0) + 1
        candidate_count = len(candidates)
        return {
            "summary": {
                "input_count": candidate_count,
                "passed_count": len(passed),
                "failed_count": len(failed),
                "strategy_type_counts": self._count_by_strategy_type(candidates),
                "passed_strategy_type_counts": self._count_by_strategy_type(passed),
                "failed_strategy_type_counts": self._count_by_strategy_type(failed),
                "failed_reason_counts": failed_reason_counts,
                "thresholds_by_type": thresholds_by_type,
                "avg_candidate_ms": round(candidate_run_ms_total / candidate_count, 2) if candidate_count else 0.0,
                "avg_code_ms": round(code_run_ms_total / code_run_count, 2) if code_run_count else 0.0,
                "cache_hit_ratio": round(cache_hit_total / evaluated_code_total, 4) if evaluated_code_total else 0.0,
                "shared_result_reused_count": shared_result_reused_count,
                "shared_result_group_count": len(shared_result_keys),
            },
            "passed": [self._build_report_entry(item) for item in passed],
            "failed": [self._build_report_entry(item) for item in failed],
        }

    async def filter(self, candidates: List[dict], db) -> List[dict]:
        for candidate in candidates:
            resolved_candidate = apply_resolved_candidate_envelope(candidate)
            candidate.clear()
            candidate.update(resolved_candidate)
        BacktestEngine = get_backtest_engine_class()
        passed: List[dict] = []
        failed: List[dict] = []
        candidate_concurrency = int(_compat_setting("BACKTEST_CONCURRENCY", BACKTEST_CONCURRENCY) or BACKTEST_CONCURRENCY)
        sem = asyncio.Semaphore(candidate_concurrency)
        preload_codes = self._collect_preload_codes(candidates)
        if preload_codes:
            await self.preload_klines(db, preload_codes)
        shared_key_by_candidate: dict[int, str] = {}
        shared_groups: dict[str, list[dict]] = {}
        shared_group_order: list[str] = []
        for candidate in candidates:
            shared_key = self._build_shared_result_key(candidate)
            shared_key_by_candidate[id(candidate)] = shared_key
            if shared_key not in shared_groups:
                shared_groups[shared_key] = []
                shared_group_order.append(shared_key)
            shared_groups[shared_key].append(candidate)
        unique_candidates = [shared_groups[key][0] for key in shared_group_order]

        async def _test_guarded(candidate: dict) -> tuple:
            queued_at = time.perf_counter()
            async with sem:
                started_at = time.perf_counter()
                result = await self._test_one(candidate, db, BacktestEngine)
                result["queue_wait_ms"] = round((started_at - queued_at) * 1000, 2)
                return candidate, result

        results = await asyncio.gather(
            *[_test_guarded(c) for c in unique_candidates],
            return_exceptions=True,
        )
        shared_results: dict[str, dict] = {}
        for candidate, item in zip(unique_candidates, results):
            shared_key = shared_key_by_candidate[id(candidate)]
            reuse_count = max(len(shared_groups.get(shared_key) or []) - 1, 0)
            if isinstance(item, BaseException):
                logger.warning(
                    "BacktestFilter candidate failed unexpectedly strategy_type=%s error=%s",
                    candidate.get("strategy_type"),
                    item,
                    exc_info=item,
                )
                result = self._build_candidate_exception_result(candidate, item)
            else:
                _, result = item
            shared_results[shared_key] = self._annotate_shared_result(
                candidate,
                result,
                key=shared_key,
                reused=False,
                reuse_count=reuse_count,
            )
        for candidate in candidates:
            shared_key = shared_key_by_candidate[id(candidate)]
            leader = (shared_groups.get(shared_key) or [candidate])[0]
            result = shared_results.get(shared_key)
            if result is None:
                result = self._annotate_shared_result(
                    candidate,
                    self._build_candidate_exception_result(candidate, RuntimeError("missing_shared_result")),
                    key=shared_key,
                    reused=False,
                    reuse_count=0,
                )
            elif candidate is not leader:
                result = self._annotate_shared_result(
                    candidate,
                    result,
                    key=shared_key,
                    reused=True,
                    reuse_count=max(len(shared_groups.get(shared_key) or []) - 1, 0),
                )
            self._apply_result_to_candidate(candidate, result, passed, failed)
        self.last_report = self._build_last_report(candidates, passed, failed)
        return passed

    @staticmethod
    def _build_median_summary(results: List[dict]) -> dict:
        if not results:
            return {}
        avg_holding_days = [
            float(metric["avg_holding_days"])
            for metric in results
            if metric.get("avg_holding_days") is not None
        ]
        turnover_values = [
            float(metric["turnover_proxy"])
            for metric in results
            if metric.get("turnover_proxy") is not None
        ]
        curve_points = [
            int(metric.get("curve_points") or len(metric.get("equity_curve") or []))
            for metric in results
            if int(metric.get("curve_points") or len(metric.get("equity_curve") or [])) > 0
        ]
        return {
            "sharpe_ratio": float(median([metric["sharpe_ratio"] for metric in results])),
            "total_return": float(median([metric["total_return"] for metric in results])),
            "max_drawdown": float(median([metric["max_drawdown"] for metric in results])),
            "win_rate": float(median([metric.get("win_rate", 0) for metric in results])),
            "trades_count": float(median([metric["trades_count"] for metric in results])),
            "avg_holding_days": float(median(avg_holding_days)) if avg_holding_days else 0.0,
            "turnover_proxy": float(median(turnover_values)) if turnover_values else 0.0,
            "curve_points": int(max(curve_points)) if curve_points else 0,
        }

    @staticmethod
    def _filter_target_weight_map_for_codes(
        target_weight_map: Optional[dict[str, Any]],
        codes: List[str],
    ) -> dict[str, float]:
        if not isinstance(target_weight_map, dict):
            return {}
        filtered: dict[str, float] = {}
        for code in list(codes or []):
            token = str(code or "").strip()
            if not token or token not in target_weight_map:
                continue
            try:
                value = float(target_weight_map.get(token, 0.0) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                filtered[token] = value
        return filtered

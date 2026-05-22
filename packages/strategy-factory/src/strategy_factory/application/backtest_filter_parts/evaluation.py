
    @classmethod
    def _extract_event_samples(
        cls,
        *,
        candidate: Optional[dict[str, Any]],
        research_task: Optional[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        payload = dict(candidate or {})
        task = dict(research_task or {})
        sources: list[tuple[str, Any]] = [
            ("research_task.event_samples", task.get("event_samples")),
            ("research_task.event_sample_set", task.get("event_sample_set")),
            ("research_task.event_study.samples", dict(task.get("event_study") or {}).get("samples")),
            ("candidate.event_samples", payload.get("event_samples")),
            ("candidate.event_context.event_samples", dict(payload.get("event_context") or {}).get("event_samples")),
            ("candidate.event_context.samples", dict(payload.get("event_context") or {}).get("samples")),
        ]
        for source_name, value in sources:
            if isinstance(value, dict):
                value = value.get("samples")
            if not isinstance(value, list) or not value:
                continue
            normalized: list[dict[str, Any]] = []
            for idx, item in enumerate(value, 1):
                if not isinstance(item, dict):
                    continue
                sample = dict(item)
                event_id = str(sample.get("event_id") or task.get("event_id") or "").strip()
                if event_id:
                    sample["event_id"] = event_id
                event_time = str(
                    sample.get("event_time")
                    or sample.get("anchor_time")
                    or sample.get("anchor_date")
                    or ""
                ).strip()
                if event_time:
                    sample["event_time"] = event_time
                if not sample.get("sample_id"):
                    sample["sample_id"] = str(sample.get("event_id") or f"event_sample_{idx}")
                normalized.append(sample)
            if normalized:
                return normalized, source_name
        return [], None

    @classmethod
    def _build_minimal_event_samples(
        cls,
        *,
        candidate: Optional[dict[str, Any]],
        research_task: Optional[dict[str, Any]],
        target_results: Optional[List[dict]],
        representative_results: Optional[List[dict]],
        fallback_results: Optional[List[dict]],
    ) -> tuple[list[dict[str, Any]], Optional[str]]:
        payload = dict(candidate or {})
        task = dict(research_task or {})
        task_event_context = dict(task.get("event_context") or {})
        payload_event_context = dict(payload.get("event_context") or {})
        event_context = task_event_context or payload_event_context
        event_id = str(
            task.get("event_id")
            or payload.get("event_id")
            or event_context.get("event_id")
            or ""
        ).strip()
        target_codes = _extract_target_codes_from_payload(payload, limit=12)
        if not target_codes:
            target_codes = cls._event_sample_list(
                task.get("target_symbols")
                or event_context.get("target_symbols")
                or payload.get("target_symbols"),
                limit=12,
            )
        target_set = set(target_codes)
        source_results = list(target_results or [])
        if not source_results and fallback_results:
            source_results = [
                dict(item or {})
                for item in list(fallback_results or [])
                if not target_set or str((item or {}).get("code") or "").strip() in target_set
            ]
        if not source_results:
            return [], None

        event_window = dict(task.get("event_window") or {})
        estimation_window = dict(task.get("estimation_window") or {})
        representative_codes = cls._event_sample_list(
            event_context.get("control_group")
            or event_context.get("benchmark_symbols")
            or event_context.get("control_symbols")
            or [item.get("code") for item in list(representative_results or [])],
            limit=8,
        )
        representative_returns = [
            cls._event_sample_float(dict(item or {}), "total_return")
            for item in list(representative_results or [])
        ]
        representative_returns = [float(value) for value in representative_returns if value is not None]
        benchmark_return = cls._event_sample_float(
            event_context,
            "benchmark_return",
            "control_return",
            "baseline_return",
        )
        if benchmark_return is None and representative_returns:
            benchmark_return = float(sum(representative_returns) / len(representative_returns))
        if benchmark_return is None:
            benchmark_return = 0.0
        benchmark_source = "event_context_control_group" if representative_codes else "event_context_minimal_baseline"
        base_anchor = str(
            event_context.get("event_time")
            or event_context.get("event_date")
            or event_context.get("snapshot_date")
            or task.get("event_time")
            or task.get("event_date")
            or task.get("snapshot_date")
            or payload.get("snapshot_date")
            or event_id
            or ""
        ).strip()

        normalized: list[dict[str, Any]] = []
        for idx, item in enumerate(source_results, 1):
            sample_payload = dict(item or {})
            code = str(sample_payload.get("code") or "").strip()
            if target_set and code and code not in target_set:
                continue
            target_return = cls._event_sample_float(sample_payload, "total_return")
            if target_return is None:
                continue
            sample_event_id = event_id or f"auto_event_{code or idx}"
            sample_anchor = base_anchor or f"{sample_event_id}:{code or idx}"
            abnormal_return = float(target_return - benchmark_return)
            normalized.append(
                {
                    "sample_id": f"{sample_event_id}:{code or idx}",
                    "event_id": sample_event_id,
                    "event_time": sample_anchor,
                    "target_return": float(target_return),
                    "benchmark_return": float(benchmark_return),
                    "abnormal_return": abnormal_return,
                    "car": abnormal_return,
                    "bhar": abnormal_return,
                    "hit": abnormal_return > 0,
                    "benchmark_source": benchmark_source,
                    "control_group": representative_codes,
                    "pre_days": max(0, int(event_window.get("pre_days") or 0)),
                    "post_days": max(1, int(event_window.get("post_days") or 1)),
                    "estimation_days": max(0, int(estimation_window.get("lookback_days") or 0)),
                    "minimal_context_sample": True,
                }
            )
        return normalized, ("auto_context_minimal" if normalized else None)

    @classmethod
    def _build_event_sample_metrics(
        cls,
        *,
        candidate: Optional[dict[str, Any]],
        research_task: Optional[dict[str, Any]],
        target_results: Optional[List[dict]] = None,
        representative_results: Optional[List[dict]] = None,
        fallback_results: Optional[List[dict]] = None,
    ) -> Optional[dict[str, Any]]:
        event_samples, sample_source = cls._extract_event_samples(candidate=candidate, research_task=research_task)
        event_study_mode = "sample_driven"
        validation_focus = str(dict(research_task or {}).get("validation_focus") or "").strip().lower()
        if not event_samples and validation_focus == "event_target_only":
            event_samples, sample_source = cls._build_minimal_event_samples(
                candidate=candidate,
                research_task=research_task,
                target_results=target_results,
                representative_results=representative_results,
                fallback_results=fallback_results,
            )
            if event_samples:
                event_study_mode = "sample_driven_minimal"
        if not event_samples:
            return None

        event_audit_incomplete = event_study_mode != "sample_driven"
        sample_metrics: list[dict[str, Any]] = []
        benchmark_sources: dict[str, int] = {}
        event_time_anchors: list[str] = []
        event_sample_ids: list[str] = []
        unique_control_codes: set[str] = set()

        for sample in event_samples:
            abnormal_post = cls._coerce_return_series(
                sample.get("abnormal_returns") or sample.get("abnormal_post_returns")
            )
            post_target = cls._coerce_return_series(
                sample.get("post_returns") or sample.get("target_post_returns")
            )
            post_benchmark = cls._coerce_return_series(
                sample.get("benchmark_post_returns") or sample.get("control_post_returns")
            )
            estimation_returns = cls._coerce_return_series(
                sample.get("estimation_returns") or sample.get("benchmark_estimation_returns")
            )

            target_total_return = cls._event_sample_float(sample, "target_return")
            if target_total_return is None and post_target is not None:
                target_total_return = float(np.prod(1.0 + post_target) - 1.0)

            benchmark_total_return = cls._event_sample_float(sample, "benchmark_return", "control_return")
            if benchmark_total_return is None and post_benchmark is not None:
                benchmark_total_return = float(np.prod(1.0 + post_benchmark) - 1.0)

            abnormal_return = cls._event_sample_float(sample, "abnormal_return")
            if abnormal_return is None and target_total_return is not None and benchmark_total_return is not None:
                abnormal_return = float(target_total_return - benchmark_total_return)

            car = cls._event_sample_float(sample, "car")
            if car is None and abnormal_post is not None:
                car = float(np.sum(abnormal_post))

            bhar = cls._event_sample_float(sample, "bhar")
            if bhar is None and post_target is not None and post_benchmark is not None:
                denominator = max(float(np.prod(1.0 + post_benchmark)), 1e-9)
                bhar = float(np.prod(1.0 + post_target) / denominator - 1.0)
            elif bhar is None and abnormal_return is not None:
                bhar = float(abnormal_return)

            pre_event_abnormal_return = cls._event_sample_float(sample, "pre_event_abnormal_return")
            if pre_event_abnormal_return is None:
                pre_abnormal = cls._coerce_return_series(
                    sample.get("pre_abnormal_returns") or sample.get("abnormal_pre_returns")
                )
                if pre_abnormal is not None:
                    pre_event_abnormal_return = float(np.sum(pre_abnormal))

            hit_ratio = cls._event_sample_float(sample, "hit_ratio")
            if hit_ratio is None:
                hit_flag = sample.get("hit")
                if hit_flag is not None:
                    hit_ratio = 1.0 if bool(hit_flag) else 0.0
                elif abnormal_return is not None:
                    hit_ratio = 1.0 if abnormal_return > 0 else 0.0

            post_event_decay = cls._event_sample_float(sample, "post_event_decay", "decay")
            if post_event_decay is None and abnormal_post is not None and abnormal_post.size > 0:
                split = max(1, int(abnormal_post.size // 2))
                early_car = float(np.sum(abnormal_post[:split]))
                late_car = float(np.sum(abnormal_post[split:])) if abnormal_post.size > split else 0.0
                decay_denominator = max(abs(early_car), 0.01)
                post_event_decay = float(late_car / decay_denominator - 1.0)

            if all(metric is None for metric in (abnormal_return, car, bhar, hit_ratio)):
                continue

            control_codes = cls._event_sample_list(
                sample.get("control_group")
                or sample.get("benchmark_symbols")
                or sample.get("control_symbols")
            )
            unique_control_codes.update(control_codes)
            benchmark_source = str(
                sample.get("benchmark_source")
                or ("sample_control_group" if control_codes else "sample_baseline")
            ).strip().lower() or "sample_baseline"
            benchmark_sources[benchmark_source] = benchmark_sources.get(benchmark_source, 0) + 1

            pre_abnormal = cls._coerce_return_series(sample.get("pre_abnormal_returns") or sample.get("abnormal_pre_returns"))
            post_observation = post_target if post_target is not None else abnormal_post

            sample_id = str(sample.get("sample_id") or sample.get("event_id") or "").strip()
            if sample_id and sample_id not in event_sample_ids:
                event_sample_ids.append(sample_id)
            anchor = str(sample.get("event_time") or sample.get("event_id") or "").strip()
            if anchor and anchor not in event_time_anchors:
                event_time_anchors.append(anchor)

            sample_metrics.append(
                {
                    "target_total_return": float(target_total_return or 0.0),
                    "benchmark_total_return": float(benchmark_total_return or 0.0),
                    "abnormal_return": float(abnormal_return or 0.0),
                    "car": float(car if car is not None else abnormal_return or 0.0),
                    "bhar": float(bhar if bhar is not None else abnormal_return or 0.0),
                    "hit_ratio": float(hit_ratio if hit_ratio is not None else 0.0),
                    "pre_event_abnormal_return": float(pre_event_abnormal_return or 0.0),
                    "post_event_decay": float(post_event_decay or 0.0),
                    "pre_days_used": int(sample.get("pre_days") or (int(pre_abnormal.size) if pre_abnormal is not None else 0)),
                    "post_days_used": int(sample.get("post_days") or (int(post_observation.size) if post_observation is not None else 0)),
                    "estimation_days_used": int(sample.get("estimation_days") or (int(estimation_returns.size) if estimation_returns is not None else 0)),
                }
            )

        if not sample_metrics:
            return None

        def _mean_value(key: str) -> float:
            values = [float(item.get(key) or 0.0) for item in sample_metrics]
            return float(sum(values) / len(values)) if values else 0.0

        benchmark_source = max(benchmark_sources.items(), key=lambda item: item[1])[0] if benchmark_sources else "sample_baseline"
        return {
            "total_return": round(_mean_value("target_total_return"), 4),
            "benchmark_return": round(_mean_value("benchmark_total_return"), 4),
            "abnormal_return": round(_mean_value("abnormal_return"), 4),
            "car": round(_mean_value("car"), 4),
            "bhar": round(_mean_value("bhar"), 4),
            "hit_ratio": round(_mean_value("hit_ratio"), 4),
            "pre_event_abnormal_return": round(_mean_value("pre_event_abnormal_return"), 4),
            "post_event_decay": round(_mean_value("post_event_decay"), 4),
            "pre_days_used": int(round(_mean_value("pre_days_used"))),
            "post_days_used": int(round(_mean_value("post_days_used"))),
            "estimation_days_used": int(round(_mean_value("estimation_days_used"))),
            "benchmark_source": benchmark_source,
            "aggregation_mode": "event_sample_average",
            "component_count": len(_extract_target_codes_from_payload(candidate or {}, limit=12)),
            "curve_points": 0,
            "event_study_mode": event_study_mode,
            "event_sample_source": sample_source,
            "event_sample_count": len(sample_metrics),
            "event_anchor_count": len(event_time_anchors),
            "event_time_anchors": event_time_anchors[:8],
            "event_sample_ids": event_sample_ids[:8],
            "control_group_count": len(unique_control_codes),
            "traceable_to_event_samples": not event_audit_incomplete,
            "event_audit_incomplete": event_audit_incomplete,
        }

    @classmethod
    def _build_event_window_metrics(
        cls,
        *,
        candidate: Optional[dict[str, Any]],
        target_results: List[dict],
        representative_results: List[dict],
        fallback_results: List[dict],
        research_task: dict[str, Any],
        target_weight_scheme: str,
        initial_capital: float,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        sample_metrics = cls._build_event_sample_metrics(
            candidate=candidate,
            research_task=research_task,
            target_results=target_results,
            representative_results=representative_results,
            fallback_results=fallback_results,
        )
        if sample_metrics is not None:
            return sample_metrics
        return {}

    @staticmethod
    def _build_backtest_assumptions(candidate: dict) -> FactoryBacktestAssumptions:
        return build_factory_backtest_assumptions(candidate)

    @staticmethod
    def _trade_density_observation_days(
        *,
        metrics: dict[str, Any],
        target_metrics: dict[str, Any],
        combined_metrics: dict[str, Any],
        event_window_metrics: dict[str, Any],
        lookback_days: float,
        post_days: float,
        trade_count: float,
        avg_holding_days: float,
    ) -> float:
        candidates: list[float] = [max(1.0, lookback_days + post_days)]
        for payload in (metrics, target_metrics, combined_metrics):
            curve_points = float(payload.get("portfolio_curve_points") or payload.get("curve_points") or 0.0)
            if curve_points > 0:
                candidates.append(curve_points)
        event_sample_days = float(event_window_metrics.get("estimation_days_used") or 0.0) + float(
            event_window_metrics.get("post_days_used") or 0.0
        )
        if event_sample_days > 0:
            candidates.append(event_sample_days)
        if trade_count > 0 and avg_holding_days > 0:
            candidates.append(float(lookback_days) + float(trade_count) * float(avg_holding_days))
        return max(1.0, *candidates)

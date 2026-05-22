
    async def _run_portfolio_engine_summary(
        self,
        *,
        candidate: dict,
        engine,
        codes: List[str],
        assumptions: FactoryBacktestAssumptions,
    ) -> Optional[dict[str, Any]]:
        if not _has_explicit_research_task(candidate):
            return None
        portfolio_runner = getattr(engine, "run_portfolio_backtest", None)
        if not callable(portfolio_runner):
            return None
        normalized_codes = [str(code or "").strip() for code in list(codes or []) if str(code or "").strip()]
        if len(normalized_codes) <= 1:
            return None

        market_data: dict[str, list] = {}
        for code in normalized_codes:
            klines = list(self._kline_cache.get(code) or [])
            if klines:
                market_data[code] = klines
        if len(market_data) <= 1:
            return None

        portfolio_params = {
            **dict(candidate.get("params") or {}),
            **assumptions.to_backtest_kwargs(),
        }
        filtered_weight_map = self._filter_target_weight_map_for_codes(
            assumptions.target_weight_map,
            list(market_data.keys()),
        )
        if filtered_weight_map:
            portfolio_params["target_weight_map"] = filtered_weight_map
        elif portfolio_params.get("target_weight_scheme") == "target_weight_map":
            portfolio_params["target_weight_scheme"] = "equal_weight"

        try:
            factory_pkg = _get_strategy_factory_package()
            to_thread = getattr(getattr(factory_pkg, "asyncio", None), "to_thread", asyncio.to_thread)
            result = await to_thread(
                portfolio_runner,
                market_data,
                candidate["strategy_type"],
                portfolio_params,
                True,
            )
        except Exception:
            logger.warning(
                "BacktestFilter portfolio engine failed strategy_type=%s codes=%s",
                candidate.get("strategy_type"),
                list(market_data.keys()),
                exc_info=True,
            )
            return None
        if not isinstance(result, dict) or not result.get("success"):
            return None
        payload = dict(result.get("data") or {})
        payload = self._merge_trade_profile_metrics(payload)
        payload["portfolio_engine_used"] = True
        payload.setdefault("component_count", len(market_data))
        payload.setdefault("component_codes", list(market_data.keys()))
        return payload

    @staticmethod
    def _coerce_equity_curve(metric: dict) -> Optional[np.ndarray]:
        raw_curve = metric.get("equity_curve")
        if not isinstance(raw_curve, (list, tuple)):
            return None
        try:
            curve = np.asarray(raw_curve, dtype=float)
        except (TypeError, ValueError):
            return None
        if curve.ndim != 1 or curve.size < 2:
            return None
        if not np.all(np.isfinite(curve)) or float(curve[0]) <= 0 or np.any(curve <= 0):
            return None
        return curve

    @staticmethod
    def _resample_curve(curve: np.ndarray, target_len: int) -> np.ndarray:
        if curve.size == target_len:
            return curve.astype(float, copy=True)
        if target_len <= 1:
            return np.asarray([float(curve[-1])], dtype=float)
        source_x = np.linspace(0.0, 1.0, curve.size)
        target_x = np.linspace(0.0, 1.0, target_len)
        return np.interp(target_x, source_x, curve).astype(float, copy=False)

    @staticmethod
    def _weighted_average(values: List[float], weights: Optional[List[float]] = None) -> float:
        if not values:
            return 0.0
        if not weights or len(weights) != len(values) or sum(weights) <= 0:
            return float(sum(values) / len(values))
        total_weight = float(sum(weights))
        return float(sum(value * weight for value, weight in zip(values, weights)) / total_weight)

    @staticmethod
    def _normalize_weight_scheme(target_weight_scheme: str) -> str:
        normalized = str(target_weight_scheme or "single_name").strip().lower()
        if normalized in {"equal", "equal_weight_proxy"}:
            return "equal_weight"
        if not normalized:
            return "single_name"
        return normalized

    @staticmethod
    def _normalize_target_weight_map(
        codes: List[str],
        target_weight_map: Optional[dict[str, Any]],
    ) -> dict[str, float]:
        normalized_codes = [str(code or "").strip() for code in list(codes or []) if str(code or "").strip()]
        if not normalized_codes:
            return {}
        raw_map = dict(target_weight_map or {})
        weights: dict[str, float] = {}
        for code in normalized_codes:
            try:
                value = float(raw_map.get(code, 0.0) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                weights[code] = value
        total = float(sum(weights.values()))
        if total <= 0:
            equal_weight = 1.0 / float(len(normalized_codes))
            return {code: equal_weight for code in normalized_codes}
        return {
            code: float(value) / total
            for code, value in weights.items()
        }

    @classmethod
    def _resolve_portfolio_allocation(
        cls,
        results: List[dict],
        *,
        target_weight_scheme: str,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, float], str]:
        normalized_scheme = cls._normalize_weight_scheme(target_weight_scheme)
        codes = [
            str(metric.get("code") or "").strip()
            for metric in results
            if str(metric.get("code") or "").strip()
        ]
        if not codes:
            return {}, normalized_scheme
        if normalized_scheme == "single_name":
            return {codes[0]: 1.0}, normalized_scheme
        normalized_map = cls._normalize_target_weight_map(codes, target_weight_map)
        if not normalized_map:
            return {}, normalized_scheme
        return normalized_map, normalized_scheme

    @classmethod
    def _build_portfolio_curve_payload(
        cls,
        results: List[dict],
        *,
        target_weight_scheme: str,
        initial_capital: float,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        if len(results) <= 1:
            return None

        allocation_weights, normalized_scheme = cls._resolve_portfolio_allocation(
            results,
            target_weight_scheme=target_weight_scheme,
            target_weight_map=target_weight_map,
        )
        if len(allocation_weights) <= 1:
            return None

        entries: List[tuple[str, np.ndarray, dict]] = []
        for metric in results:
            code = str(metric.get("code") or "").strip()
            if not code or code not in allocation_weights:
                continue
            curve = cls._coerce_equity_curve(metric)
            if curve is None:
                continue
            entries.append((code, curve / float(curve[0]), metric))
        if len(entries) <= 1:
            return None

        target_len = max(curve.size for _, curve, _ in entries)
        aggregated_curve = np.zeros(target_len, dtype=float)
        used_metrics: List[dict] = []
        used_weights: List[float] = []
        allocation_snapshot: dict[str, float] = {}
        for code, curve, metric in entries:
            weight = float(allocation_weights.get(code, 0.0) or 0.0)
            if weight <= 0:
                continue
            aggregated_curve += cls._resample_curve(curve, target_len) * weight
            allocation_snapshot[code] = round(weight, 6)
            used_metrics.append(metric)
            used_weights.append(weight)
        if len(used_metrics) <= 1:
            return None

        capital_base = max(float(initial_capital or 0.0), 1.0)
        aggregated_curve = aggregated_curve * capital_base
        allocation_mode = (
            "target_weight_map"
            if target_weight_map and normalized_scheme != "equal_weight"
            else "equal_weight"
        )
        aggregation_mode = (
            "portfolio_equal_weight"
            if allocation_mode == "equal_weight"
            else "portfolio_weighted"
        )
        return {
            "curve": aggregated_curve.astype(float, copy=False),
            "aggregation_mode": aggregation_mode,
            "allocation_mode": allocation_mode,
            "allocation_weights": allocation_snapshot,
            "component_count": len(used_metrics),
            "curve_points": int(target_len),
            "metrics": used_metrics,
            "weights": used_weights,
            "requested_weight_scheme": normalized_scheme,
        }

    @staticmethod
    def _metrics_from_equity_curve(curve: np.ndarray) -> dict:
        if curve.size < 2 or float(curve[0]) <= 0:
            return {
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
            }
        total_return = float(curve[-1] / curve[0] - 1.0)
        peaks = np.maximum.accumulate(curve)
        drawdowns = np.where(peaks > 0, (peaks - curve) / peaks, 0.0)
        max_drawdown = float(np.max(drawdowns)) if drawdowns.size else 0.0
        sharpe_ratio = 0.0
        prev = curve[:-1]
        curr = curve[1:]
        valid = prev > 0
        if np.any(valid):
            returns = (curr[valid] - prev[valid]) / prev[valid]
            returns = returns[np.isfinite(returns)]
            if returns.size > 1:
                std = float(np.std(returns))
                if std > 0:
                    annual_return = float(np.mean(returns)) * 252.0
                    annual_std = std * np.sqrt(252.0)
                    sharpe_ratio = float((annual_return - 0.02) / annual_std)
        return {
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
        }

    @classmethod
    def _summarize_portfolio_result_set(
        cls,
        results: List[dict],
        *,
        target_weight_scheme: str,
        initial_capital: float,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> Optional[dict]:
        payload = cls._build_portfolio_curve_payload(
            results,
            target_weight_scheme=target_weight_scheme,
            initial_capital=initial_capital,
            target_weight_map=target_weight_map,
        )
        if payload is None:
            return None

        curve_metrics = list(payload.get("metrics") or [])
        portfolio_curve = np.asarray(payload["curve"], dtype=float)
        portfolio_metrics = cls._metrics_from_equity_curve(portfolio_curve)
        component_trade_counts = [max(float(metric.get("trades_count") or 0.0), 0.0) for metric in curve_metrics]
        trade_weights = component_trade_counts if sum(component_trade_counts) > 0 else None
        avg_holding_days = [
            float(metric.get("avg_holding_days") or 0.0)
            for metric in curve_metrics
        ]
        win_rates = [
            float(metric.get("win_rate") or 0.0)
            for metric in curve_metrics
        ]
        turnover_values = [
            float(metric.get("turnover_proxy") or 0.0)
            for metric in curve_metrics
        ]

        return {
            "sharpe_ratio": float(portfolio_metrics["sharpe_ratio"]),
            "total_return": float(portfolio_metrics["total_return"]),
            "max_drawdown": float(portfolio_metrics["max_drawdown"]),
            "win_rate": cls._weighted_average(win_rates, trade_weights),
            "trades_count": float(sum(component_trade_counts)),
            "avg_holding_days": cls._weighted_average(avg_holding_days, trade_weights or list(payload.get("weights") or [])),
            "turnover_proxy": cls._weighted_average(turnover_values, list(payload.get("weights") or [])),
            "aggregation_mode": str(payload.get("aggregation_mode") or "portfolio_equal_weight"),
            "allocation_mode": str(payload.get("allocation_mode") or "equal_weight"),
            "allocation_weights": dict(payload.get("allocation_weights") or {}),
            "requested_weight_scheme": str(payload.get("requested_weight_scheme") or target_weight_scheme or "equal_weight"),
            "component_count": int(payload.get("component_count") or len(curve_metrics)),
            "portfolio_curve_points": int(payload.get("curve_points") or portfolio_curve.size),
            **cls._aggregate_trade_profile_metrics(
                curve_metrics,
                initial_capital=initial_capital,
            ),
        }

    @classmethod
    def _summarize_result_set(
        cls,
        results: List[dict],
        *,
        target_weight_scheme: str = "single_name",
        initial_capital: float = 100000.0,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> dict:
        if not results:
            return {}
        normalized_scheme = cls._normalize_weight_scheme(target_weight_scheme)
        if normalized_scheme != "single_name":
            portfolio_summary = cls._summarize_portfolio_result_set(
                results,
                target_weight_scheme=normalized_scheme,
                initial_capital=initial_capital,
                target_weight_map=target_weight_map,
            )
            if portfolio_summary:
                return portfolio_summary
            return {
                **cls._build_median_summary(results),
                "aggregation_mode": "median_proxy",
                "requested_weight_scheme": normalized_scheme,
                "component_count": len(results),
            }
        return cls._build_median_summary(results)

    @classmethod
    def _aggregate_result_curve(
        cls,
        results: List[dict],
        *,
        target_weight_scheme: str = "single_name",
        initial_capital: float = 100000.0,
        target_weight_map: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        if not results:
            return None
        normalized_scheme = cls._normalize_weight_scheme(target_weight_scheme)
        if normalized_scheme != "single_name":
            payload = cls._build_portfolio_curve_payload(
                results,
                target_weight_scheme=normalized_scheme,
                initial_capital=initial_capital,
                target_weight_map=target_weight_map,
            )
            if payload is not None:
                return {
                    "curve": np.asarray(payload["curve"], dtype=float),
                    "aggregation_mode": str(payload.get("aggregation_mode") or "portfolio_equal_weight"),
                    "allocation_mode": str(payload.get("allocation_mode") or "equal_weight"),
                    "allocation_weights": dict(payload.get("allocation_weights") or {}),
                    "component_count": int(payload.get("component_count") or 0),
                    "curve_points": int(payload.get("curve_points") or 0),
                }

        curves: List[np.ndarray] = []
        for metric in results:
            curve = cls._coerce_equity_curve(metric)
            if curve is None:
                continue
            curves.append(curve / float(curve[0]))
        if not curves:
            return None

        if len(curves) == 1:
            curve = curves[0] * max(float(initial_capital or 0.0), 1.0)
            return {
                "curve": curve,
                "aggregation_mode": "single_name_curve",
                "component_count": 1,
                "curve_points": int(curve.size),
            }

        target_len = max(curve.size for curve in curves)
        aligned_curves = np.vstack([cls._resample_curve(curve, target_len) for curve in curves])
        if normalized_scheme != "single_name":
            aggregated = np.mean(aligned_curves, axis=0) * max(float(initial_capital or 0.0), 1.0)
            mode = "portfolio_equal_weight"
        else:
            aggregated = np.median(aligned_curves, axis=0) * max(float(initial_capital or 0.0), 1.0)
            mode = "curve_median_proxy"
        return {
            "curve": aggregated.astype(float, copy=False),
            "aggregation_mode": mode,
            "component_count": len(curves),
            "curve_points": int(target_len),
        }

    @staticmethod
    def _daily_returns_from_curve(curve: np.ndarray) -> np.ndarray:
        if curve.size < 2:
            return np.array([], dtype=float)
        prev = curve[:-1]
        curr = curve[1:]
        valid = prev > 0
        if not np.any(valid):
            return np.array([], dtype=float)
        returns = (curr[valid] - prev[valid]) / prev[valid]
        returns = returns[np.isfinite(returns)]
        return returns.astype(float, copy=False)

    @classmethod
    def _coerce_return_series(cls, value: Any) -> Optional[np.ndarray]:
        if not isinstance(value, (list, tuple, np.ndarray)):
            return None
        try:
            arr = np.asarray(value, dtype=float)
        except (TypeError, ValueError):
            return None
        arr = arr[np.isfinite(arr)]
        if arr.size <= 0:
            return None
        return arr.astype(float, copy=False)

    @staticmethod
    def _event_sample_float(sample: dict[str, Any], *keys: str) -> Optional[float]:
        for key in keys:
            if key not in sample or sample.get(key) is None:
                continue
            try:
                return float(sample.get(key) or 0.0)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _event_sample_list(value: Any, *, limit: int = 8) -> list[str]:
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, (list, tuple, set)):
            values = list(value)
        else:
            values = []
        ordered: list[str] = []
        seen: set[str] = set()
        for item in values:
            token = str(item or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            ordered.append(token)
        return ordered[: max(1, int(limit or 8))]

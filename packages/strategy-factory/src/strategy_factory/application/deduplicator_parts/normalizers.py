    """去除与已有策略参数过于相似的候选。"""

    THRESHOLD = 0.85
    VECTOR_TRIGGER_THRESHOLD = 0.65
    VECTOR_THRESHOLD = 0.93
    MAX_VECTOR_CANDIDATES = 8
    MAX_REFRESH_PER_LINEAGE = 2
    MAX_REVISION_PER_LINEAGE = 3
    DEFAULT_BEHAVIOR_BUILD_TIMEOUT_SEC = 8.0
    DEFAULT_PREWARM_TIMEOUT_SEC = 15.0

    def __init__(self, *, vector_gateway: Optional["VectorSearchGateway"] = None):
        self.last_report: dict = {
            "summary": {
                "input_count": 0,
                "kept_count": 0,
                "dropped_count": 0,
                "vector_checks": 0,
                "existing_scan_count": 0,
                "coarse_candidate_count": 0,
                "coarse_filtered_count": 0,
                "coarse_hit_ratio": 0.0,
                "coarse_tag_hit_count": 0,
                "coarse_target_hit_count": 0,
                "vector_candidate_count": 0,
                "vector_candidate_trimmed_count": 0,
                "pgvector_available": False,
                "fallback_dedup_mode": "structural_hash",
                "structural_hash_checks": 0,
                "structural_hash_duplicates": 0,
                "intra_batch_duplicate_count": 0,
                "persisted_hash_duplicate_count": 0,
            },
            "kept": [],
            "dropped": [],
        }
        self._behavior_cache: Dict[str, Optional[List[dict]]] = {}
        self._vector_gateway = vector_gateway
        self._vector_engine = getattr(vector_gateway, "raw", vector_gateway) if vector_gateway is not None else None

    def _get_vector_gateway(self) -> "VectorSearchGateway":
        if self._vector_gateway is None:
            from ..infrastructure.mcp_adapters import MCPVectorSearchGatewayImpl

            self._vector_gateway = MCPVectorSearchGatewayImpl()
            self._vector_engine = getattr(self._vector_gateway, "raw", self._vector_gateway)
        return self._vector_gateway

    @staticmethod
    def _normalize_strategy_type(value: object) -> str:
        return str(value or "").strip().lower()

    @classmethod
    def _bucket_existing_by_type(cls, rows: List[dict]) -> Dict[str, List[dict]]:
        buckets: Dict[str, List[dict]] = {}
        for item in list(rows or []):
            strategy_type = cls._normalize_strategy_type((item or {}).get("strategy_type"))
            if not strategy_type:
                continue
            buckets.setdefault(strategy_type, []).append(item)
        return buckets

    @staticmethod
    def _tag_overlap(left_payload: Optional[dict], right_payload: Optional[dict]) -> float:
        left = {
            str(item).strip().lower()
            for item in list((left_payload or {}).get("tags") or [])
            if str(item).strip()
        }
        right = {
            str(item).strip().lower()
            for item in list((right_payload or {}).get("tags") or [])
            if str(item).strip()
        }
        if not left or not right:
            return 0.0
        union = left | right
        if not union:
            return 0.0
        return round(len(left & right) / len(union), 4)

    @staticmethod
    def _has_explicit_universe(payload: Optional[dict]) -> bool:
        return bool(_extract_target_codes_from_payload(payload or {}, limit=20))

    @classmethod
    def _has_exact_target_universe_match(
        cls,
        left_payload: Optional[dict],
        right_payload: Optional[dict],
    ) -> bool:
        left_codes = {
            str(code).strip()
            for code in _extract_target_codes_from_payload(left_payload or {}, limit=20)
            if str(code).strip()
        }
        right_codes = {
            str(code).strip()
            for code in _extract_target_codes_from_payload(right_payload or {}, limit=20)
            if str(code).strip()
        }
        return bool(left_codes and right_codes and left_codes == right_codes)

    @classmethod
    def _has_material_target_divergence(
        cls,
        candidate: Optional[dict],
        existing_item: Optional[dict],
        target_overlap: Optional[float],
    ) -> bool:
        if target_overlap is None or target_overlap >= 0.8:
            return False
        if not cls._has_explicit_universe(candidate) or not cls._has_explicit_universe(existing_item):
            return False
        return True

    def _select_vector_candidates(self, suspicious: List[dict]) -> List[Tuple[dict, float]]:
        ranked = sorted(
            list(suspicious or []),
            key=lambda item: (
                float(item.get("effective_similarity") or 0.0),
                float(item.get("target_overlap") or 0.0) if item.get("target_overlap") is not None else -1.0,
                float(item.get("tag_overlap") or 0.0),
            ),
            reverse=True,
        )
        selected: List[Tuple[dict, float]] = []
        for item in ranked[: self.MAX_VECTOR_CANDIDATES]:
            existing_item = dict(item.get("existing_item") or {})
            if not existing_item:
                continue
            selected.append((existing_item, float(item.get("effective_similarity") or 0.0)))
        return selected

    @staticmethod
    def _extract_parent_strategy_ids(candidate: Optional[dict]) -> set[str]:
        item = dict(candidate or {})
        metadata = dict(item.get("metadata") or {})
        generation_reason = dict(item.get("generation_reason") or {})
        research_task = dict(item.get("research_task") or {})
        lineage = dict(item.get("lineage") or {})
        parent_ids: set[str] = set()
        for source in (item, metadata, generation_reason, research_task, lineage):
            for key in ("parent_strategy_id", "parent_candidate_id"):
                value = str(source.get(key) or "").strip()
                if value:
                    parent_ids.add(value)
            for key in ("parent_strategy_ids", "parent_candidate_ids"):
                values = source.get(key)
                if isinstance(values, (list, tuple, set)):
                    parent_ids.update(str(value or "").strip() for value in values if str(value or "").strip())
        return parent_ids

    @staticmethod
    def _candidate_strategy_profile(candidate: Optional[dict]) -> dict:
        item = dict(candidate or {})
        if not item:
            return {}
        params = dict(item.get("params") or {})
        profile = dict(item.get("strategy_profile") or params.get("strategy_profile") or {})
        if not profile:
            profile = dict(infer_candidate_strategy_profile(item) or {})
        return {
            str(key): value
            for key, value in profile.items()
            if value not in (None, [], {}, "")
        }

    @classmethod
    def _report_item(cls, candidate: Optional[dict]) -> dict:
        item = dict(candidate or {})
        profile = cls._candidate_strategy_profile(item)
        return {
            "strategy_type": item.get("strategy_type"),
            "generator_type": item.get("generator_type"),
            "params": item.get("params"),
            "target_symbols": item.get("target_symbols") or [],
            "stock_pool": item.get("stock_pool") or {},
            "tags": item.get("tags") or [],
            "spawn_reason": item.get("spawn_reason"),
            "dedup_result": item.get("dedup_result"),
            "strategy_profile": profile,
            "candidate_family_id": profile.get("candidate_family_id"),
            "holding_period_bucket": profile.get("holding_period_bucket"),
            "alpha_source": profile.get("alpha_source"),
            "risk_level": profile.get("risk_level"),
            "regime_fit": profile.get("regime_fit"),
            "generator_mode": profile.get("generator_mode"),
        }

    @staticmethod
    def _candidate_refresh_rank(candidate: Optional[dict]) -> tuple[float, float, float]:
        item = dict(candidate or {})
        metrics = dict(item.get('backtest_metrics') or (item.get('backtest_result') or {}).get('metrics') or {})
        sharpe = float(metrics.get('sharpe_ratio') or 0.0)
        total_return = float(metrics.get('total_return') or 0.0)
        max_drawdown = float(metrics.get('max_drawdown') or 1.0)
        return (round(sharpe, 6), round(total_return, 6), round(-max_drawdown, 6))

    @staticmethod
    def _extract_quality_snapshot(item: Optional[dict]) -> dict[str, Any]:
        payload = dict(item or {})
        params = dict(payload.get("params") or {})
        quality_summary = dict(
            payload.get("quality_summary")
            or payload.get("quality_gate_summary")
            or dict(payload.get("quality_gate") or {}).get("summary")
            or {}
        )
        evidence = dict(
            payload.get("candidate_evidence_status")
            or params.get("candidate_evidence_status")
            or quality_summary.get("candidate_evidence_status")
            or {}
        )
        promotion_review = dict(
            payload.get("promotion_review")
            or payload.get("review_report")
            or quality_summary.get("promotion_review")
            or {}
        )
        backtest_metrics = dict(
            payload.get("backtest_metrics")
            or (payload.get("backtest_result") or {}).get("metrics")
            or quality_summary.get("backtest_metrics")
            or {}
        )
        observed_forward_days = list(
            evidence.get("observed_forward_days")
            or evidence.get("forward_days")
            or []
        )
        missing_forward_days = list(evidence.get("missing_forward_days") or [])
        raw_validation_grade = str(
            payload.get("raw_validation_grade")
            or quality_summary.get("raw_validation_grade")
            or evidence.get("raw_validation_grade")
            or payload.get("validation_grade")
            or quality_summary.get("validation_grade")
            or evidence.get("validation_grade")
            or ""
        ).strip().upper()
        effective_validation_grade = str(
            payload.get("validation_grade")
            or payload.get("effective_validation_grade")
            or quality_summary.get("validation_grade")
            or quality_summary.get("effective_validation_grade")
            or evidence.get("validation_grade")
            or ""
        ).strip().upper()
        promotion_ready = bool(
            evidence.get("promotion_ready")
            or quality_summary.get("promotion_ready")
        )
        total_signals = int(
            evidence.get("total_signals")
            or evidence.get("signal_total_signals")
            or quality_summary.get("signal_total_signals")
            or 0
        )
        minimum_signal_count = int(evidence.get("minimum_signal_count") or 10)
        forward_coverage_ratio = float(
            evidence.get("forward_window_coverage_ratio")
            or quality_summary.get("forward_window_coverage_ratio")
            or (
                len(observed_forward_days) / max(len(observed_forward_days) + len(missing_forward_days), 1)
                if observed_forward_days or missing_forward_days
                else 0.0
            )
            or 0.0
        )
        return {
            "validation_grade": effective_validation_grade or raw_validation_grade or None,
            "raw_validation_grade": raw_validation_grade or None,
            "effective_validation_grade": effective_validation_grade or raw_validation_grade or None,
            "promotion_ready": promotion_ready,
            "total_signals": total_signals,
            "minimum_signal_count": minimum_signal_count,
            "forward_coverage_ratio": round(max(min(forward_coverage_ratio, 1.0), 0.0), 4),
            "promotion_review_score": float(
                promotion_review.get("score")
                or quality_summary.get("promotion_review_score")
                or 0.0
            ),
            "promotion_review_status": str(
                promotion_review.get("status")
                or quality_summary.get("promotion_review_status")
                or ""
            ).strip().lower(),
            "promotion_review_recommendation": str(
                promotion_review.get("recommendation")
                or quality_summary.get("promotion_review_recommendation")
                or ""
            ).strip().lower(),
            "sharpe_ratio": float(backtest_metrics.get("sharpe_ratio") or 0.0),
            "total_return": float(backtest_metrics.get("total_return") or 0.0),
            "max_drawdown": float(backtest_metrics.get("max_drawdown") or 0.0),
        }

    @classmethod
    def _quality_snapshot_score(cls, item: Optional[dict]) -> tuple[float, bool]:
        snapshot = cls._extract_quality_snapshot(item)
        comparable = any(
            [
                snapshot.get("raw_validation_grade"),
                snapshot.get("validation_grade"),
                snapshot.get("promotion_ready"),
                snapshot.get("total_signals"),
                snapshot.get("forward_coverage_ratio"),
                snapshot.get("promotion_review_score"),
                snapshot.get("sharpe_ratio"),
            ]
        )
        if not comparable:
            return 0.0, False
        grade_score = {
            "A": 1.0,
            "B": 0.85,
            "C": 0.7,
            "D": 0.45,
        }.get(
            str(snapshot.get("raw_validation_grade") or snapshot.get("validation_grade") or "").upper(),
            0.25,
        )
        signal_ratio = min(
            float(snapshot.get("total_signals") or 0.0)
            / max(float(snapshot.get("minimum_signal_count") or 10.0), 1.0),
            1.0,
        )
        review_score = max(min(float(snapshot.get("promotion_review_score") or 0.0), 1.0), 0.0)
        sharpe_score = max(min((float(snapshot.get("sharpe_ratio") or 0.0) + 1.0) / 4.0, 1.0), 0.0)
        total_return_score = max(min(float(snapshot.get("total_return") or 0.0), 1.0), -1.0)
        drawdown_penalty = max(min(float(snapshot.get("max_drawdown") or 0.0), 1.0), 0.0)
        score = (
            grade_score * 0.26
            + signal_ratio * 0.18
            + float(snapshot.get("forward_coverage_ratio") or 0.0) * 0.22
            + (0.16 if bool(snapshot.get("promotion_ready")) else 0.0)
            + review_score * 0.1
            + sharpe_score * 0.06
            + max(total_return_score, 0.0) * 0.04
            - drawdown_penalty * 0.04
        )
        return round(score, 6), True

    @staticmethod
    def _lineage_counter(item: Optional[dict], *keys: str) -> int:
        payload = dict(item or {})
        params = dict(payload.get("params") or {})
        lineage = dict(
            payload.get("candidate_lineage_contract")
            or payload.get("lineage")
            or params.get("candidate_lineage_contract")
            or params.get("lineage")
            or {}
        )
        for source in (payload, params, lineage):
            for key in keys:
                try:
                    value = int(source.get(key) or 0)
                except Exception:
                    value = 0
                if value > 0:
                    return value
        return 0

    @classmethod
    def _suggest_holding_bucket_shift(cls, bucket: str | None) -> str | None:
        mapping = {
            "short": "medium",
            "medium": "long",
            "long": "medium",
        }
        token = str(bucket or "").strip().lower()
        return mapping.get(token) or ("medium" if token else None)

    @classmethod
    def _suggest_generator_mode_shift(cls, generator_mode: str | None) -> str | None:
        token = str(generator_mode or "").strip().lower()
        if not token:
            return "external_llm"
        return "external_llm" if token != "external_llm" else "rule"

    @classmethod
    def _lineage_quality_pressure(
        cls,
        candidate: Optional[dict],
        existing_item: Optional[dict],
        *,
        refresh_lineage_depth: int,
        revision_lineage_depth: int,
        exact_target_universe_match: bool,
    ) -> dict[str, Any]:
        candidate_snapshot = cls._extract_quality_snapshot(candidate)
        existing_snapshot = cls._extract_quality_snapshot(existing_item)
        raw_grade = str(
            existing_snapshot.get("raw_validation_grade")
            or candidate_snapshot.get("raw_validation_grade")
            or ""
        ).strip().upper()
        explicit_streak = max(
            cls._lineage_counter(
                candidate,
                "consecutive_raw_validation_d_count",
                "raw_validation_d_streak",
                "consecutive_low_quality_count",
                "low_quality_lineage_count",
            ),
            cls._lineage_counter(
                existing_item,
                "consecutive_raw_validation_d_count",
                "raw_validation_d_streak",
                "consecutive_low_quality_count",
                "low_quality_lineage_count",
            ),
        )
        low_quality_active = raw_grade == "D"
        streak = explicit_streak
        if low_quality_active and streak <= 0:
            streak = max(refresh_lineage_depth, revision_lineage_depth)
        candidate_profile = cls._candidate_strategy_profile(candidate)
        existing_profile = cls._candidate_strategy_profile(existing_item)
        candidate_holding_bucket = str(candidate_profile.get("holding_period_bucket") or "").strip().lower()
        existing_holding_bucket = str(existing_profile.get("holding_period_bucket") or "").strip().lower()
        candidate_generator_mode = str(candidate_profile.get("generator_mode") or "").strip().lower()
        existing_generator_mode = str(existing_profile.get("generator_mode") or "").strip().lower()
        holding_bucket_shift_applied = bool(
            candidate_holding_bucket
            and existing_holding_bucket
            and candidate_holding_bucket != existing_holding_bucket
        )
        generator_mode_shift_applied = bool(
            candidate_generator_mode
            and existing_generator_mode
            and candidate_generator_mode != existing_generator_mode
        )
        universe_shift_applied = not exact_target_universe_match
        structural_shift_applied = bool(
            holding_bucket_shift_applied
            or generator_mode_shift_applied
            or universe_shift_applied
        )
        required_shift = bool(low_quality_active and streak >= 2)
        retire_lineage = bool(low_quality_active and streak >= cls.MAX_REVISION_PER_LINEAGE)
        return {
            "low_quality_lineage_active": low_quality_active,
            "low_quality_lineage_streak": streak if low_quality_active else 0,
            "lineage_structural_shift_required": required_shift,
            "lineage_structural_shift_applied": structural_shift_applied,
            "holding_bucket_shift_applied": holding_bucket_shift_applied,
            "generator_mode_shift_applied": generator_mode_shift_applied,
            "universe_shift_applied": universe_shift_applied,
            "recommended_holding_bucket_shift": (
                cls._suggest_holding_bucket_shift(existing_holding_bucket or candidate_holding_bucket)
                if required_shift and not holding_bucket_shift_applied
                else None
            ),
            "recommended_generator_mode_shift": (
                cls._suggest_generator_mode_shift(existing_generator_mode or candidate_generator_mode)
                if required_shift and not generator_mode_shift_applied
                else None
            ),
            "recommended_universe_shift": bool(required_shift and not universe_shift_applied),
            "lineage_retire_recommended": retire_lineage,
            "lineage_quality_basis_grade": raw_grade or None,
        }

    @classmethod
    def _refresh_improvement_snapshot(
        cls,
        candidate: Optional[dict],
        existing_item: Optional[dict],
    ) -> dict[str, Any]:
        candidate_score, candidate_comparable = cls._quality_snapshot_score(candidate)
        existing_score, existing_comparable = cls._quality_snapshot_score(existing_item)
        if not candidate_comparable and not existing_comparable:
            return {
                "required": False,
                "passed": True,
                "candidate_score": candidate_score,
                "existing_score": existing_score,
            }
        improvement_margin = round(candidate_score - existing_score, 6)
        candidate_snapshot = cls._extract_quality_snapshot(candidate)
        existing_snapshot = cls._extract_quality_snapshot(existing_item)
        passed = bool(
            improvement_margin >= 0.05
            or (
                bool(candidate_snapshot.get("promotion_ready"))
                and not bool(existing_snapshot.get("promotion_ready"))
            )
            or (
                float(candidate_snapshot.get("forward_coverage_ratio") or 0.0)
                - float(existing_snapshot.get("forward_coverage_ratio") or 0.0)
                >= 0.2
            )
            or (
                float(candidate_snapshot.get("promotion_review_score") or 0.0)
                - float(existing_snapshot.get("promotion_review_score") or 0.0)
                >= 0.08
            )
        )
        return {
            "required": True,
            "passed": passed,
            "candidate_score": candidate_score,
            "existing_score": existing_score,
            "candidate_snapshot": candidate_snapshot,
            "existing_snapshot": existing_snapshot,
        }

    @staticmethod
    def _lineage_operation_depth(item: Optional[dict], *, mode: str) -> int:
        payload = dict(item or {})
        params = dict(payload.get("params") or {})
        lineage = dict(
            payload.get("candidate_lineage_contract")
            or payload.get("lineage")
            or params.get("candidate_lineage_contract")
            or params.get("lineage")
            or {}
        )
        keys = (
            f"{mode}_count",
            f"{mode}_depth",
            f"lineage_{mode}_count",
            f"lineage_{mode}_depth",
            f"consecutive_{mode}_count",
        )
        for source in (payload, params, lineage):
            for key in keys:
                try:
                    value = int(source.get(key) or 0)
                except Exception:
                    value = 0
                if value > 0:
                    return value
        return 0

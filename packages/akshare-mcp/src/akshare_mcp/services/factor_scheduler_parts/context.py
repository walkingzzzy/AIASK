    """Asyncio-based daily factor computation scheduler."""

    STALE_AFTER_SEC = 24 * 60 * 60
    RUN_HISTORY_LIMIT = 12

    def __init__(
        self,
        run_time: time = time(18, 0),  # 18:00 CST
        universe: Optional[List[str]] = None,
        factors: Optional[List[str]] = None,
        batch_size: int = 50,
    ):
        self.run_time = run_time
        self.universe = universe or DEFAULT_UNIVERSE
        self.factors = factors or DEFAULT_FACTORS
        self.batch_size = batch_size
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_run: Optional[datetime] = None
        self.last_result: Optional[dict] = None
        self._run_history: list[dict] = []

    async def _load_dynamic_universe(self, db) -> List[str]:
        """PR-F1: 从 stocks 表动态加载全 A 股代码，过滤北交所/B 股/老三板。

        - 排除：920xxx / 8xxxxx（北交所），200xxx / 900xxx（B 股）。
        - 阈值降到 100：只要 DB 里有 >=100 只可交易股票，就替换 DEFAULT_UNIVERSE。
        """
        try:
            acquire = getattr(db, "acquire", None)
            if not callable(acquire):
                return []
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT stock_code FROM stocks "
                    "WHERE stock_code NOT LIKE '920%' "
                    "AND stock_code NOT LIKE '8%' "
                    "AND stock_code NOT LIKE '200%' "
                    "AND stock_code NOT LIKE '900%' "
                    "ORDER BY stock_code"
                )
            raw_codes = [str(r["stock_code"]).strip() for r in (rows or []) if r.get("stock_code")]
            # Python 层兜底过滤：防止 SQL LIKE 与方言差异导致漏过滤
            codes = [
                c for c in raw_codes
                if c and len(c) >= 6
                and not (c.startswith("920") or c.startswith("8")
                         or c.startswith("200") or c.startswith("900"))
            ]
            if len(codes) >= 100:
                logger.info("_load_dynamic_universe: found %d tradable stocks", len(codes))
                return codes
        except Exception as exc:
            logger.debug("_load_dynamic_universe failed: %s", exc)
        return []

    @staticmethod
    def _isoformat(value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.astimezone()
        return value.isoformat()

    @classmethod
    def _freshness_sec(cls, value: Optional[datetime], *, now: Optional[datetime] = None) -> float:
        if value is None:
            return 0.0
        observed = value.astimezone() if value.tzinfo is not None else value.astimezone()
        current = now or datetime.now().astimezone()
        return round(max((current - observed).total_seconds(), 0.0), 3)

    @classmethod
    def _quality_flags(cls, *, errors: int, computed: int, freshness_sec: float) -> list[str]:
        flags: list[str] = []
        if errors > 0 and computed > 0:
            flags.append("partial")
        elif errors > 0:
            flags.extend(["degraded", "failed"])
        if freshness_sec > cls.STALE_AFTER_SEC:
            flags.append("stale")
        seen: set[str] = set()
        result: list[str] = []
        for flag in flags:
            if flag in seen:
                continue
            seen.add(flag)
            result.append(flag)
        return result

    @staticmethod
    def _quality_status(flags: list[str]) -> str:
        normalized = [str(flag or "").strip().lower() for flag in list(flags or []) if str(flag or "").strip()]
        if "failed" in normalized:
            return "failed"
        if "partial" in normalized or "degraded" in normalized:
            return "degraded"
        if "stale" in normalized:
            return "stale"
        return "fresh"

    @staticmethod
    def _normalize_stage_status(value: object) -> str:
        token = str(value or "").strip().lower()
        if token in {"completed", "complete", "success", "succeeded", "done"}:
            return "completed"
        if token in {"partial", "degraded", "warning"}:
            return "partial"
        if token in {"skipped", "disabled", "not_needed", "noop"}:
            return "skipped"
        if token in {"failed", "error"}:
            return "failed"
        return "completed"

    @classmethod
    def _build_stage_result(
        cls,
        stage: str,
        *,
        status: str,
        payload: Optional[dict] = None,
        retry_boundary: Optional[str] = None,
    ) -> dict:
        normalized_status = cls._normalize_stage_status(status)
        data = dict(payload or {})
        warnings = list(data.get("warnings") or [])
        failures = list(data.get("failures") or data.get("failed_batches") or [])
        result = {
            "stage": stage,
            "status": normalized_status,
            "ok": normalized_status != "failed",
            "degraded": normalized_status == "partial",
            "warning_count": int(data.get("warning_count") or len(warnings)),
            "failure_count": int(data.get("failure_count") or len(failures)),
            "attempt_count": int(data.get("attempt_count") or 1),
            **data,
        }
        if retry_boundary:
            result["retry_boundary"] = retry_boundary
            result["retryable"] = normalized_status in {"failed", "partial"}
        return result

    @classmethod
    def _summarize_stage_results(cls, stages: dict[str, dict]) -> dict:
        counts = {"completed": 0, "partial": 0, "skipped": 0, "failed": 0}
        failed_stages: list[str] = []
        partial_stages: list[str] = []
        skipped_stages: list[str] = []
        for stage_name, payload in dict(stages or {}).items():
            status = cls._normalize_stage_status((payload or {}).get("status"))
            counts[status] = int(counts.get(status, 0)) + 1
            if status == "failed":
                failed_stages.append(stage_name)
            elif status == "partial":
                partial_stages.append(stage_name)
            elif status == "skipped":
                skipped_stages.append(stage_name)
        return {
            "stage_status_counts": counts,
            "failed_stage_count": len(failed_stages),
            "partial_stage_count": len(partial_stages),
            "skipped_stage_count": len(skipped_stages),
            "failed_stages": failed_stages,
            "partial_stages": partial_stages,
            "skipped_stages": skipped_stages,
        }

    @classmethod
    def _resolve_run_status(cls, stages: dict[str, dict]) -> str:
        summary = cls._summarize_stage_results(stages)
        if summary["failed_stage_count"] > 0:
            return "failed" if summary["partial_stage_count"] == 0 and summary["stage_status_counts"].get("completed", 0) == 0 else "partial"
        if summary["partial_stage_count"] > 0:
            return "partial"
        if summary["skipped_stage_count"] == len(stages) and stages:
            return "skipped"
        return "success"

    @classmethod
    def _build_run_summary(cls, result: dict) -> dict:
        stages = dict(result.get("stages") or {})
        lineage = dict(result.get("lineage") or {})
        llm_validation = dict(result.get("llm_validation") or {})
        llm_provider = dict(result.get("llm_provider") or {})
        llm_mining = dict(result.get("llm_mining") or {})
        llm_payload = dict(llm_mining.get("data") or {})
        quality_flags = list(result.get("quality_flags") or [])
        return {
            "run_id": result.get("run_id"),
            "status": result.get("status"),
            "started_at": result.get("started_at"),
            "completed_at": result.get("completed_at"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "computed": int(result.get("computed") or 0),
            "errors": int(result.get("errors") or 0),
            "universe_size": int(result.get("universe_size") or 0),
            "quality_status": cls._quality_status(quality_flags),
            "quality_flags": quality_flags,
            "stages": {
                name: {
                    "status": str((payload or {}).get("status") or ""),
                    "failure_count": int((payload or {}).get("failure_count") or 0),
                    "warning_count": int((payload or {}).get("warning_count") or 0),
                }
                for name, payload in stages.items()
            },
            "stage_summary": cls._summarize_stage_results(stages),
            "llm_generation_artifact_id": lineage.get("llm_generation_artifact_id"),
            "validation_artifact_ids": list(llm_validation.get("validation_artifact_ids") or []),
            "generated_candidate_count": int(llm_validation.get("generated_candidate_count") or 0),
            "validated_candidate_count": int(llm_validation.get("validated_candidate_count") or 0),
            "active_pool_count_after_run": int(llm_validation.get("active_pool_count_after_run") or 0),
            "governed_active_count_after_run": int(llm_validation.get("governed_active_count_after_run") or 0),
            "llm_generation_mode": llm_payload.get("generation_mode"),
            "llm_fallback_used": bool(llm_payload.get("fallback_used")),
            "llm_fallback_reason": llm_payload.get("fallback_reason"),
            "llm_allow_local_rule_fallback": llm_payload.get("allow_local_rule_fallback"),
            "llm_provider_gate_status": llm_payload.get("provider_gate_status"),
            "llm_provider_gate_reason": llm_payload.get("provider_gate_reason"),
            "llm_provider_health_status": llm_provider.get("health_status"),
            "llm_provider_ready": bool(llm_provider.get("ready")),
            "llm_provider_enabled": bool(llm_provider.get("enabled")),
            "llm_provider_rebuild_count": int(llm_provider.get("rebuild_count") or 0),
            "llm_provider_last_error_type": llm_provider.get("last_error_type"),
        }

    def _record_run_history(self, result: dict) -> None:
        summary = self._build_run_summary(result)
        self._run_history = [summary, *list(self._run_history or [])][: self.RUN_HISTORY_LIMIT]

    @staticmethod
    def _provider_runtime():
        from .factor_llm_provider import get_factor_llm_provider

        return get_factor_llm_provider()

    def _provider_status(self) -> dict[str, Any]:
        try:
            provider = self._provider_runtime()
        except Exception as exc:
            return {
                "enabled": False,
                "configured": False,
                "ready": False,
                "health_status": "error",
                "rebuild_recommended": False,
                "last_error_type": exc.__class__.__name__,
                "last_error": str(exc),
                "request_count": 0,
                "success_count": 0,
                "consecutive_failures": 0,
                "rebuild_count": 0,
            }
        status = getattr(provider, "status", None)
        if callable(status):
            try:
                payload = dict(status() or {})
                payload.setdefault("enabled", bool(getattr(provider, "is_enabled", lambda: False)()))
                payload.setdefault("ready", bool(payload.get("enabled")) and not bool(payload.get("client_closed")))
                return payload
            except Exception as exc:
                return {
                    "enabled": False,
                    "configured": False,
                    "ready": False,
                    "health_status": "error",
                    "rebuild_recommended": False,
                    "last_error_type": exc.__class__.__name__,
                    "last_error": str(exc),
                    "request_count": 0,
                    "success_count": 0,
                    "consecutive_failures": 0,
                    "rebuild_count": 0,
                }
        enabled = bool(getattr(provider, "is_enabled", lambda: False)())
        return {
            "enabled": enabled,
            "configured": enabled,
            "ready": enabled,
            "health_status": "ready" if enabled else "disabled",
            "rebuild_recommended": False,
            "request_count": 0,
            "success_count": 0,
            "consecutive_failures": 0,
            "rebuild_count": 0,
        }

    async def _prepare_llm_provider(self, *, llm_enabled: bool, scheduler_llm: bool) -> dict[str, Any]:
        if not (llm_enabled and scheduler_llm):
            return {
                "status": "skipped",
                "action": None,
                "error": None,
                "smoke_check": {},
                "before": {},
                "after": {},
            }
        before = self._provider_status()
        action = None
        error = None
        smoke_check: dict[str, Any] = {}
        after = dict(before)
        if bool(before.get("rebuild_recommended")):
            try:
                provider = self._provider_runtime()
                rebuild_client = getattr(provider, "rebuild_client", None)
                if callable(rebuild_client):
                    result = rebuild_client(reason="factor_scheduler_preflight")
                    if asyncio.iscoroutine(result):
                        await result
                    action = "rebuild_client"
                    after = self._provider_status()
            except Exception as exc:
                error = str(exc)
                action = "rebuild_failed"
                after = self._provider_status()
        if error is None:
            try:
                provider = self._provider_runtime()
                smoke_check_fn = getattr(provider, "smoke_check", None)
                if callable(smoke_check_fn) and bool(after.get("ready")):
                    result = smoke_check_fn()
                    if asyncio.iscoroutine(result):
                        result = await result
                    smoke_check = dict(result or {})
                    smoke_status = str(smoke_check.get("status") or "").strip().lower()
                    if smoke_status and smoke_status not in {"disabled", "cached_success", "passed"}:
                        error = str(smoke_check.get("last_error") or smoke_check.get("error") or "factor llm smoke check failed")
                    action = "smoke_check" if action is None else f"{action}+smoke_check"
                    after = self._provider_status()
            except Exception as exc:
                error = str(exc)
                smoke_check = {"status": "failed", "error": str(exc)}
                action = "smoke_check_failed" if action is None else f"{action}+smoke_check_failed"
                after = self._provider_status()
        return {
            "status": "completed" if error is None else "failed",
            "action": action,
            "error": error,
            "smoke_check": smoke_check,
            "before": before,
            "after": after,
        }

    @classmethod
    def _scheduler_local_fallback_enabled(cls) -> bool:
        # Scheduler is the governed path. Keep local-rule fallback opt-in so
        # provider health issues do not silently become the main supply source.
        return cls._env_enabled("FACTOR_SCHEDULER_ALLOW_LOCAL_RULE_FALLBACK", default=False)

    @classmethod
    def _resolve_provider_gate(
        cls,
        *,
        llm_enabled: bool,
        scheduler_llm: bool,
        provider_status: Optional[dict[str, Any]] = None,
        provider_preflight: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        allow_local_rule_fallback = cls._scheduler_local_fallback_enabled()
        if not (llm_enabled and scheduler_llm):
            return {
                "status": "skipped",
                "reason": None,
                "allow_local_rule_fallback": allow_local_rule_fallback,
            }

        status = dict(provider_status or {})
        preflight = dict(provider_preflight or {})
        before = dict(preflight.get("before") or {})
        if bool(status.get("ready")):
            return {
                "status": "ready",
                "reason": None,
                "allow_local_rule_fallback": allow_local_rule_fallback,
            }
        if allow_local_rule_fallback:
            return {
                "status": "fallback_override",
                "reason": "scheduler_local_rule_fallback_override",
                "allow_local_rule_fallback": True,
            }
        if bool(before.get("ready")):
            return {
                "status": "degraded",
                "reason": "provider_degraded_after_preflight",
                "allow_local_rule_fallback": allow_local_rule_fallback,
            }
        return {
            "status": "blocked",
            "reason": "provider_not_ready_after_preflight",
            "allow_local_rule_fallback": False,
        }

    @classmethod
    def _build_quality_meta(
        cls,
        *,
        asof_dt: Optional[datetime],
        computed: int,
        errors: int,
        now: Optional[datetime] = None,
    ) -> dict:
        freshness_sec = cls._freshness_sec(asof_dt, now=now)
        return {
            "asof_time": cls._isoformat(asof_dt),
            "source": "factor_scheduler",
            "freshness_sec": freshness_sec,
            "quality_flags": cls._quality_flags(errors=errors, computed=computed, freshness_sec=freshness_sec),
        }

    @staticmethod
    def _env_enabled(name: str, default: bool = False) -> bool:
        raw = str(os.getenv(name, "1" if default else "0") or "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _safe_int(value: object, default: int = 0) -> int:
        try:
            return int(value if value is not None else default)
        except Exception:
            return int(default)

    @staticmethod
    def _normalize_codes(values: object) -> list[str]:
        if values is None:
            return []
        if isinstance(values, list):
            return [str(item).strip() for item in values if str(item).strip()]
        text = str(values or "").strip()
        if not text:
            return []
        return [item.strip() for item in text.split(",") if item.strip()]

    @classmethod
    def _select_validation_code_sample(cls, codes: list[str], *, limit: int) -> list[str]:
        normalized = list(dict.fromkeys(cls._normalize_codes(codes)))
        if len(normalized) <= limit:
            return normalized
        if limit <= 1:
            return normalized[:1]

        max_index = len(normalized) - 1
        selected_indices: list[int] = []
        used_indices: set[int] = set()
        for position in range(limit):
            target_index = int(round(position * max_index / max(limit - 1, 1)))
            if target_index not in used_indices:
                used_indices.add(target_index)
                selected_indices.append(target_index)
                continue
            for offset in range(1, len(normalized)):
                right = target_index + offset
                if right <= max_index and right not in used_indices:
                    used_indices.add(right)
                    selected_indices.append(right)
                    break
                left = target_index - offset
                if left >= 0 and left not in used_indices:
                    used_indices.add(left)
                    selected_indices.append(left)
                    break

        selected_indices.sort()
        return [normalized[index] for index in selected_indices[:limit]]

    def _resolve_validation_codes(self, llm_payload: dict) -> list[str]:
        codes = self._normalize_codes(llm_payload.get("codes")) or list(self.universe)
        if len(codes) < 4:
            return codes
        limit = max(
            4,
            min(
                self._safe_int(os.getenv("FACTOR_SCHEDULER_VALIDATION_MAX_CODES"), 24),
                len(codes),
            ),
        )
        return self._select_validation_code_sample(codes, limit=limit)

    async def _refresh_registry_summary(self, quant_manager, *, codes: list[str]) -> dict:
        kwargs = {
            "codes": codes,
            "limit": 200,
            "market_codes_only": True,
        }
        summary_resp = await quant_manager(
            action="factor_candidate_registry",
            kwargs=json.dumps({"op": "summary", **kwargs}, ensure_ascii=False),
        )
        active_pool_resp = await quant_manager(
            action="factor_candidate_registry",
            kwargs=json.dumps({"op": "active_pool", **kwargs}, ensure_ascii=False),
        )
        summary_data = summary_resp.get("data") if isinstance(summary_resp, dict) else {}
        active_pool_data = active_pool_resp.get("data") if isinstance(active_pool_resp, dict) else {}
        active_pool = active_pool_data.get("active_pool") if isinstance(active_pool_data, dict) else {}
        summary = summary_data.get("summary") if isinstance(summary_data, dict) else {}
        return {
            "registry_refresh_status": (
                "success"
                if isinstance(summary_resp, dict)
                and summary_resp.get("success")
                and isinstance(active_pool_resp, dict)
                and active_pool_resp.get("success")
                else "failed"
            ),
            "registry_summary": summary if isinstance(summary, dict) else {},
            "active_pool_count_after_run": int((active_pool or {}).get("count") or 0),
            "active_pool_mode_after_run": (active_pool or {}).get("active_pool_mode"),
            "active_pool_strict_count_after_run": int((active_pool or {}).get("strict_count") or 0),
            "active_pool_provisional_count_after_run": int((active_pool or {}).get("provisional_count") or 0),
            "governed_active_count_after_run": int((summary or {}).get("governed_active_count") or 0),
            "blocked_active_count_after_run": int((summary or {}).get("blocked_active_count") or 0),
        }

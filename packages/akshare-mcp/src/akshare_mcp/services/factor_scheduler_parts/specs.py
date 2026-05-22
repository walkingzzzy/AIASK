
    async def _run_llm_validation_cycle(self, quant_manager, llm_mining_result: dict | None) -> dict:
        meta = {
            "status": "skipped",
            "validation_attempted": False,
            "generated_candidate_count": 0,
            "validated_candidate_count": 0,
            "validation_failed_count": 0,
            "validation_codes": [],
            "validation_artifact_ids": [],
            "failed_candidates": [],
            "registry_refresh_status": "not_needed",
            "registry_summary": {},
            "active_pool_count_after_run": 0,
            "governed_active_count_after_run": 0,
            "blocked_active_count_after_run": 0,
        }
        if not isinstance(llm_mining_result, dict) or not llm_mining_result.get("success"):
            return meta

        llm_payload = llm_mining_result.get("data") if isinstance(llm_mining_result.get("data"), dict) else {}
        candidates = [dict(item or {}) for item in list(llm_payload.get("candidates") or []) if isinstance(item, dict)]
        meta["generated_candidate_count"] = len(candidates)
        if not candidates:
            meta["status"] = "skipped"
            return meta

        validation_codes = self._resolve_validation_codes(llm_payload)
        meta["validation_codes"] = validation_codes
        if len(validation_codes) < 4:
            meta["status"] = "skipped"
            meta["failed_candidates"] = [{"reason": "insufficient_validation_codes"}]
            return meta

        meta["validation_attempted"] = True
        for idx, candidate in enumerate(candidates):
            output_artifact_id = (
                f"factor_validation_scheduler_{int(datetime.now().timestamp())}_{idx}_{candidate.get('name') or 'candidate'}"
            )
            try:
                validation_resp = await quant_manager(
                    action="validate_factor_candidate",
                    kwargs=json.dumps(
                        {
                            "candidate": candidate,
                            "codes": validation_codes,
                            "persist_artifact": True,
                            "write_memory": True,
                            "output_artifact_id": output_artifact_id,
                        },
                        ensure_ascii=False,
                    ),
                )
            except Exception as exc:
                validation_resp = {"success": False, "error": str(exc)}

            if isinstance(validation_resp, dict) and validation_resp.get("success"):
                meta["validated_candidate_count"] += 1
                data = validation_resp.get("data") if isinstance(validation_resp.get("data"), dict) else {}
                artifact_id = str(data.get("artifact_id") or output_artifact_id).strip()
                if artifact_id:
                    meta["validation_artifact_ids"].append(artifact_id)
            else:
                meta["validation_failed_count"] += 1
                error = None
                if isinstance(validation_resp, dict):
                    error = validation_resp.get("error") or validation_resp.get("message")
                meta["failed_candidates"].append(
                    {
                        "candidate_index": idx,
                        "name": candidate.get("name"),
                        "error": str(error or "candidate validation failed"),
                    }
                )

        if meta["validated_candidate_count"] > 0:
            try:
                meta.update(await self._refresh_registry_summary(quant_manager, codes=validation_codes))
            except Exception as exc:
                meta["registry_refresh_status"] = "failed"
                meta["failed_candidates"].append({"reason": f"registry_refresh_failed:{exc}"})

        if meta["validated_candidate_count"] == 0 and meta["generated_candidate_count"] > 0:
            meta["status"] = "failed"
        elif meta["validation_failed_count"] > 0:
            meta["status"] = "partial"
        else:
            meta["status"] = "success"
        return meta

    def start(self):
        """Start the scheduler in the background (non-blocking)."""
        if self._running:
            logger.warning("FactorScheduler already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="factor-scheduler")
        logger.info("FactorScheduler started, daily run at %s", self.run_time)

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("FactorScheduler stopped")

    async def shutdown(self, grace_sec: float = 3.0):
        """Stop the scheduler and drain the background task before loop exit."""
        self._running = False
        task = self._task
        self._task = None
        if task is None:
            logger.info("FactorScheduler stopped")
            return
        if not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=max(0.0, grace_sec))
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        else:
            with suppress(asyncio.CancelledError):
                await task
        logger.info("FactorScheduler stopped")

    async def _loop(self):
        """Main scheduler loop — sleeps until next run_time, then executes."""
        while self._running:
            try:
                now = datetime.now()
                target = datetime.combine(now.date(), self.run_time)
                if target <= now:
                    target += timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                logger.info("FactorScheduler: next run in %.0f seconds at %s", wait_seconds, target)
                await asyncio.sleep(wait_seconds)

                if self._running:
                    await self.run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._consecutive_errors = getattr(self, '_consecutive_errors', 0) + 1
                backoff = min(60 * (2 ** (self._consecutive_errors - 1)), 3600)
                logger.error("FactorScheduler loop error (#%d, backoff %.0fs): %s", self._consecutive_errors, backoff, e, exc_info=True)
                await asyncio.sleep(backoff)

    async def run_once(self):
        """Execute a single batch factor computation run."""
        from ..storage import get_db

        load_mcp_env(
            override=False,
            only_prefixes=("FACTOR_LLM_", "FACTOR_SCHEDULER_", "STRATEGY_LLM_"),
        )

        # PR-F1: 动态加载全 A 股宇宙（替代 160 只硬编码）
        # 只要动态 universe >= 100 只可交易股票就替换，避免被 DEFAULT_UNIVERSE 长度卡住。
        db = get_db()
        dynamic_universe = [] if bool(getattr(self, "_skip_dynamic_universe", False)) else await self._load_dynamic_universe(db)
        if dynamic_universe and len(dynamic_universe) >= 100:
            previous = len(self.universe)
            self.universe = dynamic_universe
            logger.info(
                "FactorScheduler: dynamic universe loaded, %d stocks (was %d, DEFAULT=%d)",
                len(self.universe), previous, len(DEFAULT_UNIVERSE),
            )

        logger.info("FactorScheduler: starting batch compute for %d stocks", len(self.universe))
        start = datetime.now().astimezone()
        run_id = f"factor_scheduler_run_{int(start.timestamp())}_{uuid4().hex[:8]}"
        total_computed = 0
        total_errors = 0
        llm_validation_result = None
        llm_mining_result = None
        batch_failures: list[dict] = []
        processed_batches = 0
        total_batches = max((len(self.universe) + max(self.batch_size, 1) - 1) // max(self.batch_size, 1), 0)

        # Process in batches
        for i in range(0, len(self.universe), self.batch_size):
            batch = self.universe[i:i + self.batch_size]
            processed_batches += 1
            try:
                # Import and call the quant_manager batch action directly
                from ..tools.managers.quant_manager import quant_manager
                result = await quant_manager(
                    action="batch_compute_factors",
                    kwargs=json.dumps({
                        "codes": batch,
                        "factors": self.factors,
                        "persist": True,
                        "compute_ic": True,
                        # PR-F1: 显式传 max_codes 上限 = batch 长度，避免被默认 1000 截断
                        "max_codes": max(self.batch_size, len(batch)),
                    }, ensure_ascii=False),
                )
                if isinstance(result, dict):
                    if result.get("success") is False:
                        raise RuntimeError(result.get("error") or "batch_compute_factors failed")
                    data = result.get("data") or {}
                    total_computed += data.get("computed_count", 0)
                    total_errors += data.get("error_count", 0)
            except Exception as e:
                logger.error("FactorScheduler batch %d-%d error: %s", i, i + len(batch), e)
                total_errors += len(batch)
                batch_failures.append(
                    {
                        "batch_index": len(batch_failures),
                        "offset": i,
                        "size": len(batch),
                        "codes": list(batch),
                        "error": str(e),
                    }
                )

        llm_enabled = os.getenv("FACTOR_LLM_ENABLED", "0").strip() in ("1", "true", "yes")
        scheduler_llm = os.getenv("FACTOR_SCHEDULER_LLM_MINING", "1").strip().lower() in ("1", "true", "yes", "on")
        llm_provider_preflight = {
            "status": "skipped",
            "action": None,
            "error": None,
            "before": {},
            "after": {},
        }
        reset_llm_provider_after_run = False
        if llm_enabled and scheduler_llm:
            llm_provider_preflight = await self._prepare_llm_provider(
                llm_enabled=llm_enabled,
                scheduler_llm=scheduler_llm,
            )
            reset_llm_provider_after_run = bool(
                str(llm_provider_preflight.get("status") or "").strip().lower() == "failed"
                and bool(dict(llm_provider_preflight.get("before") or {}).get("ready"))
            )
        llm_provider_status = self._provider_status() if (llm_enabled and scheduler_llm) else {}
        llm_provider_gate = self._resolve_provider_gate(
            llm_enabled=llm_enabled,
            scheduler_llm=scheduler_llm,
            provider_status=llm_provider_status,
            provider_preflight=llm_provider_preflight,
        )
        if llm_enabled and scheduler_llm:
            gate_status = str(llm_provider_gate.get("status") or "").strip().lower()
            should_short_circuit_llm = gate_status == "blocked" and not bool(
                dict(llm_provider_preflight.get("before") or {}).get("ready")
            )
            if should_short_circuit_llm:
                reason = str(llm_provider_gate.get("reason") or "provider_not_ready_after_preflight")
                llm_mining_result = {
                    "success": False,
                    "error": "factor llm provider not ready after preflight",
                    "data": {
                        "warnings": [reason],
                        "generation_mode": "provider_blocked",
                        "fallback_used": False,
                        "fallback_reason": None,
                        "allow_local_rule_fallback": False,
                        "provider_gate_status": llm_provider_gate.get("status"),
                        "provider_gate_reason": reason,
                    },
                }
                llm_validation_result = {
                    "status": "failed",
                    "validation_attempted": False,
                    "generated_candidate_count": 0,
                    "validated_candidate_count": 0,
                    "validation_failed_count": 0,
                    "validation_codes": [],
                    "validation_artifact_ids": [],
                    "failed_candidates": [{"reason": reason}],
                    "registry_refresh_status": "failed",
                    "registry_summary": {},
                    "active_pool_count_after_run": 0,
                    "governed_active_count_after_run": 0,
                    "blocked_active_count_after_run": 0,
                }
            else:
                try:
                    from ..tools.managers.quant_manager import quant_manager
                    llm_mining_result = await quant_manager(
                        action="llm_factor_mining",
                        kwargs=json.dumps({
                            "codes": self.universe,
                            "allow_fallback": bool(llm_provider_gate.get("allow_local_rule_fallback")),
                            "dedup_mode": "penalty",
                        }, ensure_ascii=False),
                    )
                    llm_validation_result = await self._run_llm_validation_cycle(
                        quant_manager,
                        llm_mining_result,
                    )
                    logger.info("FactorScheduler: LLM mining completed")
                except Exception as e:
                    logger.warning("FactorScheduler: LLM mining failed: %s", e)
                    llm_mining_result = {"error": str(e)}
                    llm_validation_result = {
                        "status": "failed",
                        "validation_attempted": False,
                        "generated_candidate_count": 0,
                        "validated_candidate_count": 0,
                        "validation_failed_count": 0,
                        "validation_codes": [],
                        "validation_artifact_ids": [],
                        "failed_candidates": [{"reason": str(e)}],
                        "registry_refresh_status": "failed",
                        "registry_summary": {},
                        "active_pool_count_after_run": 0,
                        "governed_active_count_after_run": 0,
                        "blocked_active_count_after_run": 0,
                    }

        llm_provider_status = self._provider_status() if (llm_enabled and scheduler_llm) else {}
        if isinstance(llm_mining_result, dict):
            if isinstance(llm_mining_result.get("data"), dict):
                llm_mining_result["data"].setdefault(
                    "allow_local_rule_fallback",
                    bool(llm_provider_gate.get("allow_local_rule_fallback")),
                )
                llm_mining_result["data"].setdefault(
                    "provider_gate_status",
                    llm_provider_gate.get("status"),
                )
                llm_mining_result["data"].setdefault(
                    "provider_gate_reason",
                    llm_provider_gate.get("reason"),
                )
                llm_mining_result["data"]["provider_health"] = dict(llm_provider_status)
                llm_mining_result["data"]["provider_preflight"] = dict(llm_provider_preflight)
            else:
                llm_mining_result["allow_local_rule_fallback"] = bool(
                    llm_provider_gate.get("allow_local_rule_fallback")
                )
                llm_mining_result["provider_gate_status"] = llm_provider_gate.get("status")
                llm_mining_result["provider_gate_reason"] = llm_provider_gate.get("reason")
                llm_mining_result["provider_health"] = dict(llm_provider_status)
                llm_mining_result["provider_preflight"] = dict(llm_provider_preflight)

        llm_payload = llm_mining_result.get("data") if isinstance((llm_mining_result or {}).get("data"), dict) else {}
        llm_generation_artifact_id = str(llm_payload.get("artifact_id") or "").strip() or None
        llm_quality_errors = 0
        if isinstance(llm_validation_result, dict):
            if str(llm_validation_result.get("status") or "").strip().lower() in {"failed", "partial"}:
                llm_quality_errors = max(
                    1,
                    int(llm_validation_result.get("validation_failed_count") or 0),
                )

        batch_stage_status = "completed"
        if total_errors > 0 and total_computed == 0:
            batch_stage_status = "failed"
        elif total_errors > 0:
            batch_stage_status = "partial"

        llm_stage_status = "skipped"
        if llm_enabled and scheduler_llm:
            if isinstance(llm_mining_result, dict) and llm_mining_result.get("success"):
                llm_stage_status = "completed"
            else:
                llm_stage_status = "failed"

        validation_status_token = str((llm_validation_result or {}).get("status") or "").strip().lower()
        validation_stage_status = "skipped"
        if validation_status_token in {"success", "completed"}:
            validation_stage_status = "completed"
        elif validation_status_token in {"partial", "failed", "skipped"}:
            validation_stage_status = self._normalize_stage_status(validation_status_token)

        registry_refresh_status = str((llm_validation_result or {}).get("registry_refresh_status") or "").strip().lower()
        registry_stage_status = "skipped"
        if registry_refresh_status == "success":
            registry_stage_status = "completed"
        elif registry_refresh_status in {"failed", "partial"}:
            registry_stage_status = self._normalize_stage_status(registry_refresh_status)
        elif validation_stage_status == "completed" and int((llm_validation_result or {}).get("validated_candidate_count") or 0) > 0:
            registry_stage_status = "partial"

        stages = {
            "batch_compute": self._build_stage_result(
                "batch_compute",
                status=batch_stage_status,
                payload={
                    "computed_count": total_computed,
                    "error_count": total_errors,
                    "batch_count": total_batches,
                    "completed_batch_count": max(processed_batches - len(batch_failures), 0),
                    "failed_batch_count": len(batch_failures),
                    "failed_batches": batch_failures[:12],
                },
                retry_boundary="batch",
            ),
            "llm_factor_mining": self._build_stage_result(
                "llm_factor_mining",
                status=llm_stage_status,
                payload={
                    "enabled": bool(llm_enabled and scheduler_llm),
                    "artifact_id": llm_generation_artifact_id,
                    "candidate_count": int(llm_payload.get("candidate_count") or len(llm_payload.get("candidates") or [])),
                    "blocked_candidate_count": int(len(llm_payload.get("blocked_candidates") or [])),
                    "degraded": bool(llm_payload.get("degraded")),
                    "warnings": list(llm_payload.get("warnings") or []),
                    "generation_mode": llm_payload.get("generation_mode"),
                    "fallback_used": bool(llm_payload.get("fallback_used")),
                    "fallback_reason": llm_payload.get("fallback_reason"),
                    "allow_local_rule_fallback": llm_payload.get("allow_local_rule_fallback"),
                    "provider_gate_status": llm_payload.get("provider_gate_status"),
                    "provider_gate_reason": llm_payload.get("provider_gate_reason"),
                    "provider_health_status": llm_provider_status.get("health_status"),
                    "provider_ready": bool(llm_provider_status.get("ready")),
                    "provider_enabled": bool(llm_provider_status.get("enabled")),
                    "provider_rebuild_count": int(llm_provider_status.get("rebuild_count") or 0),
                    "provider_last_error_type": llm_provider_status.get("last_error_type"),
                    "provider_preflight_status": llm_provider_preflight.get("status"),
                    "provider_preflight_action": llm_provider_preflight.get("action"),
                },
                retry_boundary="workflow_stage",
            ),
            "llm_validation": self._build_stage_result(
                "llm_validation",
                status=validation_stage_status,
                payload={
                    "generated_candidate_count": int((llm_validation_result or {}).get("generated_candidate_count") or 0),
                    "validated_candidate_count": int((llm_validation_result or {}).get("validated_candidate_count") or 0),
                    "validation_failed_count": int((llm_validation_result or {}).get("validation_failed_count") or 0),
                    "validation_artifact_ids": list((llm_validation_result or {}).get("validation_artifact_ids") or []),
                    "validation_codes": list((llm_validation_result or {}).get("validation_codes") or []),
                    "failures": list((llm_validation_result or {}).get("failed_candidates") or []),
                },
                retry_boundary="candidate_validation",
            ),
            "registry_refresh": self._build_stage_result(
                "registry_refresh",
                status=registry_stage_status,
                payload={
                    "registry_refresh_status": registry_refresh_status or "not_needed",
                    "active_pool_count_after_run": int((llm_validation_result or {}).get("active_pool_count_after_run") or 0),
                    "governed_active_count_after_run": int((llm_validation_result or {}).get("governed_active_count_after_run") or 0),
                    "blocked_active_count_after_run": int((llm_validation_result or {}).get("blocked_active_count_after_run") or 0),
                },
                retry_boundary="registry_refresh",
            ),
        }

        elapsed = (datetime.now().astimezone() - start).total_seconds()
        self.last_run = datetime.now().astimezone()
        quality_meta = self._build_quality_meta(
            asof_dt=self.last_run,
            computed=total_computed,
            errors=total_errors + llm_quality_errors,
            now=self.last_run,
        )
        run_status = self._resolve_run_status(stages)
        stage_summary = self._summarize_stage_results(stages)
        recovery_checkpoint = {
            "last_completed_stage": next(
                (
                    stage_name
                    for stage_name in ("registry_refresh", "llm_validation", "llm_factor_mining", "batch_compute")
                    if self._normalize_stage_status((stages.get(stage_name) or {}).get("status")) == "completed"
                ),
                None,
            ),
            "failed_stage_names": list(stage_summary.get("failed_stages") or []),
            "retryable_stage_names": [
                stage_name
                for stage_name, stage_payload in stages.items()
                if bool((stage_payload or {}).get("retryable"))
            ],
            "processed_batch_count": processed_batches,
            "failed_batch_count": len(batch_failures),
            "failed_batch_codes": [code for item in batch_failures for code in list(item.get("codes") or [])][:24],
            "llm_generation_artifact_id": llm_generation_artifact_id,
            "validation_artifact_ids": list((llm_validation_result or {}).get("validation_artifact_ids") or []),
        }
        self.last_result = {
            "run_id": run_id,
            "status": run_status,
            "workflow_version": "p2.v1",
            "started_at": start.isoformat(),
            "completed_at": self.last_run.isoformat(),
            "computed": total_computed,
            "errors": total_errors,
            "elapsed_seconds": round(elapsed, 1),
            "universe_size": len(self.universe),
            "llm_mining": llm_mining_result,
            "llm_validation": llm_validation_result,
            "llm_provider": llm_provider_status,
            "llm_provider_preflight": llm_provider_preflight,
            "stages": stages,
            "stage_summary": stage_summary,
            "recovery_checkpoint": recovery_checkpoint,
            "lineage": {
                "source": "factor_scheduler",
                "workflow_version": "p2.v1",
                "input_universe_size": len(self.universe),
                "batch_size": self.batch_size,
                "factors": list(self.factors),
                "llm_generation_artifact_id": llm_generation_artifact_id,
                "validation_artifact_ids": list((llm_validation_result or {}).get("validation_artifact_ids") or []),
            },
            **quality_meta,
        }
        self.last_result["quality_status"] = self._quality_status(list(self.last_result.get("quality_flags") or []))
        self.last_result["stale"] = "stale" in list(self.last_result.get("quality_flags") or [])
        self.last_result["summary"] = self._build_run_summary(self.last_result)
        self._record_run_history(self.last_result)
        if reset_llm_provider_after_run:
            try:
                from .factor_llm_provider import close_factor_llm_provider

                await close_factor_llm_provider()
            except Exception:
                logger.debug("FactorScheduler: failed to reset factor llm provider after degraded preflight", exc_info=True)

        # ── Factor Mining Factory 委托 ──────────────────────────────
        factory_mining_result = None
        try:
            from .factor_scheduler import is_factory_mining_enabled, run_factory_mining_cycle
            if is_factory_mining_enabled():
                factory_mining_result = await run_factory_mining_cycle(
                    trigger="scheduler_delegate",
                    codes=self.universe[:50],
                )
                self.last_result["factory_mining"] = factory_mining_result
                logger.info(
                    "FactorScheduler: factory mining delegate completed — admitted=%d pool=%d",
                    (factory_mining_result or {}).get("admitted_count", 0),
                    (factory_mining_result or {}).get("pool_size", 0),
                )
        except Exception as exc:
            logger.debug("FactorScheduler: factory mining delegate skipped: %s", exc)
            self.last_result["factory_mining"] = {"status": "skipped", "reason": str(exc)}
        # ── End Factory Mining Factory 委托 ─────────────────────────

        logger.info(
            "FactorScheduler: completed in %.1fs — %d computed, %d errors",
            elapsed, total_computed, total_errors,
        )
        return self.last_result

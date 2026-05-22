
    def status(self) -> dict:
        """Return current scheduler status."""
        llm_validation = dict((self.last_result or {}).get("llm_validation") or {})
        llm_quality_errors = 0
        if str(llm_validation.get("status") or "").strip().lower() in {"failed", "partial"}:
            llm_quality_errors = max(
                1,
                int(llm_validation.get("validation_failed_count") or 0),
            )
        quality_meta = self._build_quality_meta(
            asof_dt=self.last_run,
            computed=int((self.last_result or {}).get("computed") or 0),
            errors=int((self.last_result or {}).get("errors") or 0) + llm_quality_errors,
        )
        return {
            "running": self._running,
            "run_time": str(self.run_time),
            "universe_size": len(self.universe),
            "factors": self.factors,
            "last_run": self._isoformat(self.last_run),
            "last_result": self.last_result,
            "last_summary": (self.last_result or {}).get("summary") if self.last_result else None,
            "run_history": list(self._run_history or []),
            "llm_provider": dict((self.last_result or {}).get("llm_provider") or self._provider_status()),
            "quality_status": self._quality_status(list(quality_meta.get("quality_flags") or [])),
            "stale": "stale" in list(quality_meta.get("quality_flags") or []),
            **quality_meta,
        }

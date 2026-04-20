
        @classmethod
        def _inject_factor_refresh_meta(cls, artifact: Optional[dict], refresh_meta: dict[str, Any]) -> dict[str, Any]:
            data = dict(artifact or {})
            summary = dict(data.get("summary") or {})
            scheduler_status = dict(data.get("scheduler_status") or {})
            normalized_meta = dict(refresh_meta or {})
            summary.update(
                {
                    "auto_refresh_enabled": bool(normalized_meta.get("auto_refresh_enabled")),
                    "refresh_attempted": bool(normalized_meta.get("refresh_attempted")),
                    "refresh_status": normalized_meta.get("refresh_status"),
                    "refresh_trigger": normalized_meta.get("refresh_trigger"),
                    "refresh_error": normalized_meta.get("refresh_error"),
                    "refreshed_before_build": bool(normalized_meta.get("refreshed_before_build")),
                }
            )
            scheduler_status.update(
                {
                    "refresh_attempted": bool(normalized_meta.get("refresh_attempted")),
                    "refresh_status": normalized_meta.get("refresh_status"),
                    "refresh_error": normalized_meta.get("refresh_error"),
                }
            )
            data["freshness_repair"] = normalized_meta
            data["summary"] = summary
            data["scheduler_status"] = scheduler_status
            return data

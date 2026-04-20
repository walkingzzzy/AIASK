
    @classmethod
    def _resolve_behavior_build_timeout_sec(cls) -> float:
        return cls._resolve_timeout_sec(
            "DEDUP_BEHAVIOR_BUILD_TIMEOUT_SEC",
            cls.DEFAULT_BEHAVIOR_BUILD_TIMEOUT_SEC,
        )

    @classmethod
    def _resolve_prewarm_timeout_sec(cls) -> float:
        return cls._resolve_timeout_sec(
            "DEDUP_PREWARM_TIMEOUT_SEC",
            cls.DEFAULT_PREWARM_TIMEOUT_SEC,
        )

    async def _bounded_behavior_gather(self, payloads: List[Tuple[str, dict]], db) -> List[Optional[List[dict]]]:
        if not payloads:
            return []
        concurrency = max(1, int(_compat_setting("DEDUP_CONCURRENCY", DEDUP_CONCURRENCY) or 1))
        sem = asyncio.Semaphore(concurrency)
        timeout_sec = self._resolve_behavior_build_timeout_sec()
        ordered_keys: List[str] = []
        unique_payloads: Dict[str, Tuple[str, dict]] = {}

        for strategy_type, params in list(payloads or []):
            normalized_params = self._normalize_params(params)
            cache_key = self._behavior_cache_key(strategy_type, normalized_params)
            ordered_keys.append(cache_key)
            unique_payloads.setdefault(cache_key, (strategy_type, normalized_params))

        async def _run(cache_key: str, strategy_type: str, params: dict) -> Optional[List[dict]]:
            async with sem:
                try:
                    return await asyncio.wait_for(
                        self._build_behavior_klines(strategy_type, params, db),
                        timeout=timeout_sec,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "deduplicator: behavior build timed out for %s after %.2fs",
                        cache_key,
                        timeout_sec,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("deduplicator: behavior build failed for %s: %s", cache_key, exc)
                return None

        unique_items = list(unique_payloads.items())
        gathered = await asyncio.gather(*[
            _run(cache_key, strategy_type, params)
            for cache_key, (strategy_type, params) in unique_items
        ])
        results_by_key = {
            cache_key: result
            for (cache_key, _payload), result in zip(unique_items, gathered)
        }
        return [results_by_key.get(cache_key) for cache_key in ordered_keys]

    async def _vector_check(self, candidate: dict, suspicious: List[Tuple[dict, float]], db) -> Optional[dict]:
        query_strategy_type = str(candidate.get("strategy_type") or "").strip()
        query_params = self._normalize_params(candidate.get("params"))
        suspicious_payloads = [
            (str(existing_item.get("strategy_type") or "").strip(), self._normalize_params(existing_item.get("params")))
            for existing_item, _ in list(suspicious or [])
            if str(existing_item.get("strategy_type") or "").strip()
        ]
        gathered = await self._bounded_behavior_gather([(query_strategy_type, query_params), *suspicious_payloads], db)
        query_klines = gathered[0] if gathered else None
        if not query_klines:
            return None

        candidate_klines_dict: Dict[str, List[dict]] = {}
        match_meta: Dict[str, dict] = {}
        for idx, (existing_item, effective_similarity) in enumerate(suspicious):
            params = self._normalize_params(existing_item.get("params"))
            klines = gathered[idx + 1] if idx + 1 < len(gathered) else None
            if not klines:
                continue
            code = str(existing_item.get("id") or existing_item.get("name") or f"candidate_{idx}")
            candidate_klines_dict[code] = klines
            match_meta[code] = {
                "matched_strategy_id": existing_item.get("id"),
                "matched_name": existing_item.get("name") or existing_item.get("strategy_type"),
                "matched_status": existing_item.get("status"),
                "param_similarity": self._param_sim(candidate.get("params", {}), params),
                "target_overlap": self._target_overlap(candidate, existing_item),
                "effective_similarity": effective_similarity,
            }
        if not candidate_klines_dict:
            return None

        gateway = self._get_vector_gateway()
        results = gateway.find_similar_patterns(
            query_klines=query_klines,
            candidate_klines_dict=candidate_klines_dict,
            top_k=1,
            method="returns",
            metric="cosine",
            backend="index",
            allow_fallback=True,
        )
        if not results:
            return None
        top = results[0]
        meta = match_meta.get(str(top.get("code")), {})
        return {
            "similarity": float(top.get("similarity") or 0.0),
            "backend": str(getattr(gateway, "last_backend_used", "") or ""),
            **meta,
        }

    async def _build_behavior_klines(self, strategy_type: str, params: dict, db) -> Optional[List[dict]]:
        factory_pkg = _get_strategy_factory_package()
        cache_key = self._behavior_cache_key(strategy_type, params)
        if cache_key in self._behavior_cache:
            return self._behavior_cache[cache_key]
        build_strategy_panels = getattr(factory_pkg, "_build_strategy_panels", None)
        if not callable(build_strategy_panels):
            self._behavior_cache[cache_key] = None
            return None
        panels = await build_strategy_panels(strategy_type, params, db, sample_size=4)
        series = panels.get("strategy_returns")
        if series is None or len(series) < 30:
            self._behavior_cache[cache_key] = None
            return None
        nonzero_ratio = float(np.count_nonzero(series)) / len(series)
        if nonzero_ratio < 0.1:
            self._behavior_cache[cache_key] = None
            return None
        price = 100.0
        pseudo_klines: List[dict] = []
        for ret in np.asarray(series[-60:], dtype=np.float64):
            open_price = price
            price = open_price * (1 + float(ret))
            pseudo_klines.append({
                "open": round(open_price, 6),
                "high": round(max(open_price, price), 6),
                "low": round(min(open_price, price), 6),
                "close": round(price, 6),
                "volume": 1.0,
            })
        self._behavior_cache[cache_key] = pseudo_klines
        return pseudo_klines

    def get_last_report(self) -> dict:
        return self.last_report

    @staticmethod
    def _target_overlap(left_payload: Optional[dict], right_payload: Optional[dict]) -> Optional[float]:
        left = set(_extract_target_codes_from_payload(left_payload or {}, limit=20))
        right = set(_extract_target_codes_from_payload(right_payload or {}, limit=20))
        if not left or not right:
            return None
        union = left | right
        if not union:
            return None
        return round(len(left & right) / len(union), 4)

    @classmethod
    def _effective_similarity(cls, param_similarity: float, target_overlap: Optional[float]) -> float:
        if target_overlap is None:
            return float(param_similarity)
        return round((float(param_similarity) + float(target_overlap)) / 2.0, 4)

    @staticmethod
    def _param_sim(left: dict, right: dict) -> float:
        keys = set(left.keys()) | set(right.keys())
        if not keys:
            return 0.0
        sims: List[float] = []
        for key in keys:
            if key not in left or key not in right:
                sims.append(0.0)
                continue
            left_value = left[key]
            right_value = right[key]
            if isinstance(left_value, (int, float)) and isinstance(right_value, (int, float)):
                denom = max(abs(left_value), abs(right_value), 1e-9)
                sims.append(1.0 - abs(left_value - right_value) / denom)
            elif left_value == right_value:
                sims.append(1.0)
            else:
                sims.append(0.0)
        return float(np.mean(sims)) if sims else 0.0

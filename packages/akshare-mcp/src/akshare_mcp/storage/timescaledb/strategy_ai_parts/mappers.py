
    async def save_factory_task_evidence(self, item: dict) -> dict:
        payload = dict(item or {})
        task_key = str(payload.get("task_key") or "").strip()
        evidence_type = str(payload.get("evidence_type") or "").strip()
        if not task_key or not evidence_type:
            raise ValueError("task_key and evidence_type are required")
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO strategy_factory_task_evidence
                    (task_key, event_id, theme_code, symbol, evidence_type, weight, evidence_payload, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
                RETURNING *
                """,
                task_key,
                payload.get("event_id"),
                str(payload.get("theme_code") or ""),
                payload.get("symbol"),
                evidence_type,
                float(payload.get("weight") or 0.0),
                json.dumps(payload.get("evidence_payload") or {}, ensure_ascii=False, default=str),
            )
        return self._decode_factory_task_evidence(dict(row))

    async def list_factory_task_evidence(
        self,
        task_key: Optional[str] = None,
        event_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[dict]:
        async with self.acquire() as conn:
            sql = "SELECT * FROM strategy_factory_task_evidence WHERE 1=1"
            params: list = []
            idx = 1
            if task_key:
                sql += f" AND task_key = ${idx}"
                params.append(str(task_key))
                idx += 1
            if event_id:
                sql += f" AND event_id = ${idx}"
                params.append(str(event_id))
                idx += 1
            sql += f" ORDER BY created_at DESC LIMIT ${idx}"
            params.append(max(1, min(int(limit or 200), 500)))
            rows = await conn.fetch(sql, *params)
        return [self._decode_factory_task_evidence(dict(row)) for row in rows]

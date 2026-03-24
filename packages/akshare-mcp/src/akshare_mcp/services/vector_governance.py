"""策略向量索引治理：索引注册表校准、重建与版本切换。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class StrategyVectorGovernanceService:
    async def _record_domain_event(self, db, *, event_type: str, source: str, payload: dict, correlation_id: str | None = None):
        if hasattr(db, 'save_strategy_domain_event'):
            await db.save_strategy_domain_event({
                'strategy_id': None,
                'aggregate_type': 'vector_index',
                'aggregate_id': payload.get('index_name') or payload.get('index_version') or 'strategy_behavior',
                'event_type': event_type,
                'source': source,
                'severity': 'info',
                'correlation_id': correlation_id,
                'payload': payload,
            })

    async def reconcile_registry(
        self,
        db,
        index_name: Optional[str] = None,
        profile_type: Optional[str] = None,
        limit_profiles: int = 2000,
    ) -> dict:
        rows = await db.list_strategy_vector_profiles(
            profile_type=profile_type,
            limit=max(1, min(int(limit_profiles or 2000), 5000)),
        ) if hasattr(db, 'list_strategy_vector_profiles') else []
        grouped: dict[tuple[str, str], dict] = {}
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            meta = dict(row.get('metadata') or {})
            resolved_index_name = str(index_name or meta.get('index_name') or 'strategy_behavior')
            version = str(row.get('index_version') or meta.get('index_version') or 'v1')
            key = (resolved_index_name, version)
            bucket = grouped.setdefault(key, {
                'index_name': resolved_index_name,
                'backend': str(row.get('backend') or 'index'),
                'status': 'active',
                'profile_type': str(row.get('profile_type') or 'behavior'),
                'vector_method': str(row.get('vector_method') or 'price_volume'),
                'metric': str(row.get('metric') or 'cosine'),
                'sample_count': 0,
                'index_version': version,
                'metadata': {
                    'strategy_ids': [],
                    'profile_ids': [],
                    'reconciled_at': now,
                },
                'built_at': now,
                'activated_at': now,
            })
            bucket['sample_count'] += 1
            if row.get('strategy_id') and row.get('strategy_id') not in bucket['metadata']['strategy_ids']:
                bucket['metadata']['strategy_ids'].append(row.get('strategy_id'))
            if row.get('id') is not None:
                bucket['metadata']['profile_ids'].append(row.get('id'))

        if hasattr(db, 'list_strategy_vector_index_snapshots'):
            snapshots = await db.list_strategy_vector_index_snapshots(index_name=index_name, limit=5000, latest_only=True)
            for snapshot in snapshots:
                key = (str(snapshot.get('index_name') or 'strategy_behavior'), str(snapshot.get('index_version') or 'v1'))
                if key not in grouped:
                    continue
                grouped[key]['metadata'].update({
                    'ann_snapshot_id': snapshot.get('id'),
                    'bucket_count': snapshot.get('bucket_count'),
                    'vector_dim': snapshot.get('vector_dim'),
                    'index_snapshot_status': snapshot.get('status'),
                })

        updated = []
        for item in grouped.values():
            updated.append(await db.save_vector_index_registry(item))

        existing = await db.list_vector_index_registry(index_name=index_name, limit=5000) if hasattr(db, 'list_vector_index_registry') else []
        active_keys = set(grouped.keys())
        stale = []
        for item in existing:
            key = (str(item.get('index_name') or 'strategy_behavior'), str(item.get('index_version') or 'v1'))
            if key in active_keys:
                continue
            if item.get('status') == 'stale':
                continue
            stale_item = await db.save_vector_index_registry({
                **item,
                'status': 'stale',
                'metadata': {
                    **dict(item.get('metadata') or {}),
                    'reconciled_at': now,
                    'stale_reason': 'profile_group_missing',
                },
            })
            stale.append(stale_item)

        if updated or stale:
            await self._record_domain_event(
                db,
                event_type='vector_index.registry_reconciled',
                source='vector_governance',
                payload={
                    'index_name': index_name or 'all',
                    'profile_type': profile_type,
                    'registry_updated': len(updated),
                    'stale_marked': len(stale),
                },
            )

        return {
            'registry_updated': len(updated),
            'stale_marked': len(stale),
            'active_indexes': len(updated),
            'items': updated,
            'stale_items': stale,
        }

    async def rebuild_index(
        self,
        db,
        index_name: str = 'strategy_behavior',
        index_version: Optional[str] = None,
        statuses: Optional[list[str]] = None,
        limit: int = 200,
        profile_type: str = 'behavior',
        vector_method: Optional[str] = None,
    ) -> dict:
        statuses = list(statuses or ['incubating', 'listed'])
        resolved_version = str(index_version or f"auto_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
        correlation_id = uuid4().hex[:12]
        from .vector_platform import get_strategy_vector_platform

        platform = get_strategy_vector_platform()
        resolved_vector_method = (
            platform.ensure_vector_method_available(vector_method)
            if hasattr(platform, 'ensure_vector_method_available')
            else str(vector_method or 'price_volume')
        )
        task_run = await db.save_strategy_task_run({
            'task_name': 'strategy_vector_rebuild',
            'task_scope': index_name,
            'task_key': resolved_version,
            'status': 'running',
            'trace_id': correlation_id,
            'payload': {
                'index_name': index_name,
                'index_version': resolved_version,
                'statuses': statuses,
                'limit': limit,
                'profile_type': profile_type,
                'vector_method': resolved_vector_method,
            },
        }) if hasattr(db, 'save_strategy_task_run') else {'id': None}

        try:
            seen = set()
            strategies = []
            for status in statuses:
                rows = await db.list_strategies(status, limit=max(1, min(int(limit or 200), 1000)))
                for row in rows:
                    sid = row.get('id')
                    if sid and sid not in seen:
                        seen.add(sid)
                        strategies.append(row)

            build_result = await platform.build_profiles_for_strategies(
                db,
                strategies,
                profile_type=profile_type,
                vector_method=resolved_vector_method,
                index_name=index_name,
                index_version=resolved_version,
            )
            persist_result = await platform.build_persisted_ann_index(
                db,
                index_name=index_name,
                index_version=resolved_version,
                profile_type=profile_type,
                task_run_id=task_run.get('id'),
                source='vector_governance',
                limit_profiles=max(1, min(int(limit or 200), 5000)),
            )

            existing = await db.list_vector_index_registry(index_name=index_name, limit=5000) if hasattr(db, 'list_vector_index_registry') else []
            for item in existing:
                version = str(item.get('index_version') or 'v1')
                if version == resolved_version:
                    continue
                await db.save_vector_index_registry({
                    **item,
                    'status': 'stale',
                    'metadata': {
                        **dict(item.get('metadata') or {}),
                        'replaced_by': resolved_version,
                        'stale_reason': 'rebuild_replaced',
                    },
                })

            if hasattr(db, 'list_strategy_vector_index_snapshots') and hasattr(db, 'save_strategy_vector_index_snapshot'):
                snapshots = await db.list_strategy_vector_index_snapshots(index_name=index_name, limit=5000, latest_only=True)
                for snapshot in snapshots:
                    version = str(snapshot.get('index_version') or 'v1')
                    if version == resolved_version or snapshot.get('status') == 'stale':
                        continue
                    await db.save_strategy_vector_index_snapshot({
                        **snapshot,
                        'status': 'stale',
                        'metadata': {
                            **dict(snapshot.get('metadata') or {}),
                            'replaced_by': resolved_version,
                            'stale_reason': 'rebuild_replaced',
                        },
                    })

            reconcile = await self.reconcile_registry(db, index_name=index_name, profile_type=profile_type)
            active_registry = await db.save_vector_index_registry({
                'index_name': index_name,
                'backend': platform.backend_name(db) if hasattr(platform, 'backend_name') else getattr(getattr(platform, 'engine', None), 'backend', 'index'),
                'status': 'active',
                'profile_type': profile_type,
                'vector_method': resolved_vector_method,
                'metric': 'cosine',
                'sample_count': int(build_result.get('count') or 0),
                'index_version': resolved_version,
                'metadata': {
                    'profile_ids': [item.get('id') for item in build_result.get('items') or [] if item.get('id') is not None],
                    'ann_snapshot_id': ((persist_result.get('snapshot') or {}).get('id')),
                    'bucket_count': persist_result.get('bucket_count'),
                    'persisted_items': persist_result.get('items_count'),
                    'task_run_id': task_run.get('id'),
                },
                'built_at': datetime.now(timezone.utc).isoformat(),
                'activated_at': datetime.now(timezone.utc).isoformat(),
            })
            result = {
                'task_run_id': task_run.get('id'),
                'index_name': index_name,
                'index_version': resolved_version,
                'strategy_count': len(strategies),
                'built_profiles': int(build_result.get('count') or 0),
                'persisted_snapshot_id': (persist_result.get('snapshot') or {}).get('id'),
                'persisted_items': int(persist_result.get('items_count') or 0),
                'bucket_count': int(persist_result.get('bucket_count') or 0),
                'active_registry': active_registry,
                'reconcile': reconcile,
            }
            if task_run.get('id') is not None and hasattr(db, 'update_strategy_task_run'):
                await db.update_strategy_task_run(task_run['id'], status='completed', result=result, completed_at=datetime.now(timezone.utc).isoformat())
            await self._record_domain_event(
                db,
                event_type='vector_index.rebuilt',
                source='vector_governance',
                correlation_id=correlation_id,
                payload=result,
            )
            return result
        except Exception as exc:
            logger.warning('StrategyVectorGovernanceService.rebuild_index failed: %s', exc)
            if task_run.get('id') is not None and hasattr(db, 'update_strategy_task_run'):
                await db.update_strategy_task_run(task_run['id'], status='failed', error=str(exc), result={'index_name': index_name, 'index_version': resolved_version}, completed_at=datetime.now(timezone.utc).isoformat())
            raise


_vector_governance_service: Optional[StrategyVectorGovernanceService] = None


def get_strategy_vector_governance_service() -> StrategyVectorGovernanceService:
    global _vector_governance_service
    if _vector_governance_service is None:
        _vector_governance_service = StrategyVectorGovernanceService()
    return _vector_governance_service

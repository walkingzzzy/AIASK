from __future__ import annotations

import math

class _StrategyDBVectorMixin:
    async def save_strategy_vector_profile(self, profile):
        payload = dict(profile)
        payload['index_name'] = payload.get('index_name') or dict(payload.get('metadata') or {}).get('index_name') or 'strategy_behavior'
        item = {'id': len(self._vector_profiles) + 1, **payload}
        self._vector_profiles.append(item)
        if self.supports_pgvector() and int(item.get('vector_dim') or len(item.get('embedding') or [])) > 0:
            store_row = {
                'profile_id': item['id'],
                'strategy_id': item.get('strategy_id'),
                'index_name': item.get('index_name') or 'strategy_behavior',
                'index_version': item.get('index_version'),
                'profile_type': item.get('profile_type'),
                'vector_method': item.get('vector_method'),
                'metric': item.get('metric') or 'cosine',
                'vector_dim': int(item.get('vector_dim') or len(item.get('embedding') or [])),
                'embedding': list(item.get('embedding') or []),
                'metadata': dict(item.get('metadata') or {}),
                'updated_at': item.get('updated_at') or item.get('created_at'),
            }
            self._vector_profile_store = [row for row in self._vector_profile_store if row.get('profile_id') != item['id']]
            self._vector_profile_store.append(store_row)
        return dict(item)

    async def list_strategy_vector_profiles(self, strategy_id=None, profile_type=None, index_name=None, index_version=None, limit=20):
        rows = list(self._vector_profiles)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if index_name:
            rows = [row for row in rows if (row.get('index_name') or dict(row.get('metadata') or {}).get('index_name') or 'strategy_behavior') == index_name]
        if profile_type:
            rows = [row for row in rows if row.get('profile_type') == profile_type]
        if index_version:
            rows = [row for row in rows if row.get('index_version') == index_version]
        rows.sort(key=lambda row: (str(row.get('updated_at') or ''), str(row.get('created_at') or '')), reverse=True)
        return [dict(row) for row in rows[:limit]]

    async def save_vector_index_registry(self, entry):
        item = dict(entry)
        self._vector_indexes = [row for row in self._vector_indexes if not (row.get('index_name') == item.get('index_name') and row.get('index_version') == item.get('index_version'))]
        self._vector_indexes.append(item)
        return dict(item)

    async def list_vector_index_registry(self, index_name=None, status=None, limit=20):
        rows = list(self._vector_indexes)
        if index_name:
            rows = [row for row in rows if row.get('index_name') == index_name]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_vector_index_snapshot(self, snapshot):
        item = {'id': len(self._vector_index_snapshots) + 1, **dict(snapshot)}
        self._vector_index_snapshots.insert(0, item)
        return dict(item)

    async def get_latest_strategy_vector_index_snapshot(self, index_name='strategy_behavior'):
        rows = await self.list_strategy_vector_index_snapshots(index_name=index_name, limit=1)
        return rows[0] if rows else None

    async def list_strategy_vector_index_snapshots(self, index_name=None, index_version=None, status=None, limit=20, latest_only=False):
        rows = list(self._vector_index_snapshots)
        if index_name:
            rows = [row for row in rows if row.get('index_name') == index_name]
        if index_version:
            rows = [row for row in rows if row.get('index_version') == index_version]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        if latest_only:
            deduped = []
            seen = set()
            for row in rows:
                key = (row.get('index_name'), row.get('index_version'))
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(row)
            rows = deduped
        return [dict(row) for row in rows[:limit]]

    async def replace_strategy_vector_index_items(self, index_name, index_version, items):
        self._vector_index_items = [
            row for row in self._vector_index_items
            if not (row.get('index_name') == index_name and row.get('index_version') == index_version)
        ]
        if self.supports_pgvector():
            self._vector_index_item_store = [
                row for row in self._vector_index_item_store
                if not (row.get('index_name') == index_name and row.get('index_version') == index_version)
            ]
        for item in items:
            stored = {'id': len(self._vector_index_items) + 1, 'index_name': index_name, 'index_version': index_version, **dict(item)}
            self._vector_index_items.append(stored)
            if self.supports_pgvector() and int(stored.get('vector_dim') or len(stored.get('embedding') or [])) > 0:
                self._vector_index_item_store.append({
                    'item_id': stored['id'],
                    'index_name': index_name,
                    'index_version': index_version,
                    'strategy_id': stored.get('strategy_id'),
                    'profile_id': stored.get('profile_id'),
                    'profile_type': stored.get('profile_type'),
                    'vector_method': stored.get('vector_method'),
                    'metric': stored.get('metric') or 'cosine',
                    'vector_dim': int(stored.get('vector_dim') or len(stored.get('embedding') or [])),
                    'embedding': list(stored.get('embedding') or []),
                    'metadata': dict(stored.get('metadata') or {}),
                    'updated_at': stored.get('updated_at') or stored.get('created_at'),
                })
        return {'index_name': index_name, 'index_version': index_version, 'count': len(items)}

    async def list_strategy_vector_index_items(self, index_name=None, index_version=None, bucket_ids=None, strategy_id=None, limit=200):
        rows = list(self._vector_index_items)
        if index_name:
            rows = [row for row in rows if row.get('index_name') == index_name]
        if index_version:
            rows = [row for row in rows if row.get('index_version') == index_version]
        if bucket_ids:
            rows = [row for row in rows if row.get('bucket_id') in set(bucket_ids)]
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        rows.sort(key=lambda row: float(row.get('coarse_score') or 0.0), reverse=True)
        return [dict(row) for row in rows[:limit]]

    @staticmethod
    def _vector_similarity(left, right, metric='cosine'):
        a = [float(item) for item in list(left or [])]
        b = [float(item) for item in list(right or [])]
        if not a or len(a) != len(b):
            return 0.0
        if metric == 'euclidean':
            distance = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
            return 1.0 / (1.0 + distance)
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a <= 1e-12 or norm_b <= 1e-12:
            return 0.0
        return dot / (norm_a * norm_b)

    async def search_strategy_vector_profiles_by_embedding(self, query_embedding, profile_type=None, index_name=None, index_version=None, exclude_strategy_id=None, limit=20, metric='cosine'):
        if not self.supports_pgvector():
            return []
        rows = await self.list_strategy_vector_profiles(profile_type=profile_type, index_name=index_name, index_version=index_version, limit=5000)
        results = []
        for row in rows:
            if exclude_strategy_id and row.get('strategy_id') == exclude_strategy_id:
                continue
            similarity = self._vector_similarity(query_embedding, row.get('embedding') or [], metric=metric)
            results.append({**dict(row), 'similarity': round(float(similarity), 6)})
        results.sort(key=lambda row: row.get('similarity', 0.0), reverse=True)
        return results[:limit]

    async def search_strategy_vector_index_items_by_embedding(self, query_embedding, index_name, index_version, profile_type=None, exclude_strategy_id=None, limit=80, metric='cosine'):
        if not self.supports_pgvector():
            return []
        rows = await self.list_strategy_vector_index_items(index_name=index_name, index_version=index_version, limit=5000)
        if profile_type:
            rows = [row for row in rows if row.get('profile_type') == profile_type]
        if exclude_strategy_id:
            rows = [row for row in rows if row.get('strategy_id') != exclude_strategy_id]
        results = []
        for row in rows:
            similarity = self._vector_similarity(query_embedding, row.get('embedding') or [], metric=metric)
            results.append({**dict(row), 'similarity': round(float(similarity), 6)})
        results.sort(key=lambda row: row.get('similarity', 0.0), reverse=True)
        return results[:limit]

    async def ensure_strategy_vector_index_item_pgvector_index(self, index_name, index_version, vector_dim, metric='cosine'):
        if not self.supports_pgvector() or int(vector_dim or 0) <= 0:
            return None
        idx_name = f"idx_svi_pg_hnsw_{self._sanitize_index_part(index_name)}_{self._sanitize_index_part(index_version)}_{int(vector_dim)}_{self._sanitize_index_part(metric)}"
        row = {
            'schemaname': 'public',
            'tablename': 'strategy_vector_index_item_store',
            'indexname': idx_name,
            'indexdef': f"CREATE INDEX {idx_name} ON strategy_vector_index_item_store USING hnsw ((embedding::vector({int(vector_dim)}) vector_cosine_ops)) WHERE index_name = '{index_name}' AND index_version = '{index_version}' AND vector_dim = {int(vector_dim)}",
            'index_name': index_name,
            'index_version': index_version,
        }
        self._vector_hnsw_indexes = [item for item in self._vector_hnsw_indexes if item.get('indexname') != idx_name]
        self._vector_hnsw_indexes.append(row)
        return idx_name

    async def ensure_strategy_vector_profile_pgvector_index(self, index_name, index_version, vector_dim, profile_type=None, metric='cosine'):
        if not self.supports_pgvector() or int(vector_dim or 0) <= 0:
            return None
        suffix = profile_type or 'all'
        idx_name = f"idx_svp_pg_hnsw_{self._sanitize_index_part(index_name)}_{self._sanitize_index_part(index_version)}_{int(vector_dim)}_{self._sanitize_index_part(suffix)}_{self._sanitize_index_part(metric)}"
        where_parts = [
            f"index_name = '{index_name}'",
            f"index_version = '{index_version}'",
            f"vector_dim = {int(vector_dim)}",
        ]
        if profile_type:
            where_parts.append(f"profile_type = '{profile_type}'")
        row = {
            'schemaname': 'public',
            'tablename': 'strategy_vector_profile_store',
            'indexname': idx_name,
            'indexdef': f"CREATE INDEX {idx_name} ON strategy_vector_profile_store USING hnsw ((embedding::vector({int(vector_dim)}) vector_cosine_ops)) WHERE {' AND '.join(where_parts)}",
            'index_name': index_name,
            'index_version': index_version,
        }
        self._vector_hnsw_indexes = [item for item in self._vector_hnsw_indexes if item.get('indexname') != idx_name]
        self._vector_hnsw_indexes.append(row)
        return idx_name

    async def list_strategy_vector_hnsw_indexes(self, index_name=None, index_version=None, limit=200):
        rows = list(self._vector_hnsw_indexes)
        if index_name:
            rows = [row for row in rows if row.get('index_name') == index_name or f"'{index_name}'" in str(row.get('indexdef') or '')]
        if index_version:
            rows = [row for row in rows if row.get('index_version') == index_version or f"'{index_version}'" in str(row.get('indexdef') or '')]
        rows.sort(key=lambda row: (str(row.get('tablename') or ''), str(row.get('indexname') or '')))
        return [dict(row) for row in rows[:limit]]

    async def get_strategy_vector_health(self, index_name='strategy_behavior', limit_versions=20, include_hnsw_indexes=False):
        table_flags = {
            'strategy_vector_profiles': True,
            'strategy_vector_profile_store': self.supports_pgvector(),
            'strategy_vector_index_snapshots': True,
            'strategy_vector_index_items': True,
            'strategy_vector_index_item_store': self.supports_pgvector(),
        }
        counts = {
            'profiles': sum(1 for row in self._vector_profiles if (row.get('index_name') or 'strategy_behavior') == index_name),
            'profile_store': sum(1 for row in self._vector_profile_store if row.get('index_name') == index_name),
            'index_snapshots': sum(1 for row in self._vector_index_snapshots if row.get('index_name') == index_name),
            'index_items': sum(1 for row in self._vector_index_items if row.get('index_name') == index_name),
            'index_item_store': sum(1 for row in self._vector_index_item_store if row.get('index_name') == index_name),
        }
        versions = {}
        for row in self._vector_indexes:
            if row.get('index_name') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['registry_status'] = row.get('status')
            item['registry_backend'] = row.get('backend')
            item['sample_count'] = int(row.get('sample_count') or item['sample_count'] or 0)
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        for row in self._vector_index_snapshots:
            if row.get('index_name') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['snapshot_status'] = row.get('status')
            item['snapshot_backend'] = row.get('backend')
            item['profile_count'] = int(row.get('profile_count') or item['profile_count'] or 0)
            item['bucket_count'] = int(row.get('bucket_count') or item['bucket_count'] or 0)
            item['vector_dim'] = int(row.get('vector_dim') or item['vector_dim'] or 0)
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        for row in self._vector_profiles:
            if (row.get('index_name') or 'strategy_behavior') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['profile_rows'] += 1
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        for row in self._vector_profile_store:
            if row.get('index_name') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['profile_store_rows'] += 1
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        for row in self._vector_index_items:
            if row.get('index_name') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['index_item_rows'] += 1
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        for row in self._vector_index_item_store:
            if row.get('index_name') != index_name or not row.get('index_version'):
                continue
            version = row['index_version']
            item = versions.setdefault(version, {
                'index_version': version,
                'last_seen': '',
                'registry_status': None,
                'registry_backend': None,
                'sample_count': 0,
                'snapshot_status': None,
                'snapshot_backend': None,
                'profile_count': 0,
                'bucket_count': 0,
                'vector_dim': 0,
                'profile_rows': 0,
                'profile_store_rows': 0,
                'index_item_rows': 0,
                'index_item_store_rows': 0,
            })
            item['index_item_store_rows'] += 1
            item['last_seen'] = max(item['last_seen'], self._best_timestamp(row))
        latest_snapshot = next((dict(row) for row in sorted(
            [row for row in self._vector_index_snapshots if row.get('index_name') == index_name],
            key=lambda row: (self._best_timestamp(row), str(row.get('index_version') or '')),
            reverse=True,
        )), None)
        latest_snapshot_version = str((latest_snapshot or {}).get('index_version') or '')
        version_rows = [dict(row) for row in versions.values()]

        def _version_sort_key(row):
            priority = 3
            version = str(row.get('index_version') or '')
            if latest_snapshot_version and version == latest_snapshot_version:
                priority = 0
            elif str(row.get('snapshot_status') or '').lower() == 'active':
                priority = 1
            elif str(row.get('registry_status') or '').lower() == 'active':
                priority = 2
            return (priority, -(datetime.fromisoformat(str(row.get('last_seen')).replace('Z', '+00:00')).timestamp() if row.get('last_seen') else 0.0), version)

        version_rows.sort(key=_version_sort_key)
        hnsw_indexes = await self.list_strategy_vector_hnsw_indexes(index_name=index_name, limit=500) if include_hnsw_indexes else []
        return {
            'index_name': index_name,
            'backend': self.get_vector_backend(),
            'pgvector_enabled': self.supports_pgvector(),
            'pgvector_extension': {'extname': 'vector', 'extversion': '0.8.1'} if self.supports_pgvector() else None,
            'tables': table_flags,
            'counts': counts,
            'latest_snapshot': latest_snapshot,
            'versions': [dict(row) for row in version_rows[:limit_versions]],
            'hnsw_indexes': hnsw_indexes,
            'hnsw_index_count': len(hnsw_indexes),
            'recommended_cleanup_versions': [row.get('index_version') for row in version_rows[1:] if row.get('index_version')],
        }

    async def cleanup_strategy_vector_history(self, index_name='strategy_behavior', keep_versions=1, dry_run=True, cleanup_hnsw=True, limit_versions=200, protect_versions=None):
        health = await self.get_strategy_vector_health(index_name=index_name, limit_versions=limit_versions, include_hnsw_indexes=cleanup_hnsw)
        versions = [row for row in list(health.get('versions') or []) if row.get('index_version')]
        latest_snapshot_version = str((health.get('latest_snapshot') or {}).get('index_version') or '').strip()
        keep_total = max(0, int(keep_versions or 0))
        protected = []
        if latest_snapshot_version:
            protected.append(latest_snapshot_version)
        protected_limit = max(keep_total, 1 if latest_snapshot_version else 0)
        for row in versions:
            version = str(row.get('index_version') or '').strip()
            if not version or version in protected:
                continue
            if len(protected) >= protected_limit:
                break
            protected.append(version)
        protected.extend(str(item) for item in list(protect_versions or []) if str(item).strip())
        protected_set = {item for item in protected if item}
        target_versions = [row for row in versions if str(row.get('index_version')) not in protected_set]
        target_set = {str(row.get('index_version')) for row in target_versions if row.get('index_version')}
        hnsw_indexes = list(health.get('hnsw_indexes') or []) if cleanup_hnsw else []
        indexes_to_drop = [row for row in hnsw_indexes if row.get('index_version') in target_set or any(f"'{version}'" in str(row.get('indexdef') or '') for version in target_set)]
        summary = {
            'index_name': index_name,
            'dry_run': bool(dry_run),
            'keep_versions': max(0, int(keep_versions or 0)),
            'protected_versions': sorted(protected_set),
            'target_versions': [row.get('index_version') for row in target_versions],
            'hnsw_indexes_to_drop': [row.get('indexname') for row in indexes_to_drop],
            'deleted': {
                'vector_index_registry': 0,
                'vector_index_snapshots': 0,
                'vector_profiles': 0,
                'vector_profile_store': 0,
                'vector_index_items': 0,
                'vector_index_item_store': 0,
                'hnsw_indexes': 0,
            },
            'version_details': [dict(row) for row in target_versions],
        }
        if dry_run or not target_set:
            return summary

        def _delete_rows(rows, *, key):
            kept = [row for row in rows if not (row.get('index_name') == index_name and row.get('index_version') in target_set)]
            return kept, len(rows) - len(kept)

        self._vector_indexes, summary['deleted']['vector_index_registry'] = _delete_rows(self._vector_indexes, key='index_version')
        self._vector_index_snapshots, summary['deleted']['vector_index_snapshots'] = _delete_rows(self._vector_index_snapshots, key='index_version')
        self._vector_profiles, summary['deleted']['vector_profiles'] = _delete_rows(self._vector_profiles, key='index_version')
        self._vector_profile_store, summary['deleted']['vector_profile_store'] = _delete_rows(self._vector_profile_store, key='index_version')
        self._vector_index_items, summary['deleted']['vector_index_items'] = _delete_rows(self._vector_index_items, key='index_version')
        self._vector_index_item_store, summary['deleted']['vector_index_item_store'] = _delete_rows(self._vector_index_item_store, key='index_version')
        if cleanup_hnsw:
            kept_indexes = [
                row for row in self._vector_hnsw_indexes
                if not (row.get('index_name') == index_name and (row.get('index_version') in target_set or any(f"'{version}'" in str(row.get('indexdef') or '') for version in target_set)))
            ]
            summary['deleted']['hnsw_indexes'] = len(self._vector_hnsw_indexes) - len(kept_indexes)
            self._vector_hnsw_indexes = kept_indexes
        return summary

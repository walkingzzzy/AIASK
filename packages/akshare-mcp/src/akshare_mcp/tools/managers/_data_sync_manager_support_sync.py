"""数据同步管理器 - MCP 工具层，供用户/AI 按需触发同步任务。

与 DataSyncScheduler (services/data_sync_scheduler.py) 的区别：
- DataSyncScheduler 是后台自动调度器（启动时 + 每日 15:30）
- 本模块是 MCP 工具，通过 ``data_sync_manager(action=...)`` 按需执行
- sync_daily/sync_init.py 是独立脚本，用于深度历史全量回填
"""

from typing import Any
import argparse
import contextlib
import importlib.util
import json
import logging
from io import StringIO
from pathlib import Path
from datetime import datetime, timedelta
from ...storage import get_db
from ...utils import ok, fail
from ..manager_protocol import normalize_manager_payload

logger = logging.getLogger(__name__)

async def _sync_klines_now(codes: list) -> dict:
    """立即执行K线同步，使用 data_source.get_kline() 完整降级链"""
    from ...data_source import data_source
    from ...storage import get_db

    db = get_db()
    results = {'success': 0, 'failed': 0, 'errors': []}

    for code in codes:
        try:
            klines = data_source.get_kline(code, 'daily', 250)
            if klines:
                try:
                    await db.save_klines(code, klines)
                except Exception as e:
                    logger.warning(f"[DataSyncManager] {code} K线写入DB失败: {e}")
                results['success'] += 1
            else:
                results['failed'] += 1
                results['errors'].append(f"{code}: 所有数据源均无数据")
        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"{code}: {e}")

    # 截断错误列表避免过长
    if len(results['errors']) > 10:
        total = len(results['errors'])
        results['errors'] = results['errors'][:10] + [f'...及其他 {total - 10} 个错误']

    return results

async def _sync_financials_check(codes: list) -> dict:
    """检查财务数据是否存在，不存在则提示用户运行 sync_init.py"""
    from ...storage import get_db

    db = get_db()
    results = {'success': 0, 'failed': 0, 'errors': [], 'message': ''}

    missing = []
    for code in codes:
        try:
            async with db.acquire() as conn:
                cnt = await conn.fetchval(
                    "SELECT COUNT(*) FROM financials WHERE stock_code = $1", code
                )
                if cnt and cnt > 0:
                    results['success'] += 1
                else:
                    missing.append(code)
                    results['failed'] += 1
        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"{code}: {e}")

    if missing:
        results['message'] = (
            f'{len(missing)} 只股票无财务数据，'
            f'建议运行 python sync_init.py 进行历史数据初始化'
        )

    return results

async def _sync_core_market_now(kwargs: dict) -> dict:
    """调用核心市场审查补数脚本，补齐指数/北向/融资融券数据。"""
    script_path = _core_market_script_path()
    if not script_path.exists():
        return {'success': 0, 'failed': 1, 'errors': [f'脚本不存在: {script_path}']}

    spec = importlib.util.spec_from_file_location("audit_sync_core_market_data_runtime", script_path)
    if spec is None or spec.loader is None:
        return {'success': 0, 'failed': 1, 'errors': [f'无法加载脚本: {script_path}']}

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    args = argparse.Namespace(
        years=max(int(kwargs.get('years', 1) or 1), 1),
        stock_codes=",".join([str(item).strip() for item in list(kwargs.get('codes') or kwargs.get('stock_codes') or []) if str(item).strip()])
        if isinstance(kwargs.get('codes') or kwargs.get('stock_codes'), list)
        else str(kwargs.get('stock_codes') or kwargs.get('codes') or ",".join(getattr(module, 'DEFAULT_STOCK_CODES', []))),
        calendar_year=int(kwargs.get('calendar_year') or datetime.now().year),
        north_days=max(int(kwargs.get('north_days', 365) or 365), 1),
        margin_days=max(int(kwargs.get('margin_days', 90) or 90), 1),
    )

    capture = StringIO()
    exit_code = 1
    with contextlib.redirect_stdout(capture):
        exit_code = await module._main(args)

    db = get_db()
    market_aux = await _load_market_aux_status(db)
    output_lines = [line for line in capture.getvalue().splitlines() if line.strip()]
    tail_lines = output_lines[-40:]
    result = {
        'success': 1 if exit_code == 0 else 0,
        'failed': 0 if exit_code == 0 else 1,
        'errors': [] if exit_code == 0 else [f'core_market_sync exit_code={exit_code}'],
        'exit_code': int(exit_code),
        'args': {
            'years': args.years,
            'stock_codes': args.stock_codes,
            'calendar_year': args.calendar_year,
            'north_days': args.north_days,
            'margin_days': args.margin_days,
        },
        'market_aux': market_aux,
        'stdout_tail': tail_lines,
    }
    return result

async def _sync_factor_context_now(kwargs: dict) -> dict:
    """调用因子上下文补数脚本，补齐新闻/公告/研报/个股资金流。"""
    script_path = _factor_context_script_path()
    if not script_path.exists():
        return {'success': 0, 'failed': 1, 'errors': [f'脚本不存在: {script_path}']}

    spec = importlib.util.spec_from_file_location("audit_sync_factor_context_runtime", script_path)
    if spec is None or spec.loader is None:
        return {'success': 0, 'failed': 1, 'errors': [f'无法加载脚本: {script_path}']}

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    raw_codes = kwargs.get('codes') or kwargs.get('stock_codes')
    args = argparse.Namespace(
        codes=",".join([str(item).strip() for item in list(raw_codes) if str(item).strip()]) if isinstance(raw_codes, list) else str(raw_codes or ""),
        scope_sources=str(kwargs.get('scope_sources') or "explicit,representative,active_pool,factory_targets"),
        active_pool_limit=max(int(kwargs.get('active_pool_limit', 12) or 12), 1),
        task_run_limit=max(int(kwargs.get('task_run_limit', 50) or 50), 1),
        news_days=max(int(kwargs.get('news_days', 30) or 30), 1),
        notice_days=max(int(kwargs.get('notice_days', 30) or 30), 1),
        item_limit=max(int(kwargs.get('item_limit', 10) or 10), 1),
    )

    capture = StringIO()
    exit_code = 1
    with contextlib.redirect_stdout(capture):
        exit_code = await module._main(args)

    db = get_db()
    market_aux = await _load_market_aux_status(db)
    output_lines = [line for line in capture.getvalue().splitlines() if line.strip()]
    tail_lines = output_lines[-40:]
    return {
        'success': 1 if exit_code == 0 else 0,
        'failed': 0 if exit_code == 0 else 1,
        'errors': [] if exit_code == 0 else [f'factor_context_sync exit_code={exit_code}'],
        'exit_code': int(exit_code),
        'args': {
            'codes': args.codes,
            'scope_sources': args.scope_sources,
            'active_pool_limit': args.active_pool_limit,
            'task_run_limit': args.task_run_limit,
            'news_days': args.news_days,
            'notice_days': args.notice_days,
            'item_limit': args.item_limit,
        },
        'market_aux': market_aux,
        'stdout_tail': tail_lines,
    }

async def _maybe_build_backfill_snapshot(
    db,
    *,
    kwargs: dict,
    collection_name: str,
    version: str | None,
    source: str,
) -> dict | None:
    if not _as_bool(kwargs.get('build_snapshot', False), False):
        return None
    if _as_bool(kwargs.get('dry_run', False), False):
        return {
            'collection_name': collection_name,
            'profile_version': str(version or '').strip() or None,
            'index_version': str(kwargs.get('index_version') or '').strip() or None,
            'status': 'skipped',
            'reason': 'dry_run',
        }

    from ...services.unified_vector_governance import build_vector_collection_snapshot

    return await build_vector_collection_snapshot(
        db,
        collection_name=collection_name,
        version=str(version or '').strip() or None,
        index_version=str(kwargs.get('index_version') or '').strip() or None,
        activate=_as_bool(kwargs.get('activate_snapshot', True), True),
        source=source,
    )

async def _sync_vector_backfill_market_docs_now(kwargs: dict) -> dict:
    """回填历史市场文本到统一向量层。"""
    from ...services.vector_backfill import backfill_market_document_vectors

    db = get_db()
    result = await backfill_market_document_vectors(
        db,
        stock_codes=kwargs.get('stock_codes') or kwargs.get('codes'),
        doc_types=kwargs.get('doc_types'),
        start_date=kwargs.get('start_date'),
        end_date=kwargs.get('end_date'),
        limit=kwargs.get('limit', 500),
        batch_size=kwargs.get('batch_size', 100),
        embed=kwargs.get('embed', True),
        chunk_size=kwargs.get('chunk_size', 800),
        overlap=kwargs.get('overlap', 120),
        version=kwargs.get('version', 'v1'),
        rebuild_existing=kwargs.get('rebuild_existing', False),
        dry_run=kwargs.get('dry_run', False),
        include_legacy_research_docs=kwargs.get('include_legacy_research_docs', False),
    )
    snapshot = await _maybe_build_backfill_snapshot(
        db,
        kwargs=kwargs,
        collection_name='market_doc_chunks',
        version=result.get('version') or kwargs.get('version') or 'v1',
        source='data_sync_manager.vector_backfill_market_docs',
    )
    market_aux = await _load_market_aux_status(db)
    return {
        'success': 1,
        'failed': 0,
        'errors': [],
        'args': {
            'stock_codes': result.get('stock_codes'),
            'doc_types': result.get('doc_types'),
            'start_date': result.get('start_date'),
            'end_date': result.get('end_date'),
            'limit': result.get('limit'),
            'batch_size': result.get('batch_size'),
            'embed': result.get('embed'),
            'chunk_size': result.get('chunk_size'),
            'overlap': result.get('overlap'),
            'version': result.get('version'),
            'rebuild_existing': result.get('rebuild_existing'),
            'dry_run': result.get('dry_run'),
            'include_legacy_research_docs': result.get('include_legacy_research_docs'),
            'build_snapshot': _as_bool(kwargs.get('build_snapshot', False), False),
            'activate_snapshot': _as_bool(kwargs.get('activate_snapshot', True), True),
            'index_version': (snapshot or {}).get('index_version') or kwargs.get('index_version'),
        },
        'backfill': result,
        'snapshot': snapshot,
        'market_aux': market_aux,
        'message': (
            f"market_doc_backfill docs={int(result.get('saved_docs') or 0)} "
            f"chunks={int(result.get('saved_chunks') or 0)} "
            f"embedded={int(result.get('embedded_chunks') or 0)}"
            + (f" snapshot={snapshot.get('status')}" if snapshot else "")
        ),
    }

async def _sync_vector_backfill_kline_patterns_now(kwargs: dict) -> dict:
    """回填 K 线模式窗口到统一向量层。"""
    from ...services.pattern_embedding_pipeline import backfill_kline_pattern_vectors

    db = get_db()
    result = await backfill_kline_pattern_vectors(
        db,
        stock_codes=kwargs.get('stock_codes') or kwargs.get('codes'),
        code_limit=kwargs.get('code_limit', 200),
        window_size=kwargs.get('window_size', kwargs.get('days', 20)),
        lookback_days=kwargs.get('lookback_days', 180),
        max_windows_per_code=kwargs.get('max_windows_per_code', 1),
        step_days=kwargs.get('step_days', 5),
        vector_method=kwargs.get('vector_method', 'returns'),
        period=kwargs.get('period', 'daily'),
        adjust=kwargs.get('adjust', ''),
        version=kwargs.get('version', 'v1'),
        rebuild_existing=kwargs.get('rebuild_existing', False),
        dry_run=kwargs.get('dry_run', False),
    )
    snapshot = await _maybe_build_backfill_snapshot(
        db,
        kwargs=kwargs,
        collection_name='kline_pattern_embeddings',
        version=result.get('version') or kwargs.get('version'),
        source='data_sync_manager.vector_backfill_kline_patterns',
    )
    market_aux = await _load_market_aux_status(db)
    return {
        'success': 1,
        'failed': 0,
        'errors': [],
        'args': {
            'stock_codes': result.get('stock_codes'),
            'code_limit': kwargs.get('code_limit', 200),
            'window_size': result.get('window_size'),
            'lookback_days': result.get('lookback_days'),
            'max_windows_per_code': result.get('max_windows_per_code'),
            'step_days': result.get('step_days'),
            'vector_method': result.get('vector_method'),
            'period': result.get('period'),
            'adjust': result.get('adjust'),
            'version': result.get('version'),
            'rebuild_existing': result.get('rebuild_existing'),
            'dry_run': result.get('dry_run'),
            'build_snapshot': _as_bool(kwargs.get('build_snapshot', False), False),
            'activate_snapshot': _as_bool(kwargs.get('activate_snapshot', True), True),
            'index_version': (snapshot or {}).get('index_version') or kwargs.get('index_version'),
        },
        'backfill': result,
        'snapshot': snapshot,
        'market_aux': market_aux,
        'message': (
            f"kline_pattern_backfill windows={int(result.get('saved_windows') or 0)} "
            f"profiles={int(result.get('saved_profiles') or 0)}"
            + (f" snapshot={snapshot.get('status')}" if snapshot else "")
        ),
    }

async def _sync_vector_backfill_stock_profiles_now(kwargs: dict) -> dict:
    """回填股票画像向量到统一向量层。"""
    from ...services.stock_profile_pipeline import backfill_stock_profile_vectors

    db = get_db()
    result = await backfill_stock_profile_vectors(
        db,
        stock_codes=kwargs.get('stock_codes') or kwargs.get('codes'),
        code_limit=kwargs.get('code_limit', 200),
        profile_types=kwargs.get('profile_types') or kwargs.get('similarity_types'),
        kline_limit=kwargs.get('kline_limit', 90),
        version=kwargs.get('version', 'v1'),
        rebuild_existing=kwargs.get('rebuild_existing', False),
        dry_run=kwargs.get('dry_run', False),
    )
    # 股票画像 collection 会同时承载多种 profile_type，自动快照默认按 collection+version 整体构建。
    snapshot = await _maybe_build_backfill_snapshot(
        db,
        kwargs=kwargs,
        collection_name='stock_profile_embeddings',
        version=result.get('version') or kwargs.get('version'),
        source='data_sync_manager.vector_backfill_stock_profiles',
    )
    market_aux = await _load_market_aux_status(db)
    return {
        'success': 1,
        'failed': 0,
        'errors': [],
        'args': {
            'stock_codes': result.get('stock_codes'),
            'code_limit': kwargs.get('code_limit', 200),
            'profile_types': result.get('profile_types'),
            'kline_limit': result.get('kline_limit'),
            'version': result.get('version'),
            'rebuild_existing': result.get('rebuild_existing'),
            'dry_run': result.get('dry_run'),
            'build_snapshot': _as_bool(kwargs.get('build_snapshot', False), False),
            'activate_snapshot': _as_bool(kwargs.get('activate_snapshot', True), True),
            'index_version': (snapshot or {}).get('index_version') or kwargs.get('index_version'),
        },
        'backfill': result,
        'snapshot': snapshot,
        'market_aux': market_aux,
        'message': (
            f"stock_profile_backfill profiles={int(result.get('saved_profiles') or 0)} "
            f"codes={int(result.get('processed_codes') or 0)}"
            + (f" snapshot={snapshot.get('status')}" if snapshot else "")
        ),
    }

async def _sync_vector_backfill_factor_candidates_now(kwargs: dict) -> dict:
    """回填因子研究记忆向量到统一向量层。"""
    from ...services.factor_candidate_vector_backfill import backfill_factor_candidate_vectors

    db = get_db()
    result = await backfill_factor_candidate_vectors(
        db,
        limit=kwargs.get('limit', 200),
        codes=kwargs.get('codes') or kwargs.get('stock_codes'),
        status=kwargs.get('status'),
        family=kwargs.get('family'),
        version=kwargs.get('version', 'v1'),
        rebuild_existing=kwargs.get('rebuild_existing', False),
        dry_run=kwargs.get('dry_run', False),
    )
    snapshot = await _maybe_build_backfill_snapshot(
        db,
        kwargs=kwargs,
        collection_name='factor_candidate_embeddings',
        version=result.get('version') or kwargs.get('version'),
        source='data_sync_manager.vector_backfill_factor_candidates',
    )
    market_aux = await _load_market_aux_status(db)
    return {
        'success': 1,
        'failed': 0,
        'errors': [],
        'args': {
            'limit': result.get('limit'),
            'codes': result.get('codes'),
            'status': result.get('status'),
            'family': result.get('family'),
            'version': result.get('version'),
            'rebuild_existing': result.get('rebuild_existing'),
            'dry_run': result.get('dry_run'),
            'build_snapshot': _as_bool(kwargs.get('build_snapshot', False), False),
            'activate_snapshot': _as_bool(kwargs.get('activate_snapshot', True), True),
            'index_version': (snapshot or {}).get('index_version') or kwargs.get('index_version'),
        },
        'backfill': result,
        'snapshot': snapshot,
        'market_aux': market_aux,
        'message': (
            f"factor_candidate_backfill profiles={int(result.get('saved_profiles') or 0)} "
            f"records={int(result.get('processed_records') or 0)}"
            + (f" snapshot={snapshot.get('status')}" if snapshot else "")
        ),
    }

async def _sync_vector_build_snapshot_now(kwargs: dict) -> dict:
    """构建统一向量 collection 的 snapshot 与 ANN 索引。"""
    from ...services.unified_vector_governance import build_vector_collection_snapshot

    db = get_db()
    collection_name = str(kwargs.get('collection_name') or kwargs.get('collection') or '').strip()
    if not collection_name:
        return {'success': 0, 'failed': 1, 'errors': ['缺少 collection_name']}

    result = await build_vector_collection_snapshot(
        db,
        collection_name=collection_name,
        version=kwargs.get('version'),
        index_version=kwargs.get('index_version'),
        profile_type=kwargs.get('profile_type'),
        limit_profiles=kwargs.get('limit_profiles', 5000),
        bucket_count=kwargs.get('bucket_count'),
        activate=kwargs.get('activate', True),
        source='data_sync_manager',
    )
    market_aux = await _load_market_aux_status(db)
    return {
        'success': 1 if str(result.get('status') or '').strip().lower() != 'failed' else 0,
        'failed': 0 if str(result.get('status') or '').strip().lower() != 'failed' else 1,
        'errors': [] if str(result.get('status') or '').strip().lower() != 'failed' else [f"vector_build_snapshot failed for {collection_name}"],
        'args': {
            'collection_name': collection_name,
            'profile_type': result.get('profile_type'),
            'version': result.get('profile_version'),
            'index_version': result.get('index_version'),
            'limit_profiles': kwargs.get('limit_profiles', 5000),
            'bucket_count': result.get('bucket_count'),
            'activate': kwargs.get('activate', True),
        },
        'snapshot': result,
        'market_aux': market_aux,
        'message': (
            f"vector_build_snapshot collection={collection_name} "
            f"status={result.get('status')} items={int(result.get('items_count') or 0)}"
        ),
    }

async def _sync_vector_benchmark_collection_now(kwargs: dict) -> dict:
    """运行统一向量 collection 的 exact-vs-ANN 检索基线评测。"""
    from ...services.unified_vector_benchmark import benchmark_vector_collection_search

    db = get_db()
    collection_name = str(kwargs.get('collection_name') or kwargs.get('collection') or '').strip()
    if not collection_name:
        return {'success': 0, 'failed': 1, 'errors': ['缺少 collection_name']}

    result = await benchmark_vector_collection_search(
        db,
        collection_name=collection_name,
        profile_type=kwargs.get('profile_type'),
        version=kwargs.get('version'),
        index_version=kwargs.get('index_version'),
        sample_size=kwargs.get('sample_size', 30),
        top_k=kwargs.get('top_k', 10),
        limit_profiles=kwargs.get('limit_profiles', 5000),
        metric=kwargs.get('metric', 'cosine'),
        persist_snapshot_metrics=kwargs.get('persist_snapshot_metrics', True),
    )
    market_aux = await _load_market_aux_status(db)
    retrieval_quality = dict(result.get('retrieval_quality') or {})
    latency_ms = dict(result.get('latency_ms') or {})
    return {
        'success': 1 if str(result.get('status') or '').strip().lower() != 'failed' else 0,
        'failed': 0 if str(result.get('status') or '').strip().lower() != 'failed' else 1,
        'errors': [] if str(result.get('status') or '').strip().lower() != 'failed' else [f"vector_benchmark_collection failed for {collection_name}"],
        'args': {
            'collection_name': collection_name,
            'profile_type': result.get('profile_type'),
            'version': result.get('profile_version'),
            'index_version': result.get('index_version'),
            'sample_size': kwargs.get('sample_size', 30),
            'top_k': kwargs.get('top_k', 10),
            'limit_profiles': kwargs.get('limit_profiles', 5000),
            'metric': kwargs.get('metric', 'cosine'),
            'persist_snapshot_metrics': _as_bool(kwargs.get('persist_snapshot_metrics', True), True),
        },
        'benchmark': result,
        'market_aux': market_aux,
        'message': (
            f"vector_benchmark collection={collection_name} "
            f"recall@k={retrieval_quality.get('recall_at_k')} "
            f"ann_p95={latency_ms.get('ann_p95')} "
            f"persisted={result.get('benchmark_persisted')}"
        ),
    }

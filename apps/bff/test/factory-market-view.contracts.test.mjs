import test from 'node:test';
import assert from 'node:assert/strict';

const { buildFactoryMarketViewResponse } = await import('../dist/strategy/strategy.service.factory-market-view.js');

test('buildFactoryMarketViewResponse aggregates factory artifacts into a stable market DTO', () => {
  const response = buildFactoryMarketViewResponse({
    capabilities: {
      ai_generation: true,
      quality_governance: true,
      actor_permissions: {
        can_run_factory: true,
        can_ai_generate: true,
      },
    },
    status: {
      running: false,
      last_run: '2026-04-22T10:00:00Z',
      research_window: {
        available: true,
        loaded_stock_count: 5200,
        planned_bulk_task_count: 320,
        selected_bulk_task_count: 20,
        effective_task_budget: 20,
        next_task_offset: 20,
      },
      full_market_topn: {
        available: true,
        snapshot_id: 'fmt_2026_04_22',
        run_id: 'factory_run_20260422',
        as_of_date: '2026-04-22',
        topn_n: 20,
        score_row_count: 5100,
        score_quality: 'healthy',
        portfolio_candidate_id: 'factory_topn_20260422',
        constituents: [{ code: '600000', name: '浦发银行', rank: 1 }],
      },
      last_summary: {
        candidates_spawned: 18,
        passed_quality_gate: 6,
        snapshot_completion_ratio: 0.95,
        snapshot_failure_reason_count: 1,
        snapshot_degraded: false,
      },
    },
    snapshot: {
      snapshot_date: '2026-04-22',
      degraded: false,
      failure_reasons: ['missing_runtime_metric'],
      completeness: { completion_ratio: 0.95 },
    },
    runs: {
      dto_version: 'strategy_market.factory_runs.v2',
      latest: {
        run_id: 'factory_run_20260422',
        status: 'success',
        completed_at: '2026-04-22T10:03:00Z',
        summary: {
          candidates_spawned: 18,
          passed_quality_gate: 6,
        },
      },
      items: [
        {
          run_id: 'factory_run_20260422',
          status: 'success',
          completed_at: '2026-04-22T10:03:00Z',
          summary: {
            candidates_spawned: 18,
            passed_quality_gate: 6,
          },
        },
        {
          run_id: 'factory_run_20260421',
          status: 'failed',
          completed_at: '2026-04-21T10:03:00Z',
          summary: {
            candidates_spawned: 10,
            passed_quality_gate: 0,
          },
        },
      ],
      count: 2,
    },
    observability: {
      overview: {
        active_factor_count: 7,
        governed_factor_count: 5,
        blocked_factor_count: 1,
        scheduler_quality_status: 'healthy',
        retrain_plan_count: 2,
        retrain_pending_count: 1,
      },
      factor_governance: {
        registry_summary: {
          governed_active_count: 5,
          blocked_count: 1,
        },
        active_pool: {
          count: 7,
          family_summary: [{ family: 'momentum', count: 3 }],
        },
        retrain_summary: {
          count: 2,
          status_counts: { planned: 1, running: 1 },
        },
        retrain_queue: [{ family: 'momentum', status: 'planned', priority: 'high' }],
      },
      degraded: false,
      errors: [],
    },
    expandedRun: {
      dto_version: 'strategy_market.factory_run.v2',
      run_id: 'factory_run_20260422',
      summary: {
        candidates_spawned: 18,
      },
      stages: {},
      pipeline: {},
    },
    selectedRunId: 'factory_run_20260422',
    sectionErrors: {},
  });

  assert.equal(response.dto_version, 'strategy_market.factory_market_view.v1');
  assert.equal(response.status?.full_market_topn?.snapshot_id, 'fmt_2026_04_22');
  assert.equal(response.surface?.snapshot_completion_ratio, 0.95);
  assert.equal(response.surface?.failed_run_count, 1);
  assert.equal(response.surface?.hero_cards?.[0]?.value, '2');
  assert.equal(response.surface?.observability_cards?.[1]?.value, '7');

  const outputKinds = (response.surface?.visible_outputs ?? []).map((item) => item.kind);
  assert.deepEqual(outputKinds, [
    'factory_run',
    'research_window',
    'full_market_topn',
    'portfolio_candidate',
    'governance_registry',
    'retrain_queue',
  ]);
  assert.equal(
    response.surface?.visible_outputs?.find((item) => item.kind === 'portfolio_candidate')?.href,
    '/strategy-market/factory_topn_20260422',
  );
});

test('buildFactoryMarketViewResponse preserves section errors and degraded state', () => {
  const response = buildFactoryMarketViewResponse({
    capabilities: null,
    status: null,
    snapshot: null,
    runs: { items: [], count: 0 },
    observability: null,
    expandedRun: null,
    sectionErrors: {
      status: 'factory status unavailable',
      observability: 'observability timeout',
    },
  });

  assert.equal(response.degraded, true);
  assert.equal(response.section_errors?.status, 'factory status unavailable');
  assert.equal(response.section_errors?.observability, 'observability timeout');
  assert.deepEqual(response.errors, ['factory status unavailable', 'observability timeout']);
  assert.deepEqual(response.surface?.visible_outputs, []);
});

test('buildFactoryMarketViewResponse falls back to runs and topn market views when status is unavailable', () => {
  const response = buildFactoryMarketViewResponse({
    capabilities: null,
    status: null,
    snapshot: null,
    runs: {
      items: [
        {
          run_id: 'factory_run_20260423',
          status: 'skipped',
          completed_at: '2026-04-23T08:15:00Z',
          summary: {
            skip_reason: 'readiness_blocked',
            research_window: {
              available: true,
              loaded_stock_count: 5505,
              planned_bulk_task_count: 12509,
              selected_bulk_task_count: 9,
              effective_task_budget: 20,
              next_task_offset: 280,
            },
          },
        },
      ],
      count: 1,
    },
    topnLatest: {
      available: true,
      score_row_count: 5167,
      snapshot: {
        available: true,
        snapshot_id: 'fmt_factory_run_1776870842_ea76e8cb',
        run_id: 'factory_run_1776870842_ea76e8cb',
        as_of_date: '2026-04-22',
        topn_n: 20,
        score_quality: 'healthy',
        portfolio_candidate_id: 'factory_topn_factory_run_1776870842_ea76e8cb',
        constituents: [{ code: '000063', name: '中兴通讯', rank: 1 }],
      },
    },
    observability: null,
    expandedRun: null,
    sectionErrors: {
      status: 'factory status timed out after 3500ms',
    },
  });

  assert.equal(response.status?.last_result?.status, 'skipped');
  assert.equal(response.status?.research_window?.loaded_stock_count, 5505);
  assert.equal(response.status?.full_market_topn?.snapshot_id, 'fmt_factory_run_1776870842_ea76e8cb');
  assert.equal(response.status?.full_market_topn?.score_row_count, 5167);
  assert.equal(response.surface?.visible_outputs?.some((item) => item.kind === 'full_market_topn'), true);
  assert.equal(response.surface?.visible_outputs?.some((item) => item.kind === 'portfolio_candidate'), true);
});

test('buildFactoryMarketViewResponse backfills research, governance, and empty retrain queue from persisted surfaces', () => {
  const response = buildFactoryMarketViewResponse({
    capabilities: null,
    status: null,
    snapshot: null,
    runs: {
      items: [
        {
          run_id: 'factory_run_20260423',
          status: 'skipped',
          completed_at: '2026-04-23T08:15:00Z',
          summary: {
            governed_candidate_pool_active: true,
            active_candidate_count: 11,
            governed_source_candidate_count: 80,
            governed_pending_candidate_count: 23,
            governed_blocked_ratio: 0.2125,
            governed_pending_ratio: 0.2875,
            governed_candidate_pool_runtime_state: 'governed_pool_active',
            scheduler_slo: {
              status: 'warning',
            },
          },
        },
      ],
      count: 1,
    },
    researchSurface: {
      available: true,
      run: {
        run_id: 'factory_run_20260422',
        status: 'success',
        completed_at: '2026-04-22T10:03:00Z',
      },
      research_window: {
        available: true,
        loaded_stock_count: 5505,
        planned_bulk_task_count: 12509,
        selected_bulk_task_count: 20,
        effective_task_budget: 20,
        next_task_offset: 280,
      },
    },
    topnLatest: {
      available: true,
      score_row_count: 5167,
      snapshot: {
        available: true,
        snapshot_id: 'fmt_factory_run_1776870842_ea76e8cb',
        run_id: 'factory_run_20260422',
        as_of_date: '2026-04-22',
        topn_n: 20,
        score_quality: 'healthy',
        portfolio_candidate_id: 'factory_topn_factory_run_20260422',
      },
    },
    retrainSurface: {
      loaded: true,
      summary: {
        count: 0,
        status_counts: {},
      },
      items: [],
    },
    observability: null,
    expandedRun: null,
    sectionErrors: {
      status: 'factory status timed out after 3500ms',
      observability: 'factory observability timed out after 5000ms',
    },
  });

  assert.equal(response.status?.research_window?.loaded_stock_count, 5505);
  assert.equal(response.surface?.visible_outputs?.some((item) => item.kind === 'research_window'), true);
  assert.equal(response.surface?.visible_outputs?.some((item) => item.kind === 'governance_registry'), true);
  assert.equal(response.surface?.visible_outputs?.some((item) => item.kind === 'retrain_queue'), true);
  assert.match(
    response.surface?.visible_outputs?.find((item) => item.kind === 'governance_registry')?.summary ?? '',
    /活跃候选 11，待治理 23，阻断 17/,
  );
  assert.equal(
    response.surface?.visible_outputs?.find((item) => item.kind === 'retrain_queue')?.status,
    'empty',
  );
});

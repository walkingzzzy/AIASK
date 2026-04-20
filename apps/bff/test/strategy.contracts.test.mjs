import test from 'node:test';
import assert from 'node:assert/strict';

const { normalizeStrategyDetailResponse } = await import('../dist/strategy/strategy.service.shared.js');

test('normalizeStrategyDetailResponse wraps raw detail payload into a stable DTO', () => {
  const detail = normalizeStrategyDetailResponse({
    id: 'strat_demo',
    name: 'Demo Strategy',
    status: 'incubating',
    metrics: [{ period: 'all', total_return: 0.12 }],
    reviews: [{ user_id: 'alice', rating: 5 }],
    nav_series: [1, '1.02', null, 1.05],
    latest_quality_report: { report_type: 'submission', summary: { validation_grade: 'B' } },
    incubation_overview: { promotion_ready: true, total_signals: 8 },
    runtime_alerts: [{ alert_id: 1, status: 'open' }],
    open_risk_events: [{ id: 2, status: 'open' }],
    vector_profiles: [{ id: 3, profile_type: 'behavior' }],
    similar_vector_profiles: [{ id: 4, strategy_id: 'peer_1' }],
    domain_events: [{ id: 5, event_type: 'status_change' }],
    task_runs: [{ id: 6, task_name: 'projection_rebuild' }],
  });

  assert.equal(detail.dto_version, 'strategy_market.detail.v2');
  assert.equal(detail.strategy?.id, 'strat_demo');
  assert.equal(detail.metrics?.length, 1);
  assert.equal(detail.reviews?.length, 1);
  assert.deepEqual(detail.nav_series, [1, 1.02, 1.05]);
  assert.equal(detail.view_model?.quality?.latest_report?.summary?.validation_grade, 'B');
  assert.equal(detail.view_model?.incubation?.overview?.promotion_ready, true);
  assert.equal(detail.view_model?.runtime?.alerts?.length, 1);
  assert.equal(detail.view_model?.runtime?.risk_events?.length, 1);
  assert.equal(detail.view_model?.vectors?.profiles?.length, 1);
  assert.equal(detail.view_model?.vectors?.similar_profiles?.length, 1);
  assert.equal(detail.view_model?.domain?.events?.length, 1);
  assert.equal(detail.view_model?.domain?.task_runs?.length, 1);
});

test('normalizeStrategyDetailResponse keeps wrapped strategy payloads and fills missing arrays', () => {
  const detail = normalizeStrategyDetailResponse({
    strategy: { id: 'wrapped_demo', name: 'Wrapped Demo' },
    view_model: {
      runtime: {
        alerts: [{ alert_id: 7, status: 'acknowledged' }],
      },
    },
  });

  assert.equal(detail.strategy?.id, 'wrapped_demo');
  assert.deepEqual(detail.metrics, []);
  assert.deepEqual(detail.reviews, []);
  assert.deepEqual(detail.nav_series, []);
  assert.equal(detail.runtime_alerts?.length, 1);
  assert.equal(detail.view_model?.runtime?.alerts?.[0]?.alert_id, 7);
});

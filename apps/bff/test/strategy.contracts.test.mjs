import test from 'node:test';
import assert from 'node:assert/strict';

const { normalizeStrategyDetailResponse } = await import('../dist/strategy/strategy.service.shared.js');
const { StrategyMarketService } = await import('../dist/strategy/strategy.service.js');

test('normalizeStrategyDetailResponse wraps raw detail payload into a stable DTO', () => {
  const detail = normalizeStrategyDetailResponse({
    id: 'strat_demo',
    name: 'Demo Strategy',
    status: 'incubating',
    subscriber_count: 7,
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
  assert.equal(detail.strategy?.favorite_count, 7);
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

test('normalizeStrategyDetailResponse carries BFF runtime action contracts', () => {
  const detail = normalizeStrategyDetailResponse({
    strategy: { id: 'action_demo', name: 'Action Demo' },
    runtime_action_contract: {
      dto_version: 'strategy_market.runtime_actions.v1',
      strategy_id: 'action_demo',
      generated_at: '2026-04-24T00:00:00.000Z',
      source: 'bff.strategy_market.runtime_action_contract',
      actor: { authenticated: false },
      state: { editable: false },
      default_order: ['view_factory_source'],
      actions: [
        {
          id: 'view_factory_source',
          label: '查看工厂来源',
          status: 'clickable',
          enabled: true,
          requires_confirmation: false,
          effect: 'navigation',
          navigation: { href: '/strategy-market/action_demo?tab=factory' },
        },
      ],
      summary: { executable_now: ['view_factory_source'], blocked: [] },
    },
  });

  assert.equal(detail.runtime_action_contract?.dto_version, 'strategy_market.runtime_actions.v1');
  assert.equal(detail.runtime_actions?.[0]?.id, 'view_factory_source');
  assert.equal(detail.view_model?.actions?.items?.[0]?.status, 'clickable');
});

test('StrategyMarketService runtime action contract blocks anonymous mutations and exposes readonly actions', () => {
  const service = new StrategyMarketService({}, {}, {}, {});
  const contract = service.buildRuntimeActionContract({
    strategy: { id: 'strat_public', name: 'Public Strategy', status: 'listed', tags: [] },
    actor: { userId: null, role: 'user' },
    ownerState: { editable: false, personal_strategy: false },
    favoriteState: { available: false, favorited: false },
    paperSessionState: { available: false, has_session: false },
  });

  const actions = Object.fromEntries(contract.actions.map((action) => [action.id, action]));
  assert.equal(actions.save_as_personal_strategy.status, 'unavailable');
  assert.match(actions.save_as_personal_strategy.unavailable_reason, /登录/);
  assert.equal(actions.open_personal_paper_session.status, 'unavailable');
  assert.equal(actions.view_factory_source.status, 'clickable');
  assert.equal(actions.ai_analyze_strategy.status, 'clickable');
  assert.equal(actions.ai_modify_personal_strategy.status, 'unavailable');
});

test('StrategyMarketService runtime action contract requires confirmation for stateful personal actions', () => {
  const service = new StrategyMarketService({}, {}, {}, {});
  const marketContract = service.buildRuntimeActionContract({
    strategy: { id: 'strat_market', name: 'Market Strategy', status: 'listed', author_id: 'factory' },
    actor: { userId: 'alice', role: 'user' },
    ownerState: { editable: false, personal_strategy: false, owned: false },
    favoriteState: { available: true, favorited: false },
    paperSessionState: { available: true, has_session: false },
  });
  const marketActions = Object.fromEntries(marketContract.actions.map((action) => [action.id, action]));
  assert.equal(marketActions.save_as_personal_strategy.status, 'confirm_required');
  assert.equal(marketActions.open_personal_paper_session.status, 'confirm_required');
  assert.equal(marketActions.ai_modify_personal_strategy.status, 'unavailable');
  assert.match(marketActions.ai_modify_personal_strategy.unavailable_reason, /市场策略/);

  const personalContract = service.buildRuntimeActionContract({
    strategy: {
      id: 'strat_personal',
      name: 'Personal Strategy',
      status: 'draft',
      author_id: 'alice',
      tags: ['personal_strategy'],
    },
    actor: { userId: 'alice', role: 'user' },
    ownerState: { editable: true, personal_strategy: true, owned: true },
    favoriteState: { available: true, favorited: true },
    paperSessionState: { available: true, has_session: true },
  });
  const personalActions = Object.fromEntries(personalContract.actions.map((action) => [action.id, action]));
  assert.equal(personalActions.save_as_personal_strategy.status, 'unavailable');
  assert.match(personalActions.save_as_personal_strategy.unavailable_reason, /已经是可编辑个人策略/);
  assert.equal(personalActions.open_personal_paper_session.status, 'clickable');
  assert.equal(personalActions.ai_modify_personal_strategy.status, 'confirm_required');
});

test('StrategyMarketService attaches runtime action contracts to strategy list payloads', () => {
  const service = new StrategyMarketService({}, {}, {}, {});
  const payload = service.withRuntimeActionContracts(
    {
      strategies: [
        {
          id: 'strat_card',
          name: 'Card Strategy',
          status: 'listed',
          author_id: 'factory',
        },
      ],
      count: 1,
    },
    { userId: 'alice', role: 'user' },
  );

  const actionContract = payload.strategies[0].runtime_action_contract;
  assert.equal(actionContract.dto_version, 'strategy_market.runtime_actions.v1');
  assert.equal(actionContract.actions.length, 5);
  assert.equal(actionContract.actions.find((action) => action.id === 'save_as_personal_strategy')?.status, 'confirm_required');
  assert.equal(actionContract.actions.find((action) => action.id === 'view_factory_source')?.status, 'clickable');
});

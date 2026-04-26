import test from 'node:test';
import assert from 'node:assert/strict';

const {
  STRATEGY_FACTORY_READINESS_REMEDIATIONS,
  STRATEGY_OPERATOR_JOB_ACTIONS,
  buildStrategyOperatorParity,
  isStrategyOperatorJobAction,
} = await import('../dist/strategy/strategy.operator-contract.js');
const { StrategyOperatorService } = await import('../dist/strategy/strategy-operator.service.js');
const { STRATEGY_MANAGER_ACTIONS } = await import('@aiask/shared-types');

test('strategy operator parity covers every strategy_manager action with no core gaps', () => {
  const parity = buildStrategyOperatorParity();
  assert.equal(parity.total_actions, STRATEGY_MANAGER_ACTIONS.length);
  assert.equal(parity.coverage.length, STRATEGY_MANAGER_ACTIONS.length);
  assert.equal(parity.unmapped_actions, 0);
  assert.equal(parity.core_unmapped_actions, 0);
  assert.equal(new Set(parity.coverage.map((item) => item.action)).size, STRATEGY_MANAGER_ACTIONS.length);
});

test('operator job allowlist covers high-risk factory closure actions only', () => {
  const parity = buildStrategyOperatorParity();
  const jobActions = new Set(parity.coverage.filter((item) => item.job_action).map((item) => item.action));
  for (const action of STRATEGY_OPERATOR_JOB_ACTIONS) {
    assert.equal(isStrategyOperatorJobAction(action), true);
    assert.equal(jobActions.has(action), true);
  }
  assert.equal(isStrategyOperatorJobAction('rank'), false);
  assert.equal(jobActions.has('rank'), false);
});

test('readiness remediations distinguish registry freshness and production sample top-up', () => {
  const byCode = new Map(STRATEGY_FACTORY_READINESS_REMEDIATIONS.map((item) => [item.code, item]));
  const governed = byCode.get('governed_candidate_pool_stale');
  assert.equal(governed.primary_action, 'factor_candidate_registry_refresh');
  assert.equal(governed.endpoint, '/api/mcp/jobs');
  assert.equal(governed.job_action, true);
  assert.deepEqual(governed.params_hint.follow_up.arguments, {
    action: 'factor_candidate_registry',
    params: { op: 'active_pool', market_codes_only: true, limit: 200 },
  });

  for (const code of ['promotion_hard_gate_pending', 'insufficient_samples']) {
    const remediation = byCode.get(code);
    assert.equal(remediation.primary_action, 'production_sample_top_up');
    assert.equal(remediation.endpoint, '/api/strategy-market/operator/jobs');
    assert.equal(remediation.job_action, true);
    assert.equal(remediation.requires_admin, true);
    assert.equal(remediation.params_hint.operator_job_action, 'incubation_sync_run');
    assert.equal(remediation.params_hint.replay_history, true);
    assert.equal(remediation.params_hint.target_realized_trades, 20);
  }
});

test('StrategyOperatorService requires confirmation and wraps allowed actions as MCP jobs', async () => {
  const calls = [];
  const fakeJobs = {
    async createToolJob(input, options) {
      calls.push({ input, options });
      return {
        accepted: true,
        deduplicated: false,
        job: {
          job_id: '00000000-0000-4000-8000-000000000001',
          status: 'queued',
          submitted_at: '2026-04-24T00:00:00.000Z',
          started_at: null,
          completed_at: null,
          poll_path: '/api/mcp/jobs/00000000-0000-4000-8000-000000000001',
          idempotency_key: null,
          target: {
            kind: 'tool',
            name: input.tool_name,
            arguments: input.arguments,
            timeout_ms: input.timeout_ms ?? 120000,
          },
          result: null,
          error: null,
          error_code: null,
          trace_id: options.traceId ?? null,
          meta: {},
        },
      };
    },
    async getJobOrThrow() {
      throw new Error('not used');
    },
  };
  const service = new StrategyOperatorService({}, fakeJobs);

  await assert.rejects(
    service.createOperatorJob({
      action: 'factory_run_once',
      confirmed: false,
      confirmation_text: '',
      params: {},
    }),
    (error) => {
      const response = typeof error.getResponse === 'function' ? error.getResponse() : {};
      return response.code === 'STRATEGY_OPERATOR_CONFIRMATION_REQUIRED';
    },
  );

  const record = await service.createOperatorJob(
    {
      action: 'factory_run_once',
      confirmed: true,
      confirmation_text: 'factory_run_once',
      strategy_id: 'strat_demo',
      params: { dry_run: false },
      timeout_ms: 300000,
    },
    { traceId: 'trace-operator' },
  );

  assert.equal(record.action, 'factory_run_once');
  assert.equal(record.strategy_id, 'strat_demo');
  assert.equal(record.poll_path, '/api/strategy-market/operator/jobs/00000000-0000-4000-8000-000000000001');
  assert.equal(calls[0].input.tool_name, 'strategy_manager');
  assert.deepEqual(calls[0].input.arguments, {
    action: 'factory_run_once',
    params: {
      dry_run: false,
      strategy_id: 'strat_demo',
      source: 'strategy_operator_console',
    },
  });
  assert.equal(calls[0].input.timeout_ms, 300000);
  assert.equal(calls[0].options.traceId, 'trace-operator');
});

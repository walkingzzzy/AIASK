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

test('StrategyOperatorService requires confirmation and wraps heavy actions as strategy task runs', async () => {
  const calls = [];
  const fakeMcp = {
    async callTool(toolName, args) {
      calls.push({ toolName, args });
      return {
        success: true,
        data: {
          accepted: true,
          queued: true,
          job_id: '42',
          task_run_id: 42,
          poll_path: '/api/strategy-market/operator/jobs/42',
          task_run: {
            id: 42,
            strategy_id: 'strat_demo',
            task_name: 'factory_run_once',
            task_scope: 'strategy_factory.worker',
            task_key: null,
            status: 'queued',
            trace_id: 'trace-operator',
            payload: {
              action: 'factory_run_once',
              params: {
                dry_run: false,
                strategy_id: 'strat_demo',
                source: 'strategy_operator_console',
                trace_id: 'trace-operator',
              },
              submitted_at: '2026-04-24T00:00:00.000Z',
            },
            result: {},
            error: null,
            started_at: '2026-04-24T00:00:00.000Z',
            completed_at: null,
          },
        },
      };
    },
  };
  const fakeJobs = {
    async createToolJob() {
      throw new Error('not used');
    },
    async getJobOrThrow() {
      throw new Error('not used');
    },
  };
  const dbQueries = [];
  const fakeDb = {
    async query(sql, params) {
      dbQueries.push({ sql, params });
      if (/INSERT INTO strategy_task_runs/i.test(sql)) {
        const [
          strategyId,
          action,
          taskScope,
          taskKey,
          traceId,
          payloadJson,
          submittedAt,
        ] = params;
        return {
          rows: [
            {
              id: 42,
              strategy_id: strategyId,
              task_name: action,
              task_scope: taskScope,
              task_key: taskKey,
              status: 'queued',
              trace_id: traceId,
              payload: JSON.parse(payloadJson),
              result: {},
              error: null,
              started_at: submittedAt,
              completed_at: null,
            },
          ],
        };
      }
      throw new Error(`unexpected query: ${sql}`);
    },
  };
  const service = new StrategyOperatorService(fakeMcp, fakeJobs, fakeDb);

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
  assert.equal(record.poll_path, '/api/strategy-market/operator/jobs/42');
  assert.equal(record.job.job_id, '42');
  assert.equal(calls.length, 0);
  assert.equal(dbQueries.length, 1);
  assert.match(dbQueries[0].sql, /INSERT INTO strategy_task_runs/i);
  assert.deepEqual(record.job.target.arguments, {
    action: 'factory_run_once',
    params: {
      dry_run: false,
      strategy_id: 'strat_demo',
      source: 'strategy_operator_console',
      trace_id: 'trace-operator',
    },
  });
  assert.deepEqual(record.job.meta, {
    queue_backend: 'db',
    task_scope: 'strategy_factory.worker',
    task_run_id: 42,
    raw_task_status: 'queued',
  });
});

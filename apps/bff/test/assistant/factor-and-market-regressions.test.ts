import 'reflect-metadata';
import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { FactorService } from '../../src/factor/factor.service';
import { MarketScheduler } from '../../src/market/market.scheduler';

test('factor calculate forwards date range and uses bounded concurrency', async () => {
  const calls: Array<Record<string, unknown>> = [];
  let active = 0;
  let maxActive = 0;

  const service = new FactorService(
    {
      callTool: async (_name: string, args: Record<string, unknown>) => {
        calls.push(args);
        active += 1;
        maxActive = Math.max(maxActive, active);
        await new Promise((resolve) => setTimeout(resolve, 10));
        active -= 1;
        return { data: { value: Number(String(args.code).slice(-1)) } };
      },
    } as never,
    {} as never,
  );

  const result = await service.calculateFactor({
    factor_name: 'momentum',
    stock_codes: ['600519', '000001', '000002'],
    start_date: '2026-01-01',
    end_date: '2026-03-01',
  });

  assert.equal(maxActive > 1, true);
  assert.equal(calls.length, 3);
  assert.equal(
    calls.every((item) => item.start_date === '2026-01-01'),
    true,
  );
  assert.equal(
    calls.every((item) => item.end_date === '2026-03-01'),
    true,
  );
  assert.deepEqual(
    result.results.map((item) => item.stock_code),
    ['600519', '000001', '000002'],
  );
});

test('factor observability aggregates scheduler, registry, memory, and model signals', async () => {
  const calls: string[] = [];
  const service = new FactorService(
    {
      callTool: async (_name: string, args: Record<string, unknown>) => {
        const action = String(args.action ?? '');
        calls.push(action);
        if (action === 'scheduler_status') {
          return {
            data: {
              quality_status: 'fresh',
              stale: false,
              freshness_sec: 12.5,
              last_result: {
                llm_validation: {
                  generated_candidate_count: 4,
                  validated_candidate_count: 2,
                  validation_failed_count: 1,
                  active_pool_count_after_run: 3,
                  governed_active_count_after_run: 2,
                },
              },
            },
          };
        }
        if (action === 'factor_candidate_registry') {
          const params = (args.params ?? {}) as Record<string, unknown>;
          if (params.op === 'summary') {
            return {
              data: {
                summary: {
                  count: 6,
                  active_count: 3,
                  governed_active_count: 2,
                  blocked_count: 1,
                  registry_stage_counts: { governed: 2, validated: 3, challenger: 1 },
                },
              },
            };
          }
          return {
            data: {
              active_pool: {
                count: 3,
                excluded_count: 2,
                latest_active_candidate_updated_at: '2026-04-01T09:00:00Z',
                exclusion_reason_counts: { multiple_testing_unavailable: 1, lookahead_risk_high: 1 },
              },
            },
          };
        }
        if (action === 'factor_research_memory') {
          return { data: { stats: { total_records: 12, duplicate_like_count: 2 } } };
        }
        if (action === 'model_registry') {
          const params = (args.params ?? {}) as Record<string, unknown>;
          if (params.op === 'summary') {
            return { data: { summary: { champion_count: 1, challenger_count: 2 } } };
          }
          if (params.op === 'retrain_summary') {
            return { data: { summary: { count: 3, status_counts: { planned: 2, completed: 1 } } } };
          }
          if (params.op === 'retrain_list') {
            return {
              data: {
                items: [
                  { artifact_id: 'retrain_plan_1', family: 'momentum', status: 'planned', target_model_count: 2 },
                ],
              },
            };
          }
        }
        throw new Error(`unexpected action ${action}`);
      },
    } as never,
    {} as never,
  );

  const result = await service.observability();

  assert.deepEqual(calls, [
    'scheduler_status',
    'factor_candidate_registry',
    'factor_candidate_registry',
    'factor_research_memory',
    'model_registry',
    'model_registry',
    'model_registry',
  ]);
  assert.equal(result.degraded, false);
  assert.equal(result.overview.scheduler_quality_status, 'fresh');
  assert.equal(result.overview.active_count, 3);
  assert.equal(result.overview.governed_active_count, 2);
  assert.equal(result.overview.champion_count, 1);
  assert.equal(result.overview.challenger_count, 2);
  assert.equal(result.overview.recent_generated_candidate_count, 4);
  assert.equal(result.overview.retrain_plan_count, 3);
  assert.equal(result.overview.retrain_pending_count, 2);
  assert.equal(result.retrain_queue[0]?.artifact_id, 'retrain_plan_1');
  assert.deepEqual(result.active_pool.exclusion_reason_counts, {
    multiple_testing_unavailable: 1,
    lookahead_risk_high: 1,
  });
});

test('market scheduler rotates quote windows instead of starving tail subscriptions', async () => {
  const requestedBatches: string[][] = [];
  const scheduler = new MarketScheduler(
    {
      getBatchQuotes: async (codes: string[]) => {
        requestedBatches.push([...codes]);
        return { quotes: codes.map((code) => ({ code, price: 1 })) };
      },
      getIndexQuote: async () => ({}),
    } as never,
    {
      pushQuote: () => undefined,
      pushBatchQuotes: () => undefined,
    } as never,
  );

  scheduler.addSubscribedCodes(Array.from({ length: 120 }, (_, index) => `code_${index + 1}`));

  await (scheduler as any).pushBatchQuotes();
  await (scheduler as any).pushBatchQuotes();
  await (scheduler as any).pushBatchQuotes();

  assert.equal(requestedBatches.length, 3);
  assert.deepEqual(requestedBatches[0][0], 'code_1');
  assert.deepEqual(requestedBatches[1][0], 'code_51');
  assert.deepEqual(requestedBatches[2][0], 'code_101');
  assert.equal(new Set(requestedBatches.flat()).size, 120);
});

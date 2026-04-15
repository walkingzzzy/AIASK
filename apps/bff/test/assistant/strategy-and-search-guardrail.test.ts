import 'reflect-metadata';
import { test } from 'node:test';
import * as assert from 'node:assert/strict';
import { plainToInstance } from 'class-transformer';
import { validateSync } from 'class-validator';
import { KlineSearchDto, SemanticDto, SimilarDto } from '../../src/search/search.controller';
import { ROLES_KEY } from '../../src/rbac/roles.decorator';
import { StrategyFactoryController } from '../../src/strategy/strategy-factory.controller';
import { StrategyRiskController } from '../../src/strategy/strategy-risk.controller';
import { StrategyVectorController } from '../../src/strategy/strategy-vector.controller';
import { FactorController } from '../../src/factor/factor.controller';
import { StrategyMarketService } from '../../src/strategy/strategy.service';

function getRoles(handler: Function): string[] | undefined {
  return Reflect.getMetadata(ROLES_KEY, handler) as string[] | undefined;
}

test('high-risk strategy and factor endpoints require admin role metadata', () => {
  assert.deepEqual(getRoles(StrategyFactoryController.prototype.factoryRunOnce), ['admin']);
  assert.deepEqual(getRoles(StrategyFactoryController.prototype.aiGenerate), ['admin']);
  assert.deepEqual(getRoles(StrategyVectorController.prototype.vectorRebuild), ['admin']);
  assert.deepEqual(getRoles(StrategyVectorController.prototype.vectorCleanup), ['admin']);
  assert.deepEqual(getRoles(StrategyRiskController.prototype.runRiskScan), ['admin']);
  assert.deepEqual(getRoles(StrategyRiskController.prototype.setRuntimeControl), ['admin']);
  assert.deepEqual(getRoles(FactorController.prototype.schedulerRunNow), ['admin']);
});

test('search query DTOs coerce numeric query params before validation', () => {
  const similar = plainToInstance(SimilarDto, { code: '600519', topN: '12', type: 'both' });
  const semantic = plainToInstance(SemanticDto, { query: '白酒 龙头', limit: '15' });
  const kline = plainToInstance(KlineSearchDto, { code: '000001', topN: '8' });

  assert.equal(similar.topN, 12);
  assert.equal(semantic.limit, 15);
  assert.equal(kline.topN, 8);
  assert.deepEqual(validateSync(similar), []);
  assert.deepEqual(validateSync(semantic), []);
  assert.deepEqual(validateSync(kline), []);
});

test('strategy auto refresh skips ranking refresh until MCP is reachable', async () => {
  const service = new StrategyMarketService(
    {
      checkAvailableTools: async () => ({ reachable: false }),
    } as never,
    {} as never,
  );

  let refreshed = false;
  const svc = service as any;
  svc.isAfterMarketClose = () => true;
  svc.dateKey = () => '2026-03-24';
  svc.refreshRankingCaches = async () => {
    refreshed = true;
    return { refreshed_count: 1 };
  };

  await svc.runAutoRefreshTick();

  assert.equal(refreshed, false);
});

test('strategy factory observability merges factory and factor governance snapshots', async () => {
  const cache = {
    resolveTtl: () => 60,
    getWithMeta: async () => ({ value: null, meta: { backend: 'memory' } }),
    set: async () => undefined,
    del: async () => undefined,
    clear: async () => undefined,
  };

  const service = new StrategyMarketService(
    {
      callTool: async (name: string, args: Record<string, unknown>) => {
        if (name === 'strategy_manager') {
          const action = String(args.action ?? '');
          if (action === 'factory_status') {
            return {
              data: {
                running: false,
                last_summary: {
                  run_id: 'run_001',
                  status: 'success',
                  candidates_spawned: 5,
                  passed_quality_gate: 2,
                },
              },
            };
          }
          if (action === 'factory_runs') {
            return {
              data: {
                items: [
                  { run_id: 'run_001', status: 'success' },
                  { run_id: 'run_000', status: 'partial' },
                ],
                latest: { run_id: 'run_001', status: 'success' },
              },
            };
          }
        }

        if (name === 'quant_manager') {
          const action = String(args.action ?? '');
          if (action === 'scheduler_status') {
            return {
              data: {
                quality_status: 'fresh',
                stale: false,
                last_result: {
                  llm_validation: {
                    generated_candidate_count: 4,
                    validated_candidate_count: 2,
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
                    active_count: 2,
                    governed_active_count: 2,
                    blocked_count: 1,
                    registry_stage_counts: { governed: 2, validated: 1 },
                  },
                },
              };
            }
            return {
              data: {
                active_pool: {
                  count: 2,
                  family_summary: [{ family: 'momentum', count: 2, promote_count: 1, avg_total_score: 82.3 }],
                },
              },
            };
          }
          if (action === 'model_registry') {
            const params = (args.params ?? {}) as Record<string, unknown>;
            if (params.op === 'summary') {
              return { data: { summary: { champion_count: 1, challenger_count: 1 } } };
            }
            if (params.op === 'retrain_summary') {
              return { data: { summary: { count: 2, status_counts: { planned: 1, completed: 1 } } } };
            }
            if (params.op === 'retrain_list') {
              return { data: { items: [{ artifact_id: 'retrain_1', family: 'momentum', status: 'planned' }] } };
            }
          }
        }

        throw new Error(`unexpected tool call ${name}`);
      },
    } as never,
    cache as never,
  );

  const result = await service.factoryObservability();

  assert.equal(result.degraded, false);
  assert.equal(result.overview.latest_factory_run_id, 'run_001');
  assert.equal(result.overview.latest_factory_status, 'success');
  assert.equal(result.overview.active_factor_count, 2);
  assert.equal(result.overview.governed_factor_count, 2);
  assert.equal(result.overview.champion_count, 1);
  assert.equal(result.overview.recent_generated_candidate_count, 4);
  assert.equal(result.overview.retrain_plan_count, 2);
  assert.equal(result.overview.retrain_pending_count, 1);
  assert.equal(result.factor_governance.active_pool.count, 2);
  assert.equal(result.factor_governance.retrain_queue[0]?.artifact_id, 'retrain_1');
  assert.deepEqual(result.errors, []);
});

test('strategy factory run-once is accepted asynchronously and exposed in status/runs', async () => {
  const cache = {
    resolveTtl: () => 60,
    getWithMeta: async () => ({ value: null, meta: { backend: 'memory' } }),
    set: async () => undefined,
    del: async () => undefined,
    clear: async () => undefined,
  };

  let resolveRun!: (value: unknown) => void;
  const runPromise = new Promise((resolve) => {
    resolveRun = resolve;
  });

  const service = new StrategyMarketService(
    {
      callTool: async (name: string, args: Record<string, unknown>) => {
        if (name !== 'strategy_manager') {
          throw new Error(`unexpected tool call ${name}`);
        }
        const action = String(args.action ?? '');
        if (action === 'factory_status') {
          return {
            data: {
              running: false,
              last_summary: {},
            },
          };
        }
        if (action === 'factory_runs') {
          return {
            data: {
              items: [],
              count: 0,
            },
          };
        }
        if (action === 'factory_run_once') {
          return runPromise;
        }
        throw new Error(`unexpected strategy action ${action}`);
      },
    } as never,
    cache as never,
  );

  const accepted = await service.factoryRunOnce() as {
    accepted: boolean;
    queued: boolean;
    request_id: string;
  };
  assert.equal(accepted.accepted, true);
  assert.equal(accepted.queued, true);

  const status = await service.factoryStatus() as {
    running?: boolean;
    local_background_run?: { request_id?: string };
  };
  assert.equal(status.running, true);
  assert.equal(status.local_background_run?.request_id, accepted.request_id);

  const runs = await service.factoryRuns(5) as {
    items?: Array<{ run_id?: string; status?: string }>;
  };
  assert.equal(runs.items?.[0]?.run_id, accepted.request_id);
  assert.equal(runs.items?.[0]?.status, 'running');

  resolveRun({ data: { run_id: 'factory_run_001', status: 'success' } });
  await new Promise((resolve) => setImmediate(resolve));

  const backgroundState = (service as unknown as { backgroundFactoryRunState?: { status?: string; upstream_run_id?: string } })
    .backgroundFactoryRunState;
  const backgroundCleanupTimer = (service as unknown as {
    backgroundFactoryRunClearTimer?: { hasRef?: () => boolean };
  }).backgroundFactoryRunClearTimer;
  assert.equal(backgroundState?.status, 'success');
  assert.equal(backgroundState?.upstream_run_id, 'factory_run_001');
  assert.equal(backgroundCleanupTimer?.hasRef?.(), false);
});

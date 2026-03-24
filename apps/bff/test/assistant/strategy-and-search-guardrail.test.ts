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

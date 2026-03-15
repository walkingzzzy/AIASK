#!/usr/bin/env node

/**
 * MCP argument boundary regression check
 *
 * 前提：apps/bff 已成功构建，存在 dist 产物。
 * 用途：验证 BFF 调 MCP 时的参数名与工具签名保持一致。
 */

import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const require = createRequire(import.meta.url);

const searchServiceDist = resolve(process.cwd(), 'apps/bff/dist/search/search.service.js');
const screenerServiceDist = resolve(process.cwd(), 'apps/bff/dist/screener/screener.service.js');
const optionsServiceDist = resolve(process.cwd(), 'apps/bff/dist/options/options.service.js');

if (!existsSync(searchServiceDist) || !existsSync(screenerServiceDist) || !existsSync(optionsServiceDist)) {
  throw new Error('缺少 apps/bff/dist 构建产物，请先执行 npm run build -w apps/bff');
}

const { SearchService } = require(searchServiceDist);
const { ScreenerService } = require(screenerServiceDist);
const { OptionsService } = require(optionsServiceDist);

function createCacheStub() {
  return {
    resolveTtl: (_key, fallback) => fallback,
    getWithMeta: async () => ({ value: null, meta: { backend: 'memory' } }),
    set: async () => {},
  };
}

async function checkSearchService() {
  const calls = [];
  const service = new SearchService({
    callTool: async (name, args) => {
      calls.push({ name, args });
      return { success: true, data: [] };
    },
  });

  await service.similarStocks({ code: '600519', topN: 7, type: 'technical' });
  await service.semanticSearch({ query: '低估值白酒', limit: 4 });
  await service.searchByKline({ code: '600519', topN: 5 });
  assert.deepEqual(calls[0], {
    name: 'search_similar_stocks',
    args: { code: '600519', top_n: 7, similarity_type: 'technical' },
  });
  assert.deepEqual(calls[1], {
    name: 'semantic_stock_search',
    args: { query: '低估值白酒', limit: 4 },
  });
  assert.deepEqual(calls[2], {
    name: 'search_by_kline',
    args: { code: '600519', top_n: 5 },
  });

  return calls;
}

async function checkScreenerService() {
  const calls = [];
  const service = new ScreenerService(
    {
      callTool: async (name, args) => {
        calls.push({ name, args });
        return { success: true, data: [] };
      },
    },
    createCacheStub(),
  );

  await service.semanticSearch('白酒龙头', 8);
  await service.conditionScreen(['ma_cross', 'rsi_oversold'], 12);
  await service.similarStocks('600519', 6);

  assert.deepEqual(calls[0], {
    name: 'semantic_stock_search',
    args: { query: '白酒龙头', limit: 8 },
  });
  assert.deepEqual(calls[1], {
    name: 'screener_manager',
    args: { action: 'technical_screen', params: { conditions: ['ma_cross', 'rsi_oversold'], limit: 12 } },
  });
  assert.deepEqual(calls[2], {
    name: 'search_similar_stocks',
    args: { code: '600519', top_n: 6, similarity_type: 'both' },
  });

  return calls;
}

async function checkOptionsService() {
  const calls = [];
  const service = new OptionsService(
    {
      callTool: async (name, args) => {
        calls.push({ name, args });
        return { success: true, data: [] };
      },
    },
    createCacheStub(),
  );

  await service.getOptionChain('510050');
  await service.getOptionGreeks('510050');
  await service.getVolatilitySmirk('510050');

  assert.deepEqual(calls[0], {
    name: 'get_option_chain',
    args: { underlying: '510050' },
  });
  assert.deepEqual(calls[1], {
    name: 'options_manager',
    args: { action: 'calculate_greeks', params: { underlying: '510050' } },
  });
  assert.deepEqual(calls[2], {
    name: 'options_manager',
    args: { action: 'volatility_smirk', params: { underlying: '510050' } },
  });

  return calls;
}

async function main() {
  const search = await checkSearchService();
  const screener = await checkScreenerService();
  const options = await checkOptionsService();

  console.log('MCP_ARG_BOUNDARY_CHECK_OK');
  console.log(JSON.stringify({ search, screener, options }, null, 2));
}

main().catch((error) => {
  console.error('MCP_ARG_BOUNDARY_CHECK_FAIL');
  console.error(error);
  process.exit(1);
});

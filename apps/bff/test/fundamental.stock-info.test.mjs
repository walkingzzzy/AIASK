import test from 'node:test';
import assert from 'node:assert/strict';

const { getOverview, getStockInfo } = await import('../dist/fundamental/fundamental.service.api.js');

test('getStockInfo returns a degraded envelope on upstream 429 with DB fallback fields', async () => {
  const cacheWrites = [];
  const service = {
    constructor: { STOCK_INFO_TTL_SECONDS: 120 },
    logger: { warn: () => {} },
    cacheService: {
      resolveTtl: () => 120,
      getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
      set: async (key, value, ttlSeconds) => cacheWrites.push({ key, value, ttlSeconds }),
    },
    callWithArgs: async () => {
      throw new Error('HTTP 429 Too Many Requests');
    },
    buildStockInfoFallbackFromDb: async (code) => ({
      code,
      name: '工商银行',
      industry: '银行',
      listDate: '',
      totalShares: null,
      floatShares: null,
      totalMarketCap: 2300000000000,
      floatMarketCap: null,
      fallbackSource: 'db.stocks',
    }),
    readRecord: (value) => (value && typeof value === 'object' && !Array.isArray(value) ? value : {}),
    unwrapRoot: (value) => value,
    toNum: (value) => (Number.isFinite(Number(value)) ? Number(value) : null),
  };

  const result = await getStockInfo(service, '601398');

  assert.equal(result.code, '601398');
  assert.equal(result.name, '工商银行');
  assert.equal(result.degraded, true);
  assert.equal(result.fallbackSource, 'db.stocks');
  assert.match(result.fallbackReason, /429/);
  assert.equal(cacheWrites.length, 1);
  assert.equal(cacheWrites[0].ttlSeconds <= 60, true);
});

test('getOverview returns degraded envelope instead of 503 when upstream fundamentals fail', async () => {
  const cacheWrites = [];
  const service = {
    constructor: { OVERVIEW_TTL_SECONDS: 300 },
    logger: { warn: () => {} },
    cacheService: {
      resolveTtl: () => 300,
      getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
      set: async (key, value, ttlSeconds) => cacheWrites.push({ key, value, ttlSeconds }),
    },
    callWithArgs: async () => {
      throw new Error('MCP upstream unavailable');
    },
    dbFallbackValuation: async () => ({ pe: 6.5, pb: 0.7, ps: null, marketCap: 2300000000000 }),
    normalizeFinancials: () => ({
      roe: null,
      netProfit: null,
      revenue: null,
      debtRatio: null,
      grossProfitMargin: null,
      netProfitMargin: null,
      operatingCashFlow: null,
    }),
    normalizeValuation: () => ({ pe: null, pb: null, ps: null, marketCap: null }),
  };

  const result = await getOverview(service, '601398');

  assert.equal(result.code, '601398');
  assert.equal(result.degraded, true);
  assert.match(result.fallbackReason, /get_financials/);
  assert.equal(result.valuation.pe, 6.5);
  assert.equal(result.valuation.pb, 0.7);
  assert.equal(cacheWrites.length, 1);
  assert.equal(cacheWrites[0].ttlSeconds <= 60, true);
});

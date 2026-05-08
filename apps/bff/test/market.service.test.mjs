import test from 'node:test';
import assert from 'node:assert/strict';

const { MarketService } = await import('../dist/market/market.service.js');

function createCacheStub() {
  return {
    resolveTtl: (_scope, fallbackSeconds) => fallbackSeconds,
    getWithMeta: async () => ({ value: null, meta: { backend: 'none' } }),
    set: async () => {},
  };
}

test('MarketService.getKline deduplicates same-day records and normalizes share volume to lots', async () => {
  const calls = [];
  const service = new MarketService(
    {
      callTool: async (tool) => {
        calls.push(tool);
        return {
        success: true,
        data: [
          { date: '2026-04-29', open: 11.43, close: 11.52, low: 11.39, high: 11.54, volume: 137842300, turnover: 1583294869 },
          { date: '2026-04-29', open: 11.43, close: 11.52, low: 11.39, high: 11.54, volume: 1378423, amount: 1583294869 },
          { date: '2026-04-30', open: 11.5, close: 11.49, low: 11.46, high: 11.6, volume: 113924162, amount: 1312827776 },
        ],
        meta: { source_chain: ['db.get_klines'] },
      };
      },
    },
    createCacheStub(),
  );

  const result = await service.getKline('000001', 'daily', 20);

  assert.equal(result.kline.length, 2);
  assert.deepEqual(calls, ['get_kline']);
  assert.deepEqual(result.kline.map((item) => item.date), ['2026-04-29', '2026-04-30']);
  assert.equal(result.kline[0].volume, 1378423);
  assert.equal(result.kline[1].volume, 1139242);
  assert.equal(result.kline[1].turnover, 1312827776);
  assert.equal(result.result_contract?.status, 'ready');
  assert.ok(result.result_contract?.riskNotes?.some((note) => /去重/.test(note)));
  assert.ok(result.result_contract?.riskNotes?.some((note) => /成交量/.test(note)));
  assert.equal(result.data_quality?.status, 'trusted');
});

test('MarketService.getKline treats database fallback as usable partial data', async () => {
  const service = new MarketService(
    {
      callTool: async () => ({
        success: true,
        data: [
          { date: '2026-04-29', open: 11.43, close: 11.52, low: 11.39, high: 11.54, volume: 1378423, amount: 1583294869 },
          { date: '2026-04-30', open: 11.5, close: 11.49, low: 11.46, high: 11.6, volume: 1139242, amount: 1312827776 },
        ],
        meta: {
          degraded: true,
          fallback_reason: ['total_timeout_exceeded:45.0s,using db.get_klines after total timeout'],
          source_chain: ['get_kline_data', 'db.get_klines'],
        },
      }),
    },
    createCacheStub(),
  );

  const result = await service.getKline('000988', 'daily', 20);

  assert.equal(result.kline.length, 2);
  assert.equal(result.result_contract?.status, 'degraded');
  assert.equal(result.data_quality?.status, 'partial');
  assert.match(result.data_quality?.reasons?.join(' / ') ?? '', /备用历史数据/);
  assert.doesNotMatch(result.data_quality?.reasons?.join(' / ') ?? '', /total_timeout_exceeded/);
});

test('MarketService.getKline falls back to local database when MCP times out', async () => {
  const service = new MarketService(
    {
      callTool: async () => {
        throw new Error('MCP error -32001: Request timed out');
      },
    },
    createCacheStub(),
    {
      enabled: true,
      query: async () => ({
        rows: [
          { time: new Date('2026-04-29T07:00:00.000Z'), code: '000988', open: 11.43, close: 11.52, low: 11.39, high: 11.54, volume: 137842300, amount: 1583294869, turnover: null, change_pct: null },
          { time: new Date('2026-04-30T07:00:00.000Z'), code: '000988', open: 11.5, close: 11.49, low: 11.46, high: 11.6, volume: 113924162, amount: 1312827776, turnover: null, change_pct: null },
        ],
      }),
    },
  );

  const result = await service.getKline('000988', 'daily', 20);

  assert.equal(result.kline.length, 2);
  assert.equal(result.result_contract?.status, 'degraded');
  assert.equal(result.contract_meta?.canonicalTool, 'db.get_klines');
  assert.equal(result.data_quality?.status, 'partial');
  assert.match(result.result_contract?.summary ?? '', /本地历史数据/);
});

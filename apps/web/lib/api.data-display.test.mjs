import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));

async function loadApiModule() {
  const sourcePath = path.resolve(TEST_DIR, 'api.ts');
  const source = fs
    .readFileSync(sourcePath, 'utf8')
    .replace(/^import[^\n]*\n/gm, '');
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
      verbatimModuleSyntax: false,
    },
  }).outputText;
  const tempFile = path.join(os.tmpdir(), `aiask-api-display-${Date.now()}-${Math.random().toString(16).slice(2)}.mjs`);
  fs.writeFileSync(tempFile, transpiled);
  return import(pathToFileURL(tempFile).href);
}

const { classifyDataTrustForDisplay, rejectFallbackPayload } = await loadApiModule();

test('partial data with samples is renderable with a quality banner', () => {
  const payload = {
    flows: [{ name: '银行', netInflow: 1200 }],
    data_quality: {
      status: 'partial',
      reasons: ['资金流数据缺少交易日期，已保留数值但不伪造日期'],
      quality_flags: ['fund_flow_date_missing'],
      sources: [{ name: 'get_sector_fund_flow', status: 'partial', sampleCount: 1 }],
    },
  };

  const decision = classifyDataTrustForDisplay(payload);

  assert.equal(rejectFallbackPayload(payload), null);
  assert.equal(decision.disposition, 'partial-valid');
  assert.equal(decision.canRenderData, true);
  assert.equal(decision.shouldShowQualityBanner, true);
});

test('degraded kline fallback with samples is renderable with a quality banner', () => {
  const payload = {
    kline: [{ date: '2026-05-06', open: 1, close: 2, low: 1, high: 2, volume: 100 }],
    result_contract: {
      status: 'degraded',
      platformMeta: {
        degraded: true,
        fallbackReason: ['K 线实时主链路响应较慢，已自动切换到备用历史数据。'],
      },
    },
    data_quality: {
      status: 'partial',
      reasons: ['K 线实时主链路响应较慢，已自动切换到备用历史数据。'],
      quality_flags: [],
      sources: [{ name: 'db.get_klines', status: 'partial', sampleCount: 1 }],
    },
  };

  const decision = classifyDataTrustForDisplay(payload);

  assert.equal(rejectFallbackPayload(payload), null);
  assert.equal(decision.disposition, 'partial-valid');
  assert.equal(decision.canRenderData, true);
  assert.equal(decision.shouldShowQualityBanner, true);
});

test('fallback-only empty shell remains blocking', () => {
  const payload = {
    data_quality: {
      status: 'unavailable',
      reasons: ['quote_unavailable'],
      quality_flags: ['quote_unavailable'],
      sources: [{ name: 'get_realtime_quote', status: 'failed', sampleCount: 0 }],
      empty_reason: '实时行情没有返回有效价格',
    },
    fallback_used: true,
    fallback_reason: 'quote_unavailable',
  };

  const decision = classifyDataTrustForDisplay(payload);

  assert.match(rejectFallbackPayload(payload) ?? '', /quote_unavailable|实时行情/);
  assert.equal(decision.disposition, 'blocking');
  assert.equal(decision.canRenderData, false);
});

test('contracted empty result is a valid empty display state when explicitly allowed', () => {
  const payload = {
    reports: [],
    notices: [],
    data_quality: {
      status: 'empty',
      reasons: ['research_empty'],
      quality_flags: ['research_empty_result'],
      sources: [{ name: 'get_research_reports', status: 'empty', sampleCount: 0 }],
      empty_reason: '当前窗口没有命中研报或公告',
    },
  };

  const decision = classifyDataTrustForDisplay(payload);

  assert.match(rejectFallbackPayload(payload) ?? '', /research_empty|当前窗口/);
  assert.equal(rejectFallbackPayload(payload, { allowEmpty: true }), null);
  assert.equal(decision.disposition, 'valid-empty');
  assert.equal(decision.isValidEmpty, true);
});

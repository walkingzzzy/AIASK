import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const testDir = path.dirname(fileURLToPath(import.meta.url));

async function loadModule(sourcePath) {
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
  const tempFile = path.join(
    os.tmpdir(),
    `aiask-technical-display-${path.basename(sourcePath)}-${Date.now()}-${Math.random().toString(16).slice(2)}.mjs`,
  );
  fs.writeFileSync(tempFile, transpiled);
  return import(pathToFileURL(tempFile).href);
}

const technicalDisplayModule = await loadModule(path.join(testDir, 'technical-display.ts'));

test('parseIndicatorPayload summarizes comma-separated numeric strings instead of dumping raw arrays', () => {
  const payload = {
    rsi: {
      value: 59.64,
      signal: 'hold',
      overbought: false,
      oversold: false,
    },
    macd: {
      macd: '0.016,0.021,0.092',
      signal: '-0.006,0.014,0.023',
      histogram: '0.022,0.048,0.069',
    },
  };

  const parsed = technicalDisplayModule.parseIndicatorPayload(payload, ['#1', '#2', '#3', '#4']);
  const macd = parsed.summary.find((item) => item.key === 'MACD');
  assert.equal(parsed.series.length, 3);
  assert.ok(macd);
  assert.deepEqual(macd.entries, [
    ['macd', '最新 0.092（3 点）'],
    ['signal', '最新 0.023（3 点）'],
    ['histogram', '最新 0.069（3 点）'],
  ]);
  assert.equal(macd.entries.some(([, value]) => value.includes(',')), false);
});

test('parseIndicatorPayload preserves scalar indicator summaries', () => {
  const payload = {
    rsi: {
      value: 59.64,
      signal: 'hold',
      overbought: false,
      oversold: false,
    },
  };

  const parsed = technicalDisplayModule.parseIndicatorPayload(payload, ['#1']);
  assert.deepEqual(parsed.summary, [
    {
      key: 'RSI',
      entries: [
        ['value', '59.64'],
        ['signal', 'hold'],
        ['overbought', 'false'],
        ['oversold', 'false'],
      ],
    },
  ]);
});

test('parseIndicatorPayload accepts warmup series with null gaps', () => {
  const payload = {
    macd: {
      macd: [null, null, 0.016, 0.021, 0.092],
      signal: [null, null, -0.006, 0.014, 0.023],
      histogram: [null, null, 0.022, 0.048, 0.069],
      warmup_periods: 33,
    },
  };

  const parsed = technicalDisplayModule.parseIndicatorPayload(payload, ['#1', '#2', '#3']);
  const macd = parsed.summary.find((item) => item.key === 'MACD');
  assert.equal(parsed.series.length, 3);
  assert.ok(macd);
  assert.deepEqual(macd.entries, [
    ['macd', '最新 0.092（5 点）'],
    ['signal', '最新 0.023（5 点）'],
    ['histogram', '最新 0.069（5 点）'],
    ['warmup_periods', '33'],
  ]);
});

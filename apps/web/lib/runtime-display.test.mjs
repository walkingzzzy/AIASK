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
    `aiask-runtime-display-${path.basename(sourcePath)}-${Date.now()}-${Math.random().toString(16).slice(2)}.mjs`,
  );
  fs.writeFileSync(tempFile, transpiled);
  return import(pathToFileURL(tempFile).href);
}

const runtimeDisplayModule = await loadModule(path.join(testDir, 'runtime-display.ts'));

test('realtime status falls back to offline when reachability is offline', () => {
  assert.equal(runtimeDisplayModule.resolveRealtimeDisplayStatus('connected', 'offline'), 'offline');
  assert.equal(runtimeDisplayModule.resolveRealtimeDisplayStatus('reconnecting', 'offline'), 'offline');
});

test('notification feed distinguishes unavailable from empty state', () => {
  const result = runtimeDisplayModule.resolveNotificationFeedState({
    enabled: true,
    itemsLength: 0,
    acceptanceStatus: 'unavailable',
    serviceUnavailable: true,
    trustStatus: 'unknown',
    reachabilityStatus: 'offline',
  });
  assert.equal(result, 'unavailable');
});

test('notification feed keeps degraded state when partial data is present', () => {
  const result = runtimeDisplayModule.resolveNotificationFeedState({
    enabled: true,
    itemsLength: 3,
    acceptanceStatus: null,
    serviceUnavailable: false,
    trustStatus: 'degraded',
    reachabilityStatus: 'online',
  });
  assert.equal(result, 'degraded');
});

test('notification feed resolves to empty only when service is healthy and no data exists', () => {
  const result = runtimeDisplayModule.resolveNotificationFeedState({
    enabled: true,
    itemsLength: 0,
    acceptanceStatus: null,
    serviceUnavailable: false,
    trustStatus: 'trusted',
    reachabilityStatus: 'online',
  });
  assert.equal(result, 'empty');
});

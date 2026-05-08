import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const testDir = path.dirname(fileURLToPath(import.meta.url));

async function loadModule(sourcePath, stubs = '') {
  const source = fs
    .readFileSync(sourcePath, 'utf8')
    .replace(/^import[^\n]*\n/gm, '');
  const transpiled = ts.transpileModule(`${stubs}\n${source}`, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
      verbatimModuleSyntax: false,
    },
  }).outputText;
  const tempFile = path.join(os.tmpdir(), `aiask-data-effects-${path.basename(sourcePath)}-${Date.now()}-${Math.random().toString(16).slice(2)}.mjs`);
  fs.writeFileSync(tempFile, transpiled);
  return import(pathToFileURL(tempFile).href);
}

const dataEffectsStubs = `
const apiKeys = {
  alerts: (...a) => ['api', 'alerts', ...a],
  auth: (...a) => ['api', 'auth', ...a],
  audit: (...a) => ['api', 'audit', ...a],
  execution: (...a) => ['api', 'execution', ...a],
  notifications: (...a) => ['api', 'notifications', ...a],
  paper: (...a) => ['api', 'paper-trading', ...a],
  portfolio: (...a) => ['api', 'portfolio', ...a],
  risk: (...a) => ['api', 'risk', ...a],
  strategy: (...a) => ['api', 'strategy-market', ...a],
};
`;

const dataEffectsModule = await loadModule(
  path.join(testDir, 'data-effects.ts'),
  dataEffectsStubs,
);

const surfaceCatalog = JSON.parse(
  fs.readFileSync(path.join(testDir, '../e2e/realworld/catalog.json'), 'utf8'),
);
const surfaceContractsStubs = `
const surfaceCatalog = ${JSON.stringify(surfaceCatalog)};
const getMutationRefreshContract = (effect) => {
  const contracts = {
    'alerts.changed': {
      affectedSurfaces: ['alerts', 'home'],
      affectedDomRegions: ['alerts-list', 'home-alert-summary'],
      expectedFields: ['rule count', 'latest alert status'],
    },
    'auth.profile.updated': {
      affectedSurfaces: ['settings', 'settings-security', 'user', 'home'],
      affectedDomRegions: ['profile form', 'header user summary', 'dashboard preferences'],
      expectedFields: ['nickname', 'riskLevel', 'avatarUrl', 'preferences'],
    },
    'auth.security.updated': {
      affectedSurfaces: ['settings-security', 'settings', 'user'],
      affectedDomRegions: ['2fa status', 'transaction confirmation toggles'],
      expectedFields: ['totpEnabled', 'transactionConfirmations'],
    },
    'auth.sessions.changed': {
      affectedSurfaces: ['settings', 'settings-audit-log'],
      affectedDomRegions: ['session list', 'audit log'],
      expectedFields: ['active sessions', 'audit entries'],
    },
    'execution.changed': {
      affectedSurfaces: ['execution', 'paper-trading', 'performance', 'risk', 'home'],
      affectedDomRegions: ['execution tasks', 'pending orders', 'performance summary', 'risk summary'],
      expectedFields: ['executionId', 'artifactId', 'pending orders', 'risk metrics'],
    },
    'notifications.changed': {
      affectedSurfaces: ['notifications', 'global-bell'],
      affectedDomRegions: ['notification list', 'notification bell'],
      expectedFields: ['unread count', 'read state', 'visible rows'],
    },
    'paper-trading.changed': {
      affectedSurfaces: ['paper-trading', 'performance', 'risk', 'execution', 'home'],
      affectedDomRegions: ['summary cards', 'positions', 'performance chart', 'risk cards'],
      expectedFields: ['total value', 'nav history', 'pending orders', 'trust status'],
    },
    'portfolio.changed': {
      affectedSurfaces: ['portfolio', 'performance', 'risk', 'home', 'strategy-market'],
      affectedDomRegions: ['portfolio list', 'portfolio detail', 'performance attribution', 'risk summary'],
      expectedFields: ['portfolio count', 'holdings', 'attribution', 'risk metrics'],
    },
    'strategy.changed': {
      affectedSurfaces: ['strategy-market', 'strategy-detail', 'portfolio', 'paper-trading'],
      affectedDomRegions: ['strategy list', 'strategy detail', 'portfolio cart', 'linked strategy context'],
      expectedFields: ['favorite state', 'strategy count', 'linked account context'],
    },
    'watchlist.changed': {
      affectedSurfaces: ['watchlist', 'market', 'stock', 'home'],
      affectedDomRegions: ['watchlist groups', 'watchlist badge', 'recent watchlist summary'],
      expectedFields: ['group count', 'item count', 'star state'],
    },
  };
  return { effect, ...(contracts[effect] ?? { affectedSurfaces: [], affectedDomRegions: [], expectedFields: [] }) };
};
`;

const surfaceContractsModule = await loadModule(
  path.join(testDir, 'surface-interaction-contracts.ts'),
  surfaceContractsStubs,
);

test('paper-trading effect invalidates paper, execution, and risk modules', () => {
  const keys = dataEffectsModule.getInvalidateKeysForEffects(['paper-trading.changed']);
  assert.deepEqual(keys, [
    ['api', 'paper-trading'],
    ['api', 'execution'],
    ['api', 'risk'],
  ]);
});

test('auth security event name is stable', () => {
  assert.equal(
    dataEffectsModule.getDataEffectEventName('auth.security.updated'),
    'aiask:data-effect:auth.security.updated',
  );
});

test('strategy interaction contract includes downstream portfolio and paper-trading proofs', () => {
  const contract = surfaceContractsModule.surfaceInteractionContracts['strategy-market'];
  assert.ok(contract);
  const downstream = contract.dependencyProofs.flatMap((item) => item.affectedSurfaces);
  assert.ok(downstream.includes('portfolio'));
  assert.ok(downstream.includes('paper-trading'));
});

test('surface interaction contracts cover all catalog surfaces', () => {
  assert.equal(Object.keys(surfaceContractsModule.surfaceInteractionContracts).length, surfaceCatalog.length);
});

test('persistent and destructive surfaces define reversible write actions', () => {
  const required = surfaceCatalog
    .filter((item) => item.mutationMode === 'persistent' || item.mutationMode === 'destructive')
    .map((item) => item.surfaceId);
  for (const surfaceId of required) {
    const contract = surfaceContractsModule.surfaceInteractionContracts[surfaceId];
    assert.ok(contract, `${surfaceId} contract missing`);
    assert.ok(contract.writeActions.length > 0, `${surfaceId} write actions missing`);
  }
});

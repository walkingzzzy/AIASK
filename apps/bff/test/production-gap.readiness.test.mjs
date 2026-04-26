import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = resolve(fileURLToPath(new URL('../../../', import.meta.url)));

const MONITORING_FILES = [
  'monitoring/prometheus.yml',
  'monitoring/alertmanager.yml',
  'monitoring/otel-collector-config.yml',
  'monitoring/postgres-exporter-queries.yml',
  'monitoring/blackbox.yml',
  'monitoring/alerts/bff-readiness.rules.yml',
];

function rootPath(relativePath) {
  return resolve(REPO_ROOT, relativePath);
}

test('monitoring profile references checked-in configuration files', () => {
  for (const file of MONITORING_FILES) {
    assert.equal(existsSync(rootPath(file)), true, `${file} should exist`);
  }
});

test('readiness entrypoint is wired in the root package.json scripts', () => {
  const pkg = JSON.parse(readFileSync(rootPath('package.json'), 'utf-8'));
  assert.equal(typeof pkg.scripts['verify:production-gap-readiness'], 'string');
  assert.equal(typeof pkg.scripts['verify:monitoring'], 'string');
});

test('health/admin and execution-audit frontend consumers remain present', () => {
  const required = [
    'apps/web/components/home/SystemStatus.tsx',
    'apps/web/app/admin/page.tsx',
    'apps/web/app/admin/tools/page.tsx',
    'apps/web/app/strategy-market/components/StrategyMarketOperatorPanel.tsx',
    'apps/web/app/strategy-market/hooks/use-strategy-detail-page.ts',
    'apps/web/app/strategy-market/components/factory-review-panel/summary-section.tsx',
  ];
  for (const file of required) {
    assert.equal(existsSync(rootPath(file)), true, `${file} should exist`);
  }
});

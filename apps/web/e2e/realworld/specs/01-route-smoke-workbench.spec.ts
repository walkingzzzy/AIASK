import { test } from '@playwright/test';
import { openSurface } from '../support/auth';
import { verifySurface } from '../support/route-assertions';
import { runScenario } from '../support/scenario';
import { pickSurfaces } from '../support/surfaces';

const SURFACES = pickSurfaces([
  'execution',
  'performance',
  'paper-trading',
  'portfolio',
  'risk',
  'alerts',
  'notifications',
  'workspace-templates',
  'skills',
  'user',
  'settings',
  'settings-security',
  'settings-audit-log',
  'strategy',
  'strategy-market',
  'strategy-detail',
  'watchlist',
  'execution-artifact-detail',
]);

test.setTimeout(300_000);

for (const surface of SURFACES) {
  test(`[surface:${surface.surfaceId}] [scenario:single] ${surface.label} 单功能`, async ({ page }, testInfo) => {
    await runScenario(page, testInfo, surface, 'single', async ({ bundle }) => {
      await openSurface(page, bundle, surface);
      await verifySurface(page, bundle, surface.surfaceId);
    });
  });
}

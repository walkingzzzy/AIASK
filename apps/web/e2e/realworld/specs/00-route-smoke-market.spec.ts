import { test } from '@playwright/test';
import { openSurface } from '../support/auth';
import { verifySurface } from '../support/route-assertions';
import { runScenario } from '../support/scenario';
import { getSurface, pickSurfaces } from '../support/surfaces';

const SURFACES = pickSurfaces([
  'home',
  'market',
  'stock',
  'fundamental',
  'technical',
  'fund-flow',
  'sentiment',
  'research',
  'valuation',
  'factor',
  'factor-analysis',
  'events',
  'screener',
  'search',
  'data',
  'macro',
  'options',
  'decision',
  'assistant',
  'chat',
]);

test.setTimeout(300_000);

for (const surface of SURFACES) {
  test(`[surface:${surface.surfaceId}] [scenario:single] ${surface.label} 单功能`, async ({ page }, testInfo) => {
    await runScenario(page, testInfo, surface, 'single', async ({ bundle }) => {
      await openSurface(page, bundle, surface);
      await verifySurface(page, bundle, surface.surfaceId);
    }, process.env.E2E_BROWSER === 'webkit' && ['assistant', 'chat'].includes(surface.surfaceId)
      ? {
          allowPageErrors: [
            /\/api\/chat\/(?:config|conversations) due to access control checks\./i,
            /^Error: 数据服务暂不可用$/,
          ],
        }
      : undefined);
  });
}

test(`[surface:backtest] [scenario:single] ${getSurface('backtest').label} 单功能`, async ({ page }, testInfo) => {
  const surface = getSurface('backtest');
  await runScenario(page, testInfo, surface, 'single', async ({ bundle }) => {
    await openSurface(page, bundle, surface);
    await verifySurface(page, bundle, surface.surfaceId);
  });
});

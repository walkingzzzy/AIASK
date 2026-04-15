import { test } from '@playwright/test';
import { loginAsRole } from '../support/auth';
import { getBundle } from '../support/bundle';
import { runScenario } from '../support/scenario';
import { getSurface } from '../support/surfaces';
import {
  runAdminCacheWorkflow,
  runAdminDeadLettersWorkflow,
  runAlertWorkflow,
  runNotificationWorkflow,
  runWatchlistWorkflow,
} from '../workflows/ops-workflows';

test.setTimeout(360_000);

test('[surface:alerts] [scenario:workflow] 告警创建与删除', async ({ page }, testInfo) => {
  const surface = getSurface('alerts');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'user', '/alerts');
    await runAlertWorkflow(page);
  });
});

test('[surface:watchlist] [scenario:workflow] 自选分组创建与加股', async ({ page }, testInfo) => {
  const surface = getSurface('watchlist');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'user', '/watchlist');
    await runWatchlistWorkflow(page, `E2E分组-${Date.now()}`);
  });
});

test('[surface:notifications] [scenario:workflow] 通知筛选批量处理', async ({ page }, testInfo) => {
  const surface = getSurface('notifications');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'user', '/notifications');
    await runNotificationWorkflow(page);
  });
});

test('[surface:admin-cache] [scenario:workflow] 管理后台缓存清理', async ({ page }, testInfo) => {
  const surface = getSurface('admin-cache');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'admin', '/admin/cache');
    await runAdminCacheWorkflow(page);
  });
});

test('[surface:admin-dead-letters] [scenario:workflow] 管理后台死信重试与清空', async ({ page }, testInfo) => {
  const surface = getSurface('admin-dead-letters');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(page, bundle, 'admin', '/admin/dead-letters');
    await runAdminDeadLettersWorkflow(page);
  });
});

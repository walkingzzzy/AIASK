import { test } from '@playwright/test';
import { getBundle } from '../support/bundle';
import { runScenario } from '../support/scenario';
import { getSurface } from '../support/surfaces';
import {
  registerThroughUi,
  runLoginLifecycleWorkflow,
  runSettingsWorkflow,
  runTwoFactorWorkflow,
} from '../workflows/auth-workflows';

test.setTimeout(360_000);

test('[surface:login] [scenario:workflow] 登录与会话生命周期', async ({ page }, testInfo) => {
  const surface = getSurface('login');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await runLoginLifecycleWorkflow(page, bundle.users.browser.username, bundle.users.browser.password);
  }, {
    expectProtectedShell: false,
    checkOverflow: false,
  });
});

test('[surface:register] [scenario:workflow] 注册后自动进入受保护工作台', async ({ page }, testInfo) => {
  const surface = getSurface('register');
  const username = `rw_reg_${Date.now()}`;
  const password = 'rw-pass-123';
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await registerThroughUi(page, username, password);
  }, {
    expectProtectedShell: true,
  });
});

test('[surface:settings-workbench] [scenario:workflow] 设置工作台资料修改与改密', async ({ page }, testInfo) => {
  const surface = getSurface('settings-workbench');
  const username = `rw_set_${Date.now()}`;
  const password = 'rw-pass-123';
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await registerThroughUi(page, username, password);
    await runSettingsWorkflow(page, username, password);
  }, {
    expectProtectedShell: true,
  });
});

test('[surface:settings-security] [scenario:workflow] 安全设置 2FA 启停', async ({ page }, testInfo) => {
  const surface = getSurface('settings-security');
  const username = `rw_2fa_${Date.now()}`;
  const password = 'rw-pass-123';
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await registerThroughUi(page, username, password);
    await runTwoFactorWorkflow(page, username, password);
  }, {
    expectProtectedShell: true,
  });
});

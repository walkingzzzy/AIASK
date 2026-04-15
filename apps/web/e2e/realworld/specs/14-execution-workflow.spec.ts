import { expect, test } from '@playwright/test';
import { loginAsRole } from '../support/auth';
import { getBundle } from '../support/bundle';
import { runScenario } from '../support/scenario';
import { getSurface } from '../support/surfaces';

test.setTimeout(360_000);

test('[surface:execution] [scenario:workflow] 执行中心到 Artifact 详情联动', async ({ page }, testInfo) => {
  const surface = getSurface('execution');
  const bundle = getBundle();
  await runScenario(page, testInfo, surface, 'workflow', async () => {
    await loginAsRole(
      page,
      bundle,
      'user',
      `/execution?execution_id=${encodeURIComponent(bundle.execution.executionId)}&account_id=${encodeURIComponent(bundle.execution.accountId)}`,
    );
    const artifactButton = page.getByRole('button', { name: /查看 Artifact|打开 artifact 详情页(?:面板)?/ }).first();
    await expect(artifactButton).toBeVisible({ timeout: 20_000 });
    await artifactButton.click();
    await expect(page).toHaveURL(new RegExp(`/execution/artifacts/${bundle.execution.artifactId}`));
    await expect(page.getByRole('heading', { name: 'Artifact 详情' })).toBeVisible();
  });
});

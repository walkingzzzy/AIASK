import { expect, test, type Page } from '@playwright/test';
import {
  assertNoCriticalPageIssues,
  assertProtectedShell,
  createPageIssueCollector,
  openProtectedPage,
  waitForSettledUi,
} from './helpers/app';

test.describe.configure({ mode: 'serial' });
test.setTimeout(240_000);

const BFF_PORT = Number(process.env.BFF_PORT || 3001);
const BFF_BASE_URL = process.env.E2E_BFF_BASE_URL || `http://127.0.0.1:${BFF_PORT}/api`;

async function loadAdminMcpStats(page: Page) {
  const response = await page.request.get(`${BFF_BASE_URL}/admin/mcp-stats`);
  expect(response.ok(), `admin mcp stats failed: ${response.status()}`).toBe(true);
  const payload = await response.json();
  expect(payload?.success).toBe(true);
  return payload.data as {
    reachable?: boolean;
    totalCalls?: number;
    tools?: Array<{ name: string; calls: number }>;
  };
}

test('should verify frontend -> BFF -> MCP -> strategy-factory chain', async ({ page }) => {
  const collector = createPageIssueCollector(page);

  await openProtectedPage(page, '/');
  await assertProtectedShell(page);

  const beforeStats = await loadAdminMcpStats(page);
  const beforeTotalCalls = Number(beforeStats?.totalCalls ?? 0);

  const rankingResponse = page.waitForResponse((response) => (
    response.url().includes('/api/strategy-market/ranking') && response.status() === 200
  ));

  await openProtectedPage(page, '/market?code=600519');
  await assertProtectedShell(page);
  await expect(page.getByRole('textbox', { name: '股票代码' })).toHaveValue('600519');
  await expect(page.getByText(/贵州茅台|600519/).first()).toBeVisible({ timeout: 30_000 });

  await Promise.all([
    rankingResponse,
    openProtectedPage(page, '/strategy-market'),
  ]);
  await assertProtectedShell(page);
  await waitForSettledUi(page, 1_500);
  await expect(page.getByRole('heading', { name: /先看筛选结果|订阅、组合和工厂动作/ }).first()).toBeVisible();
  await expect(page.getByText(/Strategy Workspace|工厂/).first()).toBeVisible();

  const afterStats = await loadAdminMcpStats(page);
  const afterTotalCalls = Number(afterStats?.totalCalls ?? 0);

  expect(afterStats?.reachable, 'MCP should remain reachable after chained UI flows').toBe(true);
  expect(
    afterTotalCalls,
    `Expected MCP tool calls to increase, before=${beforeTotalCalls}, after=${afterTotalCalls}`,
  ).toBeGreaterThan(beforeTotalCalls);

  assertNoCriticalPageIssues(collector);
  collector.dispose();
});

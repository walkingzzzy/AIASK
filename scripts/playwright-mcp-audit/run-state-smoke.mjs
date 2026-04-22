import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

import { createIssueCollector, gotoStable, login, waitForSettledUi } from './browser-common.mjs';

function parseArgs(argv) {
  const args = {
    baseUrl: 'http://127.0.0.1:3000',
    bffUrl: 'http://127.0.0.1:3001/api',
    outputDir: path.resolve('artifacts/state-smoke'),
    adminUsername: process.env.PW_AUDIT_ADMIN_USERNAME || 'admin',
    adminPassword: process.env.PW_AUDIT_ADMIN_PASSWORD || 'admin123',
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--base-url' && argv[index + 1]) {
      args.baseUrl = String(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--bff-url' && argv[index + 1]) {
      args.bffUrl = String(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--output-dir' && argv[index + 1]) {
      args.outputDir = path.resolve(argv[index + 1]);
      index += 1;
      continue;
    }
  }

  return args;
}

function mapHealthLabel(status) {
  if (status === 'normal') return '正常';
  if (status === 'degraded') return '降级';
  if (status === 'untrusted') return '不可信';
  return '未知';
}

function shortText(value, limit = 240) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
  return dirPath;
}

async function waitForCondition(check, timeoutMs = 10000, intervalMs = 200) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await check()) return true;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return false;
}

async function waitForVisible(locator, timeoutMs = 10000) {
  return waitForCondition(() => locator.isVisible().catch(() => false), timeoutMs);
}

function recordAssertion(results, condition, name, detail = '') {
  results.assertions.push({
    name,
    passed: Boolean(condition),
    detail: detail || undefined,
  });
  if (!condition) {
    throw new Error(`${name}${detail ? ` :: ${detail}` : ''}`);
  }
}

async function saveScreenshot(page, dirPath, name) {
  const filePath = path.join(dirPath, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  return filePath;
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  return { ok: response.ok, status: response.status, body };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const results = {
    generatedAt: new Date().toISOString(),
    baseUrl: args.baseUrl,
    bffUrl: args.bffUrl,
    assertions: [],
    snapshots: {},
    issues: null,
  };

  const screenshotDir = await ensureDir(path.join(args.outputDir, 'screens'));
  await ensureDir(args.outputDir);

  const health = await fetchJson(`${args.bffUrl}/health`);
  recordAssertion(results, health.ok, 'bff health endpoint reachable', `status=${health.status}`);

  const healthBody = health.body ?? {};
  const expectedServiceLabel = mapHealthLabel(healthBody.status);
  const expectedMcpLabel = mapHealthLabel(healthBody.mcp?.status);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  });
  const page = await context.newPage();
  const issueCollector = createIssueCollector(page);

  try {
    await login(page, args.baseUrl, {
      username: args.adminUsername,
      password: args.adminPassword,
    });

    await gotoStable(page, `${args.baseUrl}/`);
    await waitForSettledUi(page, 1200);
    await page.locator('summary').filter({ hasText: '展开完整首页模块' }).first().click().catch(() => {});
    await page.waitForTimeout(400);
    await page.getByRole('tab', { name: '运行与风险' }).click().catch(() => {});
    recordAssertion(
      results,
      await waitForVisible(page.getByTestId('home-system-status-modules').first(), 12000),
      'home system status module rendered',
    );
    const homeHealthSummary = page.getByTestId('home-system-health-summary').first();
    recordAssertion(
      results,
      await waitForVisible(homeHealthSummary, 12000),
      'home system health summary rendered',
    );
    await homeHealthSummary.click().catch(() => {});
    await page.waitForTimeout(400);
    const homeHealthText = await page.getByTestId('home-system-health-details').first().innerText().catch(() => '');
    recordAssertion(results, homeHealthText.includes('系统总览'), 'home health details includes overview');
    recordAssertion(
      results,
      homeHealthText.includes(expectedServiceLabel),
      'home health details includes mapped service status',
      `expected=${expectedServiceLabel}; actual=${shortText(homeHealthText)}`,
    );
    recordAssertion(
      results,
      homeHealthText.includes(`MCP`) && homeHealthText.includes(expectedMcpLabel),
      'home health details includes mapped MCP status',
      `expected=${expectedMcpLabel}; actual=${shortText(homeHealthText)}`,
    );
    recordAssertion(
      results,
      homeHealthText.includes(`传输 ${String(healthBody.mcp?.transportKind ?? healthBody.mcp?.source ?? '-')}`),
      'home health details includes MCP transport',
      shortText(homeHealthText),
    );
    results.snapshots.home = {
      healthText: shortText(homeHealthText, 800),
      screenshot: path.relative(args.outputDir, await saveScreenshot(page, screenshotDir, 'home-operations-health')),
    };

    await gotoStable(page, `${args.baseUrl}/strategy-market`);
    await waitForSettledUi(page, 1800);
    recordAssertion(
      results,
      await waitForVisible(page.getByTestId('strategy-market-catalog').first(), 12000),
      'strategy market catalog rendered',
    );
    recordAssertion(
      results,
      await waitForVisible(page.getByTestId('strategy-market-factory-overview').first(), 12000),
      'strategy market factory overview rendered',
    );
    recordAssertion(
      results,
      await waitForVisible(page.getByTestId('strategy-market-observability').first(), 12000),
      'strategy market observability rendered',
    );

    const ranking = await page.evaluate(async (bffUrl) => {
      const response = await fetch(`${bffUrl}/strategy-market/ranking?limit=3`, { credentials: 'include' });
      return { ok: response.ok, status: response.status, body: await response.json() };
    }, args.bffUrl);
    const strategies = ranking.body?.data?.strategies ?? [];
    recordAssertion(results, ranking.ok, 'strategy market ranking endpoint reachable', `status=${ranking.status}`);
    recordAssertion(results, strategies.length > 0, 'strategy market ranking returned strategies');

    const firstStrategy = strategies[0];
    const firstStrategyId = String(firstStrategy?.id ?? '').trim();
    recordAssertion(results, Boolean(firstStrategyId), 'strategy market first strategy has id');
    results.snapshots.strategyMarket = {
      firstStrategy,
      screenshot: path.relative(args.outputDir, await saveScreenshot(page, screenshotDir, 'strategy-market')),
    };

    const detail = await page.evaluate(async ({ bffUrl, strategyId }) => {
      const response = await fetch(`${bffUrl}/strategy-market/${strategyId}`, { credentials: 'include' });
      return { ok: response.ok, status: response.status, body: await response.json() };
    }, { bffUrl: args.bffUrl, strategyId: firstStrategyId });
    const detailData = detail.body?.data ?? {};
    const strategy = detailData.strategy ?? {};
    recordAssertion(results, detail.ok, 'strategy detail endpoint reachable', `status=${detail.status}`);
    recordAssertion(
      results,
      detailData.dto_version === 'strategy_market.detail.v2',
      'strategy detail dto version is stable',
      `dto_version=${String(detailData.dto_version ?? '')}`,
    );
    await gotoStable(page, `${args.baseUrl}/strategy-market/${encodeURIComponent(firstStrategyId)}`);
    await waitForSettledUi(page, 1800);
    const heroStatus = await page.getByTestId('page-primary-status').first().innerText().catch(() => '');
    recordAssertion(
      results,
      heroStatus.includes(`策略状态 ${String(strategy.status ?? '')}`),
      'strategy detail hero status includes strategy status',
      shortText(heroStatus),
    );
    recordAssertion(
      results,
      heroStatus.includes(`订阅 ${String(strategy.subscriber_count ?? '')}`),
      'strategy detail hero status includes subscriber count',
      shortText(heroStatus),
    );
    recordAssertion(
      results,
      (await page.locator('body').innerText()).includes(String(strategy.name ?? '')),
      'strategy detail body includes strategy name',
    );

    await page.getByRole('tab', { name: '工厂审查' }).first().click().catch(() => {});
    recordAssertion(
      results,
      await waitForVisible(page.getByTestId('strategy-detail-factory-review').first(), 12000),
      'strategy detail factory review rendered',
    );
    await page.getByRole('tab', { name: '运行风控' }).first().click().catch(() => {});
    await page.waitForTimeout(1200);
    recordAssertion(
      results,
      await waitForCondition(
        async () => {
          const bodyText = await page.locator('body').innerText().catch(() => '');
          return /风险事件|运行告警|恢复尝试/.test(bodyText);
        },
        12000,
      ),
      'strategy detail runtime section rendered',
    );
    await page.getByRole('tab', { name: '实验事件' }).first().click().catch(() => {});
    await page.waitForTimeout(1200);
    recordAssertion(
      results,
      await waitForCondition(
        async () => {
          const bodyText = await page.locator('body').innerText().catch(() => '');
          return /实验事件|领域事件|任务运行/.test(bodyText);
        },
        12000,
      ),
      'strategy detail experiments section rendered',
    );
    results.snapshots.strategyDetail = {
      strategy: {
        id: strategy.id,
        name: strategy.name,
        status: strategy.status,
        author_id: strategy.author_id,
        subscriber_count: strategy.subscriber_count,
      },
      heroStatus: shortText(heroStatus, 400),
      screenshot: path.relative(args.outputDir, await saveScreenshot(page, screenshotDir, 'strategy-detail')),
    };

    await gotoStable(page, `${args.baseUrl}/admin`);
    await waitForSettledUi(page, 1500);
    const refreshAction = page.getByTestId('admin-refresh-snapshot-action').first();
    if (await refreshAction.isVisible().catch(() => false)) {
      await refreshAction.click().catch(() => {});
    }
    await waitForCondition(async () => {
      const statusText = await page.getByTestId('page-primary-status').first().innerText().catch(() => '');
      return !statusText.includes('等待快照') && !statusText.includes('刷新中') && !statusText.includes('最近快照：-');
    }, 12000);
    const adminStatus = await page.getByTestId('page-primary-status').first().innerText().catch(() => '');
    recordAssertion(
      results,
      adminStatus.includes(`服务 ${expectedServiceLabel}`),
      'admin status includes mapped service status',
      shortText(adminStatus),
    );
    recordAssertion(
      results,
      adminStatus.includes(`MCP ${expectedMcpLabel}`),
      'admin status includes mapped MCP status',
      shortText(adminStatus),
    );
    if (healthBody.status === 'degraded') {
      recordAssertion(
        results,
        await waitForVisible(page.getByText('系统存在降级链路').first(), 12000),
        'admin shows degraded system issue',
      );
    }
    if (healthBody.mcp?.status === 'degraded') {
      recordAssertion(
        results,
        await waitForVisible(page.getByText('MCP 处于降级模式').first(), 12000),
        'admin shows degraded MCP issue',
      );
    }
    results.snapshots.admin = {
      statusText: shortText(adminStatus, 400),
      screenshot: path.relative(args.outputDir, await saveScreenshot(page, screenshotDir, 'admin')),
    };

    issueCollector.dispose();
    results.issues = issueCollector.issues;
    recordAssertion(
      results,
      issueCollector.issues.apiErrors.length === 0,
      'no API 5xx responses during smoke',
      issueCollector.issues.apiErrors.join(' | '),
    );
    recordAssertion(
      results,
      issueCollector.issues.consoleErrors.length === 0,
      'no console errors during smoke',
      issueCollector.issues.consoleErrors.join(' | '),
    );
    recordAssertion(
      results,
      issueCollector.issues.pageErrors.length === 0,
      'no page errors during smoke',
      issueCollector.issues.pageErrors.join(' | '),
    );
    recordAssertion(
      results,
      issueCollector.issues.requestFailures.length === 0,
      'no request failures during smoke',
      issueCollector.issues.requestFailures.join(' | '),
    );
  } finally {
    issueCollector.dispose();
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }

  const resultPath = path.join(args.outputDir, 'state-smoke-results.json');
  await fs.writeFile(resultPath, `${JSON.stringify(results, null, 2)}\n`, 'utf8');
  process.stdout.write(`${resultPath}\n`);
}

main().catch(async (error) => {
  const message = error instanceof Error ? error.stack || error.message : String(error);
  console.error(message);
  process.exitCode = 1;
});

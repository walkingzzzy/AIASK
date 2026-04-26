import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

import { createIssueCollector, gotoStable, login, resolveDynamicPath, waitForSettledUi } from './browser-common.mjs';

function parseArgs(argv) {
  const args = {
    baseUrl: 'http://127.0.0.1:3000',
    bffUrl: 'http://127.0.0.1:3001/api',
    outputDir: path.resolve('artifacts/state-smoke'),
    userUsername: process.env.PW_AUDIT_USER_USERNAME || `pwl${Date.now().toString(36).slice(-8)}`,
    userPassword: process.env.PW_AUDIT_USER_PASSWORD || 'PwAudit12345',
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

async function clickOptional(locator, timeoutMs = 1800) {
  const visible = await waitForVisible(locator, timeoutMs);
  if (!visible) return false;
  await locator.click({ timeout: timeoutMs }).catch(() => {});
  return true;
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

function mergeIssues(...issueGroups) {
  return {
    apiErrors: issueGroups.flatMap((item) => item?.apiErrors ?? []),
    httpErrors: issueGroups.flatMap((item) => item?.httpErrors ?? []),
    consoleErrors: issueGroups.flatMap((item) => item?.consoleErrors ?? []),
    pageErrors: issueGroups.flatMap((item) => item?.pageErrors ?? []),
    requestFailures: issueGroups.flatMap((item) => item?.requestFailures ?? []),
  };
}

function filterExpectedSmokeIssues(issues) {
  const consoleErrors = (issues?.consoleErrors ?? []).filter(
    (entry) => !/status of 412 \(Precondition Failed\)/i.test(String(entry)),
  );
  return {
    apiErrors: issues?.apiErrors ?? [],
    httpErrors: issues?.httpErrors ?? [],
    consoleErrors,
    pageErrors: issues?.pageErrors ?? [],
    requestFailures: issues?.requestFailures ?? [],
  };
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
  const userContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  });
  const userPage = await userContext.newPage();
  const adminContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  });
  const adminPage = await adminContext.newPage();
  let userIssueCollector = null;
  let adminIssueCollector = null;

  try {
    await login(userPage, args.baseUrl, {
      username: args.userUsername,
      password: args.userPassword,
    });
    userIssueCollector = createIssueCollector(userPage);

    await gotoStable(userPage, `${args.baseUrl}/`);
    await waitForSettledUi(userPage, 1200);
    recordAssertion(
      results,
      await waitForCondition(
        async () => {
          const bodyText = await userPage.locator('body').innerText().catch(() => '');
          return /一个覆盖市场、研究、策略与交易的智能股票分析平台/.test(bodyText);
        },
        12000,
      ),
      'home hero rendered',
    );
    recordAssertion(
      results,
      await waitForCondition(
        async () => {
          const bodyText = await userPage.locator('body').innerText().catch(() => '');
          return /首页默认只展示 3 块关键信息|核心摘要/.test(bodyText);
        },
        12000,
      ),
      'home core summary rendered',
    );
    results.snapshots.home = {
      summaryText: shortText(await userPage.locator('body').innerText().catch(() => ''), 800),
      screenshot: path.relative(args.outputDir, await saveScreenshot(userPage, screenshotDir, 'home-operations-health')),
    };

    await login(adminPage, args.baseUrl, {
      username: args.adminUsername,
      password: args.adminPassword,
    });
    adminIssueCollector = createIssueCollector(adminPage);

    const resolvedDetail = await resolveDynamicPath(userPage, args.baseUrl, {
      dynamicResolver: 'strategy-market-first-detail',
      path: '/strategy-market',
    });
    const seededStrategyId = String(resolvedDetail.path ?? '')
      .split('/')
      .pop()
      ?.trim();

    await gotoStable(userPage, `${args.baseUrl}/strategy-market`);
    await waitForSettledUi(userPage, 1800);
    recordAssertion(
      results,
      await waitForVisible(userPage.getByTestId('strategy-market-catalog').first(), 12000),
      'strategy market catalog rendered',
    );

    await gotoStable(adminPage, `${args.baseUrl}/strategy-market?workspace=factory&task=factory_cycle`);
    await waitForSettledUi(adminPage, 1800);
    recordAssertion(
      results,
      await waitForVisible(adminPage.getByTestId('strategy-market-factory-overview').first(), 12000),
      'strategy market factory overview rendered',
    );
    recordAssertion(
      results,
      await waitForVisible(adminPage.getByTestId('strategy-market-observability').first(), 12000),
      'strategy market observability rendered',
    );
    recordAssertion(
      results,
      await waitForVisible(adminPage.getByTestId('strategy-market-operator-panel').first(), 12000),
      'strategy market operator panel rendered',
    );
    results.snapshots.strategyFactory = {
      screenshot: path.relative(args.outputDir, await saveScreenshot(adminPage, screenshotDir, 'strategy-factory-operator')),
    };

    const ranking = await userPage.evaluate(async () => {
      const response = await fetch('/api/bff/strategy-market/ranking?limit=3', { credentials: 'include' });
      return { ok: response.ok, status: response.status, body: await response.json() };
    });
    const strategies = ranking.body?.data?.strategies ?? [];
    recordAssertion(results, ranking.ok, 'strategy market ranking endpoint reachable', `status=${ranking.status}`);
    recordAssertion(
      results,
      strategies.length > 0 || Boolean(seededStrategyId),
      'strategy market ranking returned strategies',
    );

    const firstStrategy = strategies[0] ?? { id: seededStrategyId };
    const firstStrategyId = String(firstStrategy?.id ?? '').trim();
    recordAssertion(results, Boolean(firstStrategyId), 'strategy market first strategy has id');
    results.snapshots.strategyMarket = {
      firstStrategy,
      screenshot: path.relative(args.outputDir, await saveScreenshot(userPage, screenshotDir, 'strategy-market')),
    };

    const detail = await userPage.evaluate(async ({ strategyId }) => {
      const response = await fetch(`/api/bff/strategy-market/${strategyId}`, { credentials: 'include' });
      return { ok: response.ok, status: response.status, body: await response.json() };
    }, { strategyId: firstStrategyId });
    const detailData = detail.body?.data ?? {};
    const strategy = detailData.strategy ?? {};
    recordAssertion(results, detail.ok, 'strategy detail endpoint reachable', `status=${detail.status}`);
    recordAssertion(
      results,
      detailData.dto_version === 'strategy_market.detail.v2',
      'strategy detail dto version is stable',
      `dto_version=${String(detailData.dto_version ?? '')}`,
    );
    await gotoStable(userPage, `${args.baseUrl}/strategy-market/${encodeURIComponent(firstStrategyId)}`);
    await waitForSettledUi(userPage, 1800);
    const detailStatus = userPage.getByTestId('page-primary-status').first();
    await waitForCondition(
      async () => /策略状态\s+\S+/.test(await detailStatus.innerText().catch(() => '')),
      12000,
    );
    const heroStatus = await detailStatus.innerText().catch(() => '');
    recordAssertion(
      results,
      /策略状态\s+\S+/.test(heroStatus),
      'strategy detail hero status rendered',
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
      (await userPage.locator('body').innerText()).includes(String(strategy.name ?? '')),
      'strategy detail body includes strategy name',
    );

    recordAssertion(
      results,
      await clickOptional(userPage.getByRole('tab', { name: '工厂审查' }).first()),
      'strategy detail factory tab available',
    );
    recordAssertion(
      results,
      await waitForCondition(
        async () => {
          const hasFactoryReview = await userPage.getByTestId('strategy-detail-factory-review').first().isVisible().catch(() => false);
          if (hasFactoryReview) return true;
          const bodyText = await userPage.locator('body').innerText().catch(() => '');
          return /闭环状态总览|默认用户视图/.test(bodyText);
        },
        12000,
      ),
      'strategy detail factory review rendered',
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
      screenshot: path.relative(args.outputDir, await saveScreenshot(userPage, screenshotDir, 'strategy-detail')),
    };

    await gotoStable(adminPage, `${args.baseUrl}/admin`);
    await waitForSettledUi(adminPage, 1500);
    const refreshAction = adminPage.getByTestId('admin-refresh-snapshot-action').first();
    if (await refreshAction.isVisible().catch(() => false)) {
      await refreshAction.click().catch(() => {});
    }
    await waitForCondition(async () => {
      const statusText = await adminPage.getByTestId('page-primary-status').first().innerText().catch(() => '');
      return !statusText.includes('等待快照') && !statusText.includes('刷新中') && !statusText.includes('最近快照：-');
    }, 12000);
    const adminStatus = await adminPage.getByTestId('page-primary-status').first().innerText().catch(() => '');
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
        await waitForVisible(adminPage.getByText('系统存在降级链路').first(), 12000),
        'admin shows degraded system issue',
      );
    }
    if (healthBody.mcp?.status === 'degraded') {
      recordAssertion(
        results,
        await waitForVisible(adminPage.getByText('MCP 处于降级模式').first(), 12000),
        'admin shows degraded MCP issue',
      );
    }
    results.snapshots.admin = {
      statusText: shortText(adminStatus, 400),
      screenshot: path.relative(args.outputDir, await saveScreenshot(adminPage, screenshotDir, 'admin')),
    };

    await gotoStable(adminPage, `${args.baseUrl}/admin/tools`);
    await waitForSettledUi(adminPage, 1500);
    recordAssertion(
      results,
      await waitForVisible(adminPage.getByTestId('admin-tools-mcp-jobs').first(), 12000),
      'admin tools MCP job panel rendered',
    );
    results.snapshots.adminTools = {
      screenshot: path.relative(args.outputDir, await saveScreenshot(adminPage, screenshotDir, 'admin-tools-mcp-jobs')),
    };

    results.issues = filterExpectedSmokeIssues(
      mergeIssues(userIssueCollector?.issues, adminIssueCollector?.issues),
    );
    recordAssertion(
      results,
      results.issues.apiErrors.length === 0,
      'no API 5xx responses during smoke',
      results.issues.apiErrors.join(' | '),
    );
    recordAssertion(
      results,
      results.issues.consoleErrors.length === 0,
      'no console errors during smoke',
      results.issues.consoleErrors.join(' | '),
    );
    recordAssertion(
      results,
      results.issues.pageErrors.length === 0,
      'no page errors during smoke',
      results.issues.pageErrors.join(' | '),
    );
    recordAssertion(
      results,
      results.issues.requestFailures.length === 0,
      'no request failures during smoke',
      results.issues.requestFailures.join(' | '),
    );
  } finally {
    userIssueCollector?.dispose?.();
    adminIssueCollector?.dispose?.();
    await userContext.close().catch(() => {});
    await adminContext.close().catch(() => {});
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

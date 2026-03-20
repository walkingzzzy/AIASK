import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const SCREENSHOT_DIR = path.join(ROOT, 'docs', 'screenshots');
const DATE_TAG = '20260317';
const WEB_ORIGIN = process.env.P4_WEB_ORIGIN ?? 'http://127.0.0.1:3000';
const API_ORIGIN = process.env.P4_API_ORIGIN ?? 'http://127.0.0.1:3001';
const MOCK_TS = '2026-03-17T20:00:00+08:00';

function envelope(data, extra = {}) {
  return {
    success: true,
    data,
    traceId: 'p4-mock-trace',
    ...extra,
  };
}

function json(route, payload, { raw = false, status = 200 } = {}) {
  return route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(raw ? payload : envelope(payload)),
  });
}

async function installApiMocks(page) {
  await page.route(`${API_ORIGIN}/socket.io/**`, (route) => route.abort());
  await page.route(`${API_ORIGIN}/api/auth/me`, (route) => json(route, {
    authenticated: true,
    user: {
      id: 'p4-admin',
      username: 'p4-admin',
      role: 'admin',
      displayName: 'P4 回归管理员',
    },
  }, { raw: true }));
  await page.route(`${API_ORIGIN}/api/auth/refresh`, (route) => json(route, { refreshed: true }, { raw: true }));
  await page.route(`${API_ORIGIN}/api/notifications/unread-count`, (route) => json(route, { count: 0 }));
  await page.route(`${API_ORIGIN}/api/notifications/list**`, (route) => json(route, { items: [] }));
  await page.route(`${API_ORIGIN}/api/notifications/mark-all-read`, (route) => json(route, { markedCount: 0 }));
  await page.route(`${API_ORIGIN}/api/watchlist/groups`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/watchlist/**`, (route) => json(route, { ok: true }));
  await page.route(`${API_ORIGIN}/api/health/mcp`, (route) => json(route, {
    status: 'degraded',
    service: 'aiask-bff',
    timestamp: MOCK_TS,
    db: { enabled: true, healthy: false },
    mcp: {
      reachable: false,
      matched: false,
      toolCount: 68,
      expectedTools: 91,
      source: 'mock-session',
      message: 'mock offline',
      activeConnections: 0,
      poolSize: 4,
    },
  }));
  await page.route(`${API_ORIGIN}/api/admin/cache-stats`, (route) => json(route, {
    hitRate: 0.42,
    totalKeys: 2480,
    memoryUsed: '128 MB',
    hits: 1050,
    misses: 1450,
    prefixes: [
      { prefix: 'quote', count: 320, hitRate: 0.28 },
      { prefix: 'strategy', count: 112, hitRate: 0.17 },
      { prefix: 'market', count: 680, hitRate: 0.71 },
      { prefix: 'research', count: 240, hitRate: 0.34 },
    ],
  }));
  await page.route(`${API_ORIGIN}/api/admin/cache/clear`, (route) => json(route, { cleared: true }));
  await page.route(`${API_ORIGIN}/api/market/quote**`, (route) => json(route, {
    quote: null,
    meta: { fetchedAt: MOCK_TS, cache: { hit: false, backend: 'mock', ttlSeconds: 0 } },
  }));
  await page.route(`${API_ORIGIN}/api/market/kline**`, (route) => json(route, {
    kline: [],
    meta: { fetchedAt: MOCK_TS, cache: { hit: false, backend: 'mock', ttlSeconds: 0 } },
  }));
  await page.route(`${API_ORIGIN}/api/market/order-book**`, (route) => json(route, {
    orderBook: { bids: [], asks: [], timestamp: null },
    meta: { fetchedAt: MOCK_TS, cache: { hit: false, backend: 'mock', ttlSeconds: 0 } },
  }));
  await page.route(`${API_ORIGIN}/api/market/limit-up-stats**`, (route) => json(route, {}));
  await page.route(`${API_ORIGIN}/api/market/limit-up**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/market/blocks**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/market/block-stocks**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/market/trade-details**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/market/minute-kline**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/market/search**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/market/stock-list**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/market/batch-quotes`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/research/list**`, (route) => json(route, {
    reports: [],
    notices: [],
    meta: { fetchedAt: MOCK_TS, cache: { hit: false, backend: 'mock', ttlSeconds: 0 } },
  }));
  await page.route(`${API_ORIGIN}/api/research/stock-news**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/research/market-news**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/research/analyst-ranking**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/research/profit-forecast**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/research/search**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/research/reports**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/research/macro**`, (route) => json(route, []));
  await page.route(`${API_ORIGIN}/api/v1/macro/indicator/**`, (route) => json(route, {
    indicator: 'gdp',
    records: [],
  }));
  await page.route(`${API_ORIGIN}/api/v1/options/chain/**`, (route) => json(route, {
    underlying: {
      code: '510300',
      name: '沪深300ETF',
      price: 3.812,
      time: '15:00:00',
      date: '2026-03-17',
    },
    selectedExpiry: [],
    options: [],
  }));
  await page.route(`${API_ORIGIN}/api/v1/options/greeks/**`, (route) => json(route, {
    code: '510300',
    option_type: 'call',
    greeks: {},
    interpretation: {},
  }));
  await page.route(`${API_ORIGIN}/api/**`, (route) => json(route, {}));
}

async function preparePage(page) {
  await page.addInitScript(() => {
    window.localStorage.setItem('onboarding-done', '1');
  });
  await page.context().addCookies([
    {
      name: 'logged_in',
      value: '1',
      url: 'http://127.0.0.1:3000',
    },
  ]);
  await installApiMocks(page);
}

async function gotoReady(page, pathname, headingPattern) {
  await page.goto(`${WEB_ORIGIN}${pathname}`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: new RegExp(headingPattern) }).first()).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(500);
}

async function shot(page, filename) {
  const target = path.join(SCREENSHOT_DIR, filename);
  await page.screenshot({ path: target, fullPage: true });
  return target;
}

async function run() {
  await fs.mkdir(SCREENSHOT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    colorScheme: 'dark',
  });
  const page = await context.newPage();
  const output = [];

  try {
    await preparePage(page);

    await gotoReady(page, '/admin', '管理后台概览');
    await expect(page.getByRole('heading', { name: '优先处理' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '第一步通常去这里' })).toBeVisible();
    output.push(await shot(page, `admin-p4-${DATE_TAG}.png`));

    await gotoReady(page, '/admin/cache', '缓存管理');
    await page.getByRole('button', { name: /清除全部缓存/ }).click();
    const confirmButton = page.getByRole('button', { name: '确认清理' });
    await expect(page.getByText('这是全量危险操作')).toBeVisible();
    await expect(confirmButton).toBeDisabled();
    await page.getByRole('checkbox', { name: /我已知晓全量清理/ }).check();
    await expect(confirmButton).toBeEnabled();
    output.push(await shot(page, `admin-cache-p4-${DATE_TAG}.png`));
    await page.getByRole('button', { name: '取消' }).click();

    await gotoReady(page, '/market', '行情看板');
    await expect(page.getByText('当前标的还没有可展示的 K 线')).toBeVisible();
    output.push(await shot(page, `market-p4-${DATE_TAG}.png`));
    await page.getByRole('tab', { name: '涨停板' }).click();
    await expect(page.getByText('当前还没有涨停榜单')).toBeVisible();
    await page.getByRole('tab', { name: '板块' }).click();
    await expect(page.getByText('先加载行业板块再看轮动')).toBeVisible();
    await page.getByRole('tab', { name: '逐笔' }).click();
    await expect(page.getByText('输入股票代码后查看逐笔成交')).toBeVisible();
    await page.getByRole('tab', { name: '分时' }).click();
    await expect(page.getByText('选择周期后加载分钟级 K 线')).toBeVisible();
    await page.getByRole('tab', { name: '搜索' }).click();
    await expect(page.getByText('先输入名称或代码开始搜索')).toBeVisible();

    await gotoReady(page, '/research', '研报公告');
    await expect(page.getByText('当前条件下暂无结果')).toBeVisible();
    output.push(await shot(page, `research-p4-${DATE_TAG}.png`));
    await page.getByRole('button', { name: '查看市场新闻' }).first().click();
    await page.getByRole('button', { name: /^查询$/ }).last().click();
    await expect(page.getByText('当前资讯分组暂无数据')).toBeVisible();

    await gotoReady(page, '/macro', '宏观经济数据分析');
    await expect(page.getByText('常用宏观入口')).toBeVisible();
    await expect(page.getByText('当前指标暂无可用历史数据')).toBeVisible();
    output.push(await shot(page, `macro-p4-${DATE_TAG}.png`));

    await gotoReady(page, '/options', '期权全景分析');
    await expect(page.getByText('当前标的暂无期权链数据')).toBeVisible();
    await expect(page.getByText('当前暂无 Greeks 数据')).toBeVisible();
    output.push(await shot(page, `options-p4-${DATE_TAG}.png`));
  } finally {
    await context.close();
    await browser.close();
  }

  console.log(JSON.stringify({ ok: true, screenshots: output }, null, 2));
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

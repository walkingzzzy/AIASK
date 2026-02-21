#!/usr/bin/env node

/**
 * Week2 最小 e2e：登录 -> 行情扩展/基本面/研报/告警 -> 鉴权与审计校验
 * 运行前提：BFF 已启动（默认 http://127.0.0.1:3001/api）
 */

const baseUrl = process.env.BFF_BASE_URL || 'http://127.0.0.1:3001/api';
const user = process.env.E2E_USER || 'demo';
const pass = process.env.E2E_PASS || 'demo123';
const admin = process.env.E2E_ADMIN || 'admin';
const adminPass = process.env.E2E_ADMIN_PASS || 'admin123';
const stockCode = process.env.E2E_STOCK_CODE || '600519';

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

async function requestJson(url, options = {}) {
  const res = await fetch(url, { cache: 'no-store', ...options });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  return { res, data };
}

async function login(username, password) {
  const { res, data } = await requestJson(`${baseUrl}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  assert(res.ok, `登录失败(${username}): HTTP ${res.status} ${JSON.stringify(data)}`);
  const authData = data?.data && typeof data.data === 'object' ? data.data : data;
  assert(authData?.accessToken, `登录返回缺少 accessToken(${username})`);
  return authData.accessToken;
}

async function getProtected(path, token) {
  return requestJson(`${baseUrl}${path}`, {
    method: 'GET',
    headers: token ? { authorization: `Bearer ${token}` } : {},
  });
}

async function run() {
  console.log(`[e2e-week2] startedAt=${new Date().toISOString()} baseUrl=${baseUrl}`);

  const unauth = await getProtected(`/fundamental/overview?code=${stockCode}`);
  assert(unauth.res.status === 401, `未登录访问应为401，实际=${unauth.res.status}`);

  const token = await login(user, pass);

  const quote = await getProtected(`/market/quote?code=${stockCode}`, token);
  assert(quote.res.ok && quote.data?.success === true, `quote 失败: ${quote.res.status}`);
  assert(quote.data?.data?.quote, `quote 返回缺少 data.quote`);

  const kline = await getProtected(`/market/kline?code=${stockCode}&period=daily`, token);
  assert(kline.res.ok && kline.data?.success === true, `kline 失败: ${kline.res.status}`);
  assert(kline.data?.data?.kline, `kline 返回缺少 data.kline`);

  const klineWeekly = await getProtected(`/market/kline?code=${stockCode}&period=weekly`, token);
  assert(klineWeekly.res.ok && klineWeekly.data?.success === true, `kline weekly 失败: ${klineWeekly.res.status}`);

  const klineMonthly = await getProtected(`/market/kline?code=${stockCode}&period=monthly`, token);
  assert(klineMonthly.res.ok && klineMonthly.data?.success === true, `kline monthly 失败: ${klineMonthly.res.status}`);

  const orderBook = await getProtected(`/market/order-book?code=${stockCode}`, token);
  assert(orderBook.res.ok && orderBook.data?.success === true, `order-book 失败: ${orderBook.res.status}`);
  assert(orderBook.data?.data?.orderBook, `order-book 返回缺少 data.orderBook`);

  const fundamental = await getProtected(`/fundamental/overview?code=${stockCode}`, token);
  assert(fundamental.res.ok && fundamental.data?.success === true, `fundamental 失败: ${fundamental.res.status}`);
  assert(fundamental.data?.data?.financials !== undefined, 'fundamental 返回缺少 financials');
  assert(fundamental.data?.data?.valuation !== undefined, 'fundamental 返回缺少 valuation');

  const fundamentalHistory = await getProtected(`/fundamental/history?code=${stockCode}&days=90`, token);
  assert(
    fundamentalHistory.res.ok && fundamentalHistory.data?.success === true,
    `fundamental history 失败: ${fundamentalHistory.res.status}`,
  );
  assert(Array.isArray(fundamentalHistory.data?.data?.points), 'fundamental history 返回缺少 points 数组');

  const research = await getProtected(`/research/list?code=${stockCode}`, token);
  assert(research.res.ok && research.data?.success === true, `research 失败: ${research.res.status}`);
  assert(Array.isArray(research.data?.data?.reports), 'research 返回缺少 reports 数组');
  assert(Array.isArray(research.data?.data?.notices), 'research 返回缺少 notices 数组');

  const researchByDays = await getProtected(`/research/list?code=${stockCode}&days=7&keyword=业绩`, token);
  assert(
    researchByDays.res.ok && researchByDays.data?.success === true,
    `research days/keyword 失败: ${researchByDays.res.status}`,
  );

  const researchCustomRange = await getProtected(
    `/research/list?code=${stockCode}&startDate=2026-01-01&endDate=2026-02-19&keyword=公告`,
    token,
  );
  assert(
    researchCustomRange.res.ok && researchCustomRange.data?.success === true,
    `research custom range 失败: ${researchCustomRange.res.status}`,
  );

  const alertCreate = await requestJson(`${baseUrl}/alerts/create`, {
    method: 'POST',
    headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    body: JSON.stringify({ code: stockCode, indicator: 'price', condition: '>', value: '1' }),
  });
  assert(
    alertCreate.res.ok && alertCreate.data?.success === true,
    `alerts create 失败: ${alertCreate.res.status} ${JSON.stringify(alertCreate.data)}`,
  );

  const alertList = await getProtected('/alerts/list?status=all', token);
  assert(alertList.res.ok && alertList.data?.success === true, `alerts list 失败: ${alertList.res.status}`);
  assert(Array.isArray(alertList.data?.data?.items), 'alerts list 返回缺少 data.items 数组');

  const alertId =
    alertCreate.data?.data?.alertId ||
    alertCreate.data?.data?.result?.data?.alert_id ||
    alertCreate.data?.data?.result?.data?.id ||
    alertCreate.data?.data?.result?.alert_id ||
    alertCreate.data?.data?.result?.id;
  if (alertId) {
    const alertDelete = await requestJson(
      `${baseUrl}/alerts/delete?alertId=${encodeURIComponent(String(alertId))}`,
      {
        method: 'DELETE',
        headers: { authorization: `Bearer ${token}` },
      },
    );
    assert(
      alertDelete.res.ok && alertDelete.data?.success === true,
      `alerts delete 失败: ${alertDelete.res.status} ${JSON.stringify(alertDelete.data)}`,
    );
  }

  const adminToken = await login(admin, adminPass);
  const logs = await getProtected('/audit/logs?limit=200', adminToken);
  assert(logs.res.ok, `audit 查询失败: HTTP ${logs.res.status}`);
  const items = logs.data?.data?.items;
  assert(Array.isArray(items), 'audit 返回缺少 data.items');

  const requiredPaths = [
    '/api/market/kline',
    '/api/market/order-book',
    '/api/fundamental/overview',
    '/api/research/list',
    '/api/alerts/create',
    '/api/alerts/list',
    '/api/alerts/delete',
  ];
  for (const p of requiredPaths) {
    const hit = items.find((it) => typeof it?.path === 'string' && it.path.includes(p));
    assert(hit, `审计日志缺少 ${p}`);
  }

  console.log('[e2e-week2] PASS');
  console.log(
    JSON.stringify(
      {
        quoteTool: quote.data?.data?.tool,
        klineTool: kline.data?.data?.tool,
        orderBookTool: orderBook.data?.data?.tool,
        fundamentalTools: fundamental.data?.data?.sourceTools,
        researchTools: research.data?.data?.sourceTools,
      },
      null,
      2,
    ),
  );
}

run().catch((err) => {
  console.error('[e2e-week2] FAIL', err?.message || err);
  process.exitCode = 1;
});


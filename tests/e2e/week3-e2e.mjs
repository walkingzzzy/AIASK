#!/usr/bin/env node

/**
 * Week3 最小 e2e：登录 -> 回测 -> 指标 -> 组合增删查
 */

const baseUrl = process.env.BFF_BASE_URL || 'http://127.0.0.1:3001/api';
const user = process.env.E2E_USER || 'demo';
const pass = process.env.E2E_PASS || 'demo123';
const stockCode = process.env.E2E_STOCK_CODE || '600519';

function assert(cond, msg) { if (!cond) throw new Error(msg); }

async function requestJson(url, options = {}) {
  const res = await fetch(url, { cache: 'no-store', ...options });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  return { res, data };
}

function pick(obj, paths) {
  for (const p of paths) {
    const v = p.split('.').reduce((acc, key) => (acc == null ? undefined : acc[key]), obj);
    if (typeof v === 'string' && v.trim()) return v.trim();
    if (typeof v === 'number' && Number.isFinite(v)) return String(v);
  }
  return '';
}

async function login(username, password) {
  const { res, data } = await requestJson(`${baseUrl}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  assert(res.ok, `登录失败(${username}): HTTP ${res.status}`);
  const authData = data?.data && typeof data.data === 'object' ? data.data : data;
  assert(authData?.accessToken, `登录返回缺少 accessToken(${username})`);
  return authData.accessToken;
}

async function run() {
  console.log(`[e2e-week3] startedAt=${new Date().toISOString()} baseUrl=${baseUrl}`);

  const unauth = await requestJson(`${baseUrl}/backtest/list?limit=5`);
  assert(unauth.res.status === 401, `未登录访问应为401，实际=${unauth.res.status}`);

  const token = await login(user, pass);
  const h = { authorization: `Bearer ${token}` };

  const runBacktest = await requestJson(`${baseUrl}/backtest/run`, {
    method: 'POST',
    headers: { ...h, 'content-type': 'application/json' },
    body: JSON.stringify({ code: stockCode, strategy: 'ma_cross' }),
  });
  assert(runBacktest.res.ok && runBacktest.data?.success === true, `backtest run 失败: ${runBacktest.res.status}`);
  const artifactId = pick(runBacktest.data, ['data.artifactId', 'data.result.data.artifact_id']);
  assert(artifactId, 'backtest run 缺少 artifactId');

  const listBacktest = await requestJson(`${baseUrl}/backtest/list?limit=10`, { headers: h });
  assert(listBacktest.res.ok && listBacktest.data?.success === true, `backtest list 失败: ${listBacktest.res.status}`);

  const metrics = await requestJson(
    `${baseUrl}/backtest/metrics?artifactId=${encodeURIComponent(artifactId)}`,
    { headers: h },
  );
  assert(metrics.res.ok && metrics.data?.success === true, `backtest metrics 失败: ${metrics.res.status}`);

  const createPortfolio = await requestJson(`${baseUrl}/portfolio/create`, {
    method: 'POST',
    headers: { ...h, 'content-type': 'application/json' },
    body: JSON.stringify({ name: `P3-E2E-${Date.now()}`, initialCapital: '100000' }),
  });
  assert(
    createPortfolio.res.ok && createPortfolio.data?.success === true,
    `portfolio create 失败: ${createPortfolio.res.status}`,
  );

  const portfolioId = Number(
    pick(createPortfolio.data, [
      'data.result.data.portfolio_id',
      'data.result.data.id',
      'data.result.portfolio_id',
      'data.result.id',
    ]),
  );

  const listPortfolio = await requestJson(`${baseUrl}/portfolio/list`, { headers: h });
  assert(listPortfolio.res.ok && listPortfolio.data?.success === true, `portfolio list 失败: ${listPortfolio.res.status}`);

  if (Number.isFinite(portfolioId) && portfolioId > 0) {
    const addHolding = await requestJson(`${baseUrl}/portfolio/add-holding`, {
      method: 'POST',
      headers: { ...h, 'content-type': 'application/json' },
      body: JSON.stringify({ portfolioId: String(portfolioId), code: stockCode, shares: '100', costPrice: '1' }),
    });
    assert(addHolding.res.ok && addHolding.data?.success === true, `add holding 失败: ${addHolding.res.status}`);

    const getPortfolio = await requestJson(
      `${baseUrl}/portfolio/get?portfolioId=${encodeURIComponent(String(portfolioId))}`,
      { headers: h },
    );
    assert(getPortfolio.res.ok && getPortfolio.data?.success === true, `portfolio get 失败: ${getPortfolio.res.status}`);

    const removeHolding = await requestJson(
      `${baseUrl}/portfolio/remove-holding?portfolioId=${encodeURIComponent(String(portfolioId))}&code=${stockCode}`,
      { method: 'DELETE', headers: h },
    );
    assert(removeHolding.res.ok && removeHolding.data?.success === true, `remove holding 失败: ${removeHolding.res.status}`);
  }

  console.log('[e2e-week3] PASS');
  console.log(JSON.stringify({ artifactId, portfolioId: Number.isFinite(portfolioId) ? portfolioId : null }, null, 2));
}

run().catch((err) => {
  console.error('[e2e-week3] FAIL', err?.message || err);
  process.exitCode = 1;
});


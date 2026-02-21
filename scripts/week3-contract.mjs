#!/usr/bin/env node

/**
 * Week3 API 合同测试（策略能力）
 * 校验 backtest/portfolio 接口响应外壳与关键字段
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
  assert(res.ok, `登录失败: HTTP ${res.status}`);
  const authData = data?.data && typeof data.data === 'object' ? data.data : data;
  assert(typeof authData?.accessToken === 'string' && authData.accessToken.length > 10, 'accessToken 合同不满足');
  return authData.accessToken;
}

function assertEnvelope(result, path) {
  assert(result.res.ok, `${path} HTTP ${result.res.status}`);
  assert(typeof result.data === 'object' && result.data !== null, `${path} 响应必须为对象`);
  assert(typeof result.data.success === 'boolean', `${path} 缺少 success:boolean`);
  assert(typeof result.data.traceId === 'string', `${path} 缺少 traceId:string`);
  assert('data' in result.data, `${path} 缺少 data 字段`);
}

async function run() {
  console.log(`[contract-week3] startedAt=${new Date().toISOString()} baseUrl=${baseUrl}`);
  const token = await login(user, pass);
  const authHeader = { authorization: `Bearer ${token}` };

  const runBacktest = await requestJson(`${baseUrl}/backtest/run`, {
    method: 'POST',
    headers: { ...authHeader, 'content-type': 'application/json' },
    body: JSON.stringify({ code: stockCode, strategy: 'ma_cross' }),
  });
  assertEnvelope(runBacktest, '/backtest/run');
  const artifactId = pick(runBacktest.data, ['data.artifactId', 'data.result.data.artifact_id']);
  assert(artifactId.length > 0, '/backtest/run 缺少 artifactId');

  const listBacktest = await requestJson(`${baseUrl}/backtest/list?limit=5`, { headers: authHeader });
  assertEnvelope(listBacktest, '/backtest/list');

  const metrics = await requestJson(
    `${baseUrl}/backtest/metrics?artifactId=${encodeURIComponent(artifactId)}`,
    { headers: authHeader },
  );
  assertEnvelope(metrics, '/backtest/metrics');

  const createPortfolio = await requestJson(`${baseUrl}/portfolio/create`, {
    method: 'POST',
    headers: { ...authHeader, 'content-type': 'application/json' },
    body: JSON.stringify({ name: `P3-${Date.now()}`, initialCapital: '100000' }),
  });
  assertEnvelope(createPortfolio, '/portfolio/create');

  const listPortfolio = await requestJson(`${baseUrl}/portfolio/list`, { headers: authHeader });
  assertEnvelope(listPortfolio, '/portfolio/list');

  console.log('[contract-week3] PASS');
  console.log(JSON.stringify({ artifactId, portfolioSource: createPortfolio.data?.data?.sourceTool }, null, 2));
}

run().catch((err) => {
  console.error('[contract-week3] FAIL', err?.message || err);
  process.exitCode = 1;
});


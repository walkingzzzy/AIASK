#!/usr/bin/env node

/**
 * Week2 API 合同测试（最小版）
 * 校验响应外壳、关键字段存在性与类型
 */

const baseUrl = process.env.BFF_BASE_URL || 'http://127.0.0.1:3001/api';
const user = process.env.E2E_USER || 'demo';
const pass = process.env.E2E_PASS || 'demo123';
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
  console.log(`[contract-week2] startedAt=${new Date().toISOString()} baseUrl=${baseUrl}`);
  const token = await login(user, pass);

  const authHeader = { authorization: `Bearer ${token}` };

  const quote = await requestJson(`${baseUrl}/market/quote?code=${stockCode}`, { headers: authHeader });
  assertEnvelope(quote, '/market/quote');
  assert(typeof quote.data.data?.tool === 'string', '/market/quote data.tool 类型错误');

  const kline = await requestJson(`${baseUrl}/market/kline?code=${stockCode}&period=daily`, { headers: authHeader });
  assertEnvelope(kline, '/market/kline');
  assert(typeof kline.data.data?.tool === 'string', '/market/kline data.tool 类型错误');

  const fundamental = await requestJson(`${baseUrl}/fundamental/overview?code=${stockCode}`, { headers: authHeader });
  assertEnvelope(fundamental, '/fundamental/overview');
  assert(typeof fundamental.data.data?.sourceTools === 'object', '/fundamental/overview sourceTools 类型错误');

  const research = await requestJson(`${baseUrl}/research/list?code=${stockCode}&days=7&keyword=业绩`, { headers: authHeader });
  assertEnvelope(research, '/research/list');
  assert(Array.isArray(research.data.data?.reports), '/research/list reports 必须是数组');
  assert(Array.isArray(research.data.data?.notices), '/research/list notices 必须是数组');

  const alertsList = await requestJson(`${baseUrl}/alerts/list?status=all`, { headers: authHeader });
  assertEnvelope(alertsList, '/alerts/list');
  assert(Array.isArray(alertsList.data.data?.items), '/alerts/list items 必须是数组');

  console.log('[contract-week2] PASS');
}

run().catch((err) => {
  console.error('[contract-week2] FAIL', err?.message || err);
  process.exitCode = 1;
});


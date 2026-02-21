#!/usr/bin/env node

/**
 * Week4 合同测试：异常边界与契约稳定性
 * - 成功路径仍满足 Envelope: { success, data, traceId }
 * - 非法参数路径返回非2xx，且包含可解析错误信息
 * - week4.1: 覆盖超大 lookback 裁剪 + injectFail 单子失败注入
 */

const baseUrl = process.env.BFF_BASE_URL || 'http://127.0.0.1:3001/api';
const user = process.env.E2E_USER || 'demo';
const pass = process.env.E2E_PASS || 'demo123';

function assert(cond, msg) { if (!cond) throw new Error(msg); }

async function requestJson(url, options = {}) {
  const res = await fetch(url, { cache: 'no-store', ...options });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  return { res, data };
}

function assertEnvelope(result, path) {
  assert(result.res.ok, `${path} HTTP ${result.res.status}`);
  assert(typeof result.data === 'object' && result.data !== null, `${path} 响应必须为对象`);
  assert(typeof result.data.success === 'boolean', `${path} 缺少 success:boolean`);
  assert(typeof result.data.traceId === 'string', `${path} 缺少 traceId:string`);
  assert('data' in result.data, `${path} 缺少 data 字段`);
}

function assertErrorShape(result, path) {
  assert(!result.res.ok, `${path} 预期非2xx，实际=${result.res.status}`);
  assert(typeof result.data === 'object' && result.data !== null, `${path} 错误响应必须为对象`);
  const hasMessage =
    typeof result.data.message === 'string' ||
    Array.isArray(result.data.message) ||
    typeof result.data.error === 'string' ||
    typeof result.data.detail === 'string' ||
    typeof result.data?.error?.message === 'string' ||
    Array.isArray(result.data?.error?.message);
  assert(hasMessage, `${path} 错误响应缺少 message/error/detail`);
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

async function run() {
  console.log(`[contract-week4] startedAt=${new Date().toISOString()} baseUrl=${baseUrl}`);
  const token = await login(user, pass);
  const h = { authorization: `Bearer ${token}` };

  // 成功契约（仍需稳定）
  const btList = await requestJson(`${baseUrl}/backtest/list?limit=5`, { headers: h });
  assertEnvelope(btList, '/backtest/list');

  const pfList = await requestJson(`${baseUrl}/portfolio/list`, { headers: h });
  assertEnvelope(pfList, '/portfolio/list');

  const riskSummary = await requestJson(`${baseUrl}/risk/summary?lookbackDays=252`, { headers: h });
  assertEnvelope(riskSummary, '/risk/summary');
  assert(typeof riskSummary.data.data?.degraded === 'boolean', '/risk/summary 缺少 degraded:boolean');

  const riskHugeLookback = await requestJson(`${baseUrl}/risk/summary?lookbackDays=999999`, { headers: h });
  assertEnvelope(riskHugeLookback, '/risk/summary?lookbackDays=999999');
  assert(Number(riskHugeLookback.data?.data?.lookbackDays) === 2000, 'lookbackDays 超大值应裁剪为 2000');

  const injectedStressFail = await requestJson(`${baseUrl}/risk/summary?lookbackDays=252&injectFail=stress`, { headers: h });
  assertEnvelope(injectedStressFail, '/risk/summary?injectFail=stress');
  assert(injectedStressFail.data?.data?.degraded === true, 'injectFail=stress 时应 degraded=true');

  // 异常边界契约
  const badPortfolioId = await requestJson(`${baseUrl}/portfolio/get?portfolioId=abc`, { headers: h });
  assertErrorShape(badPortfolioId, '/portfolio/get?portfolioId=abc');

  const badRiskPortfolioId = await requestJson(`${baseUrl}/risk/summary?portfolioId=abc&lookbackDays=252`, { headers: h });
  assertErrorShape(badRiskPortfolioId, '/risk/summary?portfolioId=abc');

  const missingArtifact = await requestJson(`${baseUrl}/backtest/metrics`, { headers: h });
  assertErrorShape(missingArtifact, '/backtest/metrics(no artifactId)');

  const badAddHolding = await requestJson(`${baseUrl}/portfolio/add-holding`, {
    method: 'POST',
    headers: { ...h, 'content-type': 'application/json' },
    body: JSON.stringify({ portfolioId: '1', code: 'BAD', shares: '100', costPrice: '1' }),
  });
  assertErrorShape(badAddHolding, '/portfolio/add-holding(invalid code)');

  const badRiskDays = await requestJson(`${baseUrl}/risk/summary?lookbackDays=abc`, { headers: h });
  assertErrorShape(badRiskDays, '/risk/summary?lookbackDays=abc');

  console.log('[contract-week4] PASS');
  console.log(JSON.stringify({
    badPortfolioIdStatus: badPortfolioId.res.status,
    badRiskPortfolioIdStatus: badRiskPortfolioId.res.status,
    missingArtifactStatus: missingArtifact.res.status,
    badAddHoldingStatus: badAddHolding.res.status,
    badRiskDaysStatus: badRiskDays.res.status,
    riskSummaryDegraded: riskSummary.data.data?.degraded,
    hugeLookbackDays: riskHugeLookback.data?.data?.lookbackDays,
    injectedStressDegraded: injectedStressFail.data?.data?.degraded,
  }, null, 2));
}

run().catch((err) => {
  console.error('[contract-week4] FAIL', err?.message || err);
  process.exitCode = 1;
});


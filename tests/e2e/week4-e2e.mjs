#!/usr/bin/env node

/**
 * Week4 E2E：异常边界 + 恢复路径
 * 流程：未登录401 -> 错误token401 -> 登录 -> 成功列表 -> week4.1 扩展边界校验
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

async function login(username, password) {
  const { res, data } = await requestJson(`${baseUrl}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  assert(res.ok, `登录失败: HTTP ${res.status}`);
  const authData = data?.data && typeof data.data === 'object' ? data.data : data;
  assert(typeof authData?.accessToken === 'string' && authData.accessToken.length > 10, 'accessToken 缺失或无效');
  return authData.accessToken;
}

function assertBadRequestLike(result, name) {
  assert(!result.res.ok, `${name} 预期失败，实际 HTTP ${result.res.status}`);
  assert(typeof result.data === 'object' && result.data !== null, `${name} 错误响应不可解析`);
  const ok =
    typeof result.data.message === 'string' ||
    Array.isArray(result.data.message) ||
    typeof result.data.error === 'string' ||
    typeof result.data.detail === 'string' ||
    typeof result.data?.error?.message === 'string' ||
    Array.isArray(result.data?.error?.message);
  assert(ok, `${name} 错误结构缺少 message/error/detail`);
}

async function run() {
  console.log(`[e2e-week4] startedAt=${new Date().toISOString()} baseUrl=${baseUrl}`);

  const unauth = await requestJson(`${baseUrl}/portfolio/list`);
  assert(unauth.res.status === 401, `未登录访问应为401，实际=${unauth.res.status}`);

  const wrongToken = await requestJson(`${baseUrl}/portfolio/list`, {
    headers: { authorization: 'Bearer INVALID_TOKEN_FOR_WEEK4' },
  });
  assert(wrongToken.res.status === 401, `错误token访问应为401，实际=${wrongToken.res.status}`);

  const token = await login(user, pass);
  const h = { authorization: `Bearer ${token}` };

  const okList = await requestJson(`${baseUrl}/portfolio/list`, { headers: h });
  assert(okList.res.ok && okList.data?.success === true, `登录后 portfolio/list 应成功，实际=${okList.res.status}`);

  const okRisk = await requestJson(`${baseUrl}/risk/summary?lookbackDays=252`, { headers: h });
  assert(okRisk.res.ok && okRisk.data?.success === true, `登录后 risk/summary 应成功，实际=${okRisk.res.status}`);
  assert(typeof okRisk.data?.data?.degraded === 'boolean', 'risk/summary 缺少 degraded:boolean');

  const hugeLookback = await requestJson(`${baseUrl}/risk/summary?lookbackDays=999999`, { headers: h });
  assert(hugeLookback.res.ok && hugeLookback.data?.success === true, `超大 lookback 应可处理，实际=${hugeLookback.res.status}`);
  assert(Number(hugeLookback.data?.data?.lookbackDays) === 2000, '超大 lookbackDays 应裁剪为 2000');

  const injectedFail = await requestJson(`${baseUrl}/risk/summary?lookbackDays=252&injectFail=exposure`, { headers: h });
  assert(injectedFail.res.ok && injectedFail.data?.success === true, `injectFail 仍应返回成功信封，实际=${injectedFail.res.status}`);
  assert(injectedFail.data?.data?.degraded === true, 'injectFail=exposure 时应 degraded=true');

  const missingArtifact = await requestJson(`${baseUrl}/backtest/metrics`, { headers: h });
  assertBadRequestLike(missingArtifact, 'backtest/metrics 缺少 artifactId');

  const badPortfolioId = await requestJson(`${baseUrl}/portfolio/get?portfolioId=abc`, { headers: h });
  assertBadRequestLike(badPortfolioId, 'portfolio/get 非法 portfolioId');

  const badRiskPortfolioId = await requestJson(`${baseUrl}/risk/summary?portfolioId=abc&lookbackDays=252`, { headers: h });
  assertBadRequestLike(badRiskPortfolioId, 'risk/summary 非法 portfolioId');

  const badAddHolding = await requestJson(`${baseUrl}/portfolio/add-holding`, {
    method: 'POST',
    headers: { ...h, 'content-type': 'application/json' },
    body: JSON.stringify({ portfolioId: '1', code: 'BAD', shares: '100', costPrice: '1' }),
  });
  assertBadRequestLike(badAddHolding, 'portfolio/add-holding 非法 code');

  const badRiskDays = await requestJson(`${baseUrl}/risk/summary?lookbackDays=abc`, { headers: h });
  assertBadRequestLike(badRiskDays, 'risk/summary 非法 lookbackDays');

  console.log('[e2e-week4] PASS');
  console.log(JSON.stringify({
    unauthStatus: unauth.res.status,
    wrongTokenStatus: wrongToken.res.status,
    okRiskDegraded: okRisk.data?.data?.degraded,
    hugeLookbackDays: hugeLookback.data?.data?.lookbackDays,
    injectedExposureDegraded: injectedFail.data?.data?.degraded,
    missingArtifactStatus: missingArtifact.res.status,
    badPortfolioIdStatus: badPortfolioId.res.status,
    badRiskPortfolioIdStatus: badRiskPortfolioId.res.status,
    badAddHoldingStatus: badAddHolding.res.status,
    badRiskDaysStatus: badRiskDays.res.status,
  }, null, 2));
}

run().catch((err) => {
  console.error('[e2e-week4] FAIL', err?.message || err);
  process.exitCode = 1;
});


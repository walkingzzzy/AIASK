#!/usr/bin/env node

/**
 * Week1 最小 e2e：登录 -> 查行情 -> 审计校验
 *
 * 运行前提：BFF 已启动（默认 http://127.0.0.1:3001/api）
 * 用法：
 *   node scripts/week1-e2e.mjs
 * 环境变量：
 *   BFF_BASE_URL=http://127.0.0.1:3001/api
 *   E2E_USER=demo
 *   E2E_PASS=demo123
 *   E2E_ADMIN=admin
 *   E2E_ADMIN_PASS=admin123
 *   E2E_STOCK_CODE=600519
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

async function postJson(url, body, token) {
  const headers = { 'content-type': 'application/json' };
  if (token) headers.authorization = `Bearer ${token}`;
  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    cache: 'no-store',
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  return { res, data };
}

async function getJson(url, token) {
  const headers = {};
  if (token) headers.authorization = `Bearer ${token}`;
  const res = await fetch(url, { method: 'GET', headers, cache: 'no-store' });
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
  const { res, data } = await postJson(`${baseUrl}/auth/login`, { username, password });
  assert(res.ok, `登录失败(${username}): HTTP ${res.status} ${JSON.stringify(data)}`);
  const authData = data?.data && typeof data.data === 'object' ? data.data : data;
  assert(authData?.accessToken, `登录返回缺少 accessToken(${username})`);
  return authData.accessToken;
}

async function run() {
  const startedAt = new Date().toISOString();
  console.log(`[e2e] startedAt=${startedAt} baseUrl=${baseUrl}`);

  const userToken = await login(user, pass);

  const quoteResp = await getJson(
    `${baseUrl}/market/quote?code=${encodeURIComponent(stockCode)}`,
    userToken,
  );
  assert(quoteResp.res.ok, `行情接口失败: HTTP ${quoteResp.res.status} ${JSON.stringify(quoteResp.data)}`);
  const quotePayload = quoteResp.data?.data;
  assert(
    quotePayload && typeof quotePayload === 'object' && 'quote' in quotePayload,
    `行情返回不符合 DTO，期望包含 data.quote 字段，实际=${JSON.stringify(quoteResp.data)}`,
  );

  const adminToken = await login(admin, adminPass);
  const logsResp = await getJson(`${baseUrl}/audit/logs?limit=100`, adminToken);
  assert(logsResp.res.ok, `审计查询失败: HTTP ${logsResp.res.status} ${JSON.stringify(logsResp.data)}`);

  const items = logsResp.data?.data?.items;
  assert(Array.isArray(items), `审计返回缺少 data.items 数组: ${JSON.stringify(logsResp.data)}`);

  const quoteAudit = items.find(
    (it) =>
      typeof it?.path === 'string' &&
      it.path.includes('/api/market/quote') &&
      typeof it?.status === 'number',
  );

  assert(quoteAudit, '未在审计日志中找到 /api/market/quote 记录');

  console.log('[e2e] PASS');
  console.log(
    JSON.stringify(
      {
        quoteTool: quotePayload?.tool,
        quoteArgsMatched: quotePayload?.argsMatched,
        auditMatched: {
          trace_id: quoteAudit.trace_id,
          path: quoteAudit.path,
          status: quoteAudit.status,
          duration_ms: quoteAudit.duration_ms,
          ts: quoteAudit.ts,
        },
      },
      null,
      2,
    ),
  );
}

run().catch((err) => {
  console.error('[e2e] FAIL', err?.message || err);
  process.exitCode = 1;
});


#!/usr/bin/env node

const args = new Map();
for (const raw of process.argv.slice(2)) {
  const [key, ...rest] = raw.split('=');
  if (!key.startsWith('--')) continue;
  args.set(key.slice(2), rest.length ? rest.join('=') : 'true');
}

const baseUrl = String(args.get('base-url') || process.env.BFF_BASE_URL || 'http://127.0.0.1:3001/api').replace(/\/$/, '');
const token = String(args.get('token') || process.env.BFF_BEARER_TOKEN || '').trim();
const cookie = String(args.get('cookie') || process.env.BFF_COOKIE || '').trim();
const username = String(args.get('username') || process.env.BFF_BENCH_USERNAME || 'demo').trim();
const password = String(args.get('password') || process.env.BFF_BENCH_PASSWORD || 'demo123').trim();
const code = String(args.get('code') || '600519').trim();
const investmentStyle = String(args.get('style') || 'balanced').trim();
const endpoint = String(args.get('endpoint') || '/assistant/unified-decision').trim();
const runs = Math.max(1, Number(args.get('runs') || '5'));
const legacyMode = String(args.get('legacy-mode') || 'false').trim() === 'true';

function collectCookies(response) {
  const headers = response.headers;
  const values = typeof headers.getSetCookie === 'function'
    ? headers.getSetCookie()
    : [headers.get('set-cookie')].filter(Boolean);

  return values.map((value) => value.split(';', 1)[0]).join('; ');
}

async function resolveAuthHeaders() {
  if (token) {
    return {
      authMode: 'bearer',
      headers: {
        authorization: `Bearer ${token}`,
      },
    };
  }

  if (cookie) {
    return {
      authMode: 'cookie',
      headers: {
        cookie,
      },
    };
  }

  if (!username || !password) {
    console.error('缺少认证信息。请提供 Bearer token、cookie，或 username/password。');
    process.exit(1);
  }

  const loginResponse = await fetch(`${baseUrl}/auth/login`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-trace-id': 'bench-login',
    },
    body: JSON.stringify({ username, password }),
  });

  if (!loginResponse.ok) {
    const payload = await loginResponse.text().catch(() => '');
    console.error(`登录失败: HTTP ${loginResponse.status} ${payload}`);
    process.exit(1);
  }

  const loginCookie = collectCookies(loginResponse);
  if (!loginCookie) {
    console.error('登录成功但未收到 cookie，无法执行基准测试。');
    process.exit(1);
  }

  return {
    authMode: 'cookie-login',
    headers: {
      cookie: loginCookie,
    },
  };
}

function percentile(sorted, p) {
  if (!sorted.length) return 0;
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * p) - 1));
  return sorted[index];
}

async function runOnce(index, authHeaders) {
  const startedAt = performance.now();
  const response = await fetch(`${baseUrl}${endpoint}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-trace-id': `bench-${Date.now()}-${index}`,
      ...authHeaders,
    },
    body: JSON.stringify({ code, investmentStyle, legacyMode }),
  });
  const durationMs = performance.now() - startedAt;
  const payload = await response.json().catch(() => ({}));
  return {
    ok: response.ok && payload?.success !== false,
    status: response.status,
    durationMs,
    traceId: payload?.traceId ?? null,
    message: payload?.message ?? null,
  };
}

async function main() {
  const auth = await resolveAuthHeaders();
  const rows = [];
  for (let i = 0; i < runs; i += 1) {
    // Keep the benchmark deterministic and easy to compare across runs.
    rows.push(await runOnce(i + 1, auth.headers));
  }

  const durations = rows.map((item) => item.durationMs).sort((a, b) => a - b);
  const failures = rows.filter((item) => !item.ok);
  const avg = durations.reduce((sum, value) => sum + value, 0) / durations.length;

  console.log(JSON.stringify({
    target: {
      baseUrl,
      endpoint,
      code,
      investmentStyle,
      legacyMode,
      runs,
      authMode: auth.authMode,
    },
    summary: {
      successCount: rows.length - failures.length,
      failureCount: failures.length,
      avgMs: Number(avg.toFixed(2)),
      minMs: Number((durations[0] || 0).toFixed(2)),
      p50Ms: Number(percentile(durations, 0.5).toFixed(2)),
      p95Ms: Number(percentile(durations, 0.95).toFixed(2)),
      maxMs: Number((durations[durations.length - 1] || 0).toFixed(2)),
    },
    runs: rows.map((item, index) => ({
      run: index + 1,
      ok: item.ok,
      status: item.status,
      durationMs: Number(item.durationMs.toFixed(2)),
      traceId: item.traceId,
      message: item.message,
    })),
  }, null, 2));

  if (failures.length) {
    process.exit(2);
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});

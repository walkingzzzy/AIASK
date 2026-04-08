import fs from 'node:fs/promises';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import process from 'node:process';
import { request } from '@playwright/test';
import { io } from 'socket.io-client';

const BFF_PORT = Number(process.env.BFF_PORT || 3001);
const BFF_BASE_URL = process.env.BFF_BASE_URL || `http://127.0.0.1:${BFF_PORT}/api`;
const BFF_ORIGIN = BFF_BASE_URL.replace(/\/api$/, '');
const DEFAULT_OUTPUT_DIR = path.resolve(process.cwd(), 'reports/aiask_e2e');

const AUTH_CREDENTIALS = [
  { username: process.env.E2E_AUTH_USERNAME || 'admin', password: process.env.E2E_AUTH_PASSWORD || 'admin' },
  { username: 'admin', password: 'admin123' },
  { username: 'demo', password: 'demo123' },
];

const MODULE_PROBES = [
  { module: 'AppModule', method: 'GET', path: '/health/ready', assertPaths: ['data.mcp.reachable'] },
  { module: 'HealthModule', method: 'GET', path: '/health', assertPaths: ['status'] },
  { module: 'DbModule', method: 'GET', path: '/health/db', assertPaths: ['data.mode'] },
  { module: 'CommonCacheModule', method: 'GET', path: '/admin/cache-stats', auth: true, assertPaths: ['data.bff'] },
  { module: 'McpGatewayModule', method: 'GET', path: '/health/mcp', assertPaths: ['data.mcp.reachable'] },
  { module: 'AuthModule', method: 'GET', path: '/auth/profile', auth: true, assertPaths: ['data.username'] },
  { module: 'MarketModule', method: 'GET', path: '/market/quote?code=600519', assertPaths: ['data.quote'] },
  { module: 'FundamentalModule', method: 'GET', path: '/fundamental/overview?code=600519', assertPaths: ['data'] },
  { module: 'ResearchModule', method: 'GET', path: '/research/market-news?limit=5', assertPaths: ['data'] },
  { module: 'AlertsModule', method: 'GET', path: '/alerts/list', auth: true, assertPaths: ['data'] },
  {
    module: 'BacktestModule',
    method: 'POST',
    path: '/backtest/run',
    body: {
      code: '600519',
      strategy: 'ma_cross',
      startDate: '2025-01-01',
      endDate: '2025-03-31',
    },
    assertPaths: ['data'],
  },
  { module: 'PortfolioModule', method: 'GET', path: '/portfolio/list', auth: true, assertPaths: ['data'] },
  { module: 'RiskModule', method: 'GET', path: '/risk/summary?lookbackDays=30', auth: true, assertPaths: ['data'] },
  { module: 'FundFlowModule', method: 'GET', path: '/fund-flow/north', assertPaths: ['data'] },
  { module: 'FactorModule', method: 'GET', path: '/factor/library', assertPaths: ['data'] },
  {
    module: 'AssistantModule',
    method: 'POST',
    path: '/assistant/unified-decision',
    auth: true,
    body: { code: '600519', investmentStyle: 'balanced' },
    assertPaths: ['data'],
  },
  { module: 'ValuationModule', method: 'GET', path: '/valuation/overview?code=600519', assertPaths: ['data'] },
  { module: 'TechnicalModule', method: 'GET', path: '/technical/available-patterns', assertPaths: ['data'] },
  { module: 'SentimentModule', method: 'GET', path: '/sentiment/fear-greed', assertPaths: ['data'] },
  { module: 'SearchModule', method: 'GET', path: '/search/semantic?query=%E7%99%BD%E9%85%92&limit=5', assertPaths: ['data'] },
  { module: 'DataModule', method: 'GET', path: '/data/tool-catalog', assertPaths: ['data'] },
  { module: 'ChatModule', method: 'GET', path: '/chat/config', auth: true, assertPaths: ['data'] },
  { module: 'AuditModule', method: 'GET', path: '/audit/my-logs', auth: true, assertPaths: ['data'] },
  { module: 'StrategyModule', method: 'GET', path: '/strategy-market/capabilities', auth: true, assertPaths: ['data'] },
  { module: 'PaperTradingModule', method: 'GET', path: '/paper-trading/accounts', auth: true, assertPaths: ['data'] },
  { module: 'OptionsModule', method: 'GET', path: '/v1/options/chain/510050', auth: true, assertPaths: ['success', 'data'] },
  { module: 'MacroModule', method: 'GET', path: '/v1/macro/indicator/cpi', auth: true, assertPaths: ['success', 'data'] },
  { module: 'ScreenerModule', method: 'GET', path: '/v1/screener/semantic?q=%E7%99%BD%E9%85%92&limit=5', auth: true, assertPaths: ['success', 'data'] },
  { module: 'SkillsModule', method: 'GET', path: '/v1/skills', auth: true, assertPaths: ['data'] },
  { module: 'WatchlistModule', method: 'GET', path: '/watchlist/groups', auth: true, assertPaths: ['data'] },
  { module: 'NotificationModule', method: 'GET', path: '/notifications/list', auth: true, assertPaths: ['data'] },
  { module: 'EventModule', method: 'GET', path: '/event/calendar', auth: true, assertPaths: ['data'] },
  { module: 'ExecutionModule', method: 'GET', path: '/execution/workbench', auth: true, assertPaths: ['data'] },
  { module: 'PerformanceModule', method: 'GET', path: '/performance/attribution?lookbackDays=30', auth: true, assertPaths: ['data'] },
  { module: 'WorkspaceModule', method: 'GET', path: '/workspace/state', auth: true, assertPaths: ['data'] },
  { module: 'ExportModule', method: 'GET', path: '/export/report?period=monthly', auth: true, assertPaths: ['data'] },
  { module: 'AdminModule', method: 'GET', path: '/admin/users', auth: true, assertPaths: ['data.items'] },
];

const WS_PROBES = [
  { module: 'WsModule', namespace: '/ws', eventName: 'subscribe:quote', eventPayload: { codes: ['600519'], type: 'stock' } },
  { module: 'PaperTradingWsNamespace', namespace: '/paper-trading', requiresAccountId: true },
];

function parseArgs(argv) {
  const args = { outputDir: DEFAULT_OUTPUT_DIR };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--output-dir' && argv[index + 1]) {
      args.outputDir = path.resolve(argv[index + 1]);
      index += 1;
    }
  }
  return args;
}

function getValueAtPath(value, dottedPath) {
  return dottedPath.split('.').reduce((current, segment) => {
    if (current == null || typeof current !== 'object') return undefined;
    return current[segment];
  }, value);
}

function summarizePayload(payload) {
  try {
    const text = JSON.stringify(payload);
    return text.length > 400 ? `${text.slice(0, 400)}...` : text;
  } catch {
    return String(payload);
  }
}

function toApiUrl(inputPath) {
  const normalizedBase = BFF_BASE_URL.endsWith('/') ? BFF_BASE_URL : `${BFF_BASE_URL}/`;
  const normalizedPath = String(inputPath || '').replace(/^\/+/, '');
  return new URL(normalizedPath, normalizedBase).toString();
}

async function login(api) {
  const attempts = [];
  for (const credentials of AUTH_CREDENTIALS) {
    const response = await api.post(toApiUrl('/auth/login'), {
      headers: { 'content-type': 'application/json' },
      data: credentials,
    });
    const body = await response.json().catch(() => null);
    if (response.ok() && body?.success) {
      return { credentials, body };
    }
    attempts.push({
      username: credentials.username,
      status: response.status(),
      body,
    });
  }
  throw new Error(`BFF 登录失败: ${JSON.stringify(attempts)}`);
}

async function runHttpProbe(api, probe) {
  const startedAt = performance.now();
  const response = await api.fetch(toApiUrl(probe.path), {
    method: probe.method,
    headers: probe.body ? { 'content-type': 'application/json' } : undefined,
    data: probe.body,
  });
  const latencyMs = Math.round(performance.now() - startedAt);
  const payload = await response.json().catch(() => null);
  const assertFailures = [];
  for (const dottedPath of probe.assertPaths || []) {
    if (getValueAtPath(payload, dottedPath) === undefined) {
      assertFailures.push(dottedPath);
    }
  }
  const envelopeMatched = Boolean(payload && typeof payload === 'object' && ('success' in payload || 'data' in payload));
  return {
    module: probe.module,
    type: 'http',
    method: probe.method,
    path: probe.path,
    latencyMs,
    statusCode: response.status(),
    ok: response.ok() && assertFailures.length === 0,
    envelopeMatched,
    missingPaths: assertFailures,
    sample: summarizePayload(payload),
  };
}

async function resolveCookieHeader(api) {
  const state = await api.storageState();
  const cookies = Array.isArray(state?.cookies) ? state.cookies : [];
  return cookies
    .filter((cookie) => String(cookie.domain || '').includes('127.0.0.1') || String(cookie.domain || '').includes('localhost'))
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join('; ');
}

async function resolvePaperTradingAccount(api) {
  const response = await api.get(toApiUrl('/paper-trading/accounts'));
  const payload = await response.json().catch(() => null);
  const items = Array.isArray(payload?.data?.accounts)
    ? payload.data.accounts
    : Array.isArray(payload?.data?.items)
      ? payload.data.items
      : Array.isArray(payload?.data)
        ? payload.data
        : [];
  const first = items.find((item) => item && typeof item === 'object');
  return String(first?.id || first?.account_id || '').trim() || null;
}

async function runWsProbe(api, probe) {
  const cookieHeader = await resolveCookieHeader(api);
  const accountId = probe.requiresAccountId ? await resolvePaperTradingAccount(api) : null;
  const startedAt = performance.now();

  return await new Promise((resolve) => {
    const socket = io(`${BFF_ORIGIN}${probe.namespace}`, {
      transports: ['websocket'],
      extraHeaders: cookieHeader ? { Cookie: cookieHeader } : undefined,
      auth: accountId ? { account_id: accountId } : undefined,
      timeout: 10_000,
      reconnection: false,
    });

    let settled = false;
    const finalize = (result) => {
      if (settled) return;
      settled = true;
      try {
        socket.disconnect();
      } catch {
        // ignore disconnect errors
      }
      resolve({
        module: probe.module,
        type: 'ws',
        namespace: probe.namespace,
        latencyMs: Math.round(performance.now() - startedAt),
        ...result,
      });
    };

    const timer = setTimeout(() => {
      finalize({
        ok: false,
        error: 'websocket_timeout',
      });
    }, 12_000);

    socket.on('connect', () => {
      if (probe.eventName) {
        socket.emit(probe.eventName, probe.eventPayload || {});
      }
      clearTimeout(timer);
      setTimeout(() => {
        finalize({
          ok: true,
          details: probe.requiresAccountId ? `connected_with_account=${accountId || 'none'}` : 'connected',
        });
      }, 400);
    });

    socket.on('connect_error', (error) => {
      clearTimeout(timer);
      finalize({
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      });
    });

    socket.on('paper.snapshot.error', (payload) => {
      clearTimeout(timer);
      finalize({
        ok: false,
        error: summarizePayload(payload),
      });
    });
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  await fs.mkdir(args.outputDir, { recursive: true });

  const api = await request.newContext({
    baseURL: BFF_ORIGIN,
    extraHTTPHeaders: { 'x-trace-id': 'bff-module-probe' },
  });

  let auth = null;
  try {
    auth = await login(api);
    const httpResults = [];
    for (const probe of MODULE_PROBES) {
      httpResults.push(await runHttpProbe(api, probe));
    }

    const wsResults = [];
    for (const probe of WS_PROBES) {
      wsResults.push(await runWsProbe(api, probe));
    }

    const moduleResults = [...httpResults, ...wsResults];
    const passedCount = moduleResults.filter((item) => item.ok).length;
    const failed = moduleResults.filter((item) => !item.ok);
    const avgLatencyMs = moduleResults.length
      ? Number((moduleResults.reduce((sum, item) => sum + item.latencyMs, 0) / moduleResults.length).toFixed(2))
      : 0;
    const contractWarnings = httpResults
      .filter((item) => !item.envelopeMatched)
      .map((item) => `${item.module}:${item.path}`);

    const report = {
      executedAt: new Date().toISOString(),
      baseUrl: BFF_BASE_URL,
      auth: {
        username: auth.credentials.username,
      },
      summary: {
        moduleCount: 38,
        httpProbeCount: MODULE_PROBES.length,
        wsProbeCount: WS_PROBES.length,
        totalProbeCount: moduleResults.length,
        passedCount,
        failedCount: failed.length,
        avgLatencyMs,
        contractWarnings,
      },
      modules: moduleResults,
      failures: failed,
    };

    const jsonPath = path.join(args.outputDir, 'bff-module-probe.json');
    const mdPath = path.join(args.outputDir, 'bff-module-probe.md');
    await fs.writeFile(jsonPath, JSON.stringify(report, null, 2), 'utf8');
    await fs.writeFile(
      mdPath,
      [
        '# BFF 模块功能探针',
        '',
        `- 执行时间: ${report.executedAt}`,
        `- BFF: ${report.baseUrl}`,
        `- 模块数: ${report.summary.moduleCount}`,
        `- 通过: ${report.summary.passedCount}`,
        `- 失败: ${report.summary.failedCount}`,
        `- 平均延迟: ${report.summary.avgLatencyMs} ms`,
        '',
        '## 失败列表',
        '',
        ...(failed.length
          ? failed.map((item) => `- ${item.module} ${item.type === 'http' ? item.path : item.namespace}: ${item.error || item.missingPaths?.join(', ') || item.statusCode}`)
          : ['- 无']),
        '',
        '## 契约告警',
        '',
        ...(contractWarnings.length ? contractWarnings.map((item) => `- ${item}`) : ['- 无']),
        '',
      ].join('\n'),
      'utf8',
    );

    console.log(JSON.stringify({
      json: jsonPath,
      markdown: mdPath,
      summary: report.summary,
    }, null, 2));

    await api.dispose();
    process.exit(failed.length === 0 ? 0 : 1);
  } catch (error) {
    await api.dispose();
    console.error(error instanceof Error ? error.stack : String(error));
    process.exit(1);
  }
}

void main();

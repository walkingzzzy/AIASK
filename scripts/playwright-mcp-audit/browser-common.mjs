import fs from 'node:fs/promises';
import path from 'node:path';

export const BREAKPOINTS = [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet-portrait', width: 768, height: 1024 },
  { name: 'tablet-landscape', width: 1024, height: 768 },
  { name: 'desktop', width: 1280, height: 900 },
  { name: 'desktop-wide', width: 1440, height: 900 },
];

export const BUDGET_LIMITS = {
  overview: 2,
  workspace: 3,
  table: 3,
};

const DEFAULT_AUDIT_API_BASE_URL = 'http://127.0.0.1:3000/api/bff';

function normalizeExplicitApiBaseUrl(raw) {
  const trimmed = String(raw || '').trim();
  if (!trimmed) return null;
  try {
    const parsed = new URL(trimmed);
    return parsed.toString().replace(/\/$/, '');
  } catch {
    return null;
  }
}

function normalizeAuditApiBaseUrl(rawBaseUrl) {
  try {
    const parsed = new URL(String(rawBaseUrl || DEFAULT_AUDIT_API_BASE_URL));
    const explicitPort = process.env.PW_AUDIT_API_PORT?.trim();
    if (explicitPort) {
      parsed.port = explicitPort;
      parsed.pathname = '/api';
    } else {
      parsed.pathname = '/api/bff';
    }
    parsed.search = '';
    parsed.hash = '';
    return parsed.toString().replace(/\/$/, '');
  } catch {
    return DEFAULT_AUDIT_API_BASE_URL;
  }
}

export function getAuditApiBaseUrl(baseUrl) {
  const explicit = normalizeExplicitApiBaseUrl(process.env.PW_AUDIT_API_BASE_URL);
  if (explicit) {
    return explicit;
  }
  return normalizeAuditApiBaseUrl(baseUrl);
}

export function resolveAuditApiUrl(baseUrl, targetPath) {
  const rawPath = String(targetPath || '').trim();
  if (!rawPath) {
    return getAuditApiBaseUrl(baseUrl);
  }
  if (/^https?:\/\//i.test(rawPath)) {
    return rawPath;
  }
  if (!rawPath.startsWith('/')) {
    return `${getAuditApiBaseUrl(baseUrl)}/${rawPath}`;
  }
  if (rawPath.startsWith('/api/')) {
    return `${getAuditApiBaseUrl(baseUrl)}${rawPath.slice(4)}`;
  }
  return `${getAuditApiBaseUrl(baseUrl)}${rawPath}`;
}

export async function gotoStable(page, url) {
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!/ERR_ABORTED|interrupted by another navigation|Timeout .*exceeded/i.test(message)) {
      throw error;
    }
  }
  await page.waitForLoadState('domcontentloaded').catch(() => {});
}

export async function dismissOnboarding(page) {
  const skip = page.getByRole('button', { name: '跳过' });
  for (let attempt = 0; attempt < 8; attempt += 1) {
    if (!(await skip.isVisible().catch(() => false))) break;
    await skip.click().catch(() => {});
    await page.waitForTimeout(250);
  }
}

export async function waitForSettledUi(page, delayMs = 900) {
  await page.waitForLoadState('domcontentloaded').catch(() => {});
  await dismissOnboarding(page);
  await page.waitForTimeout(delayMs);
}

function shouldProvisionAuditUser(credentials) {
  const username = String(credentials?.username || '').trim().toLowerCase();
  return /^pw_audit_|^pwaudit|^pwl/.test(username);
}

async function postJson(page, path, payload) {
  return page.evaluate(
    async ({ targetPath, body }) => {
      const response = await fetch(targetPath, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body),
      });
      const raw = await response.text();
      let parsed = null;
      try {
        parsed = raw ? JSON.parse(raw) : null;
      } catch {
        parsed = raw;
      }
      return { ok: response.ok, status: response.status, body: parsed };
    },
    { targetPath: path, body: payload },
  );
}

function readAuthErrorMessage(result) {
  return String(result?.body?.error?.message || result?.body?.message || '').trim();
}

function isTransientAuthCapacityError(result) {
  if (!result || result.ok) return false;
  if (result.status < 500) return false;
  const message = readAuthErrorMessage(result);
  return /too many clients already|db_query_failed|temporarily unavailable|recovery mode|connection terminated unexpectedly|请稍后重试/i.test(message);
}

export async function login(page, baseUrl, credentials) {
  await gotoStable(page, `${baseUrl}/login`);
  let loginResult = null;
  let provisionTried = false;
  const maxAttempts = 5;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    loginResult = await postJson(page, '/api/auth/login', credentials);
    if (loginResult.ok) {
      break;
    }

    if (!provisionTried && loginResult.status === 401 && shouldProvisionAuditUser(credentials)) {
      provisionTried = true;
      const registerResult = await postJson(page, '/api/auth/register', credentials);
      if (!registerResult.ok && registerResult.status !== 409) {
        const registerMessage =
          registerResult.body?.error?.message || registerResult.body?.message || `register failed: HTTP ${registerResult.status}`;
        throw new Error(registerMessage);
      }
      continue;
    }

    if (isTransientAuthCapacityError(loginResult) && attempt < maxAttempts - 1) {
      await page.waitForTimeout(1200 * (attempt + 1));
      continue;
    }

    break;
  }

  if (!loginResult.ok) {
    throw new Error(readAuthErrorMessage(loginResult) || 'login failed');
  }
  await page.evaluate(() => {
    window.localStorage.setItem('onboarding-done', '1');
    document.cookie = 'logged_in=1; Path=/; Max-Age=604800; SameSite=Lax';
  });
  await page.waitForTimeout(600);
}

export async function openProtectedPage(page, baseUrl, targetPath, credentials) {
  await gotoStable(page, `${baseUrl}/login?redirect=${encodeURIComponent(targetPath)}`);
  if (/\/login(?:\?|$)/.test(page.url())) {
    await login(page, baseUrl, credentials);
  }
  await gotoStable(page, `${baseUrl}${targetPath}`);
  await waitForSettledUi(page, 1000);
}

async function fetchJson(page, path, init = {}) {
  return page.evaluate(
    async ({ targetPath, targetInit }) => {
      const response = await fetch(targetPath, {
        credentials: 'include',
        ...targetInit,
        headers: {
          ...(targetInit?.body ? { 'content-type': 'application/json' } : {}),
          ...(targetInit?.headers || {}),
        },
      });
      const text = await response.text();
      let body = null;
      try {
        body = text ? JSON.parse(text) : null;
      } catch {
        body = text;
      }
      return {
        ok: response.ok,
        status: response.status,
        body,
      };
    },
    { targetPath: path, targetInit: init },
  );
}

async function ensureStrategyMarketSample(page, baseUrl) {
  const ranking = await fetchJson(page, resolveAuditApiUrl(baseUrl, '/api/strategy-market/ranking?limit=5'));
  const strategies = Array.isArray(ranking.body?.data?.strategies) ? ranking.body.data.strategies : [];
  const existing = strategies.find((item) => {
    const strategyId = String(item?.id || '').trim();
    return strategyId && strategyId !== '__empty__';
  });
  if (existing?.id) {
    return String(existing.id);
  }

  const create = await fetchJson(page, resolveAuditApiUrl(baseUrl, '/api/strategy-market/create'), {
    method: 'POST',
    body: JSON.stringify({
      name: 'PW 审计样本策略',
      strategy_type: 'momentum',
      description: '供 Playwright 审计与详情页联调使用的稳定样本。',
      params: {
        universe: '沪深300',
        holding_days: 10,
        rebalance: 'weekly',
      },
      factor_weights: {
        trend: 0.68,
        quality: 0.2,
        risk: 0.12,
      },
      tags: ['audit', 'playwright', 'responsive'],
    }),
  });
  const strategyId = String(create.body?.data?.strategy_id || '').trim();
  if (!create.ok || !strategyId) {
    return null;
  }

  return strategyId;
}

async function readLatestAuditStrategyId() {
  const artifactsDir = path.join(process.cwd(), 'artifacts');
  let entries = [];
  try {
    entries = await fs.readdir(artifactsDir, { withFileTypes: true });
  } catch {
    return null;
  }

  const stateSmokeDirs = entries
    .filter((entry) => entry.isDirectory() && entry.name.startsWith('state-smoke-'))
    .map((entry) => entry.name)
    .sort()
    .reverse();

  for (const dirName of stateSmokeDirs) {
    const resultPath = path.join(artifactsDir, dirName, 'state-smoke-results.json');
    try {
      const payload = JSON.parse(await fs.readFile(resultPath, 'utf8'));
      const strategyId = String(
        payload?.snapshots?.strategyDetail?.strategy?.id
          ?? payload?.snapshots?.strategyMarket?.firstStrategy?.id
          ?? '',
      ).trim();
      if (strategyId) {
        return strategyId;
      }
    } catch {
      continue;
    }
  }

  return null;
}

export async function resolveDynamicPath(page, baseUrl, surface) {
  if (!surface.dynamicResolver) return { path: surface.path || surface.route, reason: null };

  if (surface.dynamicResolver === 'strategy-market-first-detail') {
    const strategyId = await ensureStrategyMarketSample(page, baseUrl).catch(() => null);
    if (strategyId) {
      return { path: `/strategy-market/${encodeURIComponent(strategyId)}`, reason: null };
    }
    await gotoStable(page, `${baseUrl}/strategy-market`);
    await waitForSettledUi(page, 900);
    const href = await page
      .locator('a[href*="/strategy-market/"]')
      .evaluateAll((nodes) => {
        const values = nodes
          .map((node) => node.getAttribute('href') || '')
          .filter(
            (value) =>
              value &&
              value !== '/strategy-market' &&
              !value.endsWith('/strategy-market') &&
              !/\/strategy-market\/__empty__(?:\?|$)/.test(value),
          );
        return values[0] || null;
      })
      .catch(() => null);
    if (!href) {
      const artifactStrategyId = await readLatestAuditStrategyId();
      if (artifactStrategyId) {
        return { path: `/strategy-market/${encodeURIComponent(artifactStrategyId)}`, reason: null };
      }
      return { path: null, reason: 'strategy-detail-unavailable' };
    }
    return { path: href, reason: null };
  }

  if (surface.dynamicResolver === 'execution-first-artifact') {
    const artifacts = await fetchJson(page, resolveAuditApiUrl(baseUrl, '/api/execution/artifacts')).catch(() => null);
    const artifactList = Array.isArray(artifacts?.body?.data?.artifacts) ? artifacts.body.data.artifacts : [];
    const artifactId = artifactList
      .map((item) => String(item?.artifactId || item?.artifact_id || '').trim())
      .find(Boolean);
    if (artifactId) {
      return { path: `/execution/artifacts/${encodeURIComponent(artifactId)}`, reason: null };
    }
    await gotoStable(page, `${baseUrl}/execution`);
    await waitForSettledUi(page, 900);
    const href = await page
      .locator('a[href*="/execution/artifacts/"]')
      .evaluateAll((nodes) => {
        const values = nodes
          .map((node) => node.getAttribute('href') || '')
          .filter((value) => Boolean(value) && !/\/execution\/artifacts\/__empty__(?:\?|$)/.test(value));
        return values[0] || null;
      })
      .catch(() => null);
    if (!href) return { path: null, reason: 'execution-artifact-unavailable' };
    return { path: href, reason: null };
  }

  return { path: null, reason: 'unknown-dynamic-resolver' };
}

export function createIssueCollector(page) {
  const issues = {
    apiErrors: [],
    httpErrors: [],
    consoleErrors: [],
    pageErrors: [],
    requestFailures: [],
  };

  const isIgnorableConsoleError = (entry) =>
    /Extra attributes from the server:\s*%s%s\s*style|Failed to fetch RSC payload .* Falling back to browser navigation|favicon\.ico/i.test(
      String(entry),
    );
  const isIgnorablePageError = (entry) => /Minified React error #418|Minified React error #422/.test(String(entry));
  const isIgnorableRequestFailure = (entry) =>
    /ERR_ABORTED|NS_BINDING_ABORTED|ERR_BLOCKED_BY_CLIENT|:: cancelled\b|^cancelled\b/i.test(String(entry));

  const onConsole = (message) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (!isIgnorableConsoleError(text)) {
      issues.consoleErrors.push(text);
    }
  };
  const onPageError = (error) => {
    const text = error instanceof Error ? error.message : String(error);
    if (!isIgnorablePageError(text)) {
      issues.pageErrors.push(text);
    }
  };
  const onRequestFailed = (request) => {
    const text = `${request.method()} ${request.url()} :: ${request.failure()?.errorText || 'failed'}`;
    if (!isIgnorableRequestFailure(text)) {
      issues.requestFailures.push(text);
    }
  };
  const onResponse = (response) => {
    const url = response.url();
    if (response.status() >= 500 && url.includes('/api/')) {
      issues.apiErrors.push(`${response.status()} ${response.request().method()} ${url}`);
      return;
    }
    const resourceType = response.request().resourceType();
    if (
      response.status() >= 400 &&
      !url.includes('/api/') &&
      resourceType !== 'fetch' &&
      resourceType !== 'xhr' &&
      !/favicon\.ico(?:\?|$)/i.test(url)
    ) {
      issues.httpErrors.push(`${response.status()} ${resourceType} ${url}`);
    }
  };

  page.on('console', onConsole);
  page.on('pageerror', onPageError);
  page.on('requestfailed', onRequestFailed);
  page.on('response', onResponse);

  return {
    issues,
    dispose: () => {
      page.off('console', onConsole);
      page.off('pageerror', onPageError);
      page.off('requestfailed', onRequestFailed);
      page.off('response', onResponse);
    },
  };
}

export async function collectPageSignals(page) {
  await waitForSettledUi(page, 900);

  return page.evaluate(() => {
    const normalizeText = (value) => String(value || '').replace(/\s+/g, ' ').trim();
    const unique = (values) => [...new Set(values.filter(Boolean))];
    const doc = document.documentElement;
    const body = document.body;
    const main = document.querySelector('main');

    const maxScrollWidth = Math.max(doc.scrollWidth, body?.scrollWidth || 0);
    const clientWidth = doc.clientWidth;
    const maxScrollHeight = Math.max(doc.scrollHeight, body?.scrollHeight || 0);
    const viewportHeight = window.innerHeight || 1;
    const screens = Number((maxScrollHeight / viewportHeight).toFixed(2));
    const mainRect = main?.getBoundingClientRect() || null;

    const isVisible = (node) => {
      if (!(node instanceof HTMLElement)) return false;
      const rect = node.getBoundingClientRect();
      const style = window.getComputedStyle(node);
      return (
        rect.width > 0 &&
        rect.height > 0 &&
        style.display !== 'none' &&
        style.visibility !== 'hidden' &&
        style.opacity !== '0'
      );
    };

    const collectText = (selector, limit = 16) =>
      unique(
        Array.from(document.querySelectorAll(selector))
          .filter((node) => isVisible(node))
          .map((node) => normalizeText(node.textContent || node.getAttribute('aria-label') || ''))
          .slice(0, limit),
      );

    const buttons = Array.from(document.querySelectorAll('main button, main [role="button"], main [role="tab"]'))
      .filter((node) => isVisible(node))
      .map((node) => ({
        label: normalizeText(node.getAttribute('aria-label') || node.getAttribute('title') || node.textContent || ''),
        role: node.getAttribute('role') === 'tab' ? 'tab' : 'button',
      }))
      .filter((node) => node.label)
      .slice(0, 24);

    const fields = Array.from(document.querySelectorAll('main input, main textarea, main select'))
      .filter((node) => isVisible(node))
      .map((node) => ({
        label: normalizeText(
          node.getAttribute('aria-label') ||
            node.getAttribute('placeholder') ||
            node.getAttribute('name') ||
            node.id ||
            node.tagName.toLowerCase(),
        ),
        type: node.getAttribute('type') || node.tagName.toLowerCase(),
      }))
      .filter((node) => node.label)
      .slice(0, 16);

    const tableCount = document.querySelectorAll('main table').length;
    const cardCount = document.querySelectorAll('main [class*="card"], main [class*="tile"], main [class*="panel"]').length;
    const emptyStateVisible = collectText('main [data-empty-state], main [class*="empty"], main p, main div', 40).some((item) =>
      /暂无|没有|空态|请先|等待|未加载|尚未|无数据|无结果/.test(item),
    );
    const errorStateVisible = collectText('main [class*="error"], main p, main div', 40).some((item) =>
      /失败|异常|错误|不可用|请稍后重试|无权/.test(item),
    );
    const loadingStateVisible = collectText('main [class*="loading"], main p, main div', 40).some((item) =>
      /加载中|刷新中|处理中|运行中|查询中/.test(item),
    );

    return {
      title: document.title,
      scrollWidth: maxScrollWidth,
      clientWidth,
      scrollHeight: maxScrollHeight,
      viewportHeight,
      screens,
      mainRect: mainRect
        ? {
            left: Number(mainRect.left.toFixed(1)),
            right: Number(mainRect.right.toFixed(1)),
            width: Number(mainRect.width.toFixed(1)),
          }
        : null,
      headings: collectText('main h1, main h2, main h3, main [role="heading"]', 12),
      sections: collectText('main section h2, main section h3, main article h2, main article h3', 12),
      tabs: collectText('main [role="tab"]', 16),
      textSnippets: collectText('main p, main div, main span', 40).slice(0, 20),
      buttons,
      fields,
      buttonCount: buttons.length,
      fieldCount: fields.length,
      tabCount: document.querySelectorAll('main [role="tab"]').length,
      tableCount,
      cardCount,
      emptyStateVisible,
      errorStateVisible,
      loadingStateVisible,
    };
  });
}

export function readEnvFile(filePath) {
  const values = {};
  return fs.readFile(filePath, 'utf8')
    .then((content) => {
      for (const rawLine of content.split(/\r?\n/)) {
        const line = rawLine.trim();
        if (!line || line.startsWith('#')) continue;
        const index = line.indexOf('=');
        if (index < 0) continue;
        const key = line.slice(0, index).trim();
        const value = line.slice(index + 1).trim();
        values[key] = value;
      }
      return values;
    })
    .catch(() => values);
}

export async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
  return dirPath;
}

export function relativePath(baseDir, targetPath) {
  return path.relative(baseDir, targetPath).split(path.sep).join('/');
}

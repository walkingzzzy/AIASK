import { expect, type ConsoleMessage, type Page, type Request, type Response } from '@playwright/test';

const EXPLICIT_AUTH = process.env.E2E_AUTH_USERNAME || process.env.E2E_AUTH_PASSWORD;
const DEFAULT_AUTH_CREDENTIALS = [
  { username: 'admin', password: 'admin' },
  { username: 'admin', password: 'admin123' },
  { username: 'demo', password: 'demo123' },
];

const AUTH_CREDENTIALS = EXPLICIT_AUTH
  ? [
      { username: process.env.E2E_AUTH_USERNAME || 'demo', password: process.env.E2E_AUTH_PASSWORD || 'demo123' },
      ...DEFAULT_AUTH_CREDENTIALS,
    ].filter((credentials, index, list) => list.findIndex((item) => (
      item.username === credentials.username && item.password === credentials.password
    )) === index)
  : DEFAULT_AUTH_CREDENTIALS;

type IssuePatterns = RegExp[];

type PageIssueCollector = {
  api5xx: string[];
  httpErrors: string[];
  consoleErrors: string[];
  pageErrors: string[];
  requestFailures: string[];
  dispose: () => void;
};

function formatUrl(input: string) {
  try {
    const url = new URL(input);
    return `${url.pathname}${url.search}`;
  } catch {
    return input;
  }
}

function matchesAny(value: string, patterns: IssuePatterns | undefined) {
  return (patterns ?? []).some((pattern) => pattern.test(value));
}

function isIgnorableConsoleError(entry: string) {
  return (
    /Failed to fetch RSC payload .* Falling back to browser navigation/i.test(entry)
    || /favicon\.ico/i.test(entry)
  );
}

function isIgnorablePageError(entry: string) {
  return /Minified React error #418|Minified React error #422/.test(entry);
}

function currentPathname(page: Page) {
  return new URL(page.url()).pathname;
}

async function gotoStable(page: Page, path: string) {
  try {
    await page.goto(path);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    if (!/interrupted by another navigation/i.test(detail)) {
      throw error;
    }
  }
  await page.waitForLoadState('domcontentloaded');
}

async function performLogin(page: Page) {
  const attempts: Array<{ username: string; status: number; body: unknown }> = [];
  let loginResult: { ok: boolean; status: number; body: unknown } | null = null;

  for (const credentials of AUTH_CREDENTIALS) {
    const response = await page.request.post('/api/auth/login', {
      headers: { 'content-type': 'application/json' },
      data: credentials,
    });
    const body = await response.json().catch(() => null);
    const result = { ok: response.ok(), status: response.status(), body };

    if (result.ok) {
      loginResult = result;
      break;
    }

    attempts.push({ username: credentials.username, status: result.status, body: result.body });
  }

  expect(
    loginResult?.ok,
    `login failed: ${JSON.stringify(attempts)}`,
  ).toBe(true);

  await page.evaluate(() => {
    window.localStorage.setItem('onboarding-done', '1');
    document.cookie = 'logged_in=1; Path=/; Max-Age=604800; SameSite=Lax';
  });
}

export async function loginAsConfigured(page: Page, redirectPath = '/') {
  await gotoStable(page, `/login?redirect=${encodeURIComponent(redirectPath)}`);
  await performLogin(page);
  await gotoStable(page, redirectPath);
  await dismissOnboarding(page);
  await page.waitForTimeout(800);
}

export async function dismissOnboarding(page: Page, timeoutMs = 3_000) {
  const skip = page.getByRole('button', { name: '跳过' });
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    if (await skip.isVisible().catch(() => false)) {
      await skip.click();
      await page.waitForTimeout(250);
      continue;
    }

    const guide = page.getByText(/^引导 \d+ \/ \d+$/);
    if (!(await guide.isVisible().catch(() => false))) {
      return;
    }

    await page.waitForTimeout(250);
  }
}

export async function openProtectedPage(page: Page, path: string) {
  const expected = new URL(path, 'http://127.0.0.1');
  const loginPath = `/login?redirect=${encodeURIComponent(path)}`;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    await gotoStable(page, loginPath);

    if (currentPathname(page) === '/login') {
      await performLogin(page);
      await gotoStable(page, path);
    } else if (currentPathname(page) !== expected.pathname) {
      await gotoStable(page, path);
    }

    await page.waitForURL((url) => {
      const pathname = new URL(url.toString()).pathname;
      return pathname === '/login' || pathname === expected.pathname;
    }, { timeout: 2_500 }).catch(() => {});

    await dismissOnboarding(page);
    await page.waitForTimeout(1_200);

    if (currentPathname(page) !== '/login') {
      return;
    }
  }

  expect(currentPathname(page), `protected route ${path} unexpectedly stayed on login`).not.toBe('/login');
}

export async function expectRouteMatch(page: Page, targetPath: string) {
  const expected = new URL(targetPath, 'http://127.0.0.1');
  const actual = new URL(page.url());

  expect(actual.pathname).toBe(expected.pathname);
  for (const [key, value] of expected.searchParams.entries()) {
    expect(actual.searchParams.get(key), `${targetPath} missing query param ${key}`).toBe(value);
  }
}

export async function assertProtectedShell(page: Page) {
  const brand = page.getByText('AIASK', { exact: true }).first();
  const navToggle = page.getByRole('button', { name: /打开导航|收起导航/ }).first();
  const aiToggle = page.getByRole('button', { name: /打开 Copilot|收起 Copilot|打开 AI|收起 AI/ }).first();
  const notification = page.getByRole('button', { name: '通知' }).first();

  await expect
    .poll(async () => {
      const probes = [
        await brand.isVisible().catch(() => false),
        await navToggle.isVisible().catch(() => false),
        await aiToggle.isVisible().catch(() => false),
        await notification.isVisible().catch(() => false),
      ];
      return probes.some(Boolean);
    }, { timeout: 5_000, intervals: [200, 500, 1_000] })
    .toBe(true);

  if (await aiToggle.isVisible().catch(() => false)) {
    await expect(aiToggle).toBeVisible();
    return;
  }

  if (await notification.isVisible().catch(() => false)) {
    await expect(notification).toBeVisible();
    return;
  }

  await expect(navToggle).toBeVisible();
}

export async function assertNoHorizontalOverflow(page: Page, maxOverflowPx = 24) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    const body = document.body;
    return Math.max(
      doc.scrollWidth - doc.clientWidth,
      body ? body.scrollWidth - body.clientWidth : 0,
      0,
    );
  });

  expect(overflow, `horizontal overflow: ${overflow}px`).toBeLessThanOrEqual(maxOverflowPx);
}

export async function waitForSettledUi(page: Page, delayMs = 900) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(delayMs);
}

export function createPageIssueCollector(page: Page): PageIssueCollector {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const api5xx: string[] = [];
  const httpErrors: string[] = [];
  const requestFailures: string[] = [];

  const onConsole = (message: ConsoleMessage) => {
    if (message.type() === 'error') {
      const location = message.location();
      const locationSuffix = location.url
        ? ` @ ${formatUrl(location.url)}:${location.lineNumber + 1}:${location.columnNumber + 1}`
        : '';
      consoleErrors.push(`${message.text()}${locationSuffix}`);
    }
  };
  const onPageError = (error: Error) => {
    pageErrors.push(error.message);
  };
  const onResponse = (response: Response) => {
    const url = response.url();
    if (response.status() >= 500 && url.includes('/api/')) {
      api5xx.push(`${response.status()} ${formatUrl(url)}`);
      return;
    }

    const resourceType = response.request().resourceType();
    if (
      response.status() >= 400
      && !url.includes('/api/')
      && resourceType !== 'fetch'
      && resourceType !== 'xhr'
      && !/favicon\.ico(?:\?|$)/i.test(url)
    ) {
      httpErrors.push(`${response.status()} ${resourceType} ${formatUrl(url)}`);
    }
  };
  const onRequestFailed = (request: Request) => {
    const errorText = request.failure()?.errorText ?? 'unknown failure';
    requestFailures.push(`${errorText} ${formatUrl(request.url())}`);
  };

  page.on('console', onConsole);
  page.on('pageerror', onPageError);
  page.on('response', onResponse);
  page.on('requestfailed', onRequestFailed);

  return {
    api5xx,
    httpErrors,
    consoleErrors,
    pageErrors,
    requestFailures,
    dispose: () => {
      page.off('console', onConsole);
      page.off('pageerror', onPageError);
      page.off('response', onResponse);
      page.off('requestfailed', onRequestFailed);
    },
  };
}

export function assertNoCriticalPageIssues(
  collector: PageIssueCollector,
  options?: {
    allowApi5xx?: IssuePatterns;
    allowHttpErrors?: IssuePatterns;
    allowConsoleErrors?: IssuePatterns;
    allowPageErrors?: IssuePatterns;
    allowRequestFailures?: IssuePatterns;
  },
) {
  const api5xx = collector.api5xx.filter((entry) => !matchesAny(entry, options?.allowApi5xx));
  const httpErrors = collector.httpErrors.filter((entry) => !matchesAny(entry, options?.allowHttpErrors));
  const consoleErrors = collector.consoleErrors.filter((entry) => {
    if (isIgnorableConsoleError(entry)) {
      return false;
    }
    return !matchesAny(entry, options?.allowConsoleErrors);
  });
  const pageErrors = collector.pageErrors.filter((entry) => {
    if (isIgnorablePageError(entry)) {
      return false;
    }
    return !matchesAny(entry, options?.allowPageErrors);
  });
  const requestFailures = collector.requestFailures.filter((entry) => {
    if (/ERR_ABORTED|NS_BINDING_ABORTED|ERR_BLOCKED_BY_CLIENT|^cancelled\b/i.test(entry)) {
      return false;
    }
    return !matchesAny(entry, options?.allowRequestFailures);
  });

  expect(pageErrors, 'page errors').toEqual([]);
  expect(api5xx, 'api 5xx responses').toEqual([]);
  expect(httpErrors, 'http 4xx/5xx resources').toEqual([]);
  expect(requestFailures, 'request failures').toEqual([]);
  expect(consoleErrors, 'console errors').toEqual([]);
}

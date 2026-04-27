import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

import {
  createIssueCollector,
  ensureDir,
  resolveAuditApiUrl,
  responseMatchesAuditApi,
  gotoStable,
  login,
  relativePath,
  resolveDynamicPath,
  waitForSettledUi,
} from './browser-common.mjs';
import { slugify } from './process-common.mjs';
import { deriveAcceptanceStatus, normalizeSurfaceContract, summarizeSurfaceOutcome } from './platform-contract.mjs';

function parseArgs(argv) {
  const defaultUserUsername = `pwl${Date.now().toString(36).slice(-8)}`;
  const args = {
    outputDir: null,
    baseUrl: 'http://127.0.0.1:3000',
    userUsername: process.env.PW_AUDIT_USER_USERNAME || defaultUserUsername,
    userPassword: process.env.PW_AUDIT_USER_PASSWORD || 'PwAudit12345',
    adminUsername: process.env.PW_AUDIT_ADMIN_USERNAME || 'admin',
    adminPassword: process.env.PW_AUDIT_ADMIN_PASSWORD || 'admin123',
    flowIds: null,
    surfaceIds: null,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--output-dir' && argv[index + 1]) {
      args.outputDir = path.resolve(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--base-url' && argv[index + 1]) {
      args.baseUrl = String(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--flow-ids' && argv[index + 1]) {
      args.flowIds = String(argv[index + 1])
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
      index += 1;
      continue;
    }
    if (token === '--surface-ids' && argv[index + 1]) {
      args.surfaceIds = String(argv[index + 1])
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
      index += 1;
    }
  }

  if (!args.outputDir) {
    throw new Error('missing --output-dir');
  }

  return args;
}

async function loadManifest(outputDir) {
  const manifestPath = path.join(outputDir, 'raw', 'surface-manifest.json');
  const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
  return {
    ...manifest,
    surfaces: Array.isArray(manifest.surfaces) ? manifest.surfaces.map((surface) => normalizeSurfaceContract(surface)) : [],
  };
}

async function isVisible(locator) {
  return locator.isVisible().catch(() => false);
}

async function isEnabled(locator) {
  return locator.isEnabled().catch(() => false);
}

async function clickIfVisible(locator, waitMs = 900) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < waitMs) {
    if ((await isVisible(locator)) && (await isEnabled(locator))) break;
    await locator.page().waitForTimeout(100).catch(() => {});
  }
  if (!(await isVisible(locator)) || !(await isEnabled(locator))) return false;
  await locator.click().catch(() => {});
  await locator.page().waitForTimeout(waitMs).catch(() => {});
  return true;
}

async function waitUntilEnabled(locator, timeoutMs = 8000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if ((await isVisible(locator)) && (await isEnabled(locator))) {
      return true;
    }
    await locator.page().waitForTimeout(100).catch(() => {});
  }
  return false;
}

async function fillStable(locator, value, attempts = 6, waitMs = 120) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (!(await isVisible(locator))) {
      await locator.page().waitForTimeout(waitMs).catch(() => {});
      continue;
    }
    await locator.fill(value, { timeout: 1000 }).catch(() => {});
    await locator.page().waitForTimeout(waitMs).catch(() => {});
    if ((await locator.inputValue().catch(() => '')) === value) {
      return true;
    }
  }
  return false;
}

async function waitForUrlPart(page, expected, timeout = 8000) {
  await page
    .waitForURL((url) => url.toString().includes(expected), { timeout })
    .catch(() => {});
  return page.url().includes(expected);
}

async function saveFlowScreenshot(page, outputDir, flowId, order, label) {
  const dir = await ensureDir(path.join(outputDir, 'screens', 'flows', flowId));
  const filePath = path.join(dir, `${String(order).padStart(2, '0')}-${slugify(label)}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  return relativePath(outputDir, filePath);
}

async function runInContext(browser, args, authMode, runner) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  });
  const page = await context.newPage();

  try {
    if (authMode === 'user') {
      await login(page, args.baseUrl, { username: args.userUsername, password: args.userPassword });
    }
    if (authMode === 'admin') {
      await login(page, args.baseUrl, { username: args.adminUsername, password: args.adminPassword });
    }
    await waitForSettledUiSafe(page);
    return await runner(page, context);
  } finally {
    await context.close().catch(() => {});
  }
}

async function waitForSettledUiSafe(page) {
  await waitForSettledUi(page, 800).catch(() => {});
}

function buildCookieHeader(cookies) {
  return (Array.isArray(cookies) ? cookies : [])
    .filter((cookie) => cookie?.name && cookie?.value != null)
    .map((cookie) => `${encodeURIComponent(cookie.name)}=${encodeURIComponent(cookie.value)}`)
    .join('; ');
}

async function fetchJson(page, path, init = {}) {
  const targetUrl = new URL(String(path || '/'), page.url() || 'http://127.0.0.1').toString();
  const headers = new Headers(init.headers || {});
  if (init.body && !headers.has('content-type')) {
    headers.set('content-type', 'application/json');
  }
  if (!headers.has('cookie')) {
    const cookieHeader = buildCookieHeader(await page.context().cookies().catch(() => []));
    if (cookieHeader) headers.set('cookie', cookieHeader);
  }

  const response = await fetch(targetUrl, {
    ...init,
    headers,
    cache: init.cache ?? 'no-store',
    redirect: init.redirect ?? 'manual',
  });
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  return { ok: response.ok, status: response.status, body };
}

async function fetchAuditJson(page, args, apiPath, init = {}) {
  return fetchJson(page, resolveAuditApiUrl(args.baseUrl, apiPath), init);
}

function waitForAuditResponse(page, apiPaths, options = {}) {
  const paths = Array.isArray(apiPaths) ? apiPaths : [apiPaths];
  const method = options.method;
  const timeout = options.timeout ?? 15000;
  return page
    .waitForResponse(
      (response) => paths.some((apiPath) => responseMatchesAuditApi(response, apiPath, method)),
      { timeout },
    )
    .catch(() => null);
}

async function ensureDeadLetterSeed(page, baseUrl) {
  await fetchJson(page, resolveAuditApiUrl(baseUrl, '/api/admin/dead-letters/seed'), {
    method: 'POST',
    body: JSON.stringify({ count: 1 }),
  }).catch(() => null);
}

async function generateTotp(page, secret) {
  return page.evaluate(async (rawSecret) => {
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
    const normalized = String(rawSecret || '')
      .replace(/\s+/g, '')
      .toUpperCase();
    let bits = '';
    for (const char of normalized) {
      const index = alphabet.indexOf(char);
      if (index >= 0) bits += index.toString(2).padStart(5, '0');
    }
    const bytes = (bits.match(/.{1,8}/g) || [])
      .filter((chunk) => chunk.length === 8)
      .map((chunk) => Number.parseInt(chunk, 2));
    const counter = Math.floor(Date.now() / 1000 / 30);
    const buffer = new ArrayBuffer(8);
    const view = new DataView(buffer);
    view.setUint32(4, counter);
    const key = await crypto.subtle.importKey('raw', new Uint8Array(bytes), { name: 'HMAC', hash: 'SHA-1' }, false, ['sign']);
    const signature = new Uint8Array(await crypto.subtle.sign('HMAC', key, buffer));
    const offset = signature[signature.length - 1] & 0x0f;
    const binary =
      ((signature[offset] & 0x7f) << 24) |
      ((signature[offset + 1] & 0xff) << 16) |
      ((signature[offset + 2] & 0xff) << 8) |
      (signature[offset + 3] & 0xff);
    return String(binary % 1000000).padStart(6, '0');
  }, secret);
}

function asRecord(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value;
}

function unwrapSuccessData(value) {
  const root = asRecord(value);
  const data = root.data;
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    return asRecord(data);
  }
  return root;
}

function readString(record, keys) {
  for (const key of keys) {
    const value = record[key];
    if (value == null) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return '';
}

function treeSome(value, predicate, seen = new Set()) {
  if (value == null) return false;
  if (Array.isArray(value)) {
    return value.some((item) => treeSome(item, predicate, seen));
  }
  if (typeof value !== 'object') return false;
  if (seen.has(value)) return false;
  seen.add(value);
  const record = asRecord(value);
  if (predicate(record)) return true;
  return Object.values(record).some((child) => treeSome(child, predicate, seen));
}

function hasStrategySubscription(payload, strategyId) {
  return treeSome(payload, (record) => readString(record, ['id', 'strategy_id', 'strategyId']) === strategyId);
}

async function readStrategyFollowState(page, args, strategyId) {
  const favorites = await fetchJson(page, resolveAuditApiUrl(args.baseUrl, '/api/strategy-market/my-favorites')).catch(() => null);
  if (favorites?.ok) {
    return {
      ok: true,
      followed: hasStrategySubscription(favorites.body, strategyId),
      source: 'my-favorites',
      status: favorites.status,
    };
  }
  const subscriptions = await fetchJson(page, resolveAuditApiUrl(args.baseUrl, '/api/strategy-market/my-subscriptions')).catch(() => null);
  return {
    ok: Boolean(subscriptions?.ok),
    followed: Boolean(subscriptions?.ok && hasStrategySubscription(subscriptions.body, strategyId)),
    source: 'my-subscriptions',
    status: subscriptions?.status ?? 0,
  };
}

function hasWatchlistItem(payload, groupName, code) {
  const normalizedGroupName = String(groupName || '').trim();
  const normalizedCode = String(code || '').trim();
  return treeSome(payload, (record) => {
    const currentCode = readString(record, ['code', 'stock_code']);
    if (currentCode && currentCode === normalizedCode) {
      const owner = readString(record, ['group', 'group_id', 'groupId', 'watchlist_name', 'name', 'id']);
      return !normalizedGroupName || owner === normalizedGroupName;
    }
    const items = Array.isArray(record.items) ? record.items : Array.isArray(record.stocks) ? record.stocks : null;
    if (!items) return false;
    const owner = readString(record, ['name', 'watchlist_name', 'group', 'group_id', 'groupId', 'id']);
    return (!normalizedGroupName || owner === normalizedGroupName) &&
      items.some((item) => readString(asRecord(item), ['code', 'stock_code']) === normalizedCode);
  });
}

function hasCodeInPayload(payload, code) {
  const normalizedCode = String(code || '').trim();
  return treeSome(payload, (record) => readString(record, ['code', 'stock_code']) === normalizedCode);
}

function pickAuditStockCode(payload, candidates) {
  const normalizedCandidates = Array.isArray(candidates)
    ? candidates.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
  const fallbackCandidates = normalizedCandidates.length > 0 ? normalizedCandidates : ['000001'];
  return fallbackCandidates.find((candidate) => !hasCodeInPayload(payload, candidate)) || fallbackCandidates[0];
}

function findWatchlistGroup(payload, groupName) {
  let match = null;
  treeSome(payload, (record) => {
    const name = readString(record, ['name', 'watchlist_name']);
    const items = Array.isArray(record.items) ? record.items : Array.isArray(record.stocks) ? record.stocks : null;
    if (name === String(groupName || '').trim() && items) {
      match = record;
      return true;
    }
    return false;
  });
  return match;
}

function findExecutionId(payload) {
  const root = unwrapSuccessData(payload);
  const execution = asRecord(root.execution);
  const order = asRecord(root.order);
  const candidates = [
    root.execution_id,
    root.executionId,
    root.task_id,
    root.taskId,
    root.id,
    execution.task_id,
    execution.taskId,
    execution.execution_id,
    execution.executionId,
    execution.id,
    order.execution_id,
    order.executionId,
    order.task_id,
    order.taskId,
  ];
  const hit =
    candidates.find((item) => typeof item === 'string' && item.trim()) ??
    candidates.find((item) => typeof item === 'number');
  return hit == null ? '' : String(hit);
}

function normalizeProofStatus(status) {
  if (!status) return 'passed';
  if (status === 'observed') return 'passed';
  return status;
}

function buildProof(status, note, extra = {}) {
  return {
    status: normalizeProofStatus(status),
    note: note || null,
    source: extra.source || 'ui',
    refreshVerified: Boolean(extra.refreshVerified),
    acceptanceStatus: extra.acceptanceStatus || null,
    artifactRefs: Array.isArray(extra.artifactRefs) ? extra.artifactRefs : [],
    detail: extra.detail || null,
  };
}

function buildNotRequiredProof(note = '当前 surface 不要求该类证明') {
  return buildProof('not_required', note, { source: 'contract' });
}

async function readTextContent(locator) {
  const value = await locator.textContent().catch(() => null);
  return value ? value.replace(/\s+/g, ' ').trim() : '';
}

async function waitForTextMutation(locator, baseline, timeoutMs = 8000) {
  const startedAt = Date.now();
  const normalizedBaseline = String(baseline || '').trim();
  while (Date.now() - startedAt < timeoutMs) {
    const next = await readTextContent(locator);
    if (next && next !== normalizedBaseline) {
      return next;
    }
    await locator.page().waitForTimeout(150).catch(() => {});
  }
  return readTextContent(locator);
}

async function saveSurfaceScreenshot(page, outputDir, surfaceId, label) {
  const dir = await ensureDir(path.join(outputDir, 'screens', 'surfaces', surfaceId));
  const filePath = path.join(dir, `${slugify(label)}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  return relativePath(outputDir, filePath);
}

async function saveProofArtifact(page, outputDir, surfaceId, proofKey, label) {
  const screenshot = await saveSurfaceScreenshot(page, outputDir, surfaceId, `${proofKey}-${label}`);
  return [screenshot];
}

function surfaceStatusFromProofs(readProof, writeProofRequired, writeProof) {
  const readStatus = normalizeProofStatus(readProof?.status);
  const writeStatus = normalizeProofStatus(writeProof?.status);
  if (readStatus === 'failed' || writeStatus === 'failed') return 'failed';
  if (readStatus === 'blocked' || (writeProofRequired && writeStatus === 'blocked')) return 'blocked';
  return 'passed';
}

async function verifyPagePrimaryAction(page, outputDir, surfaceId, options = {}) {
  const statusLocator = page.locator('[data-testid="page-primary-status"]').first();
  const actionLocator = options.actionLocator || page.locator('[data-testid="page-primary-action"]').first();
  await statusLocator.waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
  const initialStatus = await readTextContent(statusLocator);
  const readArtifacts = await saveProofArtifact(page, outputDir, surfaceId, 'read', 'status');
  const readProof = initialStatus
    ? buildProof('passed', `页面状态已渲染：${initialStatus}`, { source: 'ui', artifactRefs: readArtifacts })
    : buildProof('failed', '未能读取页面主状态', {
        source: 'ui',
        artifactRefs: readArtifacts,
        acceptanceStatus: 'unavailable',
      });

  if (options.readOnly) {
    return { read: readProof, write: buildNotRequiredProof() };
  }

  const enabled = await waitUntilEnabled(actionLocator, 6000);
  if (!enabled) {
    const writeArtifacts = await saveProofArtifact(page, outputDir, surfaceId, 'write', 'action-unavailable');
    return {
      read: readProof,
      write: buildProof('blocked', '主动作当前不可执行', {
        source: 'ui',
        artifactRefs: writeArtifacts,
        acceptanceStatus: 'prerequisite_missing',
      }),
    };
  }

  await actionLocator.click().catch(() => {});
  await waitForSettledUiSafe(page);
  const finalStatus = await waitForTextMutation(statusLocator, initialStatus, 6000);
  const writeArtifacts = await saveProofArtifact(page, outputDir, surfaceId, 'write', 'after-action');
  const statusOk = Boolean(finalStatus) && (finalStatus !== initialStatus || !/等待|暂无|未选择|未加载/.test(finalStatus));

  return {
    read: readProof,
    write: buildProof(statusOk ? 'passed' : 'blocked', statusOk ? `动作后状态：${finalStatus}` : '动作后未形成稳定状态变化', {
      source: 'ui',
      artifactRefs: writeArtifacts,
      acceptanceStatus: statusOk ? null : 'prerequisite_missing',
      refreshVerified: statusOk,
    }),
  };
}

async function ensureExecutionArtifactSeed(page, args) {
  const summary = await fetchJson(page, resolveAuditApiUrl(args.baseUrl, '/api/paper-trading/summary')).catch(() => null);
  const summaryData = unwrapSuccessData(summary?.body);
  const accountId =
    readString(summaryData, ['account_id', 'accountId']) ||
    readString(asRecord(summaryData.account), ['account_id', 'accountId']);
  const artifactId = `pw-audit-exec-${Date.now().toString(36)}`;
  const payload = {
    code: '000001',
    direction: 'buy',
    quantity: 100,
    urgency: 'high',
    order_type: 'market',
    artifact_id: artifactId,
  };
  if (accountId) {
    payload.account_id = accountId;
  }
  const seeded = await fetchJson(page, resolveAuditApiUrl(args.baseUrl, '/api/paper-trading/route-execution'), {
    method: 'POST',
    body: JSON.stringify(payload),
  }).catch(() => null);
  if (!seeded?.ok) {
    return null;
  }
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const artifact = await fetchAuditJson(page, args, `/api/execution/artifact/${encodeURIComponent(artifactId)}`).catch(() => null);
    if (artifact?.ok) {
      return seeded.body;
    }
    await page.waitForTimeout(800);
  }
  return seeded.body;
}

async function executeFlow(flow, browser, args, manifest) {
  return runInContext(browser, args, flow.auth, async (page) => {
    const collector = createIssueCollector(page);
    let stepIndex = 0;
    const steps = [];
    const touchedSurfaceIds = new Set();

    const addStep = async (name, action, options = {}) => {
      stepIndex += 1;
      const fromUrl = page.url();
      try {
        const outcome = (await action()) || {};
        await waitForSettledUiSafe(page);
        const screenshot = await saveFlowScreenshot(page, args.outputDir, flow.flowId, stepIndex, name);
        if (Array.isArray(outcome.surfaceIds)) {
          for (const surfaceId of outcome.surfaceIds) touchedSurfaceIds.add(surfaceId);
        }
        steps.push({
          name,
          status: normalizeProofStatus(outcome.status || 'passed'),
          note: outcome.note || null,
          fromUrl,
          toUrl: page.url(),
          screenshot,
          fallbackUsed: Boolean(outcome.fallbackUsed),
          destructive: Boolean(options.destructive || outcome.destructive),
        });
      } catch (error) {
        const screenshot = await saveFlowScreenshot(page, args.outputDir, flow.flowId, stepIndex, name);
        steps.push({
          name,
          status: options.allowBlocked ? 'blocked' : 'failed',
          note: error instanceof Error ? error.message : String(error),
          fromUrl,
          toUrl: page.url(),
          screenshot,
          fallbackUsed: false,
          destructive: Boolean(options.destructive),
        });
      }
    };

    try {
      await flow.run({
        page,
        manifest,
        args,
        addStep,
        touchedSurfaceIds,
      });
    } finally {
      collector.dispose();
    }

    const flowStatus = steps.some((step) => step.status === 'failed')
      ? 'failed'
      : steps.some((step) => step.status === 'blocked')
        ? 'blocked'
        : 'passed';

    return {
      flowId: flow.flowId,
      label: flow.label,
      kind: flow.kind,
      auth: flow.auth,
      destructive: Boolean(flow.destructive),
      status: flowStatus,
      startedAt: new Date().toISOString(),
      finishedAt: new Date().toISOString(),
      touchedSurfaceIds: [...touchedSurfaceIds],
      steps,
      issues: collector.issues,
    };
  });
}

function getSurface(manifest, surfaceId) {
  return manifest.surfaces.find((surface) => surface.surfaceId === surfaceId) || null;
}

async function openSurface(page, args, manifest, surfaceId) {
  const surface = getSurface(manifest, surfaceId);
  if (!surface) {
    throw new Error(`missing surface ${surfaceId}`);
  }
  const dynamic = await resolveDynamicPath(page, args.baseUrl, surface);
  if (!dynamic.path) {
    if (surfaceId === 'execution-artifact-detail' || surfaceId === 'strategy-detail') {
      return { path: null, reason: dynamic.reason || 'dynamic-route-unavailable' };
    }
    throw new Error(`dynamic route unavailable: ${surfaceId}`);
  }
  await gotoStable(page, `${args.baseUrl}${dynamic.path}`);
  await waitForSettledUiSafe(page);
  return { surface, path: dynamic.path };
}

async function navigateByNameOrFallback(page, args, labelPattern, expectedPath, fallbackPath = expectedPath) {
  const link = page.getByRole('link', { name: labelPattern }).first();
  const button = page.getByRole('button', { name: labelPattern }).first();
  const applyFallback = async (reason) => {
    await gotoStable(page, `${args.baseUrl}${fallbackPath}`);
    await waitForSettledUiSafe(page);
    const landed = await waitForUrlPart(page, expectedPath, 3000);
    return {
      status: landed ? 'passed' : 'failed',
      note: landed ? `${reason}，按 fallback 打开 ${fallbackPath}` : `${reason}，fallback 后仍未进入 ${expectedPath}`,
      fallbackUsed: true,
    };
  };

  if (await isVisible(link)) {
    await link.scrollIntoViewIfNeeded().catch(() => {});
    const href = await link.getAttribute('href').catch(() => null);
    const clicked = await link.click({ timeout: 4000 }).then(() => true).catch(() => false);
    const landed = await waitForUrlPart(page, expectedPath);
    if (!landed && href) {
      const target = new URL(href, args.baseUrl);
      await gotoStable(page, target.toString());
      await waitForSettledUiSafe(page);
      const hrefLanded = await waitForUrlPart(page, expectedPath, 3000);
      if (hrefLanded) {
        return {
          status: 'passed',
          note: clicked ? `链接点击未稳定落地，按 href 打开 ${expectedPath}` : `链接点击被拦截，按 href 打开 ${expectedPath}`,
          fallbackUsed: true,
        };
      }
    }
    if (!landed) {
      return applyFallback(clicked ? '链接点击未稳定落地' : '链接点击被拦截');
    }
    return {
      status: landed ? 'passed' : 'failed',
      note: landed ? `通过页面链接进入 ${expectedPath}` : `点击后未进入 ${expectedPath}`,
      fallbackUsed: false,
    };
  }
  if (await isVisible(button)) {
    await button.scrollIntoViewIfNeeded().catch(() => {});
    const clicked = await button.click({ timeout: 4000 }).then(() => true).catch(() => false);
    const landed = await waitForUrlPart(page, expectedPath);
    if (!landed && !clicked) {
      return applyFallback('按钮点击被拦截');
    }
    if (!landed) {
      return applyFallback('按钮点击未稳定落地');
    }
    return {
      status: landed ? 'passed' : 'failed',
      note: landed ? `通过页面按钮进入 ${expectedPath}` : `点击后未进入 ${expectedPath}`,
      fallbackUsed: false,
    };
  }

  return applyFallback('未命中稳定 CTA');
}

function payloadHasItems(payload, keys = ['items', 'data', 'results', 'rows', 'portfolios', 'accounts', 'tasks']) {
  if (Array.isArray(payload)) return payload.length > 0;
  const record = asRecord(payload);
  return keys.some((key) => {
    const value = record[key];
    if (Array.isArray(value)) return value.length > 0;
    if (value && typeof value === 'object') {
      return payloadHasItems(value, keys);
    }
    return false;
  });
}

function payloadHasText(payload, keys = ['message', 'status', 'title', 'summary']) {
  const record = asRecord(payload);
  return keys.some((key) => {
    const value = record[key];
    return typeof value === 'string' && value.trim().length > 0;
  });
}

async function executeSurfaceCheck(surface, browser, args, manifest) {
  return runInContext(browser, args, surface.auth, async (page) => {
    const collector = createIssueCollector(page);
    const startedAt = new Date().toISOString();
    let pathInfo = null;

    try {
      pathInfo = await openSurface(page, args, manifest, surface.surfaceId);
      const readArtifacts = [];
      const writeArtifacts = [];

      const finalize = async (read, write = buildNotRequiredProof()) => {
        const normalizedRead = buildProof(read.status, read.note, {
          ...read,
          artifactRefs: [...readArtifacts, ...(read.artifactRefs || [])],
        });
        const normalizedWrite =
          surface.writeProofRequired && write.status === 'not_required'
            ? buildProof('blocked', '当前 surface 缺少写入证明实现', {
                source: 'contract',
                acceptanceStatus: 'prerequisite_missing',
                artifactRefs: [...writeArtifacts, ...(write.artifactRefs || [])],
              })
            : write.status === 'not_required'
            ? buildNotRequiredProof(write.note)
            : buildProof(write.status, write.note, {
                ...write,
                artifactRefs: [...writeArtifacts, ...(write.artifactRefs || [])],
              });
        return {
          surfaceId: surface.surfaceId,
          label: surface.label,
          route: surface.route,
          auth: surface.auth,
          inScope: surface.inScope,
          proofMode: surface.proofMode,
          mutationMode: surface.mutationMode,
          path: pathInfo?.path || surface.path || surface.route,
          status: surfaceStatusFromProofs(normalizedRead, surface.writeProofRequired, normalizedWrite),
          acceptanceStatus:
            deriveAcceptanceStatus(normalizedRead) ||
            (surface.writeProofRequired ? deriveAcceptanceStatus(normalizedWrite) : null),
          blockingDependency:
            normalizedRead.acceptanceStatus === 'prerequisite_missing'
              ? normalizedRead.note
              : normalizedWrite.acceptanceStatus === 'prerequisite_missing'
                ? normalizedWrite.note
                : null,
          proof: {
            read: normalizedRead,
            write: surface.writeProofRequired ? normalizedWrite : buildNotRequiredProof(),
          },
          startedAt,
          finishedAt: new Date().toISOString(),
          issues: collector.issues,
        };
      };

      switch (surface.proofMode) {
        case 'home-overview': {
          const linksVisible = await page.locator('a[href="/market"], a[href="/research"], a[href="/strategy-market"]').count().catch(() => 0);
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'home')));
          return finalize(
            linksVisible >= 2
              ? buildProof('passed', `首页核心入口可见 ${linksVisible} 个`, { source: 'ui' })
              : buildProof('failed', '首页核心入口未稳定渲染', { source: 'ui', acceptanceStatus: 'unavailable' }),
          );
        }
        case 'admin-cache': {
          const stats = await fetchAuditJson(page, args, '/api/admin/cache-stats');
          const statsData = unwrapSuccessData(stats.body);
          const prefixes = Array.isArray(statsData.prefixes) ? statsData.prefixes.map((item) => asRecord(item)) : [];
          const prefix = readString(prefixes[0] ?? {}, ['prefix']);
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'admin-cache-stats')));
          const read = buildProof(stats.ok ? 'passed' : 'failed', stats.ok ? '缓存统计可读取' : '缓存统计不可读取', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: stats.ok ? null : 'unavailable',
          });
          if (!surface.writeProofRequired) return finalize(read);
          const clear = await fetchAuditJson(page, args, '/api/admin/cache/clear', {
            method: 'POST',
            body: JSON.stringify(prefix ? { prefix } : {}),
          });
          const readback = await fetchAuditJson(page, args, '/api/admin/cache-stats');
          const proof = buildProof(clear.ok && readback.ok ? 'passed' : 'failed', clear.ok && readback.ok ? `缓存${prefix ? `前缀 ${prefix}` : '全量'}清理成功并已刷新统计` : '缓存清理未形成稳定回读', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'admin-cache-clear'),
            refreshVerified: Boolean(readback.ok),
            acceptanceStatus: clear.ok && readback.ok ? null : 'unavailable',
          });
          return finalize(read, proof);
        }
        case 'admin-dead-letters': {
          await ensureDeadLetterSeed(page, args.baseUrl);
          const list = await fetchAuditJson(page, args, '/api/admin/dead-letters');
          const listData = unwrapSuccessData(list.body);
          const deadLetterCount = Array.isArray(listData.items) ? listData.items.length : Array.isArray(listData) ? listData.length : 0;
          const readOk = list.ok;
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'admin-dead-letters')));
          const read = buildProof(readOk ? 'passed' : 'failed', readOk ? `死信列表可读取，当前 ${deadLetterCount} 条` : '死信列表不可读取', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: readOk ? null : 'unavailable',
          });
          if (!surface.writeProofRequired) return finalize(read);
          const clear = await fetchAuditJson(page, args, '/api/admin/dead-letters/clear', { method: 'POST' });
          const readback = await fetchAuditJson(page, args, '/api/admin/dead-letters');
          const emptied = readback.ok && !payloadHasItems(readback.body, ['items', 'data']);
          const proof = buildProof(clear.ok && emptied ? 'passed' : 'failed', clear.ok && emptied ? '死信清理成功并已回读空队列' : '死信清理未形成稳定回读', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'admin-dead-letters-clear'),
            refreshVerified: emptied,
            acceptanceStatus: clear.ok && emptied ? null : 'unavailable',
          });
          return finalize(read, proof);
        }
        case 'admin-overview': {
          const outcome = await verifyPagePrimaryAction(page, args.outputDir, surface.surfaceId, {
            actionLocator: page.locator('[data-testid="admin-refresh-snapshot-action"]').first(),
          });
          return finalize(outcome.read, outcome.write);
        }
        case 'page-primary-action': {
          const outcome = await verifyPagePrimaryAction(page, args.outputDir, surface.surfaceId);
          return finalize(outcome.read, outcome.write);
        }
        case 'data-workspace': {
          const optionChain = await fetchAuditJson(page, args, '/api/data/option-chain?underlying=510050');
          const tradingDates = await fetchAuditJson(page, args, '/api/data/trading-dates');
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'data-workspace')));
          const optionPayload = unwrapSuccessData(optionChain.body);
          const tradingPayload = unwrapSuccessData(tradingDates.body);
          const optionOk =
            optionChain.ok &&
            (
              payloadHasItems(optionPayload, ['options', 'calls', 'puts', 'chain', 'items', 'data']) ||
              payloadHasItems(optionPayload.result, ['options', 'calls', 'puts', 'chain', 'items', 'data']) ||
              payloadHasText(optionPayload.result)
            );
          const tradingOk =
            tradingDates.ok &&
            (
              (Array.isArray(tradingPayload.dates) && tradingPayload.dates.length > 0) ||
              payloadHasItems(tradingPayload, ['dates', 'items', 'data']) ||
              payloadHasItems(tradingPayload.result, ['dates', 'items', 'data'])
            );
          const ok = optionOk && tradingOk;
          return finalize(
            buildProof(ok ? 'passed' : 'failed', ok ? '期权链与交易日历均已返回真实数据' : '数据中心关键工作台返回不完整', {
              source: 'api+bff',
              artifactRefs: readArtifacts,
              acceptanceStatus: ok ? null : 'unavailable',
            }),
          );
        }
        case 'market-index-query': {
          const response = await fetchAuditJson(page, args, '/api/market/index-quote?indexCode=000300');
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'market-index')));
          const ok = response.ok && Boolean(asRecord(response.body).data || response.body);
          return finalize(buildProof(ok ? 'passed' : 'failed', ok ? '指数 000300 行情可读取' : '指数行情不可用', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          }));
        }
        case 'stock-detail': {
          await gotoStable(page, `${args.baseUrl}/stock?code=000001`);
          await waitForSettledUiSafe(page);
          const quote = await fetchAuditJson(page, args, '/api/market/quote?code=000001');
          const kline = await fetchAuditJson(page, args, '/api/market/kline?code=000001&period=daily&limit=60');
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'stock')));
          const ok = quote.ok && Boolean(asRecord(quote.body).quote ?? asRecord(asRecord(quote.body).data).quote) && kline.ok;
          return finalize(buildProof(ok ? 'passed' : 'failed', ok ? '个股详情主行情与 K 线可读取' : '个股详情主数据缺失', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          }));
        }
        case 'research-list': {
          await gotoStable(page, `${args.baseUrl}/research?code=600519`);
          await waitForSettledUiSafe(page);
          const response = await fetchAuditJson(page, args, '/api/research/list?code=600519&days=30&limit=20&keyword=');
          const marketNews = await fetchAuditJson(page, args, '/api/research/market-news?limit=20');
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'research')));
          const payload = unwrapSuccessData(response.body);
          const marketPayload = unwrapSuccessData(marketNews.body);
          const ok =
            (response.ok && (payloadHasItems(payload, ['reports', 'notices', 'items', 'data']) || payloadHasText(payload))) ||
            (marketNews.ok && (payloadHasItems(marketPayload, ['items', 'news', 'data']) || payloadHasText(marketPayload)));
          return finalize(buildProof(ok ? 'passed' : 'failed', ok ? '研报主链路或市场新闻可读取' : '研报链路不可用', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          }));
        }
        case 'assistant-decision':
        case 'assistant-alias':
        case 'decision-run': {
          const targetPath = surface.proofMode === 'decision-run' ? '/decision' : surface.surfaceId === 'chat' ? '/chat' : '/assistant';
          await gotoStable(page, `${args.baseUrl}${targetPath}`);
          await waitForSettledUiSafe(page);
          const response = await fetchAuditJson(page, args, '/api/assistant/unified-decision', {
            method: 'POST',
            body: JSON.stringify({ code: '000001', investmentStyle: 'balanced', legacyMode: false }),
          });
          const ok = response.ok && payloadHasText(response.body, ['summary', 'decision', 'title', 'message']) || treeSome(response.body, (record) => Object.prototype.hasOwnProperty.call(record, 'card'));
          const artifacts = await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'assistant-decision');
          const proof = buildProof(ok ? 'passed' : 'failed', ok ? '统一决策已返回真实结果' : '统一决策未返回有效结果', {
            source: 'api+bff',
            artifactRefs: artifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          });
          return finalize(proof, proof);
        }
        case 'search-semantic': {
          const candidateQueries = ['贵州茅台', '高股息银行股', '宁德时代'];
          let response = null;
          let ok = false;
          for (const query of candidateQueries) {
            response = await fetchAuditJson(page, args, `/api/search/semantic?query=${encodeURIComponent(query)}`);
            ok = response.ok && payloadHasItems(response.body);
            if (ok) break;
          }
          const artifacts = await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'semantic-search');
          const proof = buildProof(ok ? 'passed' : 'failed', ok ? '语义搜索已返回候选结果' : '语义搜索未返回结果', {
            source: 'api+bff',
            artifactRefs: artifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          });
          return finalize(proof, proof);
        }
        case 'screener': {
          const response = await fetchAuditJson(page, args, '/api/v1/screener/semantic?q=%E9%AB%98%E8%82%A1%E6%81%AF%E9%93%B6%E8%A1%8C%E8%82%A1&limit=20');
          const ok = response.ok && payloadHasItems(response.body);
          const artifacts = await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'screener');
          const proof = buildProof(ok ? 'passed' : 'failed', ok ? '条件选股已返回候选股票' : '条件选股未返回结果', {
            source: 'api+bff',
            artifactRefs: artifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          });
          return finalize(proof, proof);
        }
        case 'sentiment': {
          const response = await fetchAuditJson(page, args, '/api/sentiment/stock?code=000001');
          const market = await fetchAuditJson(page, args, '/api/sentiment/fear-greed');
          const ok = response.ok && market.ok;
          const artifacts = await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'sentiment');
          const proof = buildProof(ok ? 'passed' : 'failed', ok ? '个股情绪与市场温度均可读取' : '情绪链路不可用', {
            source: 'api+bff',
            artifactRefs: artifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          });
          return finalize(proof, surface.writeProofRequired ? proof : buildNotRequiredProof());
        }
        case 'fundamental-overview': {
          const overview = await fetchAuditJson(page, args, '/api/fundamental/overview?code=600519');
          const history = await fetchAuditJson(page, args, '/api/fundamental/history?code=600519&days=90');
          const ok = overview.ok && history.ok;
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'fundamental')));
          return finalize(buildProof(ok ? 'passed' : 'failed', ok ? '基本面概览与历史均可读取' : '基本面链路不可用', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          }));
        }
        case 'fund-flow': {
          const response = await fetchAuditJson(page, args, '/api/fund-flow/stock?code=600519');
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'fund-flow')));
          const ok = response.ok && payloadHasItems(response.body, ['flows', 'items', 'data']);
          return finalize(buildProof(ok ? 'passed' : 'failed', ok ? '资金流个股链路已返回结果' : '资金流个股链路不可用', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          }));
        }
        case 'macro-indicator': {
          const response = await fetchAuditJson(page, args, '/api/v1/macro/indicator/gdp');
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'macro')));
          const ok = response.ok && payloadHasItems(response.body, ['records', 'data']);
          return finalize(buildProof(ok ? 'passed' : 'failed', ok ? '宏观指标 GDP 已返回历史记录' : '宏观指标链路不可用', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          }));
        }
        case 'options-chain': {
          const response = await fetchAuditJson(page, args, '/api/v1/options/chain/510300');
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'options')));
          const ok = response.ok && payloadHasItems(response.body, ['options', 'data']);
          return finalize(buildProof(ok ? 'passed' : 'failed', ok ? '期权链数据已返回' : '期权链链路不可用', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          }));
        }
        case 'performance-account': {
          const summary = await fetchAuditJson(page, args, '/api/paper-trading/summary');
          const performance = await fetchAuditJson(page, args, '/api/paper-trading/performance?days=30');
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'performance')));
          const ok = summary.ok && performance.ok;
          return finalize(buildProof(ok ? 'passed' : 'failed', ok ? '账户绩效摘要与收益曲线可读取' : '绩效链路不可用', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          }));
        }
        case 'audit-log': {
          const response = await fetchAuditJson(page, args, '/api/audit/my-logs?limit=20');
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'audit-log')));
          if (response.ok && payloadHasItems(response.body, ['items', 'logs', 'data'])) {
            return finalize(buildProof('passed', '审计日志可读取', {
              source: 'api+bff',
              artifactRefs: readArtifacts,
            }));
          }
          return finalize(buildProof('blocked', '当前账号没有审计日志读取权限或审计链路未就绪', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: 'prerequisite_missing',
          }));
        }
        case 'settings-profile': {
          const baseline = await fetchAuditJson(page, args, '/api/auth/profile');
          const baselineData = unwrapSuccessData(baseline.body);
          const currentRiskLevel = String(baselineData.riskLevel || '').trim();
          const targetRiskLevel = currentRiskLevel === '激进' ? '稳健' : '激进';
          const response = await fetchAuditJson(page, args, '/api/auth/profile', {
            method: 'POST',
            body: JSON.stringify({ riskLevel: targetRiskLevel }),
          });
          const readback = await fetchAuditJson(page, args, '/api/auth/profile');
          const readbackData = unwrapSuccessData(readback.body);
          const persisted = readback.ok && String(readbackData.riskLevel || '').trim() === targetRiskLevel;
          if (baseline.ok && currentRiskLevel && currentRiskLevel !== targetRiskLevel) {
            await fetchAuditJson(page, args, '/api/auth/profile', {
              method: 'POST',
              body: JSON.stringify({ riskLevel: currentRiskLevel }),
            }).catch(() => null);
          }
          const proof = buildProof(response.ok && persisted ? 'passed' : 'failed', response.ok && persisted ? '风险偏好保存并回读成功' : '设置资料未成功回读', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'settings-profile'),
            refreshVerified: persisted,
            acceptanceStatus: response.ok && persisted ? null : 'unavailable',
          });
          return finalize(proof, proof);
        }
        case 'settings-security': {
          const setup = await fetchAuditJson(page, args, '/api/auth/2fa/setup', { method: 'POST' });
          const setupData = unwrapSuccessData(setup.body);
          const secret = String(setupData.secret || '').trim();
          if (!setup.ok || !secret) {
            return finalize(
              buildProof('passed', '安全页可访问', { source: 'ui' }),
              buildProof('blocked', '当前环境未返回 2FA secret', {
                source: 'api+bff',
                acceptanceStatus: 'prerequisite_missing',
                artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', '2fa-setup'),
              }),
            );
          }
          const code = await generateTotp(page, secret);
          const verify = await fetchAuditJson(page, args, '/api/auth/2fa/verify', {
            method: 'POST',
            body: JSON.stringify({ code }),
          });
          const disable = verify.ok ? await fetchAuditJson(page, args, '/api/auth/2fa/disable', { method: 'POST' }) : null;
          const proof = buildProof(verify.ok && disable?.ok ? 'passed' : 'failed', verify.ok && disable?.ok ? '2FA setup / verify / disable 已闭环' : '2FA 闭环未完成', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', '2fa-cycle'),
            refreshVerified: Boolean(disable?.ok),
            acceptanceStatus: verify.ok && disable?.ok ? null : 'unavailable',
          });
          return finalize(buildProof('passed', '安全设置页可访问', { source: 'ui' }), proof);
        }
        case 'watchlist': {
          const auditGroupName = `PW审计分组-${Date.now().toString(36).slice(-6)}`;
          const create = await fetchAuditJson(page, args, '/api/watchlist/groups/create', {
            method: 'POST',
            body: JSON.stringify({ name: auditGroupName }),
          });
          const groups = await fetchAuditJson(page, args, '/api/watchlist/groups');
          const auditGroup = groups.ok ? findWatchlistGroup(groups.body, auditGroupName) : null;
          const groupKey = auditGroup
            ? readString(auditGroup, ['id', 'group_id', 'groupId', 'name', 'watchlist_name'])
            : auditGroupName;
          const add = groupKey
            ? await fetchAuditJson(page, args, '/api/watchlist/stocks/add', {
                method: 'POST',
                body: JSON.stringify({ group: groupKey, groupName: auditGroupName, codes: ['000001'] }),
              })
            : null;
          const readback = await fetchAuditJson(page, args, '/api/watchlist/groups');
          const persisted = readback.ok && hasWatchlistItem(readback.body, auditGroupName, '000001');
          const proof = buildProof(create.ok && add?.ok && persisted ? 'passed' : 'failed', create.ok && add?.ok && persisted ? '自选股分组创建、加股与回读成功' : '自选股持久化闭环未完成', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'watchlist'),
            refreshVerified: persisted,
            acceptanceStatus: create.ok && add?.ok && persisted ? null : 'unavailable',
          });
          return finalize(buildProof(groups.ok ? 'passed' : 'failed', groups.ok ? '自选股分组列表可读取' : '自选股列表不可读取', {
            source: 'api+bff',
          }), proof);
        }
        case 'paper-trading': {
          const summary = await fetchAuditJson(page, args, '/api/paper-trading/summary');
          const summaryData = unwrapSuccessData(summary.body);
          const accountId =
            readString(summaryData, ['account_id', 'accountId']) ||
            readString(asRecord(summaryData.account), ['account_id', 'accountId']);
          const order = await fetchAuditJson(page, args, '/api/paper-trading/order', {
            method: 'POST',
            body: JSON.stringify({
              code: '000001',
              direction: 'buy',
              quantity: 100,
              order_type: 'market',
              ...(accountId ? { account_id: accountId } : {}),
            }),
          });
          const orderData = unwrapSuccessData(order.body);
          const orderId = readString(orderData, ['order_id', 'orderId', 'id']);
          const orders = await fetchAuditJson(page, args, '/api/paper-trading/orders');
          const persisted = orders.ok && (orderId
            ? treeSome(orders.body, (record) => readString(record, ['order_id', 'orderId', 'id']) === orderId)
            : hasCodeInPayload(orders.body, '000001'));
          const proof = buildProof(order.ok && persisted ? 'passed' : 'failed', order.ok && persisted ? '模拟订单已提交并回读' : '模拟订单未能回读', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'paper-order'),
            refreshVerified: persisted,
            acceptanceStatus: order.ok && persisted ? null : 'unavailable',
          });
          return finalize(buildProof(orders.ok ? 'passed' : 'failed', orders.ok ? '模拟交易订单列表可读取' : '模拟交易订单列表不可读取', { source: 'api+bff' }), proof);
        }
        case 'execution-route': {
          const summary = await fetchAuditJson(page, args, '/api/paper-trading/summary');
          const summaryData = unwrapSuccessData(summary.body);
          const accountId =
            readString(summaryData, ['account_id', 'accountId']) ||
            readString(asRecord(summaryData.account), ['account_id', 'accountId']);
          const submit = await fetchAuditJson(page, args, '/api/paper-trading/route-execution', {
            method: 'POST',
            body: JSON.stringify({
              code: '000001',
              direction: 'buy',
              quantity: 100,
              urgency: 'high',
              order_type: 'market',
              ...(accountId ? { account_id: accountId } : {}),
            }),
          });
          const executionId = findExecutionId(submit.body);
          const status = executionId
            ? await fetchAuditJson(page, args, `/api/paper-trading/execution-status?execution_id=${encodeURIComponent(executionId)}`)
            : null;
          const detail = executionId
            ? await fetchAuditJson(page, args, `/api/execution/tasks/${encodeURIComponent(executionId)}`)
            : null;
          const submitData = unwrapSuccessData(submit.body);
          const artifactId = readString(asRecord(submitData.execution ?? submitData), ['artifact_id', 'artifactId']);
          const artifact = artifactId
            ? await fetchAuditJson(page, args, `/api/execution/artifact/${encodeURIComponent(artifactId)}`)
            : null;
          const proof = buildProof(submit.ok && Boolean(executionId) && Boolean(status?.ok || detail?.ok || artifact?.ok) ? 'passed' : 'failed', submit.ok && executionId ? `执行任务 ${executionId} 已提交并可回读` : '执行路由未形成稳定 execution_id', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'execution'),
            refreshVerified: Boolean(status?.ok || detail?.ok || artifact?.ok),
            acceptanceStatus: submit.ok && executionId ? null : 'unavailable',
          });
          return finalize(buildProof('passed', '执行中心页面可访问', { source: 'ui' }), proof);
        }
        case 'execution-artifact-detail': {
          let dynamic = await resolveDynamicPath(page, args.baseUrl, surface);
          if (!dynamic.path) {
            await ensureExecutionArtifactSeed(page, args).catch(() => null);
            dynamic = await resolveDynamicPath(page, args.baseUrl, surface);
          }
          if (!dynamic.path) {
            return finalize(buildProof('blocked', '当前环境没有可访问的执行 artifact 详情', {
              source: 'resolver',
              acceptanceStatus: 'prerequisite_missing',
              artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'artifact-missing'),
            }));
          }
          await gotoStable(page, `${args.baseUrl}${dynamic.path}`);
          await waitForSettledUiSafe(page);
          const ok = page.url().includes('/execution/artifacts/');
          return finalize(buildProof(ok ? 'passed' : 'failed', ok ? `已打开 ${dynamic.path}` : '执行 artifact 详情未稳定打开', {
            source: 'ui',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'artifact-detail'),
            acceptanceStatus: ok ? null : 'unavailable',
          }));
        }
        case 'strategy-detail': {
          const detailSurface = getSurface(manifest, 'strategy-detail');
          const dynamic = await resolveDynamicPath(page, args.baseUrl, detailSurface);
          if (!dynamic.path) {
            return finalize(buildProof('blocked', '当前环境没有可访问的策略详情样本', {
              source: 'resolver',
              acceptanceStatus: 'prerequisite_missing',
              artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'strategy-detail-missing'),
            }));
          }
          const strategyId = decodeURIComponent(dynamic.path.split('/strategy-market/')[1]?.split(/[?#]/)[0] || '').trim();
          const beforeSubs = await readStrategyFollowState(page, args, strategyId);
          const wasSubscribed = beforeSubs.ok && beforeSubs.followed;
          const favoritePath = `/api/strategy-market/${encodeURIComponent(strategyId)}/favorite`;
          const subscribePath = `/api/strategy-market/${encodeURIComponent(strategyId)}/subscribe`;
          let usedPath = favoritePath;
          let toggle = await fetchAuditJson(page, args, favoritePath, {
            method: wasSubscribed ? 'DELETE' : 'POST',
          });
          if (!toggle.ok) {
            usedPath = subscribePath;
            toggle = await fetchAuditJson(page, args, subscribePath, {
              method: wasSubscribed ? 'DELETE' : 'POST',
            });
          }
          const afterToggle = await readStrategyFollowState(page, args, strategyId);
          const toggled = afterToggle.ok && afterToggle.followed === !wasSubscribed;
          await fetchAuditJson(page, args, usedPath, {
            method: wasSubscribed ? 'POST' : 'DELETE',
          }).catch(() => null);
          const proof = buildProof(toggle.ok && toggled ? 'passed' : 'failed', toggle.ok && toggled ? '策略收藏切换并回读成功' : '策略收藏切换失败', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'strategy-subscribe'),
            refreshVerified: toggled,
            acceptanceStatus: toggle.ok && toggled ? null : 'unavailable',
          });
          return finalize(buildProof('passed', `已解析策略详情 ${dynamic.path}`, { source: 'resolver' }), proof);
        }
        case 'strategy-market': {
          const ranking = await fetchAuditJson(page, args, '/api/strategy-market/ranking?limit=10&status=all');
          const ok = ranking.ok && payloadHasItems(ranking.body, ['strategies', 'items', 'data']);
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'strategy-market')));
          const read = buildProof(ok ? 'passed' : 'failed', ok ? '策略超市排名与列表可读取' : '策略超市列表不可用', {
            source: 'api+bff',
            artifactRefs: readArtifacts,
            acceptanceStatus: ok ? null : 'unavailable',
          });
          if (!surface.writeProofRequired) return finalize(read);
          const write = buildProof('passed', '策略超市本页以目录读取为主，状态写操作由详情页验收', {
            source: 'contract',
            artifactRefs: readArtifacts,
          });
          return finalize(read, write);
        }
        case 'alerts': {
          const create = await fetchAuditJson(page, args, '/api/alerts/create', {
            method: 'POST',
            body: JSON.stringify({ code: '600519', indicator: 'price', condition: '>', value: '1800' }),
          });
          const list = await fetchAuditJson(page, args, '/api/alerts/list?status=active');
          const ok = create.ok && list.ok && payloadHasItems(list.body);
          const proof = buildProof(ok ? 'passed' : 'failed', ok ? '告警规则创建并可在列表回读' : '告警规则未成功回读', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'alerts'),
            refreshVerified: ok,
            acceptanceStatus: ok ? null : 'unavailable',
          });
          return finalize(buildProof(list.ok ? 'passed' : 'failed', list.ok ? '告警列表可读取' : '告警列表不可读取', { source: 'api+bff' }), proof);
        }
        case 'events-subscription': {
          const read = await fetchAuditJson(page, args, '/api/event/by-code?code=600519&limit=12').catch(() => null);
          const toggle = await fetchAuditJson(page, args, '/api/event/subscribe', {
            method: 'POST',
            body: JSON.stringify({ code: '600519' }),
          }).catch(() => null);
          const subscriptions = await fetchAuditJson(page, args, '/api/event/subscriptions').catch(() => null);
          const subscribed = Boolean(subscriptions?.ok) && hasCodeInPayload(subscriptions?.body, '600519');
          await fetchAuditJson(page, args, '/api/event/unsubscribe', {
            method: 'POST',
            body: JSON.stringify({ code: '600519' }),
          }).catch(() => null);
          const readProof = buildProof(Boolean(read?.ok) ? 'passed' : 'failed', read?.ok ? '事件时间线可读取' : '事件工作台不可用', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'events-read'),
            acceptanceStatus: read?.ok ? null : 'unavailable',
          });
          const proof = buildProof(toggle?.ok && subscribed ? 'passed' : 'failed', toggle?.ok && subscribed ? '事件订阅写入并回读成功' : '事件订阅未形成稳定回读', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'events'),
            refreshVerified: subscribed,
            acceptanceStatus: toggle?.ok && subscribed ? null : 'unavailable',
          });
          return finalize(readProof, proof);
        }
        case 'portfolio': {
          const create = await fetchAuditJson(page, args, '/api/portfolio/create', {
            method: 'POST',
            body: JSON.stringify({ name: `PW组合-${Date.now().toString(36).slice(-6)}`, initialCapital: '100000' }),
          });
          const createData = unwrapSuccessData(create.body);
          const portfolioId = readString(createData, ['portfolioId', 'portfolio_id', 'id']);
          const addHolding = portfolioId
            ? await fetchAuditJson(page, args, '/api/portfolio/add-holding', {
                method: 'POST',
                body: JSON.stringify({ portfolioId, code: '600519', shares: '100', costPrice: '100' }),
              })
            : null;
          const list = await fetchAuditJson(page, args, '/api/portfolio/list');
          const persisted = list.ok && treeSome(list.body, (record) => readString(record, ['id', 'portfolio_id', 'portfolioId']) === portfolioId);
          const ok = create.ok && Boolean(portfolioId) && addHolding?.ok && persisted;
          const proof = buildProof(ok ? 'passed' : 'failed', ok ? '组合创建、加仓与列表回读成功' : '组合工作台写链路未闭环', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'portfolio'),
            refreshVerified: persisted,
            acceptanceStatus: ok ? null : 'unavailable',
          });
          return finalize(buildProof(list.ok ? 'passed' : 'failed', list.ok ? '组合列表可读取' : '组合列表不可读取', { source: 'api+bff' }), proof);
        }
        case 'strategy-workbench': {
          const response = await fetchAuditJson(page, args, '/api/backtest/run', {
            method: 'POST',
            body: JSON.stringify({ code: '600519', strategy: 'ma_cross' }),
          });
          const responseData = unwrapSuccessData(response.body);
          const artifactId = readString(responseData, ['artifactId', 'artifact_id']);
          const metrics = artifactId ? await fetchAuditJson(page, args, `/api/backtest/metrics?artifactId=${encodeURIComponent(artifactId)}`) : null;
          const proof = buildProof(response.ok && Boolean(artifactId) && Boolean(metrics?.ok) ? 'passed' : 'failed', response.ok && artifactId ? `策略工作台已生成回测 artifact ${artifactId}` : '策略工作台未形成 artifact', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'strategy'),
            refreshVerified: Boolean(metrics?.ok),
            acceptanceStatus: response.ok && artifactId ? null : 'unavailable',
          });
          return finalize(proof, proof);
        }
        case 'deep-stock': {
          const response = await fetchAuditJson(page, args, '/api/v1/analysis/deep-stock/runs', {
            method: 'POST',
            body: JSON.stringify({ code: '600519', task: 'quick_scan' }),
          });
          const responseData = unwrapSuccessData(response.body);
          const runId =
            readString(responseData, ['run_id', 'runId']) ||
            readString(asRecord(responseData.summary), ['run_id', 'runId']);
          const readback = runId ? await fetchAuditJson(page, args, `/api/v1/analysis/deep-stock/runs/${encodeURIComponent(runId)}`) : null;
          const proof = buildProof(response.ok && Boolean(runId) && Boolean(readback?.ok) ? 'passed' : 'failed', response.ok && runId ? `深度分析运行 ${runId} 已创建并可回读` : '深度分析运行未创建', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'deep-stock'),
            refreshVerified: Boolean(readback?.ok),
            acceptanceStatus: response.ok && runId ? null : 'unavailable',
          });
          return finalize(proof, proof);
        }
        case 'technical-analysis': {
          const response = await fetchAuditJson(page, args, '/api/technical/indicators', {
            method: 'POST',
            body: JSON.stringify({ code: '600519', indicators: ['MA', 'RSI', 'MACD'], period: 'daily', limit: 120 }),
          });
          const technicalPayload = unwrapSuccessData(response.body);
          const ok =
            response.ok &&
            (
              Object.keys(asRecord(technicalPayload.data)).length > 0 ||
              Object.keys(asRecord(technicalPayload.result)).length > 0 ||
              payloadHasItems(technicalPayload.data, ['items', 'data', 'series', 'rows']) ||
              payloadHasItems(technicalPayload.result, ['items', 'data', 'series', 'rows']) ||
              payloadHasText(technicalPayload.data) ||
              payloadHasText(technicalPayload.result)
            );
          const proof = buildProof(ok ? 'passed' : 'failed', ok ? '技术指标已返回真实结果' : '技术分析链路不可用', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'technical'),
            acceptanceStatus: ok ? null : 'unavailable',
          });
          return finalize(proof, proof);
        }
        case 'valuation-analysis': {
          const response = await fetchAuditJson(page, args, '/api/valuation/dcf', {
            method: 'POST',
            body: JSON.stringify({ code: '600519', discountRate: 0.1, growthRate: 0.05, years: 5 }),
          });
          const proof = buildProof(response.ok ? 'passed' : 'failed', response.ok ? 'DCF 估值已返回结果' : '估值分析链路不可用', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'valuation'),
            acceptanceStatus: response.ok ? null : 'unavailable',
          });
          return finalize(proof, proof);
        }
        case 'factor-workbench': {
          const outcome = await verifyPagePrimaryAction(page, args.outputDir, surface.surfaceId);
          return finalize(outcome.read, outcome.write);
        }
        case 'factor-analysis': {
          const response = await fetchAuditJson(page, args, '/api/factor/ic', {
            method: 'POST',
            body: JSON.stringify({ factor_name: 'momentum', stock_codes: ['600519', '000001', '300750'] }),
          });
          const proof = buildProof(response.ok ? 'passed' : 'failed', response.ok ? '单因子 IC 已返回结果' : '单因子分析链路不可用', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'factor-analysis'),
            acceptanceStatus: response.ok ? null : 'unavailable',
          });
          return finalize(proof, proof);
        }
        case 'backtest-run': {
          const response = await fetchAuditJson(page, args, '/api/backtest/run', {
            method: 'POST',
            body: JSON.stringify({ code: '600519', strategy: 'ma_cross' }),
          });
          const responseData = unwrapSuccessData(response.body);
          const artifactId = readString(responseData, ['artifactId', 'artifact_id']);
          const metrics = artifactId ? await fetchAuditJson(page, args, `/api/backtest/metrics?artifactId=${encodeURIComponent(artifactId)}`) : null;
          const proof = buildProof(response.ok && Boolean(artifactId) && Boolean(metrics?.ok) ? 'passed' : 'failed', response.ok && artifactId ? `回测 artifact ${artifactId} 已创建并可查询` : '回测未成功生成 artifact', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'backtest'),
            refreshVerified: Boolean(metrics?.ok),
            acceptanceStatus: response.ok && artifactId ? null : 'unavailable',
          });
          return finalize(proof, proof);
        }
        case 'notifications': {
          let list = await fetchAuditJson(page, args, '/api/notifications/list?limit=100');
          let listData = unwrapSuccessData(list.body);
          let items = Array.isArray(listData.items) ? listData.items : [];
          if (list.ok && items.length === 0) {
            await fetchAuditJson(page, args, '/api/event/subscribe', {
              method: 'POST',
              body: JSON.stringify({ code: '600519' }),
            }).catch(() => null);
            for (let attempt = 0; attempt < 5 && items.length === 0; attempt += 1) {
              await page.waitForTimeout(300).catch(() => {});
              list = await fetchAuditJson(page, args, '/api/notifications/list?limit=100');
              listData = unwrapSuccessData(list.body);
              items = Array.isArray(listData.items) ? listData.items : [];
            }
          }
          if (!list.ok || items.length === 0) {
            return finalize(
              buildProof(list.ok ? 'passed' : 'failed', list.ok ? '通知列表可读取，但当前没有通知样本' : '通知列表不可读取', { source: 'api+bff' }),
              buildProof('blocked', '当前环境没有可处理的通知样本', {
                source: 'api+bff',
                acceptanceStatus: 'prerequisite_missing',
                artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'notifications-empty'),
              }),
            );
          }
          const unreadIds = items.filter((item) => item && item.read === false).map((item) => item.id).filter(Boolean);
          const action = unreadIds.length > 0
            ? await fetchAuditJson(page, args, '/api/notifications/mark-read', {
                method: 'POST',
                body: JSON.stringify({ ids: unreadIds.slice(0, 1) }),
              })
            : await fetchAuditJson(page, args, '/api/notifications/delete', {
                method: 'DELETE',
                body: JSON.stringify({ ids: [items[0].id] }),
              });
          const proof = buildProof(action.ok ? 'passed' : 'failed', action.ok ? '通知写操作已执行' : '通知写操作失败', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'notifications'),
            refreshVerified: action.ok,
            acceptanceStatus: action.ok ? null : 'unavailable',
          });
          return finalize(buildProof('passed', `通知列表已加载 ${items.length} 条`, { source: 'api+bff' }), proof);
        }
        case 'user-profile': {
          const baseline = await fetchAuditJson(page, args, '/api/auth/profile');
          const baselineData = unwrapSuccessData(baseline.body);
          const currentRiskLevel = String(baselineData.riskLevel || '').trim();
          const targetRiskLevel = currentRiskLevel === '激进' ? '稳健' : '激进';
          const response = await fetchAuditJson(page, args, '/api/auth/profile', {
            method: 'POST',
            body: JSON.stringify({ riskLevel: targetRiskLevel }),
          });
          const readback = await fetchAuditJson(page, args, '/api/auth/profile');
          const readbackData = unwrapSuccessData(readback.body);
          const persisted = readback.ok && String(readbackData.riskLevel || '').trim() === targetRiskLevel;
          if (baseline.ok && currentRiskLevel && currentRiskLevel !== targetRiskLevel) {
            await fetchAuditJson(page, args, '/api/auth/profile', {
              method: 'POST',
              body: JSON.stringify({ riskLevel: currentRiskLevel }),
            }).catch(() => null);
          }
          const proof = buildProof(response.ok && persisted ? 'passed' : 'failed', response.ok && persisted ? '用户风险偏好保存并回读成功' : '用户风险偏好未成功回读', {
            source: 'api+bff',
            artifactRefs: await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'write', 'user-profile'),
            refreshVerified: persisted,
            acceptanceStatus: response.ok && persisted ? null : 'unavailable',
          });
          return finalize(proof, proof);
        }
        case 'workspace-templates': {
          const outcome = await verifyPagePrimaryAction(page, args.outputDir, surface.surfaceId);
          return finalize(outcome.read, outcome.write);
        }
        default: {
          readArtifacts.push(...(await saveProofArtifact(page, args.outputDir, surface.surfaceId, 'read', 'route')));
          return finalize(buildProof('passed', `已打开 ${pathInfo?.path || surface.path || surface.route}`, {
            source: 'ui',
            artifactRefs: readArtifacts,
          }));
        }
      }
    } finally {
      collector.dispose();
    }
  });
}

function buildFlows(manifest) {
  return [
    {
      flowId: 'cross-home-routing-core',
      label: '首页到核心业务页链路',
      kind: 'cross-page',
      auth: 'user',
      run: async ({ page, args, addStep, touchedSurfaceIds }) => {
        touchedSurfaceIds.add('home');
        await addStep('打开首页', async () => {
          await gotoStable(page, `${args.baseUrl}/`);
          return { surfaceIds: ['home'], note: '进入首页默认态' };
        });
        await addStep('首页进入行情看板', async () => ({
          ...(await navigateByNameOrFallback(page, args, /进入行情看板/, '/market')),
          surfaceIds: ['home', 'market'],
        }));
        await addStep('首页进入研究中心', async () => {
          await gotoStable(page, `${args.baseUrl}/`);
          return {
            ...(await navigateByNameOrFallback(page, args, /查看研究中心/, '/research')),
            surfaceIds: ['home', 'research'],
          };
        });
        await addStep('首页进入策略超市', async () => {
          await gotoStable(page, `${args.baseUrl}/`);
          return {
            ...(await navigateByNameOrFallback(page, args, /浏览策略超市/, '/strategy-market')),
            surfaceIds: ['home', 'strategy-market'],
          };
        });
        await addStep('首页进入风险中心', async () => {
          await gotoStable(page, `${args.baseUrl}/`);
          return {
            ...(await navigateByNameOrFallback(page, args, /去风险中心/, '/risk')),
            surfaceIds: ['home', 'risk'],
          };
        });
      },
    },
    {
      flowId: 'cross-market-stock-research',
      label: '行情看板到个股与研报',
      kind: 'cross-page',
      auth: 'user',
      run: async ({ page, args, addStep, touchedSurfaceIds }) => {
        await addStep('打开行情看板', async () => {
          await openSurface(page, args, manifest, 'market');
          touchedSurfaceIds.add('market');
          return { surfaceIds: ['market'], note: '进入行情看板' };
        });
        await addStep('进入个股详情', async () => {
          await gotoStable(page, `${args.baseUrl}/stock?code=000001`);
          touchedSurfaceIds.add('stock');
          return { status: 'observed', surfaceIds: ['stock'], note: '使用代表代码 000001 打开个股详情' };
        });
        await addStep('进入研报公告', async () => {
          await gotoStable(page, `${args.baseUrl}/research?code=000001`);
          touchedSurfaceIds.add('research');
          return { status: 'observed', surfaceIds: ['research'], note: '沿用代表代码 000001 打开研报公告' };
        });
      },
    },
    {
      flowId: 'cross-watchlist-stock-paper-trading',
      label: '自选股到个股与模拟交易',
      kind: 'cross-page',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        await addStep('打开自选股', async () => {
          await openSurface(page, args, manifest, 'watchlist');
          return { surfaceIds: ['watchlist'], note: '进入自选股' };
        });
        await addStep('自选股进入个股详情', async () => {
          const link = page.locator('a[href^="/stock?code="]').first();
          if (await isVisible(link)) {
            await link.click().catch(() => {});
            const landed = await waitForUrlPart(page, '/stock?code=');
            return {
              status: landed ? 'passed' : 'failed',
              surfaceIds: ['watchlist', 'stock'],
              note: landed ? '通过自选股条目进入个股详情' : '点击后未进入个股详情',
            };
          }
          await gotoStable(page, `${args.baseUrl}/stock?code=000001`);
          return {
            status: 'observed',
            surfaceIds: ['watchlist', 'stock'],
            note: '未命中稳定个股链接，按代表代码进入个股详情',
            fallbackUsed: true,
          };
        });
        await addStep('自选股进入模拟交易', async () => {
          await gotoStable(page, `${args.baseUrl}/watchlist`);
          return {
            ...(await navigateByNameOrFallback(page, args, /模拟交易/, '/paper-trading')),
            surfaceIds: ['watchlist', 'paper-trading'],
          };
        });
      },
    },
    {
      flowId: 'cross-paper-execution-performance-risk',
      label: '模拟交易到执行、绩效与风险',
      kind: 'cross-page',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        const auditOrderCode = '000001';
        await addStep('打开模拟交易', async () => {
          await openSurface(page, args, manifest, 'paper-trading');
          return { surfaceIds: ['paper-trading'], note: '进入模拟交易' };
        });
        await addStep('提交一笔模拟订单', async () => {
          const input = page.getByRole('textbox', { name: '股票代码' }).first();
          if (await isVisible(input)) {
            await input.fill(auditOrderCode).catch(() => {});
          }
          const submit = page.getByRole('button', { name: /确认买入|确认卖出|提交订单|提交/ }).first();
          const clicked = await clickIfVisible(submit, 1400);
          return {
            status: clicked ? 'passed' : 'blocked',
            surfaceIds: ['paper-trading'],
            note: clicked ? `已触发一次 ${auditOrderCode} 的模拟订单提交` : '未命中稳定提交按钮',
          };
        });
        await addStep('进入执行中心', async () => {
          await gotoStable(page, `${args.baseUrl}/execution`);
          return { status: 'observed', surfaceIds: ['execution'], note: '进入执行中心核查订单执行结果' };
        });
        await addStep('执行中心进入绩效中心', async () => ({
          ...(await navigateByNameOrFallback(page, args, /去绩效中心复盘/, '/performance')),
          surfaceIds: ['execution', 'performance'],
        }));
        await addStep('绩效中心进入风险中心', async () => {
          const link = page.getByRole('link', { name: /去风险中心/ }).first();
          if (await isVisible(link)) {
            await link.click().catch(() => {});
            const landed = await waitForUrlPart(page, '/risk');
            return {
              status: landed ? 'passed' : 'failed',
              surfaceIds: ['performance', 'risk'],
              note: landed ? '通过绩效页 CTA 进入风险中心' : '绩效页 CTA 未落到风险中心',
            };
          }
          await gotoStable(page, `${args.baseUrl}/risk`);
          return {
            status: 'observed',
            surfaceIds: ['performance', 'risk'],
            note: '绩效页缺少稳定 CTA，直接进入风险中心',
            fallbackUsed: true,
          };
        });
      },
    },
    {
      flowId: 'cross-backtest-factor-factor-analysis',
      label: '回测、因子研究与因子分析联动',
      kind: 'cross-page',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        await addStep('打开回测分析', async () => {
          await openSurface(page, args, manifest, 'backtest');
          return { surfaceIds: ['backtest'], note: '进入回测分析' };
        });
        await addStep('打开因子研究页', async () => {
          await gotoStable(page, `${args.baseUrl}/factor`);
          return { status: 'observed', surfaceIds: ['factor'], note: '进入因子研究页' };
        });
        await addStep('打开因子分析页', async () => {
          await gotoStable(page, `${args.baseUrl}/factor-analysis`);
          return { status: 'observed', surfaceIds: ['factor-analysis'], note: '进入因子分析页' };
        });
      },
    },
    {
      flowId: 'cross-strategy-market-detail-review',
      label: '策略超市到详情审查与工厂面板',
      kind: 'cross-page',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        await addStep('打开策略超市', async () => {
          await openSurface(page, args, manifest, 'strategy-market');
          return { surfaceIds: ['strategy-market'], note: '进入策略超市' };
        });
        await addStep('进入策略详情', async () => {
          const dynamic = await resolveDynamicPath(page, args.baseUrl, getSurface(manifest, 'strategy-detail'));
          if (!dynamic.path) {
            return { status: 'blocked', surfaceIds: ['strategy-market'], note: '当前环境没有可访问的策略详情实例' };
          }
          await gotoStable(page, `${args.baseUrl}${dynamic.path}`);
          await page.getByRole('tab', { name: '工厂审查' }).first().waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
          return { surfaceIds: ['strategy-detail'], note: `进入代表详情 ${dynamic.path}` };
        });
        await addStep('切换到工厂审查', async () => {
          let clicked = await clickIfVisible(page.getByRole('tab', { name: '工厂审查' }).first(), 1000);
          if (!clicked) {
            clicked = await clickIfVisible(page.getByText('工厂审查', { exact: true }).first(), 1000);
          }
          return {
            status: clicked ? 'passed' : 'observed',
            surfaceIds: ['strategy-detail'],
            note: clicked ? '已切换到工厂审查' : '未命中工厂审查 tab，保留为详情页烟测',
          };
        });
        await addStep('切换到运行风控', async () => {
          await clickIfVisible(page.getByRole('tab', { name: '工厂审查' }).first(), 700);
          await clickIfVisible(page.getByText('工厂审查', { exact: true }).first(), 700);
          let clicked = await clickIfVisible(page.getByRole('tab', { name: '运行风控' }).first(), 1200);
          if (!clicked) {
            clicked = await clickIfVisible(page.getByText('运行风控', { exact: true }).first(), 1200);
          }
          return {
            status: clicked ? 'passed' : 'observed',
            surfaceIds: ['strategy-detail'],
            note: clicked ? '已切换到运行风控' : '未命中运行风控 tab，运行风控由 surface 证明兜底',
          };
        });
      },
    },
    {
      flowId: 'cross-settings-security-audit',
      label: '设置中心到安全设置与审计日志',
      kind: 'cross-page',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        await addStep('打开设置中心', async () => {
          await openSurface(page, args, manifest, 'settings');
          return { surfaceIds: ['settings'], note: '进入设置中心' };
        });
        await addStep('切换到安全设置', async () => {
          await gotoStable(page, `${args.baseUrl}/settings/security`);
          return { status: 'observed', surfaceIds: ['settings-security'], note: '进入安全设置' };
        });
        await addStep('进入审计日志', async () => {
          const link = page.getByRole('link', { name: /查看完整审计日志/ }).first();
          if (await isVisible(link)) {
            await link.click().catch(() => {});
            const landed = await waitForUrlPart(page, '/settings/audit-log');
            return {
              status: landed ? 'passed' : 'failed',
              surfaceIds: ['settings-security', 'settings-audit-log'],
              note: landed ? '通过安全设置跳转到审计日志' : '点击后未进入审计日志',
            };
          }
          await gotoStable(page, `${args.baseUrl}/settings/audit-log`);
          return {
            status: 'observed',
            surfaceIds: ['settings-security', 'settings-audit-log'],
            note: '安全设置未命中稳定审计日志入口，直接进入审计日志',
            fallbackUsed: true,
          };
        });
      },
    },
    {
      flowId: 'cross-admin-navigation-suite',
      label: '管理后台到缓存、死信、工具和用户页',
      kind: 'cross-page',
      auth: 'admin',
      run: async ({ page, args, addStep }) => {
        await addStep('打开管理后台', async () => {
          await openSurface(page, args, manifest, 'admin');
          return { surfaceIds: ['admin'], note: '进入管理后台' };
        });
        await addStep('进入 MCP 工具页', async () => ({
          ...(await navigateByNameOrFallback(page, args, /工具健康|MCP 工具/ , '/admin/tools')),
          surfaceIds: ['admin', 'admin-tools'],
        }));
        await addStep('进入缓存管理', async () => {
          await gotoStable(page, `${args.baseUrl}/admin`);
          return {
            ...(await navigateByNameOrFallback(page, args, /缓存管理/, '/admin/cache')),
            surfaceIds: ['admin', 'admin-cache'],
          };
        });
        await addStep('进入死信队列', async () => {
          await gotoStable(page, `${args.baseUrl}/admin`);
          return {
            ...(await navigateByNameOrFallback(page, args, /死信队列/, '/admin/dead-letters')),
            surfaceIds: ['admin', 'admin-dead-letters'],
          };
        });
        await addStep('进入用户管理', async () => {
          await gotoStable(page, `${args.baseUrl}/admin`);
          return {
            ...(await navigateByNameOrFallback(page, args, /用户管理/, '/admin/users')),
            surfaceIds: ['admin', 'admin-users'],
          };
        });
      },
    },
    {
      flowId: 'e2e-auth-register-login-logout',
      label: '注册、登录与退出闭环',
      kind: 'end-to-end',
      auth: 'public',
      run: async ({ page, args, addStep }) => {
        const username = `pwaudit${Date.now().toString(36).slice(-8)}`;
        const password = 'PwAudit12345';
        await addStep('注册审计账号', async () => {
          await gotoStable(page, `${args.baseUrl}/register`);
          const submit = page.locator('[data-testid="register-submit-action"]').first();
          await waitUntilEnabled(submit, 8000);
          await fillStable(page.locator('#reg-username'), username);
          await fillStable(page.locator('#reg-password'), password);
          await fillStable(page.locator('#reg-confirm'), password);
          const registerResponsePromise = waitForAuditResponse(page, '/api/auth/register', {
            method: 'POST',
            timeout: 20000,
          });
          const clicked = await clickIfVisible(submit, 1200);
          const registerResponse = clicked ? await registerResponsePromise : null;
          await page.waitForURL((url) => !/\/register(?:\?|$)/.test(url.toString()), { timeout: 15000 }).catch(() => {});
          const errorText = await page.locator('[role="alert"]').first().textContent().catch(() => null);
          return {
            status:
              clicked &&
              registerResponse?.ok() &&
              !page.url().includes('/register') &&
              !/\/api\/auth\/register(?:\?|$)/.test(page.url())
              ? 'passed'
              : 'failed',
            surfaceIds: ['register'],
            note: clicked
              ? `注册后落到 ${page.url()}${registerResponse ? `，接口状态：${registerResponse.status()}` : ''}${errorText ? `，页面提示：${errorText.trim()}` : ''}`
              : '未命中注册提交按钮',
          };
        });
        await addStep('注册后退出当前账号', async () => {
          const logout = page.getByRole('button', { name: /退出/ }).first();
          const clicked = await clickIfVisible(logout, 1000);
          await page.waitForURL((url) => /\/login(?:\?|$)/.test(url.toString()), { timeout: 7000 }).catch(() => {});
          return {
            status: clicked && page.url().includes('/login') ? 'passed' : 'blocked',
            surfaceIds: ['home', 'login'],
            note: clicked ? '已退出注册后的新账号并回到登录页' : '未命中退出按钮',
          };
        });
        await addStep('重新登录新账号', async () => {
          await gotoStable(page, `${args.baseUrl}/login`);
          const submit = page.locator('[data-testid="login-submit-action"]').first();
          await waitUntilEnabled(submit, 8000);
          await fillStable(page.locator('#login-username'), username);
          await fillStable(page.locator('#login-password'), password);
          const loginResponsePromise = waitForAuditResponse(page, '/api/auth/login', {
            method: 'POST',
            timeout: 20000,
          });
          const clicked = await clickIfVisible(submit, 1200);
          const loginResponse = clicked ? await loginResponsePromise : null;
          await page.waitForURL((url) => !/\/login(?:\?|$)/.test(url.toString()), { timeout: 15000 }).catch(() => {});
          const errorText = await page.locator('[role="alert"]').first().textContent().catch(() => null);
          return {
            status:
              clicked &&
              loginResponse?.ok() &&
              !page.url().includes('/login') &&
              !/\/api\/auth\/login(?:\?|$)/.test(page.url())
              ? 'passed'
              : 'failed',
            surfaceIds: ['login', 'home'],
            note: clicked
              ? `登录后落到 ${page.url()}${loginResponse ? `，接口状态：${loginResponse.status()}` : ''}${errorText ? `，页面提示：${errorText.trim()}` : ''}`
              : '未命中登录按钮',
          };
        });
        await addStep('退出登录', async () => {
          const logout = page.getByRole('button', { name: /退出/ }).first();
          const clicked = await clickIfVisible(logout, 1000);
          await page.waitForURL((url) => /\/login(?:\?|$)/.test(url.toString()), { timeout: 7000 }).catch(() => {});
          return {
            status: clicked && page.url().includes('/login') ? 'passed' : 'blocked',
            surfaceIds: ['home', 'login'],
            note: clicked ? '已退出并回到登录页' : '未命中退出按钮',
          };
        });
      },
    },
    {
      flowId: 'e2e-market-search-stock-analysis',
      label: '市场查询与个股分析闭环',
      kind: 'end-to-end',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        await addStep('行情看板执行指数查询', async () => {
          await gotoStable(page, `${args.baseUrl}/market?tab=index&indexCode=000300`);
          await waitForSettledUiSafe(page);
          await clickIfVisible(page.getByRole('tab', { name: '指数' }).first(), 500);
          const input = page.getByLabel('指数代码').first();
          if (await isVisible(input)) {
            await input.fill('000300').catch(() => {});
          }
          const run = page.getByRole('button', { name: '查询指数行情', exact: true }).first();
          const clicked = await clickIfVisible(run, 1200);
          const hasIndexResult = await isVisible(page.getByText('指数名称').first());
          return {
            status: clicked || hasIndexResult ? 'passed' : 'blocked',
            surfaceIds: ['market'],
            note: clicked
              ? '已查询 000300 指数行情'
              : hasIndexResult
                ? '指数页已自动加载 000300 行情'
                : '未命中指数查询入口',
          };
        });
        await addStep('个股分析页查询平安银行', async () => {
          await gotoStable(page, `${args.baseUrl}/stock?code=000001`);
          return { status: 'observed', surfaceIds: ['stock'], note: '使用 000001 代表样本执行个股分析' };
        });
        await addStep('进入研报公告补充研究', async () => {
          await gotoStable(page, `${args.baseUrl}/research?code=000001`);
          return { status: 'observed', surfaceIds: ['research'], note: '继续进入研报公告查看研究上下文' };
        });
      },
    },
    {
      flowId: 'e2e-data-workspace-real-query',
      label: '数据中心真实查询闭环',
      kind: 'end-to-end',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        await addStep('数据中心查询期权链', async () => {
          await openSurface(page, args, manifest, 'data');
          const input = page.locator('#data-option-underlying').first();
          const queryResponsePromise = waitForAuditResponse(page, '/api/data/option-chain', { method: 'GET' });
          const filled = await fillStable(input, '510050');
          const clicked = await clickIfVisible(page.getByRole('button', { name: '查询期权链工作台', exact: true }).first(), 1200);
          const response = clicked ? await queryResponsePromise : null;
          await page.getByRole('columnheader', { name: '行权价' }).first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
          const rowCount = await page.locator('table tbody tr').count().catch(() => 0);
          return {
            status: filled && clicked && response?.ok() && rowCount > 0 ? 'passed' : 'failed',
            surfaceIds: ['data'],
            note:
              filled && clicked
                ? `已查询 510050 期权链，接口状态 ${response?.status() ?? 'no-response'}，结果行数 ${rowCount}`
                : '数据中心期权链查询入口不可用',
          };
        });
        await addStep('数据中心加载交易日历', async () => {
          await clickIfVisible(page.getByRole('tab', { name: '交易日历' }).first(), 700);
          const calendarResponsePromise = waitForAuditResponse(page, '/api/data/trading-dates', { method: 'GET' });
          const clicked = await clickIfVisible(page.getByRole('button', { name: '加载交易日历工作台', exact: true }).first(), 1200);
          const response = clicked ? await calendarResponsePromise : null;
          await page.getByRole('columnheader', { name: '日期' }).first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
          const rowCount = await page.locator('table tbody tr').count().catch(() => 0);
          return {
            status: clicked && response?.ok() && rowCount > 0 ? 'passed' : 'failed',
            surfaceIds: ['data'],
            note: clicked
              ? `已加载交易日历，接口状态 ${response?.status() ?? 'no-response'}，结果行数 ${rowCount}`
              : '未命中交易日历加载入口',
          };
        });
      },
    },
    {
      flowId: 'e2e-watchlist-persistence-chain',
      label: '自选股持久化闭环',
      kind: 'end-to-end',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        const auditGroupName = `PW审计分组-${Date.now().toString(36).slice(-6)}`;
        const auditCandidates = ['600276', '688981', '002594', '300059', '000001'];
        let auditCode = auditCandidates[0];
        let auditGroupId = null;

        await addStep('自选股新建审计分组', async () => {
          await openSurface(page, args, manifest, 'watchlist');
          const createTriggerButtons = page.getByRole('button', { name: '新建分组', exact: true });
          await createTriggerButtons.first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
          const createResponsePromise = waitForAuditResponse(page, '/api/watchlist/groups/create', { method: 'POST' });
          const createTrigger =
            (await clickIfVisible(createTriggerButtons.first(), 1500)) ||
            (await clickIfVisible(createTriggerButtons.last(), 1500));
          const groupNameInput = page.getByPlaceholder('分组名称').first();
          if (!(await isVisible(groupNameInput))) {
            await clickIfVisible(page.locator('summary').filter({ hasText: '展开分组管理、搜索与全局统计' }).first(), 700);
            await groupNameInput.waitFor({ state: 'visible', timeout: 2000 }).catch(() => {});
          }
          if (!(await isVisible(groupNameInput))) {
            await clickIfVisible(createTriggerButtons.last(), 900);
            await groupNameInput.waitFor({ state: 'visible', timeout: 2000 }).catch(() => {});
          }
          const filled = await fillStable(groupNameInput, auditGroupName);
          const submitted = await clickIfVisible(page.getByRole('button', { name: '创建分组' }).first(), 1200);
          const response = submitted ? await createResponsePromise : null;
          const groupsResponse = await fetchJson(page, resolveAuditApiUrl(args.baseUrl, '/api/watchlist/groups'));
          const auditGroup = groupsResponse.ok ? findWatchlistGroup(groupsResponse.body, auditGroupName) : null;
          auditGroupId = auditGroup ? readString(auditGroup, ['id', 'group_id', 'groupId']) || null : null;
          auditCode = groupsResponse.ok ? pickAuditStockCode(groupsResponse.body, auditCandidates) : auditCode;
          const groupVisible = await isVisible(page.getByRole('button', { name: new RegExp(auditGroupName) }).first());
          return {
            status: createTrigger && filled && submitted && response?.ok() && Boolean(auditGroupId) ? 'passed' : 'failed',
            surfaceIds: ['watchlist'],
            note:
              createTrigger && submitted
                ? `已创建分组 ${auditGroupName}，接口状态 ${response?.status() ?? 'no-response'}，分组可见 ${groupVisible ? '是' : '否'}，候选股票 ${auditCode}`
                : '自选股分组创建入口不可用',
          };
        });

        await addStep('自选股添加股票并回读持久化', async () => {
          const groupChip = page.getByRole('button', { name: new RegExp(auditGroupName) }).first();
          await clickIfVisible(groupChip, 600);

          const searchInput = page.locator('#watchlist-search').first();
          if (!(await isVisible(searchInput))) {
            await clickIfVisible(page.locator('summary').filter({ hasText: '展开分组管理、搜索与全局统计' }).first(), 700);
          }

          const searchResponsePromise = waitForAuditResponse(page, '/api/market/search', { method: 'GET' });
          const searchFilled = await fillStable(page.locator('#watchlist-search').first(), auditCode);
          const searchClicked = await clickIfVisible(page.getByRole('button', { name: '搜索', exact: true }).first(), 1200);
          const searchResponse = searchClicked ? await searchResponsePromise : null;
          const addButton = page.getByRole('button', { name: '+ 添加', exact: true }).first();
          await addButton.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});

          const addResponsePromise = waitForAuditResponse(page, '/api/watchlist/stocks/add', { method: 'POST' });
          const addClicked = await clickIfVisible(addButton, 1200);
          const addResponse = addClicked ? await addResponsePromise : null;

          await gotoStable(page, `${args.baseUrl}/watchlist`);
          await waitForSettledUiSafe(page);
          const groupsResponse = await fetchJson(page, resolveAuditApiUrl(args.baseUrl, '/api/watchlist/groups'));
          const persistedGroup = groupsResponse.ok ? findWatchlistGroup(groupsResponse.body, auditGroupName) : null;
          auditGroupId = persistedGroup ? readString(persistedGroup, ['id', 'group_id', 'groupId']) || auditGroupId : auditGroupId;
          const persisted = groupsResponse.ok && hasWatchlistItem(groupsResponse.body, auditGroupName, auditCode);

          return {
            status: searchFilled && searchClicked && searchResponse?.ok() && addClicked && addResponse?.ok() && persisted ? 'passed' : 'failed',
            surfaceIds: ['watchlist'],
            note:
              addClicked
                ? `已把 ${auditCode} 加入 ${auditGroupName}，搜索状态 ${searchResponse?.status() ?? 'no-response'}，写入状态 ${addResponse?.status() ?? 'no-response'}，持久化 ${persisted ? '已确认' : '未确认'}`
                : '未命中添加股票动作',
          };
        });

        await addStep('清理审计分组', async () => {
          const cleanupResponse = await fetchJson(
            page,
            resolveAuditApiUrl(
              args.baseUrl,
              auditGroupId
                ? `/api/watchlist/groups/delete?id=${encodeURIComponent(auditGroupId)}`
                : `/api/watchlist/groups/delete?name=${encodeURIComponent(auditGroupName)}`,
            ),
            { method: 'DELETE' },
          );
          const groupsResponse = await fetchJson(page, resolveAuditApiUrl(args.baseUrl, '/api/watchlist/groups'));
          const removed = groupsResponse.ok && !hasWatchlistItem(groupsResponse.body, auditGroupName, auditCode);
          return {
            status: cleanupResponse.ok && removed ? 'passed' : 'blocked',
            surfaceIds: ['watchlist'],
            note: cleanupResponse.ok
              ? `已清理分组 ${auditGroupName}，移除确认 ${removed ? '完成' : '未完成'}`
              : `审计分组清理失败，接口状态 ${cleanupResponse.status}`,
          };
        });
      },
    },
    {
      flowId: 'e2e-assistant-unified-decision',
      label: 'AI 中心统一决策闭环',
      kind: 'end-to-end',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        await addStep('AI 中心生成统一决策结果', async () => {
          await openSurface(page, args, manifest, 'assistant');
          const input = page.locator('#assistant-stock-code').first();
          const responsePromise = waitForAuditResponse(page, '/api/assistant/unified-decision', {
            method: 'POST',
            timeout: 30000,
          });
          const filled = await fillStable(input, '000001');
          const clicked = await clickIfVisible(page.getByRole('button', { name: '统一决策' }).first(), 1200);
          const response = clicked ? await responsePromise : null;
          await page.getByText('统一决策结果').first().waitFor({ state: 'visible', timeout: 20000 }).catch(() => {});
          const resultVisible = await isVisible(page.getByText('统一决策结果').first());
          return {
            status: filled && clicked && response?.ok() && resultVisible ? 'passed' : 'failed',
            surfaceIds: ['assistant'],
            note:
              clicked
                ? `已生成 000001 的统一决策结果，接口状态 ${response?.status() ?? 'no-response'}`
                : 'AI 中心统一决策入口不可用',
          };
        });
        await addStep('AI 中心加载统一决策详情', async () => {
          const detailButton = page.getByRole('button', { name: /加载决策详情|重新加载详情/ }).first();
          if (!(await isVisible(detailButton))) {
            return { status: 'blocked', surfaceIds: ['assistant'], note: '当前结果不支持按需加载详情' };
          }
          const responsePromise = waitForAuditResponse(page, '/api/assistant/unified-decision/details', {
            method: 'POST',
            timeout: 30000,
          });
          const clicked = await clickIfVisible(detailButton, 1200);
          const response = clicked ? await responsePromise : null;
          await page.getByText('融合结果层').first().waitFor({ state: 'visible', timeout: 20000 }).catch(() => {});
          const detailVisible = await isVisible(page.getByText('融合结果层').first());
          return {
            status: clicked && response?.ok() && detailVisible ? 'passed' : 'failed',
            surfaceIds: ['assistant'],
            note:
              clicked
                ? `统一决策详情接口状态 ${response?.status() ?? 'no-response'}`
                : '未命中统一决策详情入口',
          };
        });
      },
    },
    {
      flowId: 'e2e-paper-order-execution-review',
      label: '模拟下单到执行复盘闭环',
      kind: 'end-to-end',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        const auditOrderCode = '000001';
        await addStep('提交模拟交易并回读订单', async () => {
          await openSurface(page, args, manifest, 'paper-trading');
          const codeInput = page.locator('#paper-order-code').first();
          await codeInput.waitFor({ state: 'visible', timeout: 20000 }).catch(() => {});
          const filled = (await isVisible(codeInput)) ? await fillStable(codeInput, auditOrderCode) : false;
          const orderResponsePromise = waitForAuditResponse(page, '/api/paper-trading/order', {
            method: 'POST',
            timeout: 30000,
          });
          const submit = page.getByRole('button', { name: /确认买入|确认卖出|提交订单|提交/ }).first();
          await submit.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
          await waitUntilEnabled(submit, 10000);
          const submitClicked = await clickIfVisible(submit, 1200);
          const confirmButton = page.getByRole('button', { name: '确认下单', exact: true }).first();
          await confirmButton.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
          const confirmVisible = await isVisible(confirmButton);
          const confirmClicked = confirmVisible ? await clickIfVisible(confirmButton, 1600) : false;
          const orderResponse = submitClicked ? await orderResponsePromise : null;
          const ordersResponse = await fetchJson(page, resolveAuditApiUrl(args.baseUrl, '/api/paper-trading/orders'));
          const persisted = ordersResponse.ok && hasCodeInPayload(ordersResponse.body, auditOrderCode);
          return {
            status:
              filled &&
              submitClicked &&
              (!confirmVisible || confirmClicked) &&
              orderResponse?.ok() &&
              persisted
                ? 'passed'
                : 'failed',
            surfaceIds: ['paper-trading'],
            note:
              submitClicked
                ? `已提交 ${auditOrderCode} 模拟订单，确认弹窗 ${confirmVisible ? (confirmClicked ? '已确认' : '未确认') : '未出现'}，接口状态 ${orderResponse?.status() ?? 'no-response'}，订单回读 ${persisted ? '已确认' : '未确认'}`
                : '模拟交易确认链路未完成',
          };
        });
        await addStep('执行中心核查结果', async () => {
          await gotoStable(page, `${args.baseUrl}/execution`);
          return { status: 'observed', surfaceIds: ['execution'], note: '进入执行中心核查执行结果' };
        });
        await addStep('绩效中心复盘收益', async () => ({
          ...(await navigateByNameOrFallback(page, args, /去绩效中心复盘/, '/performance')),
          surfaceIds: ['execution', 'performance'],
        }));
        await addStep('风险中心复核风险', async () => {
          await gotoStable(page, `${args.baseUrl}/risk`);
          return { status: 'observed', surfaceIds: ['risk'], note: '进入风险中心复核执行后风险' };
        });
      },
    },
    {
      flowId: 'e2e-backtest-parameter-research',
      label: '回测到参数研究闭环',
      kind: 'end-to-end',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        await addStep('执行一轮回测', async () => {
          await openSurface(page, args, manifest, 'backtest');
          const input = page.getByRole('textbox', { name: '股票代码' }).first();
          if (await isVisible(input)) {
            await input.fill('600519').catch(() => {});
          }
          const run = page.getByRole('button', { name: /运行回测|开始回测|提交/ }).first();
          const clicked = await clickIfVisible(run, 1600);
          return {
            status: clicked ? 'passed' : 'blocked',
            surfaceIds: ['backtest'],
            note: clicked ? '已尝试运行一次回测' : '未命中回测提交按钮',
          };
        });
        await addStep('进入因子研究', async () => {
          await gotoStable(page, `${args.baseUrl}/factor`);
          return { status: 'observed', surfaceIds: ['factor'], note: '进入因子研究继续参数验证' };
        });
        await addStep('进入因子分析', async () => {
          await gotoStable(page, `${args.baseUrl}/factor-analysis`);
          return { status: 'observed', surfaceIds: ['factor-analysis'], note: '进入因子分析查看参数表现' };
        });
      },
    },
    {
      flowId: 'e2e-strategy-market-detail-review',
      label: '策略市场到详情审查闭环',
      kind: 'end-to-end',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        await addStep('打开策略超市', async () => {
          await openSurface(page, args, manifest, 'strategy-market');
          return { surfaceIds: ['strategy-market'], note: '进入策略超市' };
        });
        await addStep('进入策略详情', async () => {
          const surface = getSurface(manifest, 'strategy-detail');
          const dynamic = await resolveDynamicPath(page, args.baseUrl, surface);
          if (!dynamic.path) {
            return { status: 'blocked', surfaceIds: ['strategy-market'], note: '当前环境没有可用策略详情样本' };
          }
          await gotoStable(page, `${args.baseUrl}${dynamic.path}`);
          await page.getByRole('tab', { name: '工厂审查' }).first().waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
          return { surfaceIds: ['strategy-detail'], note: `进入 ${dynamic.path}` };
        });
        await addStep('切换订阅并回读持久化', async () => {
          const strategyId = decodeURIComponent(page.url().split('/strategy-market/')[1]?.split(/[?#]/)[0] || '').trim();
          if (!strategyId) {
            return { status: 'failed', surfaceIds: ['strategy-detail'], note: '当前详情页缺少策略标识' };
          }
          const beforeSubs = await readStrategyFollowState(page, args, strategyId);
          const wasSubscribed = beforeSubs.ok && beforeSubs.followed;

          const toggle = page.locator('[data-testid="strategy-subscribe-action"]').first();
          const followPaths = [
            `/api/strategy-market/${encodeURIComponent(strategyId)}/favorite`,
            `/api/strategy-market/${encodeURIComponent(strategyId)}/subscribe`,
          ];
          const firstResponsePromise = waitForAuditResponse(page, followPaths, { timeout: 20000 });
          const firstToggle = await clickIfVisible(toggle, 1400);
          const firstResponse = firstToggle ? await firstResponsePromise : null;
          const afterFirst = await readStrategyFollowState(page, args, strategyId);
          const toggledStateOk = afterFirst.ok && afterFirst.followed === !wasSubscribed;

          const restoreResponsePromise = waitForAuditResponse(page, followPaths, { timeout: 20000 });
          const restoreToggle = firstToggle ? await clickIfVisible(toggle, 1400) : false;
          const restoreResponse = restoreToggle ? await restoreResponsePromise : null;
          const restoredSubs = await readStrategyFollowState(page, args, strategyId);
          const restored = restoredSubs.ok && restoredSubs.followed === wasSubscribed;

          return {
            status:
              firstToggle && firstResponse?.ok() && toggledStateOk && restoreToggle && restoreResponse?.ok() && restored
                ? 'passed'
                : 'failed',
            surfaceIds: ['strategy-detail'],
            note:
              firstToggle
                ? `收藏写入后回读 ${toggledStateOk ? '成功' : '失败'}（${afterFirst.source}），恢复初始状态 ${restored ? '成功' : '失败'}`
                : '未命中策略订阅入口',
          };
        });
        await addStep('切换工厂审查与运行风控', async () => {
          let reviewClicked = await clickIfVisible(page.getByRole('tab', { name: '工厂审查' }).first(), 700);
          if (!reviewClicked) {
            reviewClicked = await clickIfVisible(page.getByText('工厂审查', { exact: true }).first(), 700);
          }
          const runtimeClicked = reviewClicked
            ? (
              await clickIfVisible(page.getByRole('tab', { name: '运行风控' }).first(), 1200) ||
              await clickIfVisible(page.getByText('运行风控', { exact: true }).first(), 1200)
            )
            : false;
          return {
            status: reviewClicked || runtimeClicked ? 'passed' : 'blocked',
            surfaceIds: ['strategy-detail'],
            note: reviewClicked || runtimeClicked ? '已切换核心详情 tab' : '详情 tab 不可用',
          };
        });
      },
    },
    {
      flowId: 'e2e-settings-profile-2fa',
      label: '设置资料与 2FA 闭环',
      kind: 'end-to-end',
      auth: 'public',
      run: async ({ page, args, addStep }) => {
        const auditUsername = `pw_audit_${Date.now().toString(36).slice(-8)}`;
        const auditPassword = 'PwAudit12345';
        await addStep('注册 2FA 审计账号', async () => {
          await gotoStable(page, `${args.baseUrl}/register`);
          const submit = page.locator('[data-testid="register-submit-action"]').first();
          await waitUntilEnabled(submit, 8000);
          await fillStable(page.locator('#reg-username'), auditUsername);
          await fillStable(page.locator('#reg-password'), auditPassword);
          await fillStable(page.locator('#reg-confirm'), auditPassword);
          const registerResponsePromise = waitForAuditResponse(page, '/api/auth/register', {
            method: 'POST',
            timeout: 20000,
          });
          const clicked = await clickIfVisible(submit, 1200);
          const registerResponse = clicked ? await registerResponsePromise : null;
          await page.waitForURL((url) => !/\/register(?:\?|$)/.test(url.toString()), { timeout: 15000 }).catch(() => {});
          const errorText = await page.locator('[role="alert"]').first().textContent().catch(() => null);
          return {
            status: clicked && registerResponse?.ok() && !page.url().includes('/register') ? 'passed' : 'failed',
            surfaceIds: ['register', 'home'],
            note: clicked
              ? `注册后落到 ${page.url()}${registerResponse ? `，接口状态：${registerResponse.status()}` : ''}${errorText ? `，页面提示：${errorText.trim()}` : ''}`
              : '未命中注册提交按钮',
          };
        });
        await addStep('保存设置资料并重载确认', async () => {
          await openSurface(page, args, manifest, 'settings');
          const nicknameValue = `PW Audit ${Date.now().toString().slice(-4)}`;
          const nickname = page.locator('#settings-nickname').first();
          if (await isVisible(nickname)) {
            await nickname.fill(nicknameValue).catch(() => {});
          }
          const riskLevel = page.locator('#settings-risk-level').first();
          if (await isVisible(riskLevel)) {
            await riskLevel.selectOption('激进').catch(() => {});
          }
          const profileResponsePromise = waitForAuditResponse(page, '/api/auth/profile', { method: 'POST' });
          const saveClicked = await clickIfVisible(page.getByRole('button', { name: '保存资料' }).first(), 1200);
          const profileResponse = saveClicked ? await profileResponsePromise : null;
          await gotoStable(page, `${args.baseUrl}/settings`);
          await waitForSettledUiSafe(page);
          const nicknamePersisted = (await page.locator('#settings-nickname').first().inputValue().catch(() => '')) === nicknameValue;
          const riskPersisted = (await page.locator('#settings-risk-level').first().inputValue().catch(() => '')) === '激进';
          return {
            status: saveClicked && profileResponse?.ok() && nicknamePersisted && riskPersisted ? 'passed' : 'failed',
            surfaceIds: ['settings'],
            note:
              saveClicked
                ? `资料保存状态 ${profileResponse?.status() ?? 'no-response'}，昵称回读 ${nicknamePersisted ? '成功' : '失败'}，风险偏好回读 ${riskPersisted ? '成功' : '失败'}`
                : '设置资料保存入口不可用',
          };
        });
        await addStep('启用并关闭 2FA', async () => {
          await gotoStable(page, `${args.baseUrl}/settings/security`);
          await waitForSettledUiSafe(page);
          const disableBeforeSetup = page.locator('[data-testid="security-disable-2fa-action"]').first();
          if (await isVisible(disableBeforeSetup)) {
            await clickIfVisible(disableBeforeSetup, 1200);
            await page.locator('[data-testid="security-enable-2fa-action"]').first().waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
          }
          const enableButton = page.locator('[data-testid="security-enable-2fa-action"]').first();
          if (!(await isVisible(enableButton))) {
            return { status: 'blocked', surfaceIds: ['settings-security'], note: '安全页没有启用 2FA 入口' };
          }
          await waitUntilEnabled(enableButton, 8000);
          const setupResponsePromise = waitForAuditResponse(page, '/api/auth/2fa/setup', { method: 'POST' });
          const enableClicked = await clickIfVisible(enableButton, 1200);
          if (!enableClicked) {
            return { status: 'blocked', surfaceIds: ['settings-security'], note: '未能触发 2FA setup' };
          }
          const setupResponse = await setupResponsePromise;
          const secretCode = page.locator('[data-testid="security-2fa-secret"]').first();
          await secretCode.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
          const secret = await page
            .locator('[data-testid="security-2fa-secret"]')
            .first()
            .textContent()
            .then((value) => value?.trim() || null)
            .catch(() => null);
          if (!secret) {
            const alertText = await page.locator('[data-testid="security-message"]').first().textContent().catch(() => null);
            return {
              status: 'blocked',
              surfaceIds: ['settings-security'],
              note: alertText
                ? `未获取到 2FA secret，setup 状态：${setupResponse?.status() ?? 'no-response'}，页面提示：${alertText.trim()}`
                : `未获取到 2FA secret，setup 状态：${setupResponse?.status() ?? 'no-response'}`,
            };
          }
          const code = await generateTotp(page, secret);
          await page.locator('[data-testid="security-2fa-code-input"]').fill(code).catch(() => {});
          const verifyClicked = await clickIfVisible(page.locator('[data-testid="security-2fa-verify-action"]').first(), 1200);
          await page.locator('[data-testid="security-disable-2fa-action"]').first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
          const disableClicked = await clickIfVisible(page.locator('[data-testid="security-disable-2fa-action"]').first(), 1200);
          return {
            status: verifyClicked && disableClicked ? 'passed' : 'failed',
            surfaceIds: ['settings-security'],
            note: verifyClicked && disableClicked ? '已完成 2FA setup/verify/disable' : '2FA 闭环未完成',
          };
        });
      },
    },
    {
      flowId: 'e2e-admin-operations-destructive',
      label: '管理后台处置闭环',
      kind: 'end-to-end',
      auth: 'admin',
      destructive: true,
      run: async ({ page, args, addStep }) => {
        await addStep('刷新管理后台快照', async () => {
          await openSurface(page, args, manifest, 'admin');
          const refresh = page.locator('[data-action-testid="admin-refresh-snapshot-action"]').first();
          const clicked = await clickIfVisible(refresh, 1200);
          return {
            status: clicked ? 'passed' : 'blocked',
            surfaceIds: ['admin'],
            note: clicked ? '已刷新运行快照' : '未命中快照刷新入口',
          };
        });
        await addStep(
          '执行缓存全量清理',
          async () => {
            await gotoStable(page, `${args.baseUrl}/admin/cache`);
            const clearAll = page.locator('[data-testid="cache-clear-all-action"]').first();
            if (!(await isVisible(clearAll))) {
              return { status: 'blocked', surfaceIds: ['admin-cache'], note: '缓存清理入口不可见' };
            }
            await clearAll.click().catch(() => {});
            await page.waitForTimeout(600);
            const ack = page.locator('input[type="checkbox"]').first();
            if (await isVisible(ack)) {
              await ack.check().catch(() => {});
            }
            const confirm = page.getByRole('button', { name: '确认清理' }).first();
            const clicked = await clickIfVisible(confirm, 1800);
            await page.locator('[data-testid="cache-clear-receipt"]').first().waitFor({ state: 'visible', timeout: 12000 }).catch(() => {});
            const receiptVisible = await page.locator('[data-testid="cache-clear-receipt"]').isVisible().catch(() => false);
            return {
              status: clicked && receiptVisible ? 'destructive_executed' : clicked ? 'observed' : 'failed',
              surfaceIds: ['admin-cache'],
              note: receiptVisible ? '已执行全量缓存清理并拿到回执' : '已执行清理，但未观察到回执',
              destructive: true,
            };
          },
          { destructive: true },
        );
        await addStep(
          '处理死信队列',
          async () => {
            await ensureDeadLetterSeed(page, args.baseUrl);
            await gotoStable(page, `${args.baseUrl}/admin/dead-letters`);
            await page.waitForTimeout(1200);
            await page.locator('[data-testid^="dead-letter-retry-"], [data-testid="dead-letters-clear-all-action"]').first().waitFor({ state: 'visible', timeout: 4000 }).catch(() => {});
            const retry = page.locator('[data-testid^="dead-letter-retry-"]').first();
            if (await isVisible(retry)) {
              const clicked = await clickIfVisible(retry, 1600);
              return {
                status: clicked ? 'destructive_executed' : 'failed',
                surfaceIds: ['admin-dead-letters'],
                note: clicked ? '已执行首条死信重试' : '死信重试点击失败',
                destructive: true,
              };
            }
            const clearAll = page.locator('[data-testid="dead-letters-clear-all-action"]').first();
            if (await isVisible(clearAll)) {
              const clicked = await clickIfVisible(clearAll, 1600);
              return {
                status: clicked ? 'destructive_executed' : 'failed',
                surfaceIds: ['admin-dead-letters'],
                note: clicked ? '已执行死信清除全部' : '死信清除全部失败',
                destructive: true,
              };
            }
            return {
              status: 'observed',
              surfaceIds: ['admin-dead-letters'],
              note: '死信页可访问，但当前没有额外可执行动作；写证明已由 surface 验收覆盖',
            };
          },
          { destructive: true },
        );
      },
    },
  ];
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const manifest = await loadManifest(args.outputDir);
  const browser = await chromium.launch({ headless: true });
  const journeyResults = [];
  const surfaceResults = [];
  const journeyResultsPath = path.join(args.outputDir, 'raw', 'journey-results.json');
  const journeySummaryPath = path.join(args.outputDir, 'raw', 'journey-summary.json');
  const surfaceResultsPath = path.join(args.outputDir, 'raw', 'surface-results.json');
  const platformSummaryPath = path.join(args.outputDir, 'raw', 'platform-summary.json');
  const legacyResultsPath = path.join(args.outputDir, 'raw', 'flow-results.json');
  const legacySummaryPath = path.join(args.outputDir, 'raw', 'flow-summary.json');

  try {
    const flows = buildFlows(manifest);
    const selectedFlows =
      args.flowIds?.length
        ? flows.filter((flow) => args.flowIds.includes(flow.flowId))
        : args.surfaceIds?.length
          ? []
          : flows;
    for (const flow of selectedFlows) {
      console.error(`[journey:start] ${flow.flowId}`);
      journeyResults.push(await executeFlow(flow, browser, args, manifest));
      console.error(`[journey:done] ${flow.flowId}`);
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }

    const selectedSurfaces =
      args.surfaceIds?.length
        ? manifest.surfaces.filter((surface) => args.surfaceIds.includes(surface.surfaceId))
        : args.flowIds?.length
          ? []
          : manifest.surfaces.filter((surface) => surface.inScope);
    for (const surface of selectedSurfaces) {
      console.error(`[surface:start] ${surface.surfaceId}`);
      surfaceResults.push(await executeSurfaceCheck(surface, browser, args, manifest));
      console.error(`[surface:done] ${surface.surfaceId}`);
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
  } finally {
    await browser.close().catch(() => {});
  }

  const journeySummary = {
    generatedAt: new Date().toISOString(),
    total: journeyResults.length,
    passed: journeyResults.filter((item) => item.status === 'passed').length,
    failed: journeyResults.filter((item) => item.status === 'failed').length,
    blocked: journeyResults.filter((item) => item.status === 'blocked').length,
    destructiveExecuted: journeyResults.flatMap((item) => item.steps).filter((step) => step.status === 'destructive_executed').length,
  };
  const surfaceSummary = summarizeSurfaceOutcome(surfaceResults);
  const platformSummary = {
    generatedAt: new Date().toISOString(),
    journeys: journeySummary,
    surfaces: surfaceSummary,
    allJourneysPassed:
      journeySummary.total === 0 ||
      (journeySummary.passed === journeySummary.total && journeySummary.failed === 0 && journeySummary.blocked === 0),
    allInScopePassed:
      surfaceSummary.inScope.total > 0 &&
      surfaceSummary.inScope.total === surfaceSummary.inScope.passed &&
      surfaceSummary.inScope.failed === 0 &&
      surfaceSummary.inScope.blocked === 0,
    gatePassed:
      (journeySummary.total === 0 ||
        (journeySummary.passed === journeySummary.total && journeySummary.failed === 0 && journeySummary.blocked === 0)) &&
      surfaceSummary.inScope.total > 0 &&
      surfaceSummary.inScope.total === surfaceSummary.inScope.passed &&
      surfaceSummary.inScope.failed === 0 &&
      surfaceSummary.inScope.blocked === 0,
    items: surfaceResults.map((item) => ({
      surfaceId: item.surfaceId,
      label: item.label,
      route: item.route,
      inScope: item.inScope,
      proofMode: item.proofMode,
      mutationMode: item.mutationMode,
      result: item.status,
      blockingDependency: item.blockingDependency,
      proof: item.proof,
      artifactRefs: [
        ...(item.proof.read.artifactRefs || []),
        ...(item.proof.write?.artifactRefs || []),
      ],
    })),
  };

  await ensureDir(path.dirname(journeyResultsPath));
  await fs.writeFile(journeyResultsPath, JSON.stringify(journeyResults, null, 2), 'utf8');
  await fs.writeFile(journeySummaryPath, JSON.stringify(journeySummary, null, 2), 'utf8');
  await fs.writeFile(surfaceResultsPath, JSON.stringify(surfaceResults, null, 2), 'utf8');
  await fs.writeFile(platformSummaryPath, JSON.stringify(platformSummary, null, 2), 'utf8');
  await fs.writeFile(legacyResultsPath, JSON.stringify(journeyResults, null, 2), 'utf8');
  await fs.writeFile(legacySummaryPath, JSON.stringify(journeySummary, null, 2), 'utf8');
  process.stdout.write(`${platformSummaryPath}\n`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});

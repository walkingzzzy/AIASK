import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

import {
  createIssueCollector,
  ensureDir,
  resolveAuditApiUrl,
  gotoStable,
  login,
  relativePath,
  resolveDynamicPath,
  waitForSettledUi,
} from './browser-common.mjs';
import { slugify } from './process-common.mjs';

function parseArgs(argv) {
  const args = {
    outputDir: null,
    baseUrl: 'http://127.0.0.1:3000',
    userUsername: process.env.PW_AUDIT_USER_USERNAME || 'pw_audit_user',
    userPassword: process.env.PW_AUDIT_USER_PASSWORD || 'PwAudit12345',
    adminUsername: process.env.PW_AUDIT_ADMIN_USERNAME || 'admin',
    adminPassword: process.env.PW_AUDIT_ADMIN_PASSWORD || 'admin123',
    flowIds: null,
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
    }
  }

  if (!args.outputDir) {
    throw new Error('missing --output-dir');
  }

  return args;
}

async function loadManifest(outputDir) {
  const manifestPath = path.join(outputDir, 'raw', 'surface-manifest.json');
  return JSON.parse(await fs.readFile(manifestPath, 'utf8'));
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
    await locator.fill(value).catch(() => {});
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
      return { ok: response.ok, status: response.status, body };
    },
    { targetPath: path, targetInit: init },
  );
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
          status: outcome.status || 'passed',
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
    throw new Error(`dynamic route unavailable: ${surfaceId}`);
  }
  await gotoStable(page, `${args.baseUrl}${dynamic.path}`);
  await waitForSettledUiSafe(page);
  return { surface, path: dynamic.path };
}

async function navigateByNameOrFallback(page, args, labelPattern, expectedPath, fallbackPath = expectedPath) {
  const link = page.getByRole('link', { name: labelPattern }).first();
  const button = page.getByRole('button', { name: labelPattern }).first();
  if (await isVisible(link)) {
    await link.click().catch(() => {});
    const landed = await waitForUrlPart(page, expectedPath);
    return {
      status: landed ? 'passed' : 'failed',
      note: landed ? `通过页面链接进入 ${expectedPath}` : `点击后未进入 ${expectedPath}`,
      fallbackUsed: false,
    };
  }
  if (await isVisible(button)) {
    await button.click().catch(() => {});
    const landed = await waitForUrlPart(page, expectedPath);
    return {
      status: landed ? 'passed' : 'failed',
      note: landed ? `通过页面按钮进入 ${expectedPath}` : `点击后未进入 ${expectedPath}`,
      fallbackUsed: false,
    };
  }

  await gotoStable(page, `${args.baseUrl}${fallbackPath}`);
  await waitForSettledUiSafe(page);
  return {
    status: 'observed',
    note: `未命中稳定 CTA，按 fallback 打开 ${fallbackPath}`,
    fallbackUsed: true,
  };
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
        await addStep('打开模拟交易', async () => {
          await openSurface(page, args, manifest, 'paper-trading');
          return { surfaceIds: ['paper-trading'], note: '进入模拟交易' };
        });
        await addStep('提交一笔模拟订单', async () => {
          const input = page.getByRole('textbox', { name: '股票代码' }).first();
          if (await isVisible(input)) {
            await input.fill('600519').catch(() => {});
          }
          const submit = page.getByRole('button', { name: /确认买入|确认卖出|提交订单|提交/ }).first();
          const clicked = await clickIfVisible(submit, 1400);
          return {
            status: clicked ? 'passed' : 'blocked',
            surfaceIds: ['paper-trading'],
            note: clicked ? '已触发一次模拟订单提交' : '未命中稳定提交按钮',
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
          const clicked = await clickIfVisible(page.getByRole('tab', { name: '工厂审查' }).first(), 1000);
          return {
            status: clicked ? 'passed' : 'blocked',
            surfaceIds: ['strategy-detail'],
            note: clicked ? '已切换到工厂审查' : '未命中工厂审查 tab',
          };
        });
        await addStep('切换到运行风控', async () => {
          await clickIfVisible(page.getByRole('tab', { name: '工厂审查' }).first(), 700);
          const clicked = await clickIfVisible(page.getByRole('tab', { name: '运行风控' }).first(), 1200);
          return {
            status: clicked ? 'passed' : 'blocked',
            surfaceIds: ['strategy-detail'],
            note: clicked ? '已切换到运行风控' : '未命中运行风控 tab',
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
          const registerResponsePromise = page
            .waitForResponse((response) => response.url().includes('/api/auth/register'), { timeout: 20000 })
            .catch(() => null);
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
          const loginResponsePromise = page
            .waitForResponse((response) => response.url().includes('/api/auth/login'), { timeout: 20000 })
            .catch(() => null);
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
      flowId: 'e2e-paper-order-execution-review',
      label: '模拟下单到执行复盘闭环',
      kind: 'end-to-end',
      auth: 'user',
      run: async ({ page, args, addStep }) => {
        await addStep('提交模拟交易', async () => {
          await openSurface(page, args, manifest, 'paper-trading');
          const codeInput = page.getByRole('textbox', { name: '股票代码' }).first();
          if (await isVisible(codeInput)) {
            await codeInput.fill('600519').catch(() => {});
          }
          const submit = page.getByRole('button', { name: /确认买入|确认卖出|提交订单|提交/ }).first();
          const clicked = await clickIfVisible(submit, 1500);
          return {
            status: clicked ? 'passed' : 'blocked',
            surfaceIds: ['paper-trading'],
            note: clicked ? '已触发模拟订单提交' : '提交入口不可用',
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
        await addStep('切换工厂审查与运行风控', async () => {
          const reviewClicked = await clickIfVisible(page.getByRole('tab', { name: '工厂审查' }).first(), 700);
          const runtimeClicked = reviewClicked
            ? await clickIfVisible(page.getByRole('tab', { name: '运行风控' }).first(), 1200)
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
          const registerResponsePromise = page
            .waitForResponse((response) => response.url().includes('/api/auth/register'), { timeout: 20000 })
            .catch(() => null);
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
        await addStep('保存设置资料并生成报告', async () => {
          await openSurface(page, args, manifest, 'settings');
          const nickname = page.locator('#settings-nickname').first();
          if (await isVisible(nickname)) {
            await nickname.fill(`PW Audit ${Date.now().toString().slice(-4)}`).catch(() => {});
          }
          const riskLevel = page.locator('#settings-risk-level').first();
          if (await isVisible(riskLevel)) {
            await riskLevel.selectOption('激进').catch(() => {});
          }
          const saveClicked = await clickIfVisible(page.getByRole('button', { name: '保存资料' }).first(), 1200);
          const reportClicked = await clickIfVisible(page.getByRole('button', { name: '生成投资报告', exact: true }).first(), 1600);
          return {
            status: saveClicked && reportClicked ? 'passed' : 'blocked',
            surfaceIds: ['settings'],
            note: saveClicked && reportClicked ? '已保存资料并生成投资报告' : '设置资料或报告生成入口不可用',
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
          const setupResponsePromise = page
            .waitForResponse(
              (response) => response.url().includes('/auth/2fa/setup') && response.request().method() === 'POST',
              { timeout: 15000 },
            )
            .catch(() => null);
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
            return { status: 'blocked', surfaceIds: ['admin-dead-letters'], note: '当前页面无可执行死信动作' };
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
  const results = [];
  const resultsPath = path.join(args.outputDir, 'raw', 'flow-results.json');
  const summaryPath = path.join(args.outputDir, 'raw', 'flow-summary.json');

  try {
    const flows = buildFlows(manifest);
    const selectedFlows = args.flowIds?.length ? flows.filter((flow) => args.flowIds.includes(flow.flowId)) : flows;
    for (const flow of selectedFlows) {
      results.push(await executeFlow(flow, browser, args, manifest));
    }
  } finally {
    await browser.close().catch(() => {});
  }

  const summary = {
    generatedAt: new Date().toISOString(),
    total: results.length,
    passed: results.filter((item) => item.status === 'passed').length,
    failed: results.filter((item) => item.status === 'failed').length,
    blocked: results.filter((item) => item.status === 'blocked').length,
    destructiveExecuted: results.flatMap((item) => item.steps).filter((step) => step.status === 'destructive_executed').length,
  };

  await ensureDir(path.dirname(resultsPath));
  await fs.writeFile(resultsPath, JSON.stringify(results, null, 2), 'utf8');
  await fs.writeFile(summaryPath, JSON.stringify(summary, null, 2), 'utf8');
  process.stdout.write(`${summaryPath}\n`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});

import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

import {
  BREAKPOINTS,
  BUDGET_LIMITS,
  collectPageSignals,
  createIssueCollector,
  dismissOnboarding,
  ensureDir,
  gotoStable,
  login,
  relativePath,
  resolveDynamicPath,
  waitForSettledUi,
} from './browser-common.mjs';

const SCREENSHOT_BREAKPOINTS = {
  mobile: 'mobile',
  'desktop-wide': 'desktop',
  'tablet-landscape': 'tablet',
};

function parseArgs(argv) {
  const defaultUserUsername = `pwl${Date.now().toString(36).slice(-8)}`;
  const args = {
    outputDir: null,
    baseUrl: 'http://127.0.0.1:3000',
    userUsername: process.env.PW_AUDIT_USER_USERNAME || defaultUserUsername,
    userPassword: process.env.PW_AUDIT_USER_PASSWORD || 'PwAudit12345',
    adminUsername: process.env.PW_AUDIT_ADMIN_USERNAME || 'admin',
    adminPassword: process.env.PW_AUDIT_ADMIN_PASSWORD || 'admin123',
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
  try {
    return JSON.parse(await fs.readFile(manifestPath, 'utf8'));
  } catch {
    const catalogPath = path.join(process.cwd(), 'apps', 'web', 'e2e', 'realworld', 'catalog.json');
    const catalog = JSON.parse(await fs.readFile(catalogPath, 'utf8'));
    return {
      surfaces: catalog.map((surface) => ({
        surfaceId: surface.surfaceId,
        label: surface.label,
        group: surface.group,
        route: surface.route,
        path: surface.path || surface.route,
        auth: surface.auth,
        family: surface.family || surface.group,
        budgetClass: surface.budgetClass || 'overview',
        dynamicResolver: surface.dynamicResolver || null,
      })),
    };
  }
}

function needsTabletShot(surface) {
  return surface.budgetClass === 'workspace' || surface.budgetClass === 'table';
}

async function saveScreenshot(page, outputDir, surface, breakpoint) {
  const targetDirName = SCREENSHOT_BREAKPOINTS[breakpoint.name];
  if (!targetDirName) return null;
  if (targetDirName === 'tablet' && !needsTabletShot(surface)) return null;
  const screenshotDir = await ensureDir(path.join(outputDir, 'screens', targetDirName));
  const filePath = path.join(screenshotDir, `${surface.surfaceId}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  return filePath;
}

function buildAssertions(signals, limit) {
  const noHorizontalOverflow = signals.scrollWidth <= signals.clientWidth + 1;
  const mainUsable =
    !signals.mainRect || (signals.mainRect.left >= -1 && signals.mainRect.right <= signals.clientWidth + 1);
  const withinBudget = signals.screens <= limit + 0.01;
  const disclosureReady = signals.tabCount === 0 || signals.tabs.length > 0;
  const controlsVisible = signals.buttonCount + signals.fieldCount === 0 || signals.buttons.length + signals.fields.length > 0;

  return {
    noHorizontalOverflow,
    mainUsable,
    withinBudget,
    disclosureReady,
    controlsVisible,
  };
}

function normalizeResult(result, outputDir) {
  if (!result.screenshotPath) return result;
  return {
    ...result,
    screenshotPath: relativePath(outputDir, result.screenshotPath),
  };
}

async function runSurface(page, args, surface, breakpoint, outputDir) {
  const dynamic = await resolveDynamicPath(page, args.baseUrl, surface);
  if (!dynamic.path) {
    return {
      surfaceId: surface.surfaceId,
      label: surface.label,
      family: surface.family,
      group: surface.group,
      breakpoint: breakpoint.name,
      width: breakpoint.width,
      height: breakpoint.height,
      path: surface.path,
      finalPath: null,
      budgetClass: surface.budgetClass,
      limit: BUDGET_LIMITS[surface.budgetClass] || 3,
      status: 'blocked',
      blockedReason: dynamic.reason,
      screenshotPath: null,
      issues: {
        apiErrors: [],
        httpErrors: [],
        consoleErrors: [],
        pageErrors: [],
        requestFailures: [],
      },
    };
  }

  const issueCollector = createIssueCollector(page);
  try {
    await gotoStable(page, `${args.baseUrl}${dynamic.path}`);
    await dismissOnboarding(page);
    const signals = await collectPageSignals(page);
    const screenshotPath = await saveScreenshot(page, outputDir, surface, breakpoint);
    const limit = BUDGET_LIMITS[surface.budgetClass] || 3;
    const assertions = buildAssertions(signals, limit);

    return normalizeResult(
      {
        surfaceId: surface.surfaceId,
        label: surface.label,
        family: surface.family,
        group: surface.group,
        breakpoint: breakpoint.name,
        width: breakpoint.width,
        height: breakpoint.height,
        path: surface.path,
        finalPath: dynamic.path,
        title: signals.title,
        budgetClass: surface.budgetClass,
        limit,
        screens: signals.screens,
        screenshotPath,
        signals,
        issues: issueCollector.issues,
        assertions,
        passed: Object.values(assertions).every(Boolean),
        status: 'completed',
      },
      outputDir,
    );
  } catch (error) {
    const message = error instanceof Error ? error.stack || error.message : String(error);
    return {
      surfaceId: surface.surfaceId,
      label: surface.label,
      family: surface.family,
      group: surface.group,
      breakpoint: breakpoint.name,
      width: breakpoint.width,
      height: breakpoint.height,
      path: surface.path,
      finalPath: dynamic.path,
      budgetClass: surface.budgetClass,
      limit: BUDGET_LIMITS[surface.budgetClass] || 3,
      status: 'error',
      error: message,
      screenshotPath: null,
      issues: issueCollector.issues,
    };
  } finally {
    issueCollector.dispose();
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const manifest = await loadManifest(args.outputDir);
  const resultsPath = path.join(args.outputDir, 'raw', 'responsive-audit-results.json');
  const summaryPath = path.join(args.outputDir, 'raw', 'responsive-audit-summary.json');
  const selected = args.surfaceIds?.length
    ? manifest.surfaces.filter((surface) => args.surfaceIds.includes(surface.surfaceId))
    : manifest.surfaces;
  const browser = await chromium.launch({ headless: true });
  const results = [];

  try {
    for (const breakpoint of BREAKPOINTS) {
      const groups = [
        { auth: 'public', surfaces: selected.filter((surface) => surface.auth === 'public'), credentials: null },
        {
          auth: 'user',
          surfaces: selected.filter((surface) => surface.auth === 'user'),
          credentials: { username: args.userUsername, password: args.userPassword },
        },
        {
          auth: 'admin',
          surfaces: selected.filter((surface) => surface.auth === 'admin'),
          credentials: { username: args.adminUsername, password: args.adminPassword },
        },
      ];

      for (const group of groups) {
        if (!group.surfaces.length) continue;
        const context = await browser.newContext({
          viewport: { width: breakpoint.width, height: breakpoint.height },
          locale: 'zh-CN',
          timezoneId: 'Asia/Shanghai',
        });
        const page = await context.newPage();

        try {
          if (group.credentials) {
            try {
              await login(page, args.baseUrl, group.credentials);
              await waitForSettledUi(page, 700);
            } catch (error) {
              const message = error instanceof Error ? error.stack || error.message : String(error);
              for (const surface of group.surfaces) {
                results.push({
                  surfaceId: surface.surfaceId,
                  label: surface.label,
                  family: surface.family,
                  group: surface.group,
                  breakpoint: breakpoint.name,
                  width: breakpoint.width,
                  height: breakpoint.height,
                  path: surface.path,
                  finalPath: null,
                  budgetClass: surface.budgetClass,
                  limit: BUDGET_LIMITS[surface.budgetClass] || 3,
                  status: 'error',
                  error: `login failed: ${message}`,
                  screenshotPath: null,
                  issues: {
                    apiErrors: [],
                    httpErrors: [],
                    consoleErrors: [],
                    pageErrors: [],
                    requestFailures: [],
                  },
                });
              }
              continue;
            }
          }

          for (const surface of group.surfaces) {
            const result = await runSurface(page, args, surface, breakpoint, args.outputDir);
            results.push(result);
          }
        } finally {
          await context.close().catch(() => {});
        }
      }
    }
  } finally {
    await browser.close().catch(() => {});
  }

  const completed = results.filter((item) => item.status === 'completed');
  const summary = {
    generatedAt: new Date().toISOString(),
    total: results.length,
    surfaces: [...new Set(results.map((item) => item.surfaceId))].length,
    passed: completed.filter((item) => item.passed).length,
    failed: completed.filter((item) => !item.passed).length,
    blocked: results.filter((item) => item.status === 'blocked').length,
    errors: results.filter((item) => item.status === 'error').length,
    overBudget: completed.filter((item) => !item.assertions.withinBudget).length,
    overflow: completed.filter((item) => !item.assertions.noHorizontalOverflow).length,
    byBreakpoint: BREAKPOINTS.map((breakpoint) => {
      const rows = completed.filter((item) => item.breakpoint === breakpoint.name);
      return {
        breakpoint: breakpoint.name,
        total: rows.length,
        passed: rows.filter((item) => item.passed).length,
        overflow: rows.filter((item) => !item.assertions.noHorizontalOverflow).length,
        overBudget: rows.filter((item) => !item.assertions.withinBudget).length,
      };
    }),
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

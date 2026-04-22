import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

function parseArgs(argv) {
  const defaultUserUsername = `pwl${Date.now().toString(36).slice(-8)}`;
  const args = {
    outputDir: null,
    baseUrl: 'http://127.0.0.1:3000',
    userUsername: process.env.PW_AUDIT_USER_USERNAME || defaultUserUsername,
    userPassword: process.env.PW_AUDIT_USER_PASSWORD || 'PwAudit12345',
    adminUsername: process.env.PW_AUDIT_ADMIN_USERNAME || 'admin',
    adminPassword: process.env.PW_AUDIT_ADMIN_PASSWORD || 'admin123',
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
    if (token === '--user-username' && argv[index + 1]) {
      args.userUsername = String(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--user-password' && argv[index + 1]) {
      args.userPassword = String(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--admin-username' && argv[index + 1]) {
      args.adminUsername = String(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--admin-password' && argv[index + 1]) {
      args.adminPassword = String(argv[index + 1]);
      index += 1;
    }
  }

  if (!args.outputDir) {
    throw new Error('missing --output-dir');
  }

  return args;
}

function chunk(list, size) {
  const chunks = [];
  for (let index = 0; index < list.length; index += size) {
    chunks.push(list.slice(index, index + size));
  }
  return chunks;
}

function collectMarkedResults(lines) {
  return lines
    .filter((line) => line.includes('__PW_AUDIT_RESULTS__'))
    .flatMap((line) => {
      const markerIndex = line.indexOf('__PW_AUDIT_RESULTS__');
      if (markerIndex < 0) return [];
      try {
        const payload = JSON.parse(line.slice(markerIndex + '__PW_AUDIT_RESULTS__'.length));
        return Array.isArray(payload?.results) ? payload.results : [];
      } catch {
        return [];
      }
    });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const manifestPath = path.join(args.outputDir, 'raw', 'surface-manifest.json');
  const helperPath = path.join(process.cwd(), 'scripts', 'playwright-mcp-audit', 'mcp-helper.js');
  const crawlJsonPath = path.join(args.outputDir, 'raw', 'mcp-crawl-results.json');
  const consoleLogPath = path.join(args.outputDir, 'raw', 'mcp-console.log');

  const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
  const helperSource = await fs.readFile(helperPath, 'utf8');
  const helper = eval(helperSource);

  const byAuth = {
    public: ['register', 'login'].filter((surfaceId) => manifest.surfaces.some((surface) => surface.surfaceId === surfaceId)),
    user: manifest.surfaces.filter((surface) => surface.auth === 'user').map((surface) => surface.surfaceId),
    admin: manifest.surfaces.filter((surface) => surface.auth === 'admin').map((surface) => surface.surfaceId),
  };

  const authWorkflowUser = {
    username: `pwl${Date.now().toString().slice(-8)}`,
    password: 'PwAudit12345',
  };

  const groups = [
    {
      label: 'public-auth',
      surfaceIds: byAuth.public,
      auth: { mode: 'public' },
      authWorkflowUser,
    },
    ...chunk(byAuth.user, 8).map((surfaceIds, index) => ({
      label: `user-${String(index + 1).padStart(2, '0')}`,
      surfaceIds,
      auth: { mode: 'user', username: args.userUsername, password: args.userPassword },
    })),
    {
      label: 'admin-all',
      surfaceIds: byAuth.admin,
      auth: { mode: 'admin', username: args.adminUsername, password: args.adminPassword },
    },
  ];

  const consoleLines = [];
  const browser = await chromium.launch({ headless: true });

  try {
    for (const group of groups) {
      if (!group.surfaceIds.length) continue;
      const context = await browser.newContext({
        viewport: { width: 1440, height: 900 },
        locale: 'zh-CN',
        timezoneId: 'Asia/Shanghai',
      });
      const page = await context.newPage();
      page.on('console', (message) => {
        consoleLines.push(`[${group.label}] [${message.type()}] ${message.text()}`);
      });
      page.on('pageerror', (error) => {
        consoleLines.push(
          `[${group.label}] [pageerror] ${error instanceof Error ? error.stack || error.message : String(error)}`,
        );
      });
      console.log(`running ${group.label} (${group.surfaceIds.length})`);
      try {
        const summary = await helper(page, {
          manifestUrl: `file://${manifestPath}`,
          manifest,
          outputRoot: args.outputDir,
          baseUrl: args.baseUrl,
          groupLabel: group.label,
          surfaceIds: group.surfaceIds,
          auth: group.auth,
          authWorkflowUser: group.authWorkflowUser || null,
        });
        console.log(`finished ${group.label}: ${JSON.stringify(summary)}`);
      } finally {
        await context.close().catch(() => {});
      }
    }

    const results = collectMarkedResults(consoleLines);
    await fs.writeFile(crawlJsonPath, JSON.stringify(results, null, 2), 'utf8');
    await fs.writeFile(consoleLogPath, `${consoleLines.join('\n')}\n`, 'utf8');
    console.log(`saved ${results.length} results to ${crawlJsonPath}`);
  } finally {
    await browser.close().catch(() => {});
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});

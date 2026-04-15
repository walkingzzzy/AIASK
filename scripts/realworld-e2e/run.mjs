import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { Client } from 'pg';
import Redis from 'ioredis';
import { aggregateRealworldReports } from './report.mjs';
import { bootstrapBrowserEnvironment } from './bootstrap.mjs';
import { seedBrowserEnvironment } from './seed.mjs';
import {
  APPS_WEB,
  REPORTS_ROOT,
  ROOT,
  ensureDir,
  loadMergedEnv,
  removeIfExists,
  resolvePythonBin,
  runCommand,
  sanitizeIdentifier,
  sleep,
  startProcess,
  stopProcess,
  timestampId,
  waitForHttp,
} from './shared.mjs';

function parseArgs(argv) {
  const args = { browser: null, outputDir: null };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--browser' && argv[index + 1]) {
      args.browser = argv[index + 1];
      index += 1;
      continue;
    }
    if (token === '--output-dir' && argv[index + 1]) {
      args.outputDir = path.resolve(argv[index + 1]);
      index += 1;
    }
  }
  return args;
}

function buildDatabaseUrl(baseUrl, databaseName) {
  const url = new URL(baseUrl);
  url.pathname = `/${databaseName}`;
  return url.toString();
}

function buildAdminDatabaseUrl(baseUrl) {
  const url = new URL(baseUrl);
  url.pathname = '/postgres';
  return url.toString();
}

function buildRedisUrl(baseUrl, dbIndex) {
  const url = new URL(baseUrl);
  url.pathname = `/${dbIndex}`;
  return url.toString();
}

function parseDatabaseUrl(databaseUrl) {
  const url = new URL(databaseUrl);
  return {
    host: url.hostname,
    port: url.port || '5432',
    database: url.pathname.replace(/^\//, ''),
    user: decodeURIComponent(url.username || 'postgres'),
    password: decodeURIComponent(url.password || 'postgres'),
  };
}

async function recreateDatabase(adminDatabaseUrl, databaseName) {
  const client = new Client({ connectionString: adminDatabaseUrl });
  await client.connect();
  try {
    await client.query('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid()', [databaseName]);
    await client.query(`DROP DATABASE IF EXISTS "${databaseName}"`);
    await client.query(`CREATE DATABASE "${databaseName}"`);
  } finally {
    await client.end();
  }
}

async function dropDatabase(adminDatabaseUrl, databaseName) {
  const client = new Client({ connectionString: adminDatabaseUrl });
  await client.connect();
  try {
    await client.query('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid()', [databaseName]);
    await client.query(`DROP DATABASE IF EXISTS "${databaseName}"`);
  } finally {
    await client.end();
  }
}

async function flushRedis(redisUrl) {
  const redis = new Redis(redisUrl, { lazyConnect: true });
  await redis.connect();
  try {
    await redis.flushdb();
  } finally {
    await redis.quit();
  }
}

function browserPortOffset(browser) {
  if (browser === 'webkit') return 20;
  if (browser === 'mobile') return 40;
  return 0;
}

function browserTag(browser) {
  if (browser === 'webkit') return 'wk';
  if (browser === 'mobile') return 'mb';
  return 'cr';
}

function buildRuntime({ baseEnv, browser, runId, outputRoot }) {
  const offset = browserPortOffset(browser);
  const tag = browserTag(browser);
  const shortRunId = runId.slice(0, 12).replace(/-/g, '').toLowerCase();
  const envName = `realworld-${runId}`;
  const browserDir = path.join(outputRoot, browser);
  const runtimeDir = path.join(browserDir, 'runtime');
  const databaseName = sanitizeIdentifier(`stockdb_e2e_${browser}_${shortRunId}`, 48);
  const databaseUrl = buildDatabaseUrl(baseEnv.DATABASE_URL || 'postgresql://postgres:postgres@127.0.0.1:5432/stockdb', databaseName);
  const adminDatabaseUrl = buildAdminDatabaseUrl(baseEnv.DATABASE_URL || 'postgresql://postgres:postgres@127.0.0.1:5432/stockdb');
  const redisUrl = buildRedisUrl(baseEnv.REDIS_URL || 'redis://127.0.0.1:6379', 10 + offset / 20);
  const webPort = 3400 + offset;
  const bffPort = 3401 + offset;
  const webBaseUrl = `http://127.0.0.1:${webPort}`;
  const bffBaseUrl = `http://127.0.0.1:${bffPort}/api`;
  const playwrightOutputDir = path.join(browserDir, 'playwright-output');
  const playwrightJsonPath = path.join(browserDir, 'playwright-report.json');
  const playwrightHtmlDir = path.join(browserDir, 'playwright-html');

  return {
    runId,
    shortRunId,
    envName,
    resetMode: 'full-reset-per-browser',
    browser,
    outputDir: browserDir,
    runtimeDir,
    mcpRuntimeDir: runtimeDir,
    webPort,
    bffPort,
    webBaseUrl,
    bffBaseUrl,
    wsUrl: `http://127.0.0.1:${bffPort}`,
    databaseName,
    databaseUrl,
    adminDatabaseUrl,
    redisUrl,
    playwrightOutputDir,
    playwrightJsonPath,
    playwrightHtmlDir,
    browserUsername: `rw_${tag}_${shortRunId}`,
    browserPassword: `rw_${browser}_${shortRunId}_pass`,
    baseEnv,
    pgClientFactory: () => new Client({ connectionString: databaseUrl }),
  };
}

async function prepareRuntime(runtime) {
  await removeIfExists(runtime.outputDir);
  await ensureDir(runtime.outputDir);
  await ensureDir(runtime.runtimeDir);
  await recreateDatabase(runtime.adminDatabaseUrl, runtime.databaseName);
  await flushRedis(runtime.redisUrl);
}

async function teardownRuntime(runtime) {
  await flushRedis(runtime.redisUrl).catch(() => null);
  await dropDatabase(runtime.adminDatabaseUrl, runtime.databaseName).catch(() => null);
}

async function runMigrations(runtime) {
  const result = await runCommand('npm', ['run', 'migrate', '-w', 'apps/bff'], {
    cwd: ROOT,
    env: {
      ...process.env,
      ...runtime.baseEnv,
      DATABASE_URL: runtime.databaseUrl,
    },
    stdoutPath: path.join(runtime.outputDir, 'migrate.stdout.log'),
    stderrPath: path.join(runtime.outputDir, 'migrate.stderr.log'),
  });
  if (result.exitCode !== 0) {
    throw new Error(`database migrations failed for ${runtime.browser}`);
  }
}

async function runMcpSchemaBootstrap(runtime) {
  const pythonBin = resolvePythonBin();
  const pythonPath = [
    path.join(ROOT, 'packages', 'akshare-mcp', 'src'),
    path.join(ROOT, 'packages', 'strategy-factory', 'src'),
  ].join(path.delimiter);
  const database = parseDatabaseUrl(runtime.databaseUrl);
  const result = await runCommand(pythonBin, [path.join(ROOT, 'scripts', 'realworld-e2e', 'mcp_schema_bootstrap.py')], {
    cwd: ROOT,
    env: {
      ...process.env,
      ...runtime.baseEnv,
      PYTHONPATH: pythonPath,
      AKSHARE_MCP_STARTUP_PROFILE: 'tool-only',
      DB_HOST: database.host,
      DB_PORT: database.port,
      DB_NAME: database.database,
      DB_USER: database.user,
      DB_PASSWORD: database.password,
    },
    stdoutPath: path.join(runtime.outputDir, 'mcp-schema-bootstrap.stdout.log'),
    stderrPath: path.join(runtime.outputDir, 'mcp-schema-bootstrap.stderr.log'),
  });
  if (result.exitCode !== 0) {
    throw new Error(`mcp schema bootstrap failed for ${runtime.browser}`);
  }
}

function buildBffEnv(runtime) {
  const pythonBin = resolvePythonBin();
  const pythonPath = [
    path.join(ROOT, 'packages', 'akshare-mcp', 'src'),
    path.join(ROOT, 'packages', 'strategy-factory', 'src'),
  ].join(path.delimiter);
  const database = parseDatabaseUrl(runtime.databaseUrl);

  return {
    ...process.env,
    ...runtime.baseEnv,
    E2E_ENV_NAME: runtime.envName,
    E2E_RUN_ID: runtime.runId,
    E2E_BROWSER: runtime.browser,
    E2E_RESET_MODE: runtime.resetMode,
    NODE_ENV: 'development',
    BFF_PORT: String(runtime.bffPort),
    DATABASE_URL: runtime.databaseUrl,
    DB_HOST: database.host,
    DB_PORT: database.port,
    DB_NAME: database.database,
    DB_USER: database.user,
    DB_PASSWORD: database.password,
    POSTGRES_HOST: database.host,
    POSTGRES_PORT: database.port,
    POSTGRES_DB: database.database,
    POSTGRES_USER: database.user,
    POSTGRES_PASSWORD: database.password,
    REDIS_URL: runtime.redisUrl,
    CORS_ORIGIN: `${runtime.webBaseUrl},http://localhost:${runtime.webPort}`,
    DATABASE_POOL_MAX: runtime.baseEnv.DATABASE_POOL_MAX || '4',
    MCP_POOL_SIZE: runtime.baseEnv.MCP_POOL_SIZE || '4',
    MCP_POOL_ACQUIRE_TIMEOUT_MS: runtime.baseEnv.MCP_POOL_ACQUIRE_TIMEOUT_MS || '15000',
    MCP_STDIO_STARTUP_PROFILE: process.env.E2E_MCP_STDIO_STARTUP_PROFILE || 'worker',
    MCP_STDIO_CWD: runtime.mcpRuntimeDir,
    MCP_STDIO_COMMAND: pythonBin,
    MCP_STDIO_ARGS: runtime.baseEnv.MCP_STDIO_ARGS || '["-m","akshare_mcp.server"]',
    MCP_STDIO_PYTHONPATH: pythonPath,
    APP_ENABLE_DEMO_USER: runtime.baseEnv.APP_ENABLE_DEMO_USER || 'true',
    APP_ADMIN_PASSWORD: runtime.baseEnv.APP_ADMIN_PASSWORD || 'admin123',
    APP_DEMO_PASSWORD: runtime.baseEnv.APP_DEMO_PASSWORD || 'demo123',
    APP_JWT_SECRET: runtime.baseEnv.APP_JWT_SECRET || 'dev-secret-change-me',
    MARKET_SCHEDULER_ENABLED: 'false',
    STRATEGY_MARKET_AUTO_REFRESH_ENABLED: 'false',
    STRATEGY_FACTORY_SCHEDULE_MODE: 'manual',
    STRATEGY_FACTORY_STARTUP_WARMUP_ENABLED: '0',
    STARTUP_EMBEDDING_CHECK_ENABLED: '0',
  };
}

function buildWebEnv(runtime) {
  return {
    ...process.env,
    ...runtime.baseEnv,
    E2E_ENV_NAME: runtime.envName,
    E2E_RUN_ID: runtime.runId,
    E2E_BROWSER: runtime.browser,
    NEXT_PUBLIC_BFF_BASE_URL: runtime.bffBaseUrl,
    NEXT_PUBLIC_WS_URL: runtime.wsUrl,
  };
}

async function startServers(runtime) {
  const bffHandle = startProcess('npm', ['run', 'dev', '-w', 'apps/bff'], {
    cwd: ROOT,
    env: buildBffEnv(runtime),
    logPath: path.join(runtime.outputDir, 'bff.log'),
  });
  const webHandle = startProcess('npx', ['next', 'dev', '-p', String(runtime.webPort)], {
    cwd: APPS_WEB,
    env: buildWebEnv(runtime),
    logPath: path.join(runtime.outputDir, 'web.log'),
  });

  try {
    await waitForHttp(`${runtime.bffBaseUrl}/health/ready`, { timeoutMs: 240_000 });
    await waitForHttp(`${runtime.bffBaseUrl}/health/mcp`, {
      timeoutMs: 240_000,
      validateResponse: (response) => response.status < 500,
    });
    await waitForHttp(`${runtime.webBaseUrl}/login`, {
      timeoutMs: 240_000,
      validateResponse: (response) => response.status < 500,
    });
  } catch (error) {
    await stopProcess(webHandle);
    await stopProcess(bffHandle);
    throw error;
  }

  return { bffHandle, webHandle };
}

async function runPlaywright(runtime, bundlePath) {
  const env = {
    ...process.env,
    ...runtime.baseEnv,
    PW_NO_WEBSERVER: '1',
    E2E_ENV_NAME: runtime.envName,
    E2E_RUN_ID: runtime.runId,
    E2E_BROWSER: runtime.browser,
    E2E_RESET_MODE: runtime.resetMode,
    E2E_BASE_URL: runtime.webBaseUrl,
    E2E_BFF_BASE_URL: runtime.bffBaseUrl,
    E2E_FIXTURE_BUNDLE_PATH: bundlePath,
    E2E_PLAYWRIGHT_OUTPUT_DIR: runtime.playwrightOutputDir,
    E2E_PLAYWRIGHT_JSON: runtime.playwrightJsonPath,
    E2E_PLAYWRIGHT_HTML: runtime.playwrightHtmlDir,
    E2E_BROWSER_USERNAME: runtime.browserUsername,
    E2E_BROWSER_PASSWORD: runtime.browserPassword,
  };

  return runCommand('npx', ['playwright', 'test', '--config', 'apps/web/playwright.realworld.config.ts'], {
    cwd: ROOT,
    env,
    stdoutPath: path.join(runtime.outputDir, 'playwright.stdout.log'),
    stderrPath: path.join(runtime.outputDir, 'playwright.stderr.log'),
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const runId = timestampId();
  const outputRoot = args.outputDir || path.join(REPORTS_ROOT, runId);
  const baseEnv = await loadMergedEnv();
  const browsers = args.browser ? [args.browser] : ['chromium', 'webkit', 'mobile'];
  const browserResults = [];
  const startedAt = new Date().toISOString();

  await ensureDir(outputRoot);

  let hasFailures = false;

  for (const browser of browsers) {
    const runtime = buildRuntime({ baseEnv, browser, runId, outputRoot });
    const metaPath = path.join(runtime.outputDir, 'browser-meta.json');
    const browserMeta = {
      browser,
      startedAt: new Date().toISOString(),
      status: 'running',
      outputDir: runtime.outputDir,
    };

    try {
      await prepareRuntime(runtime);
      await runMigrations(runtime);
      await runMcpSchemaBootstrap(runtime);
      await bootstrapBrowserEnvironment(runtime);
      const servers = await startServers(runtime);

      try {
        const bundle = await seedBrowserEnvironment(runtime);
        const bundlePath = path.join(runtime.outputDir, 'fixture-bundle.json');
        await fs.writeFile(bundlePath, JSON.stringify(bundle, null, 2), 'utf8');

        const playwrightResult = await runPlaywright(runtime, bundlePath);
        browserMeta.status = playwrightResult.exitCode === 0 ? 'passed' : 'failed';
        browserMeta.playwrightExitCode = playwrightResult.exitCode;
        if (playwrightResult.exitCode !== 0) {
          hasFailures = true;
        }
      } finally {
        await stopProcess(servers.webHandle);
        await stopProcess(servers.bffHandle);
      }
    } catch (error) {
      browserMeta.status = 'failed';
      browserMeta.error = error instanceof Error ? error.stack || error.message : String(error);
      hasFailures = true;
    } finally {
      browserMeta.endedAt = new Date().toISOString();
      browserMeta.playwrightJsonPath = runtime.playwrightJsonPath;
      browserMeta.playwrightHtmlDir = runtime.playwrightHtmlDir;
      await ensureDir(runtime.outputDir);
      await fs.writeFile(metaPath, JSON.stringify(browserMeta, null, 2), 'utf8');
      browserResults.push({
        browser,
        outputDir: runtime.outputDir,
        playwrightJsonPath: runtime.playwrightJsonPath,
        playwrightHtmlDir: runtime.playwrightHtmlDir,
      });
      await teardownRuntime(runtime);
      await sleep(2_000);
    }
  }

  const endedAt = new Date().toISOString();
  const aggregate = await aggregateRealworldReports(outputRoot, browserResults, {
    runId,
    envName: `realworld-${runId}`,
    startedAt,
    endedAt,
  });

  if (aggregate.uniqueSurfaceCount < 54) {
    hasFailures = true;
  }

  process.exitCode = hasFailures ? 1 : 0;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

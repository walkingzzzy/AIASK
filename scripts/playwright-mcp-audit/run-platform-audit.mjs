import { spawn } from 'node:child_process';
import { createWriteStream } from 'node:fs';
import fs from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';

import { ensureDir } from './browser-common.mjs';
import { runCommand } from './process-common.mjs';

const DEFAULT_WEB_PORT = 3300;
const DEFAULT_BFF_PORT = 3301;
const STARTUP_TIMEOUT_MS = 120000;
const STOP_TIMEOUT_MS = 10000;
const AUDIT_ADMIN_PASSWORD = process.env.PW_AUDIT_RUNTIME_ADMIN_PASSWORD || 'PwAuditAdmin#2026';

function parseArgs(argv) {
  const args = {
    outputDir: path.resolve(process.cwd(), 'artifacts', 'frontend-e2e-audit'),
    enforce: false,
    webPort: Number.parseInt(process.env.PW_AUDIT_WEB_PORT || '', 10) || DEFAULT_WEB_PORT,
    bffPort: Number.parseInt(process.env.PW_AUDIT_BFF_PORT || '', 10) || DEFAULT_BFF_PORT,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--output-dir' && argv[index + 1]) {
      args.outputDir = path.resolve(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === '--web-port' && argv[index + 1]) {
      args.webPort = Number.parseInt(argv[index + 1], 10) || args.webPort;
      index += 1;
      continue;
    }
    if (token === '--bff-port' && argv[index + 1]) {
      args.bffPort = Number.parseInt(argv[index + 1], 10) || args.bffPort;
      index += 1;
      continue;
    }
    if (token === '--enforce') {
      args.enforce = true;
    }
  }

  return args;
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, 'utf8'));
}

async function readJsonIfExists(filePath) {
  try {
    return await readJson(filePath);
  } catch {
    return null;
  }
}

async function findFreePort(preferredPort, maxAttempts = 40, forbiddenPorts = new Set()) {
  for (let index = 0; index < maxAttempts; index += 1) {
    const candidate = preferredPort + index;
    if (forbiddenPorts.has(candidate)) {
      continue;
    }
    const available = await new Promise((resolve) => {
      const server = net.createServer();
      server.unref();
      server.on('error', () => resolve(false));
      server.listen(candidate, '127.0.0.1', () => {
        server.close(() => resolve(true));
      });
    });
    if (available) {
      return candidate;
    }
  }
  throw new Error(`unable to find a free port near ${preferredPort}`);
}

function startManagedProcess({ label, command, args, cwd, env, logDir }) {
  const stdoutPath = path.join(logDir, `${label}.stdout.log`);
  const stderrPath = path.join(logDir, `${label}.stderr.log`);
  const stdoutStream = createWriteStream(stdoutPath, { flags: 'w' });
  const stderrStream = createWriteStream(stderrPath, { flags: 'w' });
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, ...env },
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: true,
  });

  child.stdout.pipe(stdoutStream);
  child.stderr.pipe(stderrStream);

  let exitState = null;
  const exited = new Promise((resolve) => {
    child.on('exit', (code, signal) => {
      exitState = { code, signal };
      resolve(exitState);
    });
  });

  return {
    label,
    command,
    args,
    cwd,
    env,
    child,
    exited,
    get exitState() {
      return exitState;
    },
    stdoutPath,
    stderrPath,
    stdoutStream,
    stderrStream,
  };
}

async function closeStream(stream) {
  if (!stream) return;
  await new Promise((resolve) => {
    stream.end(resolve);
  }).catch(() => {});
}

async function stopManagedProcess(service) {
  if (!service) return;

  const finalize = async () => {
    await Promise.all([closeStream(service.stdoutStream), closeStream(service.stderrStream)]);
  };

  if (!service.child?.pid || service.exitState) {
    await finalize();
    return;
  }

  try {
    process.kill(-service.child.pid, 'SIGTERM');
  } catch {
    service.child.kill('SIGTERM');
  }

  const exited = await Promise.race([
    service.exited.then(() => true),
    new Promise((resolve) => setTimeout(() => resolve(false), STOP_TIMEOUT_MS)),
  ]);

  if (!exited) {
    try {
      process.kill(-service.child.pid, 'SIGKILL');
    } catch {
      service.child.kill('SIGKILL');
    }
    await service.exited.catch(() => {});
  }

  await finalize();
}

async function waitForHttpReady(url, options = {}) {
  const {
    label = url,
    timeoutMs = STARTUP_TIMEOUT_MS,
    intervalMs = 1000,
    accept = (response) => response.ok,
    onTick = null,
  } = options;
  const startedAt = Date.now();
  let lastError = null;

  while (Date.now() - startedAt < timeoutMs) {
    if (typeof onTick === 'function') {
      const tickError = await onTick();
      if (tickError) {
        throw tickError;
      }
    }

    try {
      const response = await fetch(url, {
        redirect: 'manual',
        headers: { 'cache-control': 'no-store' },
      });
      const bodyText = await response.text().catch(() => '');
      if (await accept(response, bodyText)) {
        return;
      }
      lastError = new Error(`${label} is not ready yet: HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  const detail = lastError instanceof Error ? lastError.message : String(lastError || 'unknown');
  throw new Error(`timed out waiting for ${label}: ${detail}`);
}

function serviceExitedError(service) {
  const exit = service.exitState || { code: null, signal: null };
  return new Error(
    `${service.label} exited before becoming ready (code=${String(exit.code)} signal=${String(exit.signal)}). logs: ${service.stdoutPath}, ${service.stderrPath}`,
  );
}

async function resolveAdminAuditCredentials(bffBaseUrl) {
  const username = process.env.PW_AUDIT_ADMIN_USERNAME || 'admin';
  const candidates = [
    process.env.PW_AUDIT_ADMIN_PASSWORD,
    'admin123',
    'admin',
    AUDIT_ADMIN_PASSWORD,
  ]
    .map((value) => String(value || '').trim())
    .filter(Boolean);
  const tried = [];

  for (const password of [...new Set(candidates)]) {
    tried.push(password);
    try {
      const response = await fetch(`${bffBaseUrl}/auth/login`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (response.ok) {
        return { username, password };
      }
    } catch {
      // Ignore transient probe failures and continue trying the next credential.
    }
  }

  throw new Error(`unable to resolve admin audit credentials for ${username}; tried ${tried.length} candidate(s)`);
}

async function startAuditRuntime(args, outputDir) {
  const runtimeDir = await ensureDir(path.join(outputDir, 'raw', 'runtime'));
  const logDir = await ensureDir(path.join(runtimeDir, 'logs'));
  const webPort = await findFreePort(args.webPort);
  const bffPort = await findFreePort(webPort === args.bffPort ? args.bffPort + 1 : args.bffPort, 40, new Set([webPort]));
  const webBaseUrl = `http://127.0.0.1:${webPort}`;
  const bffBaseUrl = `http://127.0.0.1:${bffPort}/api`;
  const workspaceRoot = process.cwd();

  const bffService = startManagedProcess({
    label: 'bff',
    command: 'node',
    args: [path.join(workspaceRoot, 'apps', 'bff', 'dist', 'main.js')],
    cwd: workspaceRoot,
    env: {
      NODE_ENV: 'production',
      BFF_PORT: String(bffPort),
      CORS_ORIGIN: [webBaseUrl, webBaseUrl.replace('127.0.0.1', 'localhost')].join(','),
      APP_ADMIN_PASSWORD: AUDIT_ADMIN_PASSWORD,
    },
    logDir,
  });

  await waitForHttpReady(`${bffBaseUrl}/health/live`, {
    label: 'bff health',
    accept: async (response, bodyText) => {
      if (!response.ok) return false;
      try {
        const body = bodyText ? JSON.parse(bodyText) : {};
        return body?.success === true;
      } catch {
        return false;
      }
    },
    onTick: async () => (bffService.exitState ? serviceExitedError(bffService) : null),
  });

  const webService = startManagedProcess({
    label: 'web',
    command: 'node',
    args: [
      path.join(workspaceRoot, 'node_modules', 'next', 'dist', 'bin', 'next'),
      'start',
      '-p',
      String(webPort),
      '-H',
      '127.0.0.1',
    ],
    cwd: path.join(workspaceRoot, 'apps', 'web'),
    env: {
      NODE_ENV: 'production',
      PORT: String(webPort),
      BFF_BASE_URL: bffBaseUrl,
      NEXT_PUBLIC_BFF_BASE_URL: bffBaseUrl,
      WS_URL: `ws://127.0.0.1:${bffPort}`,
      NEXT_PUBLIC_WS_URL: `ws://127.0.0.1:${bffPort}`,
      ALLOW_LOCALHOST_PORT_WILDCARD: 'true',
    },
    logDir,
  });

  await waitForHttpReady(`${webBaseUrl}/api/bff-availability`, {
    label: 'web runtime',
    accept: async (response, bodyText) => {
      if (!response.ok) return false;
      try {
        const body = bodyText ? JSON.parse(bodyText) : {};
        return body?.reachable === true;
      } catch {
        return false;
      }
    },
    onTick: async () => (webService.exitState ? serviceExitedError(webService) : null),
  });

  await waitForHttpReady(`${webBaseUrl}/login`, {
    label: 'web login page',
    accept: async (response, bodyText) => response.ok && /<html/i.test(bodyText),
    onTick: async () => (webService.exitState ? serviceExitedError(webService) : null),
  });

  const metadata = {
    generatedAt: new Date().toISOString(),
    web: {
      port: webPort,
      baseUrl: webBaseUrl,
      stdoutLog: webService.stdoutPath,
      stderrLog: webService.stderrPath,
    },
    bff: {
      port: bffPort,
      baseUrl: bffBaseUrl,
      stdoutLog: bffService.stdoutPath,
      stderrLog: bffService.stderrPath,
    },
  };
  const metadataPath = path.join(runtimeDir, 'runtime-bootstrap.json');
  await fs.writeFile(metadataPath, JSON.stringify(metadata, null, 2), 'utf8');

  return {
    webBaseUrl,
    bffBaseUrl,
    metadataPath,
    logDir,
    services: [webService, bffService],
  };
}

async function stopAuditRuntime(runtime) {
  if (!runtime?.services?.length) return;
  for (const service of runtime.services) {
    await stopManagedProcess(service);
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const scriptsDir = path.join(process.cwd(), 'scripts', 'playwright-mcp-audit');
  await fs.rm(args.outputDir, { recursive: true, force: true });
  await ensureDir(path.join(args.outputDir, 'raw'));

  let snapshotCreated = false;
  let runtime = null;
  let auditError = null;
  let auditStdout = null;
  let auditStderr = null;

  try {
    await runCommand('node', [path.join(scriptsDir, 'build-manifest.mjs'), '--output-dir', args.outputDir]);
    await runCommand('node', [path.join(scriptsDir, 'env-snapshot.mjs'), '--output-dir', args.outputDir]);
    snapshotCreated = true;
    runtime = await startAuditRuntime(args, args.outputDir);
    const adminCredentials = await resolveAdminAuditCredentials(runtime.bffBaseUrl);
    auditStdout = createWriteStream(path.join(runtime.logDir, 'run-flow-audit.stdout.log'), { flags: 'w' });
    auditStderr = createWriteStream(path.join(runtime.logDir, 'run-flow-audit.stderr.log'), { flags: 'w' });
    await runCommand(
      'node',
      [path.join(scriptsDir, 'run-flow-audit.mjs'), '--output-dir', args.outputDir, '--base-url', runtime.webBaseUrl],
      {
        env: {
          PW_AUDIT_API_BASE_URL: runtime.bffBaseUrl,
          PW_AUDIT_ADMIN_USERNAME: adminCredentials.username,
          PW_AUDIT_ADMIN_PASSWORD: adminCredentials.password,
        },
        stdoutFile: auditStdout,
        stderrFile: auditStderr,
      },
    );
  } catch (error) {
    auditError = error;
  } finally {
    await Promise.all([closeStream(auditStdout), closeStream(auditStderr)]);
    await stopAuditRuntime(runtime).catch(() => {});
    if (snapshotCreated) {
      await runCommand('node', [path.join(scriptsDir, 'env-restore.mjs'), '--output-dir', args.outputDir], {
        allowFailure: true,
      });
    }
  }

  const platformSummaryPath = path.join(args.outputDir, 'raw', 'platform-summary.json');
  const platformSummary = await readJsonIfExists(platformSummaryPath);

  if (auditError) {
    throw auditError;
  }

  if (!platformSummary) {
    throw new Error(`missing platform summary: ${platformSummaryPath}`);
  }

  if (args.enforce && !platformSummary.gatePassed) {
    const inScope = platformSummary.surfaces?.inScope ?? {};
    const journeys = platformSummary.journeys ?? {};
    throw new Error(
      `frontend platform audit failed: surfaces passed=${inScope.passed ?? 0} failed=${inScope.failed ?? 0} blocked=${inScope.blocked ?? 0} total=${inScope.total ?? 0}; journeys passed=${journeys.passed ?? 0} failed=${journeys.failed ?? 0} blocked=${journeys.blocked ?? 0} total=${journeys.total ?? 0}`,
    );
  }

  process.stdout.write(`${platformSummaryPath}\n`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});

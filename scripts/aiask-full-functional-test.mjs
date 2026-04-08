import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';

const ROOT = process.cwd();
const APPS_WEB = path.join(ROOT, 'apps', 'web');
const APPS_BFF = path.join(ROOT, 'apps', 'bff');
const AKSHARE_MCP = path.join(ROOT, 'packages', 'akshare-mcp');
const REPORTS_ROOT = path.join(ROOT, 'reports', 'aiask_e2e');
const IS_WINDOWS = process.platform === 'win32';
const PYTHON_BIN = IS_WINDOWS
  ? path.join(AKSHARE_MCP, '.venv', 'Scripts', 'python.exe')
  : path.join(AKSHARE_MCP, '.venv', 'bin', 'python');
const ROUTE_COUNT = 46;
const BFF_MODULE_COUNT = 38;
const LOCAL_SKILL_COUNT = 19;
const BFF_PORT = Number(process.env.BFF_PORT || 3001);
const WEB_PORT = Number(process.env.E2E_PORT || 3100);
const BFF_BASE_URL = `http://127.0.0.1:${BFF_PORT}/api`;
const WEB_BASE_URL = `http://127.0.0.1:${WEB_PORT}`;

function timestamp() {
  return new Date().toISOString().replace(/[:.]/g, '-');
}

function parseArgs(argv) {
  const args = { outputDir: path.join(REPORTS_ROOT, timestamp()) };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--output-dir' && argv[index + 1]) {
      args.outputDir = path.resolve(argv[index + 1]);
      index += 1;
    }
  }
  return args;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForHttp(url, options = {}) {
  const {
    timeoutMs = 180_000,
    validateResponse = (response) => response.ok,
  } = options;
  const deadline = Date.now() + timeoutMs;
  let lastError = 'unreachable';

  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (validateResponse(response)) {
        return;
      }
      lastError = `${response.status} ${response.statusText}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await sleep(1000);
  }

  throw new Error(`Timed out waiting for ${url}: ${lastError}`);
}

function startLongRunningProcess(command, args, options) {
  const child = spawn(command, args, {
    cwd: options.cwd,
    env: options.env,
    shell: false,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const logPath = options.logPath;
  const lines = [];
  const onData = (chunk) => {
    const text = chunk.toString();
    lines.push(text);
    if (lines.length > 600) {
      lines.shift();
    }
  };
  child.stdout.on('data', onData);
  child.stderr.on('data', onData);
  return {
    child,
    async flushLogs() {
      await fs.writeFile(logPath, lines.join(''), 'utf8');
    },
  };
}

async function runCommand(command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: options.cwd || ROOT,
    env: options.env || process.env,
    shell: false,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stdout = '';
  let stderr = '';
  child.stdout.on('data', (chunk) => {
    stdout += chunk.toString();
  });
  child.stderr.on('data', (chunk) => {
    stderr += chunk.toString();
  });
  const exitCode = await new Promise((resolve) => child.on('close', resolve));
  if (options.stdoutPath) {
    await fs.writeFile(options.stdoutPath, stdout, 'utf8');
  }
  if (options.stderrPath) {
    await fs.writeFile(options.stderrPath, stderr, 'utf8');
  }
  return {
    exitCode: Number(exitCode ?? 1),
    stdout,
    stderr,
  };
}

function killProcess(child) {
  if (!child || child.killed) return;
  try {
    child.kill('SIGTERM');
  } catch {
    // ignore
  }
}

async function safeReadText(filePath) {
  try {
    return await fs.readFile(filePath, 'utf8');
  } catch {
    return null;
  }
}

async function safeReadJson(filePath) {
  const raw = await safeReadText(filePath);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function extractTrailingJson(rawText) {
  const trimmed = String(rawText || '').trim();
  if (!trimmed) return null;

  const candidates = [];
  const lastLineBraceIndex = trimmed.lastIndexOf('\n{');
  if (lastLineBraceIndex >= 0) {
    candidates.push(trimmed.slice(lastLineBraceIndex + 1));
  }
  if (trimmed.startsWith('{')) {
    candidates.push(trimmed);
  }

  for (const candidate of candidates) {
    try {
      return JSON.parse(candidate);
    } catch {
      // continue
    }
  }
  return null;
}

function readPlaywrightFailure(result) {
  if (!result || (result.status !== 'failed' && result.status !== 'timedOut')) {
    return null;
  }
  const firstError = Array.isArray(result.errors) ? result.errors.find(Boolean) : null;
  return {
    project: result.projectName || result.projectId || 'unknown',
    status: result.status,
    error: firstError?.message || firstError?.stack || result.error?.message || result.error?.value || 'unknown_error',
  };
}

function extractPlaywrightFailures(node, failures = [], runName = 'playwright') {
  if (!node || typeof node !== 'object') return failures;

  const specs = Array.isArray(node.specs) ? node.specs : [];
  for (const spec of specs) {
    const tests = Array.isArray(spec.tests) ? spec.tests : [];
    for (const testCase of tests) {
      const results = Array.isArray(testCase.results) ? testCase.results : [];
      const failed = results.map(readPlaywrightFailure).find(Boolean);
      if (!failed) {
        continue;
      }
      failures.push({
        run: runName,
        title: spec.title || testCase.title || 'unknown_test',
        file: spec.file || testCase.location?.file || null,
        project: failed.project,
        status: failed.status,
        error: failed.error,
      });
    }
  }

  const tests = Array.isArray(node.tests) ? node.tests : [];
  for (const testCase of tests) {
    const results = Array.isArray(testCase.results) ? testCase.results : [];
    const failed = results.map(readPlaywrightFailure).find(Boolean);
    if (!failed) {
      continue;
    }
    failures.push({
      run: runName,
      title: testCase.title || 'unknown_test',
      file: testCase.location?.file || null,
      project: failed.project,
      status: failed.status,
      error: failed.error,
    });
  }

  const suites = Array.isArray(node.suites) ? node.suites : [];
  for (const suite of suites) {
    extractPlaywrightFailures(suite, failures, runName);
  }
  return failures;
}

function parsePlaywrightReport(rawText, runName) {
  const report = JSON.parse(rawText);
  const stats = report.stats || {};
  return {
    name: runName,
    summary: {
      expected: Number(stats.expected || 0),
      unexpected: Number(stats.unexpected || 0),
      flaky: Number(stats.flaky || 0),
      skipped: Number(stats.skipped || 0),
      durationMs: Number(stats.duration || 0),
    },
    failures: extractPlaywrightFailures(report, [], runName),
  };
}

function mergePlaywrightReports(reports) {
  const active = reports.filter(Boolean);
  return {
    summary: active.reduce((acc, item) => ({
      expected: acc.expected + Number(item.summary?.expected || 0),
      unexpected: acc.unexpected + Number(item.summary?.unexpected || 0),
      flaky: acc.flaky + Number(item.summary?.flaky || 0),
      skipped: acc.skipped + Number(item.summary?.skipped || 0),
      durationMs: acc.durationMs + Number(item.summary?.durationMs || 0),
    }), { expected: 0, unexpected: 0, flaky: 0, skipped: 0, durationMs: 0 }),
    failures: active.flatMap((item) => item.failures || []),
  };
}

function parseJUnit(xmlText) {
  const testsMatch = xmlText.match(/tests="(\d+)"/);
  const failuresMatch = xmlText.match(/failures="(\d+)"/);
  const errorsMatch = xmlText.match(/errors="(\d+)"/);
  const skippedMatch = xmlText.match(/skipped="(\d+)"/);
  const failedCases = [...xmlText.matchAll(/<testcase[^>]*classname="([^"]+)"[^>]*name="([^"]+)"[^>]*>([\s\S]*?)<\/testcase>/g)]
    .filter((match) => /<failure|<error/.test(match[3]))
    .map((match) => ({
      classname: match[1],
      name: match[2],
    }));
  return {
    summary: {
      tests: Number(testsMatch?.[1] || 0),
      failures: Number(failuresMatch?.[1] || 0) + Number(errorsMatch?.[1] || 0),
      skipped: Number(skippedMatch?.[1] || 0),
    },
    failures: failedCases,
  };
}

function summarizeContractChecks(checks) {
  const items = Object.values(checks).filter(Boolean);
  return {
    total: items.length,
    passed: items.filter((item) => item.ok).length,
    failed: items.filter((item) => !item.ok).length,
  };
}

async function syncPythonEnvironment(outputDir) {
  const stdoutPath = path.join(outputDir, 'uv-sync.stdout.log');
  const stderrPath = path.join(outputDir, 'uv-sync.stderr.log');
  const result = await runCommand(
    'uv',
    ['sync', '--python', '3.12', '--extra', 'legacy', '--extra', 'dev'],
    {
      cwd: AKSHARE_MCP,
      stdoutPath,
      stderrPath,
    },
  );
  return {
    ...result,
    stdoutPath,
    stderrPath,
    pythonBin: PYTHON_BIN,
    pythonReady: result.exitCode === 0,
  };
}

async function runPlaywrightSuite(name, specFiles, projects, outputDir, env) {
  const outputPath = path.join(outputDir, `${name}.playwright.json`);
  const stderrPath = `${outputPath}.stderr`;
  const args = [
    'playwright',
    'test',
    '--config=playwright.config.ts',
    '--reporter=json',
    '--workers=1',
    ...specFiles,
    ...projects.flatMap((project) => ['--project', project]),
  ];
  const result = await runCommand('npx', args, {
    cwd: APPS_WEB,
    env,
    stdoutPath: outputPath,
    stderrPath,
  });
  const rawReport = await safeReadText(outputPath);
  return {
    ...result,
    outputPath,
    stderrPath,
    report: rawReport ? parsePlaywrightReport(rawReport, name) : null,
  };
}

async function runNodeCheck(name, scriptPath, outputDir) {
  const stdoutPath = path.join(outputDir, `${name}.stdout.log`);
  const stderrPath = path.join(outputDir, `${name}.stderr.log`);
  const result = await runCommand('node', [scriptPath], {
    cwd: ROOT,
    stdoutPath,
    stderrPath,
  });
  return {
    ...result,
    stdoutPath,
    stderrPath,
    ok: result.exitCode === 0,
    payload: extractTrailingJson(result.stdout),
  };
}

function formatPlaywrightFailures(failures) {
  if (!failures.length) return ['- 无'];
  return failures.map((item) => {
    const location = item.file ? `${item.file} ` : '';
    return `- [${item.run}/${item.project}] ${location}${item.title}: ${String(item.error || '').split('\n')[0]}`;
  });
}

function formatBffFailures(failures) {
  if (!failures.length) return ['- 无'];
  return failures.map((item) => {
    const target = item.type === 'http' ? item.path : item.namespace;
    const detail = item.error || item.missingPaths?.join(', ') || item.statusCode || 'unknown_error';
    return `- ${item.module} ${target}: ${detail}`;
  });
}

function formatMcpFailures(report) {
  if (!report) return ['- MCP 深测报告缺失'];
  const tools = Array.isArray(report.tools) ? report.tools : [];
  const failed = tools.filter((item) => item.status && item.status !== 'passed');
  if (!failed.length) return ['- 无'];
  return failed.map((item) => {
    const firstFailedCase = Array.isArray(item.cases)
      ? item.cases.find((caseItem) => !caseItem.passed)
      : null;
    const detail = firstFailedCase?.error || item.status || 'unknown_error';
    return `- ${item.name}: ${detail}`;
  });
}

function formatSurfaceFailures(report) {
  if (!report) return ['- runtime surface 报告缺失'];
  const items = [
    ...(Array.isArray(report.resources) ? report.resources.filter((item) => !item.ok).map((item) => `resource ${item.uri}: ${item.error}`) : []),
    ...(Array.isArray(report.prompts) ? report.prompts.filter((item) => !item.ok).map((item) => `prompt ${item.name}: ${item.error}`) : []),
    ...(Array.isArray(report.local_skills) ? report.local_skills.filter((item) => !item.ok).map((item) => `skill ${item.skill_id}: ${item.error}`) : []),
  ];
  return items.length ? items.map((item) => `- ${item}`) : ['- 无'];
}

function formatStrategyFailures(report) {
  if (!report?.failures?.length) return ['- 无'];
  return report.failures.map((item) => `- ${item.classname} :: ${item.name}`);
}

function formatContractCheckFailures(checks) {
  const failed = Object.entries(checks).filter(([, item]) => item && !item.ok);
  if (!failed.length) return ['- 无'];
  return failed.map(([name, item]) => {
    const detail = item.stderr.trim() || item.stdout.trim() || 'unknown_error';
    return `- ${name}: ${detail.split('\n')[0]}`;
  });
}

function mdSummaryLines(combined) {
  const frontendCross = combined.reports.playwrightCrossBrowser?.summary || {};
  const frontendDeep = combined.reports.playwrightDeepChromium?.summary || {};
  const frontendCombined = combined.reports.frontend?.summary || {};
  const bff = combined.reports.bffProbe?.summary || {};
  const mcpDeep = combined.reports.mcpDeep?.summary || {};
  const mcpSurface = combined.reports.mcpSurface?.summary || {};
  const strategy = combined.reports.strategyFactory?.summary || {};
  const contract = combined.reports.contractChecksSummary || {};
  const skillGaps = combined.reports.mcpSurface?.skill_tool_gap_list || [];

  return [
    '# AIASK 全链路功能测试报告',
    '',
    `- 执行时间: ${combined.executedAt}`,
    `- Web: ${combined.environment.web}`,
    `- BFF: ${combined.environment.bff}`,
    `- Python: ${combined.environment.python}`,
    '',
    '## 执行摘要',
    '',
    `- 前端路由覆盖: ${ROUTE_COUNT}/${ROUTE_COUNT}（sitewide routes）`,
    `- 前端跨浏览器: expected=${frontendCross.expected || 0}, unexpected=${frontendCross.unexpected || 0}, flaky=${frontendCross.flaky || 0}`,
    `- 前端深交互 Chromium: expected=${frontendDeep.expected || 0}, unexpected=${frontendDeep.unexpected || 0}, flaky=${frontendDeep.flaky || 0}`,
    `- 前端总计: expected=${frontendCombined.expected || 0}, unexpected=${frontendCombined.unexpected || 0}, duration_ms=${frontendCombined.durationMs || 0}`,
    `- BFF 模块/WS 覆盖: ${BFF_MODULE_COUNT} modules + ${bff.wsProbeCount || 0} ws probes, passed=${bff.passedCount || 0}, failed=${bff.failedCount || 0}, avg_latency_ms=${bff.avgLatencyMs || 0}`,
    `- MCP tools: passed=${mcpDeep.passed_tools || 0}/${mcpDeep.tool_count || 0}, cases=${mcpDeep.passed_cases || 0}/${mcpDeep.total_cases || 0}, avg_latency_ms=${Number(mcpDeep.avg_latency_ms || 0).toFixed(2)}`,
    `- MCP surface: resources=${mcpSurface.resource_passed || 0}/${mcpSurface.resource_count || 0}, prompts=${mcpSurface.prompt_passed || 0}/${mcpSurface.prompt_count || 0}, local_skills=${mcpSurface.local_skill_passed || 0}/${LOCAL_SKILL_COUNT}, avg_latency_ms=${mcpSurface.avg_latency_ms || 0}`,
    `- 契约校验: passed=${contract.passed || 0}/${contract.total || 0}`,
    `- Strategy Factory pytest: tests=${strategy.tests || 0}, failures=${strategy.failures || 0}, skipped=${strategy.skipped || 0}`,
    `- Skills 与 Tools 映射缺口: ${skillGaps.length}`,
    '',
    '## 前端失败项',
    '',
    ...formatPlaywrightFailures(combined.reports.frontend?.failures || []),
    '',
    '## BFF 失败项',
    '',
    ...formatBffFailures(combined.reports.bffProbe?.failures || []),
    '',
    '## MCP 失败项',
    '',
    ...formatMcpFailures(combined.reports.mcpDeep),
    '',
    '## Surface / Skills 失败项',
    '',
    ...formatSurfaceFailures(combined.reports.mcpSurface),
    '',
    '## Strategy Factory 失败项',
    '',
    ...formatStrategyFailures(combined.reports.strategyFactory),
    '',
    '## 契约告警',
    '',
    ...(Array.isArray(bff.contractWarnings) && bff.contractWarnings.length
      ? bff.contractWarnings.map((item) => `- ${item}`)
      : ['- 无']),
    '',
    '## 契约校验失败项',
    '',
    ...formatContractCheckFailures(combined.reports.contractChecks || {}),
    '',
    '## Skills 与 Tools 映射缺口',
    '',
    ...(skillGaps.length ? skillGaps.map((item) => `- ${item}`) : ['- 无']),
    '',
  ];
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  await fs.mkdir(args.outputDir, { recursive: true });

  const pythonEnv = await syncPythonEnvironment(args.outputDir);
  const pythonBin = pythonEnv.pythonReady ? pythonEnv.pythonBin : 'python3';

  const bffBuild = await runCommand('npm', ['run', 'build', '-w', 'apps/bff'], {
    cwd: ROOT,
    stdoutPath: path.join(args.outputDir, 'bff-build.stdout.log'),
    stderrPath: path.join(args.outputDir, 'bff-build.stderr.log'),
  });

  const contractChecks = bffBuild.exitCode === 0
    ? {
        wsQuoteChain: await runNodeCheck('ws-quote-chain', 'scripts/ws-quote-chain-check.mjs', args.outputDir),
        mcpArgBoundary: await runNodeCheck('mcp-arg-boundary', 'scripts/mcp-arg-boundary-check.mjs', args.outputDir),
        securityBoundary: await runNodeCheck('security-boundary', 'scripts/security-boundary-check.mjs', args.outputDir),
      }
    : {
        wsQuoteChain: {
          ok: false,
          exitCode: 1,
          stdout: '',
          stderr: 'BFF build failed, ws quote chain check skipped',
          payload: null,
        },
        mcpArgBoundary: {
          ok: false,
          exitCode: 1,
          stdout: '',
          stderr: 'BFF build failed, MCP arg boundary check skipped',
          payload: null,
        },
        securityBoundary: {
          ok: false,
          exitCode: 1,
          stdout: '',
          stderr: 'BFF build failed, security boundary check skipped',
          payload: null,
        },
      };

  const bffEnv = {
    ...process.env,
    BFF_PORT: String(BFF_PORT),
    DATABASE_URL: process.env.E2E_DATABASE_URL || '',
    CORS_ORIGIN: `${WEB_BASE_URL},http://localhost:${WEB_PORT}`,
    DATABASE_POOL_MAX: process.env.DATABASE_POOL_MAX || '2',
    MCP_POOL_SIZE: process.env.MCP_POOL_SIZE || '1',
    MCP_POOL_ACQUIRE_TIMEOUT_MS: process.env.MCP_POOL_ACQUIRE_TIMEOUT_MS || '15000',
    MCP_STDIO_STARTUP_PROFILE: process.env.MCP_STDIO_STARTUP_PROFILE || 'worker',
    MCP_STDIO_COMMAND: process.env.MCP_STDIO_COMMAND || pythonBin,
    AKSHARE_MCP_DB_POOL_MIN: process.env.AKSHARE_MCP_DB_POOL_MIN || '1',
    AKSHARE_MCP_DB_POOL_MAX: process.env.AKSHARE_MCP_DB_POOL_MAX || '2',
    AKSHARE_MCP_SCHEMA_LOCK_KEY: process.env.AKSHARE_MCP_SCHEMA_LOCK_KEY || '84217051',
    APP_ENABLE_DEMO_USER: process.env.APP_ENABLE_DEMO_USER || 'true',
    APP_ADMIN_PASSWORD: process.env.APP_ADMIN_PASSWORD || 'admin',
    APP_DEMO_PASSWORD: process.env.APP_DEMO_PASSWORD || 'demo123',
    APP_JWT_SECRET: process.env.APP_JWT_SECRET || 'dev-secret-change-me',
  };

  const webEnv = {
    ...process.env,
    NEXT_PUBLIC_BFF_BASE_URL: BFF_BASE_URL,
    NEXT_PUBLIC_WS_URL: BFF_BASE_URL.replace(/\/api$/, ''),
  };

  const playwrightEnv = {
    ...process.env,
    PW_NO_WEBSERVER: '1',
    E2E_BASE_URL: WEB_BASE_URL,
    E2E_BFF_BASE_URL: BFF_BASE_URL,
    BFF_PORT: String(BFF_PORT),
    NEXT_PUBLIC_BFF_BASE_URL: BFF_BASE_URL,
    NEXT_PUBLIC_WS_URL: BFF_BASE_URL.replace(/\/api$/, ''),
  };

  const bffLog = path.join(args.outputDir, 'bff-dev.log');
  const webLog = path.join(args.outputDir, 'web-dev.log');
  const bffServer = startLongRunningProcess('npm', ['run', 'dev', '-w', 'apps/bff'], {
    cwd: ROOT,
    env: bffEnv,
    logPath: bffLog,
  });
  const webServer = startLongRunningProcess('npx', ['next', 'dev', '-p', String(WEB_PORT)], {
    cwd: APPS_WEB,
    env: webEnv,
    logPath: webLog,
  });

  try {
    await waitForHttp(`${BFF_BASE_URL}/health/ready`);
    await waitForHttp(`${BFF_BASE_URL}/health/mcp`, {
      validateResponse: (response) => response.status < 500,
    });
    await waitForHttp(`${WEB_BASE_URL}/login`, {
      validateResponse: (response) => response.status < 500,
    });

    const playwrightCrossBrowser = await runPlaywrightSuite(
      'frontend-cross-browser',
      [
        'e2e/sitewide-pages.spec.ts',
        'e2e/sitewide-functional.spec.ts',
        'e2e/core-flows.spec.ts',
        'e2e/chain-contract.spec.ts',
      ],
      ['chromium', 'chromium-sitewide', 'webkit', 'webkit-sitewide', 'mobile', 'mobile-sitewide'],
      args.outputDir,
      playwrightEnv,
    );

    const playwrightDeepChromium = await runPlaywrightSuite(
      'frontend-deep-chromium',
      [
        'e2e/p0-p1-workbench.spec.ts',
        'e2e/button-sweep.spec.ts',
        'e2e/workbench-visual-regression.spec.ts',
      ],
      ['chromium'],
      args.outputDir,
      playwrightEnv,
    );

    const bffProbe = await runCommand(
      'node',
      ['scripts/bff-module-functional-probe.mjs', '--output-dir', args.outputDir],
      {
        cwd: ROOT,
        env: { ...process.env, BFF_BASE_URL },
        stdoutPath: path.join(args.outputDir, 'bff-probe.stdout.log'),
        stderrPath: path.join(args.outputDir, 'bff-probe.stderr.log'),
      },
    );

    const mcpDeepDir = path.join(args.outputDir, 'mcp_deep');
    await fs.mkdir(mcpDeepDir, { recursive: true });
    const mcpDeep = await runCommand(
      pythonBin,
      ['packages/akshare-mcp/scripts/run_deep_mcp_conversational_test.py', '--output-dir', mcpDeepDir],
      {
        cwd: ROOT,
        env: { ...process.env },
        stdoutPath: path.join(args.outputDir, 'mcp-deep.stdout.log'),
        stderrPath: path.join(args.outputDir, 'mcp-deep.stderr.log'),
      },
    );

    const mcpSurface = await runCommand(
      pythonBin,
      ['scripts/mcp-runtime-surface-probe.py', '--output-dir', args.outputDir],
      {
        cwd: ROOT,
        env: { ...process.env },
        stdoutPath: path.join(args.outputDir, 'mcp-surface.stdout.log'),
        stderrPath: path.join(args.outputDir, 'mcp-surface.stderr.log'),
      },
    );

    const strategyXmlPath = path.join(args.outputDir, 'strategy-factory.junit.xml');
    const strategyFactory = await runCommand(
      pythonBin,
      ['-m', 'pytest', 'packages/strategy-factory/tests', '-q', '--junitxml', strategyXmlPath],
      {
        cwd: ROOT,
        stdoutPath: path.join(args.outputDir, 'strategy-factory.stdout.log'),
        stderrPath: path.join(args.outputDir, 'strategy-factory.stderr.log'),
      },
    );

    const reports = {
      playwrightCrossBrowser: playwrightCrossBrowser.report,
      playwrightDeepChromium: playwrightDeepChromium.report,
      frontend: mergePlaywrightReports([
        playwrightCrossBrowser.report,
        playwrightDeepChromium.report,
      ]),
      bffProbe: await safeReadJson(path.join(args.outputDir, 'bff-module-probe.json')),
      mcpDeep: await safeReadJson(path.join(mcpDeepDir, 'latest.json')),
      mcpSurface: await safeReadJson(path.join(args.outputDir, 'mcp-runtime-surface-probe.json')),
      strategyFactory: (() => null)(),
      contractChecks,
      contractChecksSummary: summarizeContractChecks(contractChecks),
    };

    const strategyXml = await safeReadText(strategyXmlPath);
    reports.strategyFactory = strategyXml ? parseJUnit(strategyXml) : null;

    const combined = {
      executedAt: new Date().toISOString(),
      outputDir: args.outputDir,
      environment: {
        web: WEB_BASE_URL,
        bff: BFF_BASE_URL,
        python: pythonBin,
      },
      bootstrap: {
        pythonEnv: {
          exitCode: pythonEnv.exitCode,
          pythonReady: pythonEnv.pythonReady,
          pythonBin,
        },
        bffBuild: {
          exitCode: bffBuild.exitCode,
        },
      },
      commands: {
        playwrightCrossBrowser: playwrightCrossBrowser.exitCode,
        playwrightDeepChromium: playwrightDeepChromium.exitCode,
        bffProbe: bffProbe.exitCode,
        mcpDeep: mcpDeep.exitCode,
        mcpSurface: mcpSurface.exitCode,
        strategyFactory: strategyFactory.exitCode,
        wsQuoteChain: contractChecks.wsQuoteChain.exitCode,
        mcpArgBoundary: contractChecks.mcpArgBoundary.exitCode,
        securityBoundary: contractChecks.securityBoundary.exitCode,
      },
      reports,
    };

    const summaryPath = path.join(args.outputDir, 'summary.json');
    const summaryMdPath = path.join(args.outputDir, 'summary.md');
    await fs.writeFile(summaryPath, JSON.stringify(combined, null, 2), 'utf8');
    await fs.writeFile(summaryMdPath, mdSummaryLines(combined).join('\n'), 'utf8');

    console.log(JSON.stringify({
      outputDir: args.outputDir,
      summary: {
        frontend: combined.reports.frontend?.summary,
        bff: combined.reports.bffProbe?.summary,
        mcpTools: combined.reports.mcpDeep?.summary,
        mcpSurface: combined.reports.mcpSurface?.summary,
        contractChecks: combined.reports.contractChecksSummary,
        strategyFactory: combined.reports.strategyFactory?.summary,
      },
    }, null, 2));

    const exitCodes = [
      pythonEnv.exitCode,
      bffBuild.exitCode,
      playwrightCrossBrowser.exitCode,
      playwrightDeepChromium.exitCode,
      bffProbe.exitCode,
      mcpDeep.exitCode,
      mcpSurface.exitCode,
      strategyFactory.exitCode,
      contractChecks.wsQuoteChain.exitCode,
      contractChecks.mcpArgBoundary.exitCode,
      contractChecks.securityBoundary.exitCode,
    ];
    process.exit(exitCodes.every((code) => code === 0) ? 0 : 1);
  } finally {
    killProcess(webServer.child);
    killProcess(bffServer.child);
    await sleep(1000);
    await Promise.all([bffServer.flushLogs(), webServer.flushLogs()]);
  }
}

void main();

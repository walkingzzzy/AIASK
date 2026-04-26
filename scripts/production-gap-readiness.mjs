import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, '..');
const PYTHON = process.env.PYTHON || 'python';
const BFF_PORT = process.env.BFF_PORT || '3001';
const args = new Set(process.argv.slice(2));
const options = {
  withTests: args.has('--with-tests') || args.has('--full'),
  live: args.has('--live') || args.has('--full'),
  json: args.has('--json'),
};

const monitoringFiles = [
  'monitoring/prometheus.yml',
  'monitoring/alertmanager.yml',
  'monitoring/otel-collector-config.yml',
  'monitoring/postgres-exporter-queries.yml',
  'monitoring/blackbox.yml',
  'monitoring/alerts/bff-readiness.rules.yml',
];

const advisoryGaps = [
  {
    area: 'execution-audit acceptance -> replay -> acceptance',
    title: 'Real replay is intentionally excluded from default smoke',
    detail: 'The replay script mutates incubation and paper-trading runtime state, so the readiness script only verifies contracts and CLI entrypoints by default.',
  },
];

const results = [];

function repoPath(relativePath) {
  return resolve(REPO_ROOT, relativePath);
}

function fileExists(relativePath) {
  return existsSync(repoPath(relativePath));
}

function addResult(result) {
  results.push(result);
}

function buildStaticResult({
  area,
  title,
  paths,
  blocking = true,
  note = '',
  runtimeHint = '',
}) {
  const missing = paths.filter((path) => !fileExists(path));
  addResult({
    area,
    title,
    blocking,
    code: missing.length === 0 ? 'present' : 'missing',
    assertion: 'n/a',
    runtime: runtimeHint || 'not_run',
    status: missing.length === 0 ? 'pass' : 'fail',
    detail: missing.length === 0
      ? note || `Present: ${paths.join(', ')}`
      : `Missing: ${missing.join(', ')}`,
  });
}

async function runCommand(command, commandArgs, { cwd = REPO_ROOT, timeoutMs = 120_000 } = {}) {
  return await new Promise((resolveResult) => {
    const child = spawn(command, commandArgs, {
      cwd,
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '';
    let stderr = '';
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
    }, timeoutMs);

    child.stdout.on('data', (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on('data', (chunk) => {
      stderr += String(chunk);
    });
    child.on('error', (error) => {
      clearTimeout(timer);
      resolveResult({
        ok: false,
        code: null,
        stdout,
        stderr: `${stderr}${stderr ? '\n' : ''}${String(error.message || error)}`,
        timedOut,
      });
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolveResult({
        ok: code === 0 && !timedOut,
        code,
        stdout,
        stderr,
        timedOut,
      });
    });
  });
}

async function runJsonProbe(url, { timeoutMs = 5_000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
      signal: controller.signal,
    });
    const text = await response.text();
    return {
      ok: response.ok,
      status: response.status,
      body: text,
    };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      body: String(error?.message || error),
    };
  } finally {
    clearTimeout(timer);
  }
}

function addAssertionResult({
  area,
  title,
  command,
  outcome,
  blocking = true,
  runtime = 'not_run',
}) {
  const detail = outcome.ok
    ? `Passed: ${command.join(' ')}`
    : `Failed: ${command.join(' ')}${outcome.timedOut ? ' (timed out)' : ''}\n${String(outcome.stderr || outcome.stdout || '').trim()}`;
  addResult({
    area,
    title,
    blocking,
    code: 'present',
    assertion: outcome.ok ? 'passed' : 'failed',
    runtime,
    status: outcome.ok ? 'pass' : 'fail',
    detail,
  });
}

function addRuntimeResult({
  area,
  title,
  ok,
  detail,
  blocking = true,
}) {
  addResult({
    area,
    title,
    blocking,
    code: 'present',
    assertion: 'n/a',
    runtime: ok ? 'verified' : 'failed',
    status: ok ? 'pass' : 'fail',
    detail,
  });
}

buildStaticResult({
  area: 'observability/health',
  title: 'BFF health, metrics, and frontend consumers are wired',
  paths: [
    'apps/bff/src/health/health.service.ts',
    'apps/bff/src/health/health.controller.ts',
    'apps/bff/src/observability/observability.service.ts',
    'apps/bff/src/observability/observability.interceptor.ts',
    'apps/web/lib/system-health.ts',
    'apps/web/components/home/SystemStatus.tsx',
    'apps/web/app/admin/page.tsx',
    'apps/web/app/api/bff-availability/route.ts',
  ],
  note: 'Health snapshots feed the home page, admin overview, and the lightweight BFF availability probe.',
});

buildStaticResult({
  area: 'observability/health',
  title: 'Monitoring profile files referenced by docker-compose exist',
  paths: monitoringFiles,
  note: 'monitoring:up and verify:monitoring now have checked-in config, rule, and exporter query files.',
});

buildStaticResult({
  area: 'observability/health',
  title: 'State smoke covers health, admin tools, and strategy factory operator surfaces',
  paths: [
    'scripts/playwright-mcp-audit/run-state-smoke.mjs',
    'apps/web/app/admin/tools/page.tsx',
    'apps/web/app/strategy-market/components/StrategyMarketOperatorPanel.tsx',
  ],
  note: 'verify:state-smoke now checks admin health, admin MCP jobs, and the strategy factory operator panel.',
});

buildStaticResult({
  area: 'mcp-jobs/mcp-gateway transport',
  title: 'Gateway transport, degraded error contract, operator jobs, and admin transport surfaces are wired',
  paths: [
    'apps/bff/src/mcp-gateway/mcp-gateway.service.ts',
    'apps/bff/src/mcp-gateway/mcp-transport.contract.ts',
    'apps/bff/src/mcp-jobs/mcp-jobs.service.ts',
    'apps/bff/src/mcp-jobs/mcp-jobs.controller.ts',
    'apps/bff/src/strategy/strategy-operator.controller.ts',
    'apps/bff/src/strategy/strategy-operator.service.ts',
    'apps/bff/src/strategy/strategy.operator-contract.ts',
    'apps/bff/src/common/degrade.interceptor.ts',
    'apps/bff/src/common/acceptance.ts',
    'apps/web/components/home/SystemStatus.tsx',
    'apps/web/app/admin/page.tsx',
    'apps/web/app/admin/tools/page.tsx',
    'apps/web/app/strategy-market/components/StrategyMarketOperatorPanel.tsx',
  ],
  note: 'Transport state and MCP job submission/polling are surfaced through admin tools and the strategy factory operator panel.',
});

buildStaticResult({
  area: 'execution-audit acceptance -> replay -> acceptance',
  title: 'Execution-audit scripts, BFF route, and strategy-market review UI are wired',
  paths: [
    'apps/bff/src/strategy/strategy-incubation.controller.ts',
    'apps/web/app/strategy-market/hooks/use-strategy-detail-page.ts',
    'apps/web/app/strategy-market/components/factory-review-panel/summary-section.tsx',
    'scripts/strategy-execution-audit-acceptance.py',
    'scripts/strategy-incubation-history-replay.py',
    'packages/akshare-mcp/tests/test_execution_audit_replay_contract.py',
    'packages/strategy-factory/tests/test_execution_audit_gate_taxonomy.py',
  ],
  note: 'The review panel can fetch acceptance, trigger backfill acceptance, and the scripts close the acceptance -> replay -> acceptance loop offline.',
});

if (options.withTests) {
  const sharedTypesBuild = await runCommand('npm', ['run', 'build', '-w', 'packages/shared-types']);
  addAssertionResult({
    area: 'shared contract baseline',
    title: 'Shared types build',
    command: ['npm', 'run', 'build', '-w', 'packages/shared-types'],
    outcome: sharedTypesBuild,
    blocking: true,
  });

  const bffBuild = sharedTypesBuild.ok
    ? await runCommand('npm', ['run', 'build', '-w', 'apps/bff'])
    : { ok: false, stderr: 'Skipped because packages/shared-types build failed.', stdout: '', code: null, timedOut: false };
  addAssertionResult({
    area: 'shared contract baseline',
    title: 'BFF build',
    command: ['npm', 'run', 'build', '-w', 'apps/bff'],
    outcome: bffBuild,
    blocking: true,
  });

  const nodeTestCommands = [
    {
      area: 'observability/health',
      title: 'Health service contract tests',
      command: ['node', '--test', 'apps/bff/test/health.service.test.mjs'],
    },
    {
      area: 'mcp-jobs/mcp-gateway transport',
      title: 'MCP jobs + transport contract tests',
      command: [
        'node',
        '--test',
        'apps/bff/test/mcp-jobs.service.test.mjs',
        'apps/bff/test/mcp-transport.contracts.test.mjs',
        'apps/bff/test/strategy.operator-contracts.test.mjs',
      ],
    },
    {
      area: 'cross-cutting readiness',
      title: 'Readiness fixture regression tests',
      command: ['node', '--test', 'apps/bff/test/production-gap.readiness.test.mjs'],
    },
  ];

  for (const item of nodeTestCommands) {
    const outcome = bffBuild.ok
      ? await runCommand(item.command[0], item.command.slice(1))
      : { ok: false, stderr: 'Skipped because apps/bff build failed.', stdout: '', code: null, timedOut: false };
    addAssertionResult({
      area: item.area,
      title: item.title,
      command: item.command,
      outcome,
      blocking: true,
    });
  }

  const pythonContracts = await runCommand(
    PYTHON,
    [
      '-m',
      'pytest',
      'packages/akshare-mcp/tests/test_execution_audit_replay_contract.py',
      'packages/strategy-factory/tests/test_execution_audit_gate_taxonomy.py',
      '-q',
    ],
    { timeoutMs: 180_000 },
  );
  addAssertionResult({
    area: 'execution-audit acceptance -> replay -> acceptance',
    title: 'Python execution-audit contract tests',
    command: [
      PYTHON,
      '-m',
      'pytest',
      'packages/akshare-mcp/tests/test_execution_audit_replay_contract.py',
      'packages/strategy-factory/tests/test_execution_audit_gate_taxonomy.py',
      '-q',
    ],
    outcome: pythonContracts,
    blocking: true,
  });

  const cliChecks = [
    {
      area: 'execution-audit acceptance -> replay -> acceptance',
      title: 'Acceptance CLI parses --help',
      command: [PYTHON, 'scripts/strategy-execution-audit-acceptance.py', '--help'],
    },
    {
      area: 'execution-audit acceptance -> replay -> acceptance',
      title: 'Replay CLI parses --help',
      command: [PYTHON, 'scripts/strategy-incubation-history-replay.py', '--help'],
    },
  ];

  for (const item of cliChecks) {
    const outcome = await runCommand(item.command[0], item.command.slice(1), { timeoutMs: 60_000 });
    addAssertionResult({
      area: item.area,
      title: item.title,
      command: item.command,
      outcome,
      blocking: true,
    });
  }
}

if (options.live) {
  const monitoringSmoke = await runCommand('node', ['scripts/monitoring-smoke.mjs'], { timeoutMs: 60_000 });
  addRuntimeResult({
    area: 'observability/health',
    title: 'Monitoring smoke probes',
    ok: monitoringSmoke.ok,
    detail: monitoringSmoke.ok
      ? 'verify:monitoring passed against the live BFF/monitoring stack.'
      : `verify:monitoring failed.\n${String(monitoringSmoke.stderr || monitoringSmoke.stdout || '').trim()}`,
  });

  const mcpProbe = await runJsonProbe(`http://127.0.0.1:${BFF_PORT}/api/health/mcp`);
  addRuntimeResult({
    area: 'mcp-jobs/mcp-gateway transport',
    title: 'Live MCP transport probe',
    ok: mcpProbe.ok,
    detail: mcpProbe.ok
      ? `GET /api/health/mcp returned ${mcpProbe.status}.`
      : `GET /api/health/mcp failed with status ${mcpProbe.status}: ${mcpProbe.body}`,
  });
}

for (const advisory of advisoryGaps) {
  addResult({
    area: advisory.area,
    title: advisory.title,
    blocking: false,
    code: 'partial',
    assertion: 'missing_or_manual',
    runtime: 'manual',
    status: 'warn',
    detail: advisory.detail,
  });
}

const blockingFailures = results.filter((result) => result.blocking && result.status === 'fail');
const warnings = results.filter((result) => result.status === 'warn');

if (options.json) {
  console.log(JSON.stringify({
    ok: blockingFailures.length === 0,
    options,
    results,
    warnings,
  }, null, 2));
} else {
  console.log('Production-Gap Readiness');
  console.log(`cwd: ${REPO_ROOT}`);
  console.log(`mode: ${options.withTests ? 'static+assertions' : 'static'}${options.live ? '+live' : ''}`);
  console.log('');

  for (const result of results) {
    console.log(`[${result.status.toUpperCase()}] ${result.area} :: ${result.title}`);
    console.log(`  code=${result.code} assertion=${result.assertion} runtime=${result.runtime}${result.blocking ? ' blocking' : ' advisory'}`);
    console.log(`  ${String(result.detail).split('\n').join('\n  ')}`);
    console.log('');
  }

  console.log(`Summary: blocking_failures=${blockingFailures.length} warnings=${warnings.length}`);
}

process.exitCode = blockingFailures.length === 0 ? 0 : 1;

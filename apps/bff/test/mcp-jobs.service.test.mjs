import test from 'node:test';
import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';

const { McpJobsService } = await import('../dist/mcp-jobs/mcp-jobs.service.js');
const { McpGatewayTimeoutError } = await import('../dist/mcp-gateway/mcp-gateway.errors.js');

class FakeCacheService {
  constructor() {
    this.store = new Map();
  }

  async get(key) {
    return this.store.has(key) ? this.clone(this.store.get(key)) : null;
  }

  async set(key, value) {
    this.store.set(key, this.clone(value));
  }

  resolveTtl(_scope, fallbackSeconds) {
    return fallbackSeconds;
  }

  clone(value) {
    return value == null ? value : JSON.parse(JSON.stringify(value));
  }
}

class FakeMcpGatewayService {
  constructor({ result, error, snapshot, defaultTimeoutMs = 45000 }) {
    this.result = result;
    this.error = error;
    this.snapshot = snapshot;
    this.defaultTimeoutMs = defaultTimeoutMs;
    this.calls = [];
  }

  resolveToolTimeoutMs(timeoutMs) {
    return Math.max(1000, Number(timeoutMs ?? this.defaultTimeoutMs));
  }

  getTransportSnapshot() {
    return {
      healthyConnections: 1,
      dedicatedConnections: 0,
      ...this.snapshot,
    };
  }

  async callTool(name, args, options) {
    this.calls.push({ name, args, options });
    if (this.error) {
      throw this.error;
    }
    return this.result;
  }
}

async function waitForTerminalJob(service, jobId) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    const job = await service.getJob(jobId);
    if (job && (job.status === 'succeeded' || job.status === 'failed')) {
      return job;
    }
    await delay(10);
  }
  throw new Error(`Timed out waiting for job ${jobId} to become terminal`);
}

function buildSnapshot(overrides = {}) {
  return {
    requestedTransport: 'streamable-http',
    transportKind: 'stdio',
    degraded: true,
    fallbackReason: 'streamable_http_connect_failed',
    sourceChain: ['streamable-http', 'stdio'],
    endpoint: '/tmp/akshare-mcp',
    lastError: 'connect ECONNREFUSED',
    ...overrides,
  };
}

test('McpJobsService stores resolved timeout, trace id, transport snapshot, and replays idempotent jobs', async () => {
  const gateway = new FakeMcpGatewayService({
    result: { ok: true },
    snapshot: buildSnapshot(),
  });
  const cache = new FakeCacheService();
  const service = new McpJobsService(gateway, cache);

  const created = await service.createToolJob(
    {
      tool_name: 'demo_tool',
      arguments: { code: '000001' },
      idempotency_key: ' idem-1 ',
    },
    { traceId: 'trace-123' },
  );

  assert.equal(created.accepted, true);
  assert.equal(created.deduplicated, false);
  assert.equal(created.job.idempotency_key, 'idem-1');
  assert.equal(created.job.trace_id, 'trace-123');
  assert.equal(created.job.target.timeout_ms, 45000);
  assert.equal(created.job.meta.transport.active_transport, 'stdio');

  const settled = await waitForTerminalJob(service, created.job.job_id);
  assert.equal(settled.status, 'succeeded');
  assert.deepEqual(settled.result, { ok: true });
  assert.equal(gateway.calls[0].options.timeoutMs, 45000);

  const deduplicated = await service.createToolJob(
    {
      tool_name: 'ignored_when_replayed',
      idempotency_key: 'idem-1',
    },
    { traceId: 'trace-456' },
  );

  assert.equal(deduplicated.deduplicated, true);
  assert.equal(deduplicated.job.job_id, created.job.job_id);
  assert.equal(deduplicated.job.trace_id, 'trace-123');
});

test('McpJobsService classifies tool call timeouts without treating them as transport-unavailable', async () => {
  const gateway = new FakeMcpGatewayService({
    error: new McpGatewayTimeoutError(
      'MCP tool slow_tool timed out after 1200ms',
      'tool_call',
    ),
    snapshot: buildSnapshot(),
  });
  const service = new McpJobsService(gateway, new FakeCacheService());

  const created = await service.createToolJob({
    tool_name: 'slow_tool',
    timeout_ms: 1200,
  });

  const settled = await waitForTerminalJob(service, created.job.job_id);
  assert.equal(settled.status, 'failed');
  assert.equal(settled.error_code, 'MCP_JOB_TIMEOUT');
  assert.equal(settled.target.timeout_ms, 1200);
  assert.equal(settled.meta.transport.active_transport, 'stdio');
  assert.equal(gateway.calls[0].options.timeoutMs, 1200);
});

test('McpJobsService marks transport bootstrap failures separately from tool execution failures', async () => {
  const gateway = new FakeMcpGatewayService({
    error: new Error(
      'Unable to establish MCP connection via streamable-http; last error: connect ECONNREFUSED',
    ),
    snapshot: buildSnapshot({ transportKind: 'none', sourceChain: ['none'] }),
  });
  const service = new McpJobsService(gateway, new FakeCacheService());

  const created = await service.createToolJob({
    tool_name: 'broken_tool',
  });

  const settled = await waitForTerminalJob(service, created.job.job_id);
  assert.equal(settled.status, 'failed');
  assert.equal(settled.error_code, 'MCP_JOB_TRANSPORT_UNAVAILABLE');
  assert.equal(settled.meta.transport.active_transport, 'none');
});

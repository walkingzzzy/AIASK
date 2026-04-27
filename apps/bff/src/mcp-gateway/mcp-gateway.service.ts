import { Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { existsSync } from 'node:fs';
import { delimiter, isAbsolute, resolve } from 'node:path';
import { performance } from 'node:perf_hooks';
import { ObservabilityService } from '../observability/observability.service';
import { McpGatewayTimeoutError } from './mcp-gateway.errors';
import { withToolTransportMeta } from './mcp-transport.contract';

type McpTransportMode = 'stdio' | 'streamable-http' | 'sse' | 'auto';
type McpTransportKind = 'stdio' | 'streamable-http' | 'sse';
type McpTransport = StdioClientTransport | StreamableHTTPClientTransport | SSEClientTransport;

type McpHealth = {
  reachable: boolean;
  toolCount: number | null;
  expectedTools: number | null;
  matched: boolean;
  source: string;
  message: string;
  poolSize?: number;
  activeConnections?: number;
  transportMode?: McpTransportMode;
  transportKind?: McpTransportKind | 'none';
  degraded?: boolean;
  fallbackReason?: string | null;
  sourceChain?: string[];
  endpoint?: string | null;
  lastError?: string | null;
  stale?: boolean;
  staleReason?: string | null;
};

type McpStartupProfile = 'full' | 'worker' | 'tool-only';

type McpConnectionMeta = {
  requestedTransport: McpTransportMode;
  transportKind: McpTransportKind;
  degraded: boolean;
  fallbackReason: string | null;
  sourceChain: string[];
  endpoint: string | null;
  lastError: string | null;
};

interface PooledConnection {
  id: number;
  client: Client;
  transport: McpTransport;
  busy: boolean;
  connectPromise: Promise<void> | null;
  meta: McpConnectionMeta;
}

type HealthCacheEntry = {
  value: McpHealth;
  expiresAt: number;
  staleUntil: number;
};

type Waiter = {
  resolve: (conn: PooledConnection) => void;
  reject: (error: Error) => void;
  timeout: ReturnType<typeof setTimeout>;
};

type BuildIsolatedPythonPathOptions = {
  cwd: string;
  configured?: string | null;
  exists?: (path: string) => boolean;
};

type McpFailureMode = 'timeout' | 'transport' | 'validation' | 'tool_error' | 'unknown';

type ToolMetricBucket = {
  calls: number;
  errors: number;
  totalLatencyMs: number;
  samples: number[];
  failureModes: Partial<Record<McpFailureMode, number>>;
};

export function buildIsolatedPythonPath({
  cwd,
  configured,
  exists = existsSync,
}: BuildIsolatedPythonPathOptions): string {
  const sources = [
    configured,
    resolve(cwd, 'src'),
    resolve(cwd, '..', 'strategy-factory', 'src'),
  ];

  const parts = sources
    .flatMap((value) => (value ? value.split(delimiter) : []))
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .map((part) => (isAbsolute(part) ? part : resolve(cwd, part)))
    .filter((part, index, list) => list.indexOf(part) === index)
    .filter((part) => exists(part));

  return parts.join(delimiter);
}

@Injectable()
export class McpGatewayService implements OnModuleDestroy {
  private readonly logger = new Logger(McpGatewayService.name);
  private static readonly DEDICATED_TOOL_CONNECTIONS = new Set<string>();

  private pool: PooledConnection[] = [];
  private readonly poolSize: number;
  private readonly fullProfilePoolSlots: number;
  private readonly poolAcquireTimeoutMs: number;
  private readonly toolCallTimeoutMs: number;
  private readonly healthCacheTtlMs: number;
  private readonly healthStaleIfErrorMs: number;
  private readonly transportMode: McpTransportMode;
  private readonly streamableHttpUrl: string;
  private readonly allowSseFallback: boolean;
  private readonly allowStdioFallback: boolean;
  private readonly streamableHttpTimeoutMs: number;
  private readonly streamableHttpHeaders: Record<string, string>;
  private waitQueue: Waiter[] = [];
  private dedicatedConnections = new Map<string, PooledConnection>();
  private dedicatedWaitQueues = new Map<string, Waiter[]>();
  private initPromise: Promise<void> | null = null;
  private poolCreationInFlight: Promise<PooledConnection> | null = null;
  private healthCache: HealthCacheEntry | null = null;
  private healthInFlight: Promise<McpHealth> | null = null;
  private initialized = false;
  private totalToolCalls = 0;
  private totalToolErrors = 0;
  private readonly latencyHistoryMs: number[] = [];
  private readonly toolUsage = new Map<string, number>();
  private readonly toolMetrics = new Map<string, ToolMetricBucket>();
  private readonly failureModeTotals = new Map<McpFailureMode, number>();
  private lastTransportError: string | null = null;
  private lastConnectionMeta: McpConnectionMeta | null = null;

  constructor(
    private readonly configService: ConfigService,
    private readonly observability: ObservabilityService,
  ) {
    this.poolSize = Math.max(
      1,
      Number(this.configService.get<string>('MCP_POOL_SIZE', '4')),
    );
    this.fullProfilePoolSlots = this.resolveConfiguredFullProfilePoolSlots();
    this.poolAcquireTimeoutMs = Math.max(
      1000,
      Number(this.configService.get<string>('MCP_POOL_ACQUIRE_TIMEOUT_MS', '5000')),
    );
    this.toolCallTimeoutMs = Math.max(
      1000,
      Number(this.configService.get<string>('MCP_TOOL_TIMEOUT_MS', '30000')),
    );
    this.healthCacheTtlMs = Math.max(
      1000,
      Number(this.configService.get<string>('MCP_HEALTH_CACHE_TTL_MS', '10000')),
    );
    this.healthStaleIfErrorMs = Math.max(
      this.healthCacheTtlMs,
      Number(this.configService.get<string>('MCP_HEALTH_STALE_IF_ERROR_MS', '120000')),
    );
    this.transportMode = this.resolveTransportMode();
    this.streamableHttpUrl = this.configService.get<string>('MCP_STREAMABLE_HTTP_URL', '').trim();
    this.allowSseFallback = this.readBooleanConfig('MCP_STREAMABLE_HTTP_ALLOW_SSE_FALLBACK', true);
    this.allowStdioFallback = this.readBooleanConfig('MCP_TRANSPORT_ALLOW_STDIO_FALLBACK', true);
    this.streamableHttpTimeoutMs = Math.max(
      1000,
      Number(this.configService.get<string>('MCP_STREAMABLE_HTTP_TIMEOUT_MS', '10000')),
    );
    this.streamableHttpHeaders = this.parseHeaderConfig(
      this.configService.get<string>('MCP_STREAMABLE_HTTP_HEADERS', ''),
    );
  }

  async onModuleDestroy(): Promise<void> {
    await this.disposeAll();
  }

  async checkAvailableTools(): Promise<McpHealth> {
    const cached = this.getCachedHealth();
    if (cached) {
      return cached;
    }

    if (this.healthInFlight) {
      return this.healthInFlight;
    }

    const stale = this.getStaleHealth('pool_busy_or_waiting');
    if (this.shouldServeStaleHealth() && stale) {
      return stale;
    }

    this.healthInFlight = this.fetchAvailableTools().finally(() => {
      this.healthInFlight = null;
    });
    return this.healthInFlight;
  }

  private async fetchAvailableTools(): Promise<McpHealth> {
    const configuredExpected = this.configService.get<string>('MCP_EXPECTED_TOOLS');
    const expectedTools = configuredExpected != null && configuredExpected !== ''
      ? Number(configuredExpected)
      : null;

    try {
      const conn = await this.acquire();
      try {
        let tools: Awaited<ReturnType<Client['listTools']>>;
        try {
          tools = await conn.client.listTools(undefined, {
            timeout: Math.min(this.toolCallTimeoutMs, 30_000),
          });
        } catch (error) {
          this.recordTransportError(error);
          if (this.isTransportError(error)) {
            this.logger.warn(`Transport error on pool[${conn.id}] while listing tools, recycling connection`);
            await this.recycleConnection(conn);
          }
          throw error;
        }
        const count = Array.isArray(tools?.tools) ? tools.tools.length : null;
        if (count !== null) {
          const resolvedExpectedTools = expectedTools ?? count;
          return this.cacheHealth({
            reachable: true,
            toolCount: count,
            expectedTools: resolvedExpectedTools,
            matched: count === resolvedExpectedTools,
            source: conn.meta.transportKind,
            message: expectedTools == null ? 'ok(dynamic-runtime-baseline)' : 'ok',
            poolSize: this.poolSize,
            activeConnections: this.pool.length,
            transportMode: this.transportMode,
            transportKind: conn.meta.transportKind,
            degraded: conn.meta.degraded,
            fallbackReason: conn.meta.fallbackReason,
            sourceChain: conn.meta.sourceChain,
            endpoint: conn.meta.endpoint,
            lastError: conn.meta.lastError ?? this.lastTransportError,
          });
        }
      } finally {
        this.release(conn);
      }
    } catch (error) {
      const stale = this.getStaleHealth(this.formatError(error));
      if (stale) {
        return stale;
      }
    }

    const transport = this.getTransportSnapshot();
    return this.cacheHealth({
      reachable: false,
      toolCount: null,
      expectedTools,
      matched: false,
      source: transport.transportKind,
      message: 'MCP not reachable or available_tools response format unknown',
      poolSize: this.poolSize,
      activeConnections: this.pool.length,
      transportMode: transport.requestedTransport,
      transportKind: transport.transportKind,
      degraded: true,
      fallbackReason: transport.fallbackReason,
      sourceChain: transport.sourceChain,
      endpoint: transport.endpoint,
      lastError: transport.lastError,
    });
  }

  async callTool(
    name: string,
    args: Record<string, unknown> = {},
    options?: { timeoutMs?: number; retryOnTransportError?: boolean },
  ): Promise<unknown> {
    const dedicated = McpGatewayService.DEDICATED_TOOL_CONNECTIONS.has(name);
    const timeoutMs = this.resolveToolTimeoutMs(options?.timeoutMs);
    const maxAttempts = options?.retryOnTransportError ? 2 : 1;
    let lastError: unknown = null;

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      let conn: PooledConnection | null = null;
      const startedAt = performance.now();
      try {
        conn = dedicated ? await this.acquireDedicated(name) : await this.acquire();
        const result = await this.withTimeout(
          conn.client.callTool(
            { name, arguments: args },
            undefined,
            {
              timeout: timeoutMs,
              resetTimeoutOnProgress: true,
              maxTotalTimeout: timeoutMs,
            },
          ),
          timeoutMs,
          `MCP tool ${name} timed out after ${timeoutMs}ms`,
          'tool_call',
        );
        this.recordToolMetric(name, performance.now() - startedAt, false, conn.meta);
        return this.normalizeToolResult(result, conn.meta);
      } catch (error) {
        lastError = error;
        this.recordToolMetric(name, performance.now() - startedAt, true, conn?.meta, error);
        const transportError = this.isTransportError(error);
        const canRetry = transportError && attempt < maxAttempts;
        if (transportError && conn) {
          this.logger.warn(
            `Transport error on pool[${conn.id}], recycling connection${canRetry ? ' before retry' : ''}`,
          );
          await this.recycleConnection(conn, dedicated ? name : undefined);
        }
        if (!canRetry) {
          throw error;
        }
      } finally {
        if (conn) {
          if (dedicated) this.releaseDedicated(name, conn);
          else this.release(conn);
        }
      }
    }

    throw lastError instanceof Error ? lastError : new Error(String(lastError ?? `MCP tool ${name} failed`));
  }

  async readResource(uri: string): Promise<unknown> {
    const conn = await this.acquire();
    const startedAt = performance.now();
    try {
      const result = await this.withTimeout(
        conn.client.readResource(
          { uri },
          {
            timeout: this.toolCallTimeoutMs,
            resetTimeoutOnProgress: true,
            maxTotalTimeout: this.toolCallTimeoutMs,
          },
        ),
        this.toolCallTimeoutMs,
        `MCP resource ${uri} timed out after ${this.toolCallTimeoutMs}ms`,
        'resource_read',
      );
      this.recordToolMetric(`resource:${uri}`, performance.now() - startedAt, false, conn.meta);
      return this.normalizeResourceResult(result);
    } catch (error) {
      this.recordToolMetric(`resource:${uri}`, performance.now() - startedAt, true, conn.meta, error);
      if (this.isTransportError(error)) {
        this.logger.warn(`Transport error on pool[${conn.id}] while reading resource, recycling connection`);
        await this.recycleConnection(conn);
      }
      throw error;
    } finally {
      this.release(conn);
    }
  }

  getMetricsSnapshot(): {
    totalCalls: number;
    avgLatency: number;
    p99Latency: number;
    errorRate: number;
    failureModes: Array<{ mode: McpFailureMode; count: number }>;
    queue: { shared: number; dedicated: number; poolSize: number; acquireTimeoutMs: number; toolTimeoutMs: number };
    tools: Array<{
      name: string;
      calls: number;
      avgMs: number;
      p99Ms: number;
      errors: number;
      errorRate: number;
      status: 'healthy' | 'degraded' | 'down';
      failureModes: Array<{ mode: McpFailureMode; count: number }>;
    }>;
    transport: ReturnType<McpGatewayService['getTransportSnapshot']>;
  } {
    const samples = [...this.latencyHistoryMs].sort((a, b) => a - b);
    const avgLatency = samples.length > 0
      ? samples.reduce((sum, value) => sum + value, 0) / samples.length
      : 0;
    const p99Index = samples.length > 0
      ? Math.min(samples.length - 1, Math.max(0, Math.ceil(samples.length * 0.99) - 1))
      : 0;
    const topTools = [...this.toolMetrics.entries()]
      .sort((left, right) => right[1].calls - left[1].calls || left[0].localeCompare(right[0]))
      .slice(0, 12)
      .map(([name, bucket]) => {
        const toolSamples = [...bucket.samples].sort((a, b) => a - b);
        const toolP99Index = toolSamples.length > 0
          ? Math.min(toolSamples.length - 1, Math.max(0, Math.ceil(toolSamples.length * 0.99) - 1))
          : 0;
        const errorRate = bucket.calls > 0 ? (bucket.errors / bucket.calls) * 100 : 0;
        const p99Ms = Number((toolSamples[toolP99Index] ?? 0).toFixed(2));
        const status: 'healthy' | 'degraded' | 'down' = bucket.errors === 0
          ? 'healthy'
          : errorRate >= 50
            ? 'down'
            : 'degraded';
        return {
          name,
          calls: bucket.calls,
          avgMs: Number((bucket.calls > 0 ? bucket.totalLatencyMs / bucket.calls : 0).toFixed(2)),
          p99Ms,
          errors: bucket.errors,
          errorRate: Number(errorRate.toFixed(2)),
          status,
          failureModes: Object.entries(bucket.failureModes)
            .map(([mode, count]) => ({ mode: mode as McpFailureMode, count: Number(count ?? 0) }))
            .filter((item) => item.count > 0)
            .sort((left, right) => right.count - left.count || left.mode.localeCompare(right.mode)),
        };
      });

    return {
      totalCalls: this.totalToolCalls,
      avgLatency: Number(avgLatency.toFixed(2)),
      p99Latency: Number((samples[p99Index] ?? 0).toFixed(2)),
      errorRate: this.totalToolCalls > 0
        ? Number(((this.totalToolErrors / this.totalToolCalls) * 100).toFixed(2))
        : 0,
      failureModes: [...this.failureModeTotals.entries()]
        .map(([mode, count]) => ({ mode, count }))
        .sort((left, right) => right.count - left.count || left.mode.localeCompare(right.mode)),
      queue: {
        shared: this.waitQueue.length,
        dedicated: [...this.dedicatedWaitQueues.values()].reduce((sum, queue) => sum + queue.length, 0),
        poolSize: this.poolSize,
        acquireTimeoutMs: this.poolAcquireTimeoutMs,
        toolTimeoutMs: this.toolCallTimeoutMs,
      },
      tools: topTools,
      transport: this.getTransportSnapshot(),
    };
  }

  getTransportSnapshot(): {
    requestedTransport: McpTransportMode;
    transportKind: McpTransportKind | 'none';
    degraded: boolean;
    fallbackReason: string | null;
    sourceChain: string[];
    endpoint: string | null;
    lastError: string | null;
    healthyConnections: number;
    dedicatedConnections: number;
  } {
    const liveConnections = [...this.pool, ...this.dedicatedConnections.values()];
    const liveMeta = liveConnections[0]?.meta ?? this.lastConnectionMeta;
    return {
      requestedTransport: this.transportMode,
      transportKind: liveMeta?.transportKind ?? 'none',
      degraded: Boolean(liveMeta?.degraded || this.lastTransportError),
      fallbackReason: liveMeta?.fallbackReason ?? null,
      sourceChain: liveMeta?.sourceChain ?? [],
      endpoint: liveMeta?.endpoint ?? (this.streamableHttpUrl || null),
      lastError: liveMeta?.lastError ?? this.lastTransportError,
      healthyConnections: liveConnections.length,
      dedicatedConnections: this.dedicatedConnections.size,
    };
  }

  resolveToolTimeoutMs(timeoutMs?: number | null): number {
    return Math.max(1000, Number(timeoutMs ?? this.toolCallTimeoutMs));
  }

  /* ── Pool Management ── */

  private async acquire(): Promise<PooledConnection> {
    if (!this.initialized) {
      await this.initPool();
    }

    while (true) {
      const idle = this.pool.find((c) => !c.busy);
      if (idle) {
        idle.busy = true;
        return idle;
      }

      if (this.pool.length < this.poolSize) {
        const conn = await this.createPoolConnection();
        if (!conn) continue;
        conn.busy = true;
        return conn;
      }

      return this.waitForConnection(
        this.waitQueue,
        `Timed out waiting ${this.poolAcquireTimeoutMs}ms for an available MCP pool connection`,
      );
    }
  }

  private release(conn: PooledConnection): void {
    if (!this.pool.includes(conn)) {
      const waiter = this.waitQueue.shift();
      if (waiter) {
        void this.acquire()
          .then((nextConn) => waiter.resolve(nextConn))
          .catch((error) => {
            this.logger.error(`Failed to reacquire MCP connection for waiter: ${String(error)}`);
            this.waitQueue.unshift(waiter);
          });
      }
      return;
    }

    conn.busy = false;
    const waiter = this.waitQueue.shift();
    if (waiter) {
      conn.busy = true;
      waiter.resolve(conn);
    }
  }

  private async acquireDedicated(toolName: string): Promise<PooledConnection> {
    const existing = this.dedicatedConnections.get(toolName);
    if (existing) {
      if (!existing.busy) {
        existing.busy = true;
        return existing;
      }
      const queue = this.dedicatedWaitQueues.get(toolName) ?? [];
      this.dedicatedWaitQueues.set(toolName, queue);
      return this.waitForConnection(
        queue,
        `Timed out waiting ${this.poolAcquireTimeoutMs}ms for dedicated MCP connection ${toolName}`,
      );
    }

    const conn = await this.createConnection(this.poolSize + this.dedicatedConnections.size);
    conn.busy = true;
    this.dedicatedConnections.set(toolName, conn);
    this.logger.log(`MCP dedicated connection[${conn.id}] assigned to ${toolName}`);
    return conn;
  }

  private releaseDedicated(toolName: string, conn: PooledConnection): void {
    const current = this.dedicatedConnections.get(toolName);
    if (current !== conn) return;

    conn.busy = false;
    const queue = this.dedicatedWaitQueues.get(toolName);
    const waiter = queue?.shift();
    if (waiter) {
      conn.busy = true;
      waiter.resolve(conn);
    }
    if (queue && queue.length === 0) {
      this.dedicatedWaitQueues.delete(toolName);
    }
  }

  private async initPool(): Promise<void> {
    if (this.initialized) return;
    if (this.initPromise) {
      await this.initPromise;
      return;
    }

    this.initPromise = (async () => {
      const first = await this.createConnection(0);
      this.pool.push(first);
      this.initialized = true;
      this.logger.log(
        `MCP pool initialized (1/${this.poolSize} connections, heavy-worker slots=${this.fullProfilePoolSlots})`,
      );
      void this.warmPool().catch((error) => {
        this.logger.warn(`MCP pool warmup stopped: ${this.formatError(error)}`);
      });
    })();

    try {
      await this.initPromise;
    } finally {
      this.initPromise = null;
    }
  }

  private async createPoolConnection(): Promise<PooledConnection | null> {
    if (this.poolCreationInFlight) {
      await this.poolCreationInFlight.catch(() => null);
      return null;
    }

    const connectionId = this.pool.length;
    const creation = this.createConnection(connectionId);
    this.poolCreationInFlight = creation;
    try {
      const conn = await creation;
      this.pool.push(conn);
      return conn;
    } finally {
      if (this.poolCreationInFlight === creation) {
        this.poolCreationInFlight = null;
      }
    }
  }

  private async warmPool(): Promise<void> {
    while (this.initialized && this.pool.length < this.poolSize) {
      const conn = await this.createPoolConnection();
      if (!conn) continue;
      this.logger.log(`MCP pool warmup connected (${this.pool.length}/${this.poolSize})`);
    }
  }

  private async createConnection(id: number): Promise<PooledConnection> {
    const requestedTransport = this.transportMode;
    const attemptedKinds: McpTransportKind[] = [];
    const fallbackReasons: string[] = [];
    let lastError: unknown = null;

    for (const kind of this.resolveTransportCandidates()) {
      if ((kind === 'streamable-http' || kind === 'sse') && !this.streamableHttpUrl) {
        if (requestedTransport !== 'stdio') {
          fallbackReasons.push('streamable_http_url_missing');
        }
        continue;
      }
      attemptedKinds.push(kind);
      try {
        const resolved = await this.connectTransport(id, kind);
        const meta: McpConnectionMeta = {
          requestedTransport,
          transportKind: kind,
          degraded: fallbackReasons.length > 0 || attemptedKinds.length > 1,
          fallbackReason: fallbackReasons[0] ?? (attemptedKinds.length > 1 ? `${attemptedKinds[0]}_connect_failed` : null),
          sourceChain: [...attemptedKinds],
          endpoint: resolved.endpoint,
          lastError: lastError ? this.formatError(lastError) : null,
        };
        this.lastTransportError = meta.lastError;
        this.lastConnectionMeta = meta;
        return { id, client: resolved.client, transport: resolved.transport, busy: false, connectPromise: null, meta };
      } catch (error) {
        lastError = error;
        fallbackReasons.push(`${kind.replace(/-/g, '_')}_connect_failed`);
        this.recordTransportError(error);
      }
    }

    throw new Error(
      `Unable to establish MCP connection via ${requestedTransport}; last error: ${this.formatError(lastError)}`,
    );
  }

  private async connectTransport(
    id: number,
    kind: McpTransportKind,
  ): Promise<{ client: Client; transport: McpTransport; endpoint: string | null }> {
    if (kind === 'stdio') {
      const cwd = this.resolveMcpCwd();
      const command = this.resolveMcpCommand(cwd);
      const args = this.parseArgs(
        this.configService.get<string>('MCP_STDIO_ARGS', '["-m","akshare_mcp.server"]'),
      );
      const startupProfile = this.resolveStartupProfile(id);
      const env: Record<string, string> = {
        ...Object.entries(process.env).reduce<Record<string, string>>((acc, [k, v]) => {
          if (typeof v === 'string') acc[k] = v;
          return acc;
        }, {}),
        PYTHONPATH: this.buildPythonPath(cwd),
        PYTHONIOENCODING:
          this.configService.get<string>('MCP_STDIO_PYTHONIOENCODING', 'utf-8'),
        AKSHARE_MCP_STARTUP_PROFILE: startupProfile,
        AKSHARE_MCP_CONNECTION_SLOT: String(id),
        AKSHARE_MCP_DB_POOL_MIN: this.configService.get<string>('AKSHARE_MCP_DB_POOL_MIN', '1'),
        AKSHARE_MCP_DB_POOL_MAX: this.configService.get<string>('AKSHARE_MCP_DB_POOL_MAX', '2'),
      };
      const transport = new StdioClientTransport({
        command,
        args,
        cwd,
        env,
        stderr: 'inherit',
      });
      const client = this.createClient(id);
      try {
        await client.connect(transport);
      } catch (error) {
        try { await transport.close(); } catch { /* ignore */ }
        throw error;
      }
      this.logger.log(`MCP pool connection[${id}] established (transport=stdio, profile=${startupProfile})`);
      return { client, transport, endpoint: cwd };
    }

    const url = new URL(this.streamableHttpUrl);
    const requestInit: RequestInit = {
      headers: this.streamableHttpHeaders,
    };
    const client = this.createClient(id);

    if (kind === 'streamable-http') {
      const transport = new StreamableHTTPClientTransport(url, {
        requestInit,
        reconnectionOptions: {
          initialReconnectionDelay: 1000,
          maxReconnectionDelay: Math.max(2000, this.streamableHttpTimeoutMs * 3),
          reconnectionDelayGrowFactor: 1.5,
          maxRetries: 2,
        },
      });
      try {
        await this.withTimeout(
          client.connect(transport),
          this.streamableHttpTimeoutMs,
          `MCP Streamable HTTP connection timed out after ${this.streamableHttpTimeoutMs}ms`,
          'transport_connect',
        );
      } catch (error) {
        try { await transport.close(); } catch { /* ignore */ }
        throw error;
      }
      this.logger.log(`MCP pool connection[${id}] established (transport=streamable-http, endpoint=${url.toString()})`);
      return { client, transport, endpoint: url.toString() };
    }

    const transport = new SSEClientTransport(url, {
      requestInit,
      eventSourceInit: { fetch: globalThis.fetch as typeof globalThis.fetch },
    });
    try {
      await this.withTimeout(
        client.connect(transport),
        this.streamableHttpTimeoutMs,
        `MCP SSE connection timed out after ${this.streamableHttpTimeoutMs}ms`,
        'transport_connect',
      );
    } catch (error) {
      try { await transport.close(); } catch { /* ignore */ }
      throw error;
    }
    this.logger.log(`MCP pool connection[${id}] established (transport=sse, endpoint=${url.toString()})`);
    return { client, transport, endpoint: url.toString() };
  }

  private createClient(id: number): Client {
    return new Client(
      { name: `aiask-bff-pool-${id}`, version: '0.1.0' },
      { capabilities: {} },
    );
  }

  private resolveTransportCandidates(): McpTransportKind[] {
    switch (this.transportMode) {
      case 'stdio':
        return ['stdio'];
      case 'streamable-http':
        return [
          'streamable-http',
          ...(this.allowSseFallback ? ['sse'] as const : []),
          ...(this.allowStdioFallback ? ['stdio'] as const : []),
        ];
      case 'sse':
        return [
          'sse',
          ...(this.allowStdioFallback ? ['stdio'] as const : []),
        ];
      case 'auto':
      default:
        if (!this.streamableHttpUrl) {
          return ['stdio'];
        }
        return [
          'streamable-http',
          ...(this.allowSseFallback ? ['sse'] as const : []),
          ...(this.allowStdioFallback ? ['stdio'] as const : []),
        ];
    }
  }

  private resolveTransportMode(): McpTransportMode {
    const normalized = this.configService.get<string>('MCP_TRANSPORT', 'auto').trim().toLowerCase();
    if (normalized === 'stdio') return 'stdio';
    if (normalized === 'streamable-http' || normalized === 'streamable_http' || normalized === 'http') {
      return 'streamable-http';
    }
    if (normalized === 'sse') return 'sse';
    return 'auto';
  }

  private async recycleConnection(conn: PooledConnection, dedicatedTool?: string): Promise<void> {
    try { await conn.transport.close(); } catch { /* ignore */ }

    try {
      const fresh = await this.createConnection(conn.id);
      conn.client = fresh.client;
      conn.transport = fresh.transport;
      conn.connectPromise = fresh.connectPromise;
      conn.meta = fresh.meta;
    } catch (err) {
      if (dedicatedTool) {
        this.dedicatedConnections.delete(dedicatedTool);
      } else {
        const idx = this.pool.indexOf(conn);
        if (idx !== -1) {
          this.pool.splice(idx, 1);
        }
      }
      this.logger.error(`Failed to recycle pool[${conn.id}]: ${err}`);
    }
  }

  private async disposeAll(): Promise<void> {
    const pendingWaiters = [...this.waitQueue, ...Array.from(this.dedicatedWaitQueues.values()).flat()];
    for (const waiter of pendingWaiters) {
      clearTimeout(waiter.timeout);
      waiter.reject(new Error('MCP gateway is shutting down'));
    }
    for (const conn of this.pool) {
      try {
        await conn.transport.close();
      } catch { /* ignore */ }
    }
    for (const conn of this.dedicatedConnections.values()) {
      try {
        await conn.transport.close();
      } catch { /* ignore */ }
    }
    this.pool = [];
    this.dedicatedConnections.clear();
    this.dedicatedWaitQueues.clear();
    this.healthCache = null;
    this.healthInFlight = null;
    this.initPromise = null;
    this.poolCreationInFlight = null;
    this.initialized = false;
  }

  /* ── Utilities ── */

  private isTransportError(error: unknown): boolean {
    if (error instanceof McpGatewayTimeoutError) {
      return error.scope === 'transport_connect';
    }
    if (!error || typeof error !== 'object') return true;
    const msg = String((error as Error).message ?? '').toLowerCase();
    return (
      msg.includes('epipe') ||
      msg.includes('connection') ||
      msg.includes('closed') ||
      msg.includes('transport') ||
      msg.includes('streamable http') ||
      msg.includes('no valid session') ||
      msg.includes('session id') ||
      msg.includes('posting to endpoint') ||
      msg.includes('econnreset') ||
      msg.includes('econnrefused') ||
      msg.includes('broken pipe') ||
      msg.includes('timed out')
    );
  }

  private readBooleanConfig(key: string, fallback: boolean): boolean {
    const raw = this.configService.get<string>(key);
    if (raw == null || raw.trim().length === 0) return fallback;
    return !['0', 'false', 'off', 'no'].includes(raw.trim().toLowerCase());
  }

  private parseHeaderConfig(raw: string): Record<string, string> {
    const trimmed = raw.trim();
    if (!trimmed) return {};
    try {
      const parsed = JSON.parse(trimmed);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return {};
      }
      return Object.entries(parsed).reduce<Record<string, string>>((acc, [key, value]) => {
        if (value != null && String(value).trim()) {
          acc[key] = String(value);
        }
        return acc;
      }, {});
    } catch {
      return {};
    }
  }

  private formatError(error: unknown): string {
    if (error instanceof Error) return error.message;
    return String(error);
  }

  private recordTransportError(error: unknown): void {
    this.lastTransportError = this.formatError(error);
  }

  private waitForConnection(queue: Waiter[], timeoutMessage: string): Promise<PooledConnection> {
    return new Promise<PooledConnection>((resolve, reject) => {
      let waiter!: Waiter;
      waiter = {
        resolve: (conn) => {
          clearTimeout(waiter.timeout);
          resolve(conn);
        },
        reject: (error) => {
          clearTimeout(waiter.timeout);
          reject(error);
        },
        timeout: setTimeout(() => {
          const index = queue.indexOf(waiter);
          if (index !== -1) {
            queue.splice(index, 1);
          }
          reject(new Error(timeoutMessage));
        }, this.poolAcquireTimeoutMs),
      };
      queue.push(waiter);
    });
  }

  private async withTimeout<T>(
    promise: Promise<T>,
    timeoutMs: number,
    message: string,
    scope: 'resource_read' | 'tool_call' | 'transport_connect',
  ): Promise<T> {
    return await new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => reject(new McpGatewayTimeoutError(message, scope)), timeoutMs);
      promise.then(
        (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        (error) => {
          clearTimeout(timer);
          reject(error);
        },
      );
    });
  }

  private cacheHealth(value: McpHealth): McpHealth {
    this.observability.setDependencyState(
      'mcp',
      !value.reachable ? 'untrusted' : value.degraded || value.matched === false ? 'degraded' : 'normal',
    );
    this.healthCache = {
      value,
      expiresAt: Date.now() + this.healthCacheTtlMs,
      staleUntil: Date.now() + this.healthStaleIfErrorMs,
    };
    return value;
  }

  private getCachedHealth(): McpHealth | null {
    if (!this.healthCache) return null;
    if (Date.now() > this.healthCache.expiresAt) {
      return null;
    }
    return this.healthCache.value;
  }

  private getStaleHealth(reason: string): McpHealth | null {
    if (!this.healthCache || Date.now() > this.healthCache.staleUntil) return null;
    if (!this.healthCache.value.reachable) return null;
    return {
      ...this.healthCache.value,
      stale: true,
      staleReason: reason || 'health_probe_failed',
    };
  }

  private shouldServeStaleHealth(): boolean {
    if (!this.healthCache) return false;
    if (Date.now() > this.healthCache.staleUntil) return false;
    const poolBusy = this.pool.length >= this.poolSize && this.pool.every((conn) => conn.busy);
    return poolBusy || this.waitQueue.length > 0;
  }

  private resolveMcpCwd(): string {
    const configured = this.configService.get<string>('MCP_STDIO_CWD');
    if (configured && configured.trim().length > 0) {
      return configured.trim();
    }

    const candidates = [
      resolve(__dirname, '..', '..', '..', '..', 'packages', 'akshare-mcp'),
      resolve(__dirname, '..', '..', '..', 'packages', 'akshare-mcp'),
      resolve(process.cwd(), 'packages', 'akshare-mcp'),
      resolve(process.cwd(), '..', '..', 'packages', 'akshare-mcp'),
    ];

    const hit = candidates.find((candidate) => existsSync(candidate));
    return hit ?? candidates[0];
  }

  private resolveMcpCommand(cwd: string): string {
    const configured = this.configService.get<string>('MCP_STDIO_COMMAND');
    if (configured && configured.trim().length > 0) {
      return configured.trim();
    }

    const venvPython = process.platform === 'win32'
      ? resolve(cwd, '.venv', 'Scripts', 'python.exe')
      : resolve(cwd, '.venv', 'bin', 'python');

    if (existsSync(venvPython)) {
      return venvPython;
    }

    return 'python';
  }

  private buildPythonPath(cwd: string): string {
    const configured = this.configService.get<string>('MCP_STDIO_PYTHONPATH');
    // Keep MCP stdio imports isolated from ambient shell/watcher PYTHONPATH.
    // Extra import roots must be added explicitly through MCP_STDIO_PYTHONPATH.
    return buildIsolatedPythonPath({ cwd, configured });
  }

  private parseArgs(raw: string): string[] {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.every((item) => typeof item === 'string')) {
        return parsed;
      }
    } catch {
      // fallback below
    }

    return raw
      .split(' ')
      .map((part) => part.trim())
      .filter((part) => part.length > 0);
  }

  private resolveConfiguredFullProfilePoolSlots(): number {
    const configured = this.configService.get<string>('MCP_FULL_PROFILE_POOL_SLOTS');
    const startupProfile = this.configService.get<string>('MCP_STDIO_STARTUP_PROFILE', 'balanced').trim().toLowerCase();
    let fallback = 1;
    if (startupProfile === 'tool-only' || startupProfile === 'tool_only') {
      fallback = 0;
    } else if (startupProfile === 'full' || startupProfile === 'worker') {
      fallback = this.poolSize;
    }
    const raw = configured != null && configured.trim().length > 0 ? configured : String(fallback);
    const parsed = Number(raw);
    const resolved = Number.isFinite(parsed) ? parsed : fallback;
    return Math.max(0, Math.min(this.poolSize, resolved));
  }

  private resolveStartupProfile(id: number): McpStartupProfile {
    const raw = this.configService.get<string>('MCP_STDIO_STARTUP_PROFILE', 'balanced').trim().toLowerCase();
    if (raw === 'full') return 'full';
    if (raw === 'worker') return 'worker';
    if (raw === 'tool-only' || raw === 'tool_only') return 'tool-only';
    return id < this.fullProfilePoolSlots ? 'worker' : 'tool-only';
  }

  private recordToolMetric(
    name: string,
    latencyMs: number,
    errored: boolean,
    meta?: McpConnectionMeta | null,
    error?: unknown,
  ): void {
    this.totalToolCalls += 1;
    if (errored) {
      this.totalToolErrors += 1;
    }

    const normalizedName = name.trim();
    this.toolUsage.set(normalizedName, (this.toolUsage.get(normalizedName) ?? 0) + 1);
    this.latencyHistoryMs.push(latencyMs);
    if (this.latencyHistoryMs.length > 500) {
      this.latencyHistoryMs.splice(0, this.latencyHistoryMs.length - 500);
    }
    const bucket = this.toolMetrics.get(normalizedName) ?? {
      calls: 0,
      errors: 0,
      totalLatencyMs: 0,
      samples: [],
      failureModes: {},
    };
    bucket.calls += 1;
    bucket.totalLatencyMs += latencyMs;
    bucket.samples.push(latencyMs);
    if (bucket.samples.length > 100) {
      bucket.samples.splice(0, bucket.samples.length - 100);
    }
    if (errored) {
      bucket.errors += 1;
      const mode = this.classifyFailureMode(error);
      bucket.failureModes[mode] = (bucket.failureModes[mode] ?? 0) + 1;
      this.failureModeTotals.set(mode, (this.failureModeTotals.get(mode) ?? 0) + 1);
    }
    this.toolMetrics.set(normalizedName, bucket);
    this.observability.recordMcpCall({
      name: normalizedName,
      latencyMs,
      errored,
      transportKind: meta?.transportKind ?? this.getTransportSnapshot().transportKind,
      degraded: Boolean(meta?.degraded ?? this.getTransportSnapshot().degraded),
    });
  }

  private classifyFailureMode(error: unknown): McpFailureMode {
    if (!error) return 'unknown';
    const message = this.formatError(error).toLowerCase();
    if (error instanceof McpGatewayTimeoutError || message.includes('timeout') || message.includes('timed out')) {
      return 'timeout';
    }
    if (this.isTransportError(error)) return 'transport';
    if (
      message.includes('validation') ||
      message.includes('invalid') ||
      message.includes('schema') ||
      message.includes('pydantic') ||
      message.includes('parse')
    ) {
      return 'validation';
    }
    return 'tool_error';
  }

  private withFallbackMetaDefaults(payload: unknown): unknown {
    return this.withFallbackMetaDefaultsForTransport(payload, null);
  }

  private withFallbackMetaDefaultsForTransport(
    payload: unknown,
    transportMeta: McpConnectionMeta | null,
  ): unknown {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return payload;
    }

    const node = payload as Record<string, unknown>;
    const hasFallbackShape =
      'backend_requested' in node ||
      'backend_used' in node ||
      'fallback_used' in node ||
      'fallback_reason' in node ||
      'latency_ms' in node ||
      'source' in node;

    if (!hasFallbackShape) {
      const nestedData = node.data;
      if (nestedData && typeof nestedData === 'object' && !Array.isArray(nestedData)) {
        const normalizedData = this.withFallbackMetaDefaultsForTransport(
          nestedData,
          transportMeta,
        ) as Record<string, unknown>;
        const nestedHasFallbackShape =
          normalizedData &&
          typeof normalizedData === 'object' &&
          !Array.isArray(normalizedData) &&
          ('backend_requested' in normalizedData ||
            'backend_used' in normalizedData ||
            'fallback_used' in normalizedData ||
            'fallback_reason' in normalizedData ||
            'latency_ms' in normalizedData);

        if (nestedHasFallbackShape) {
          return {
            ...node,
            data: normalizedData,
            backend_requested: normalizedData.backend_requested ?? null,
            backend_used: normalizedData.backend_used ?? null,
            fallback_used:
              typeof normalizedData.fallback_used === 'boolean'
                ? normalizedData.fallback_used
                : false,
            fallback_reason: normalizedData.fallback_reason ?? null,
            latency_ms:
              typeof normalizedData.latency_ms === 'number'
                ? normalizedData.latency_ms
                : 0,
            transport: normalizedData.transport ?? null,
          };
        }
      }

      return payload;
    }

    const backendRequested =
      typeof node.backend_requested === 'string' && node.backend_requested.length > 0
        ? node.backend_requested
        : typeof node.backend_used === 'string' && node.backend_used.length > 0
          ? node.backend_used
          : typeof node.source === 'string' && node.source.length > 0
            ? node.source
            : 'unknown';

    const backendUsed =
      typeof node.backend_used === 'string' && node.backend_used.length > 0
        ? node.backend_used
        : typeof node.source === 'string' && node.source.length > 0
          ? node.source
          : 'unknown';

    const fallbackUsed =
      typeof node.fallback_used === 'boolean'
        ? node.fallback_used
        : backendRequested !== backendUsed;

    const latencyMs = typeof node.latency_ms === 'number' ? node.latency_ms : 0;
    const fallbackReason =
      typeof node.fallback_reason === 'string'
        ? node.fallback_reason
        : node.fallback_reason != null
          ? String(node.fallback_reason)
          : null;
    const transport = transportMeta
      ? withToolTransportMeta(
        {
          backend_requested: backendRequested,
          backend_used: backendUsed,
          fallback_used: fallbackUsed,
          fallback_reason: fallbackReason,
          latency_ms: latencyMs,
        },
        {
          requestedTransport: transportMeta.requestedTransport,
          transportKind: transportMeta.transportKind,
          degraded: transportMeta.degraded,
          fallbackReason: transportMeta.fallbackReason,
          sourceChain: transportMeta.sourceChain,
          endpoint: transportMeta.endpoint,
          lastError: transportMeta.lastError,
        },
      ).transport
      : null;

    return {
      ...node,
      backend_requested: backendRequested,
      backend_used: backendUsed,
      fallback_used: fallbackUsed,
      fallback_reason: fallbackReason,
      latency_ms: latencyMs,
      ...(transport ? { transport } : {}),
    };
  }

  private normalizeToolResult(result: unknown, transportMeta: McpConnectionMeta): unknown {
    if (!result || typeof result !== 'object') return result;

    const node = result as Record<string, unknown>;

    if ('structuredContent' in node && node.structuredContent !== undefined) {
      return this.withFallbackMetaDefaultsForTransport(node.structuredContent, transportMeta);
    }

    if (Array.isArray(node.content)) {
      const textBlock = node.content.find(
        (item) =>
          item &&
          typeof item === 'object' &&
          (item as Record<string, unknown>).type === 'text' &&
          typeof (item as Record<string, unknown>).text === 'string',
      ) as Record<string, unknown> | undefined;

      if (textBlock?.text && typeof textBlock.text === 'string') {
        try {
          return this.withFallbackMetaDefaultsForTransport(JSON.parse(textBlock.text), transportMeta);
        } catch {
          return textBlock.text;
        }
      }
    }

    return this.withFallbackMetaDefaultsForTransport(result, transportMeta);
  }

  private normalizeResourceResult(result: unknown): unknown {
    if (!result || typeof result !== 'object') return result;

    const node = result as Record<string, unknown>;
    const contents = Array.isArray(node.contents) ? node.contents : [];
    if (contents.length === 1) {
      const [content] = contents;
      if (content && typeof content === 'object' && typeof (content as Record<string, unknown>).text === 'string') {
        const text = String((content as Record<string, unknown>).text);
        try {
          return JSON.parse(text);
        } catch {
          return text;
        }
      }
      return content;
    }

    return contents.map((content) => {
      if (!content || typeof content !== 'object') return content;
      const block = content as Record<string, unknown>;
      if (typeof block.text === 'string') {
        try {
          return JSON.parse(block.text);
        } catch {
          return block.text;
        }
      }
      return block;
    });
  }
}

import { Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { existsSync } from 'node:fs';
import { delimiter, isAbsolute, resolve } from 'node:path';
import { performance } from 'node:perf_hooks';

type McpHealth = {
  reachable: boolean;
  toolCount: number | null;
  expectedTools: number | null;
  matched: boolean;
  source: string;
  message: string;
  poolSize?: number;
  activeConnections?: number;
};

type McpStartupProfile = 'full' | 'tool-only';

interface PooledConnection {
  id: number;
  client: Client;
  transport: StdioClientTransport;
  busy: boolean;
  connectPromise: Promise<void> | null;
}

type Waiter = {
  resolve: (conn: PooledConnection) => void;
  reject: (error: Error) => void;
  timeout: ReturnType<typeof setTimeout>;
};

@Injectable()
export class McpGatewayService implements OnModuleDestroy {
  private readonly logger = new Logger(McpGatewayService.name);
  private static readonly DEDICATED_TOOL_CONNECTIONS = new Set(['alerts_manager']);

  private pool: PooledConnection[] = [];
  private readonly poolSize: number;
  private readonly fullProfilePoolSlots: number;
  private readonly poolAcquireTimeoutMs: number;
  private readonly toolCallTimeoutMs: number;
  private waitQueue: Waiter[] = [];
  private dedicatedConnections = new Map<string, PooledConnection>();
  private dedicatedWaitQueues = new Map<string, Waiter[]>();
  private initialized = false;
  private totalToolCalls = 0;
  private totalToolErrors = 0;
  private readonly latencyHistoryMs: number[] = [];
  private readonly toolUsage = new Map<string, number>();

  constructor(private readonly configService: ConfigService) {
    this.poolSize = Math.max(
      1,
      Number(this.configService.get<string>('MCP_POOL_SIZE', '8')),
    );
    this.fullProfilePoolSlots = Math.max(
      0,
      Math.min(
        this.poolSize,
        Number(this.configService.get<string>('MCP_FULL_PROFILE_POOL_SLOTS', '0')),
      ),
    );
    this.poolAcquireTimeoutMs = Math.max(
      1000,
      Number(this.configService.get<string>('MCP_POOL_ACQUIRE_TIMEOUT_MS', '5000')),
    );
    this.toolCallTimeoutMs = Math.max(
      1000,
      Number(this.configService.get<string>('MCP_TOOL_TIMEOUT_MS', '30000')),
    );
  }

  async onModuleDestroy(): Promise<void> {
    await this.disposeAll();
  }

  async checkAvailableTools(): Promise<McpHealth> {
    const configuredExpected = this.configService.get<string>('MCP_EXPECTED_TOOLS');
    const expectedTools = configuredExpected != null && configuredExpected !== ''
      ? Number(configuredExpected)
      : null;

    try {
      const conn = await this.acquire();
      try {
        const tools = await conn.client.listTools();
        const count = Array.isArray(tools?.tools) ? tools.tools.length : null;
        if (count !== null) {
          const resolvedExpectedTools = expectedTools ?? count;
          return {
            reachable: true,
            toolCount: count,
            expectedTools: resolvedExpectedTools,
            matched: count === resolvedExpectedTools,
            source: 'stdio',
            message: expectedTools == null ? 'ok(dynamic-runtime-baseline)' : 'ok',
            poolSize: this.poolSize,
            activeConnections: this.pool.length,
          };
        }
      } finally {
        this.release(conn);
      }
    } catch {
      // ignore and fallthrough
    }

    return {
      reachable: false,
      toolCount: null,
      expectedTools,
      matched: false,
      source: 'none',
      message: 'MCP not reachable or available_tools response format unknown',
      poolSize: this.poolSize,
      activeConnections: this.pool.length,
    };
  }

  async callTool(name: string, args: Record<string, unknown> = {}): Promise<unknown> {
    const dedicated = McpGatewayService.DEDICATED_TOOL_CONNECTIONS.has(name);
    const conn = dedicated ? await this.acquireDedicated(name) : await this.acquire();
    const startedAt = performance.now();
    try {
      const result = await this.withTimeout(
        conn.client.callTool({ name, arguments: args }),
        this.toolCallTimeoutMs,
        `MCP tool ${name} timed out after ${this.toolCallTimeoutMs}ms`,
      );
      this.recordToolMetric(name, performance.now() - startedAt, false);
      return this.normalizeToolResult(result);
    } catch (error) {
      this.recordToolMetric(name, performance.now() - startedAt, true);
      if (this.isTransportError(error)) {
        this.logger.warn(`Transport error on pool[${conn.id}], recycling connection`);
        await this.recycleConnection(conn, dedicated ? name : undefined);
      }
      throw error;
    } finally {
      if (dedicated) this.releaseDedicated(name, conn);
      else this.release(conn);
    }
  }

  getMetricsSnapshot(): {
    totalCalls: number;
    avgLatency: number;
    p99Latency: number;
    errorRate: number;
    tools: Array<{ name: string; calls: number }>;
  } {
    const samples = [...this.latencyHistoryMs].sort((a, b) => a - b);
    const avgLatency = samples.length > 0
      ? samples.reduce((sum, value) => sum + value, 0) / samples.length
      : 0;
    const p99Index = samples.length > 0
      ? Math.min(samples.length - 1, Math.max(0, Math.ceil(samples.length * 0.99) - 1))
      : 0;
    const topTools = [...this.toolUsage.entries()]
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
      .slice(0, 12)
      .map(([name, calls]) => ({ name, calls }));

    return {
      totalCalls: this.totalToolCalls,
      avgLatency: Number(avgLatency.toFixed(2)),
      p99Latency: Number((samples[p99Index] ?? 0).toFixed(2)),
      errorRate: this.totalToolCalls > 0
        ? Number(((this.totalToolErrors / this.totalToolCalls) * 100).toFixed(2))
        : 0,
      tools: topTools,
    };
  }

  /* ── Pool Management ── */

  private async acquire(): Promise<PooledConnection> {
    if (!this.initialized) {
      await this.initPool();
    }

    const idle = this.pool.find((c) => !c.busy);
    if (idle) {
      idle.busy = true;
      return idle;
    }

    if (this.pool.length < this.poolSize) {
      const conn = await this.createConnection(this.pool.length);
      conn.busy = true;
      this.pool.push(conn);
      return conn;
    }

    return this.waitForConnection(
      this.waitQueue,
      `Timed out waiting ${this.poolAcquireTimeoutMs}ms for an available MCP pool connection`,
    );
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
    this.initialized = true;

    const first = await this.createConnection(0);
    this.pool.push(first);
    this.logger.log(
      `MCP pool initialized (1/${this.poolSize} connections, full-profile slots=${this.fullProfilePoolSlots})`,
    );
  }

  private async createConnection(id: number): Promise<PooledConnection> {
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
    };

    const transport = new StdioClientTransport({
      command,
      args,
      cwd,
      env,
      stderr: 'inherit',
    });

    const client = new Client(
      { name: `aiask-bff-pool-${id}`, version: '0.1.0' },
      { capabilities: {} },
    );

    try {
      await client.connect(transport);
    } catch (error) {
      try { await transport.close(); } catch { /* ignore */ }
      throw error;
    }

    this.logger.log(`MCP pool connection[${id}] established (profile=${startupProfile})`);
    return { id, client, transport, busy: false, connectPromise: null };
  }

  private async recycleConnection(conn: PooledConnection, dedicatedTool?: string): Promise<void> {
    try { await conn.transport.close(); } catch { /* ignore */ }

    try {
      const fresh = await this.createConnection(conn.id);
      conn.client = fresh.client;
      conn.transport = fresh.transport;
      conn.connectPromise = fresh.connectPromise;
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
    this.initialized = false;
  }

  /* ── Utilities ── */

  private isTransportError(error: unknown): boolean {
    if (!error || typeof error !== 'object') return true;
    const msg = String((error as Error).message ?? '').toLowerCase();
    return (
      msg.includes('epipe') ||
      msg.includes('connection') ||
      msg.includes('closed') ||
      msg.includes('transport') ||
      msg.includes('econnreset') ||
      msg.includes('econnrefused') ||
      msg.includes('broken pipe') ||
      msg.includes('timed out')
    );
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

  private async withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
    return await new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(message)), timeoutMs);
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

  private resolveMcpCwd(): string {
    const configured = this.configService.get<string>('MCP_STDIO_CWD');
    if (configured && configured.trim().length > 0) {
      return configured.trim();
    }

    const fromRepoRoot = resolve(process.cwd(), 'packages', 'akshare-mcp');
    if (existsSync(fromRepoRoot)) return fromRepoRoot;

    const fromAppDir = resolve(process.cwd(), '..', '..', 'packages', 'akshare-mcp');
    if (existsSync(fromAppDir)) return fromAppDir;

    return fromRepoRoot;
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
    const sources = [
      process.env.PYTHONPATH,
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
      .filter((part) => existsSync(part));

    return parts.join(delimiter);
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

  private resolveStartupProfile(id: number): McpStartupProfile {
    const raw = this.configService.get<string>('MCP_STDIO_STARTUP_PROFILE', 'balanced').trim().toLowerCase();
    if (raw === 'full') return 'full';
    if (raw === 'tool-only' || raw === 'tool_only' || raw === 'worker') return 'tool-only';
    return id < this.fullProfilePoolSlots ? 'full' : 'tool-only';
  }

  private recordToolMetric(name: string, latencyMs: number, errored: boolean): void {
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
  }

  private withFallbackMetaDefaults(payload: unknown): unknown {
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
        const normalizedData = this.withFallbackMetaDefaults(nestedData) as Record<string, unknown>;
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

    return {
      ...node,
      backend_requested: backendRequested,
      backend_used: backendUsed,
      fallback_used: fallbackUsed,
      fallback_reason: node.fallback_reason ?? null,
      latency_ms: latencyMs,
    };
  }

  private normalizeToolResult(result: unknown): unknown {
    if (!result || typeof result !== 'object') return result;

    const node = result as Record<string, unknown>;

    if ('structuredContent' in node && node.structuredContent !== undefined) {
      return this.withFallbackMetaDefaults(node.structuredContent);
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
          return this.withFallbackMetaDefaults(JSON.parse(textBlock.text));
        } catch {
          return textBlock.text;
        }
      }
    }

    return this.withFallbackMetaDefaults(result);
  }
}
